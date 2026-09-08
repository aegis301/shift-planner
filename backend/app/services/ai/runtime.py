from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AiTaskRun, PlanningPeriod, User
from app.schemas import RosterSlotAssignmentUpsert
from app.services.ai.planning_tools import READ_TOOL_SPECS, TASK_TOOL_ALLOWLIST, invoke_read_tool
from app.services.ai.prompts import MAX_AGENT_STEPS, TASK_SYSTEM_PROMPTS
from app.services.ai.providers import LlmProvider, OpenAiProvider, ToolCall, provider_for
from app.services.ai.tracing import emit_langfuse_trace, new_trace_id
from app.services.ai_settings import get_or_create_ai_settings, load_decrypted_api_key
from app.services.authz import assert_planning_shift_group_scope, planner_shift_group_ids
from app.services.mcp_access import McpPrincipal
from app.services.planning import get_shift_group_planning_status
from app.services.roster_matrix import get_roster_matrix, upsert_roster_slot_assignment
from app.services.validation import validate_roster

_provider_override: LlmProvider | None = None


def set_provider_override(provider: LlmProvider | None) -> None:
    global _provider_override
    _provider_override = provider


def _principal_for_user(db: Session, user: User) -> McpPrincipal:
    groups = planner_shift_group_ids(db, user) if user.role != "admin" else ()
    return McpPrincipal(
        user_id=user.id,
        organization_id=user.organization_id,
        role=user.role,
        shift_group_ids=tuple(sorted(groups)),
    )


def _invoke_tool_safe(
    db: Session,
    principal: McpPrincipal,
    call: ToolCall,
    allowed: set[str],
) -> Any:
    try:
        return invoke_read_tool(db, principal, call.name, call.arguments, allowed=allowed)
    except Exception as tool_exc:
        return {"error": str(tool_exc)}


def _truncate(value: Any, *, limit: int = 4000) -> Any:
    encoded = json.dumps(value, default=str)
    if len(encoded) <= limit:
        return value
    return {"truncated": True, "preview": encoded[:limit]}


def _parse_json_object(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    try:
        loaded = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            loaded = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError:
            return None
    return loaded if isinstance(loaded, dict) else None


def _validate_draft_proposals(
    db: Session,
    *,
    organization_id: int,
    planning_period_id: int,
    shift_group_id: int | None,
    proposals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    roster = get_roster_matrix(
        db,
        planning_period_id,
        organization_id=organization_id,
        shift_group_id=shift_group_id,
    )
    slot_ids = {slot.id for slot in roster.slots}
    assigned = {row.roster_slot_id for row in roster.assignments}
    member_ids = {member.id for member in roster.team_members}
    cleaned: list[dict[str, Any]] = []
    seen: set[int] = set()
    for item in proposals:
        try:
            slot_id = int(item["roster_slot_id"])
            team_member_id = int(item["team_member_id"])
        except (KeyError, TypeError, ValueError):
            continue
        if slot_id not in slot_ids or slot_id in assigned or slot_id in seen:
            continue
        if team_member_id not in member_ids:
            continue
        reason = str(item.get("reason") or "")
        cleaned.append(
            {
                "roster_slot_id": slot_id,
                "team_member_id": team_member_id,
                "reason": reason,
            }
        )
        seen.add(slot_id)
    return cleaned


def _attach_validation(
    db: Session,
    *,
    organization_id: int,
    planning_period_id: int,
    shift_group_id: int | None,
    output: dict[str, Any],
) -> dict[str, Any]:
    warnings = [
        warning.model_dump(mode="json")
        for warning in validate_roster(
            db,
            planning_period_id,
            organization_id=organization_id,
            shift_group_id=shift_group_id,
        )
    ]
    output = dict(output)
    output["current_validation"] = warnings
    return output


def run_ai_task(
    db: Session,
    *,
    user: User,
    task_id: str,
    planning_period_id: int,
    shift_group_id: int | None,
) -> AiTaskRun:
    if task_id not in TASK_TOOL_ALLOWLIST:
        raise ValueError("Unknown AI task")
    assert_planning_shift_group_scope(db, user, shift_group_id)
    period = db.get(PlanningPeriod, planning_period_id)
    if period is None or period.organization_id != user.organization_id:
        raise ValueError("Planning period not found")
    settings_row = get_or_create_ai_settings(db, organization_id=user.organization_id)
    if not settings_row.is_enabled:
        raise ValueError("AI assistant is disabled for this organization")
    if task_id not in (settings_row.enabled_task_ids or []):
        raise ValueError("This AI task is not enabled")
    api_key = load_decrypted_api_key(settings_row)
    if settings_row.monthly_token_budget is not None:
        used = db.scalar(
            select(func.coalesce(func.sum(AiTaskRun.prompt_tokens + AiTaskRun.completion_tokens), 0)).where(
                AiTaskRun.organization_id == user.organization_id,
                AiTaskRun.created_at >= datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0),
            )
        )
        if int(used or 0) >= settings_row.monthly_token_budget:
            raise ValueError("Monthly AI token budget reached")
    if task_id == "draft_fair_roster":
        if shift_group_id is None:
            raise ValueError("shift_group_id is required")
        status_row = get_shift_group_planning_status(
            db,
            planning_period_id=planning_period_id,
            shift_group_id=shift_group_id,
            organization_id=user.organization_id,
        )
        if status_row is not None and status_row.status == "published":
            raise ValueError("Cannot draft a roster while this shift group is published")

    principal = _principal_for_user(db, user)
    allowed = set(TASK_TOOL_ALLOWLIST[task_id])
    tools = [spec for spec in READ_TOOL_SPECS if spec["name"] in allowed]
    provider = _provider_override or provider_for(settings_row.provider)
    locale = user.locale if user.locale in {"de", "en"} else "de"
    system = TASK_SYSTEM_PROMPTS[task_id]
    user_message = {
        "role": "user",
        "content": json.dumps(
            {
                "locale": locale,
                "task_id": task_id,
                "planning_period_id": planning_period_id,
                "shift_group_id": shift_group_id,
                "year": period.year,
                "month": period.month,
            }
        ),
    }
    messages: list[dict[str, Any]] = [user_message]
    run = AiTaskRun(
        organization_id=user.organization_id,
        user_id=user.id,
        task_id=task_id,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        status="running",
        input_json={"planning_period_id": planning_period_id, "shift_group_id": shift_group_id},
        applied_assignment_ids=[],
        langfuse_trace_id=new_trace_id(),
    )
    db.add(run)
    db.flush()

    prompt_tokens = 0
    completion_tokens = 0
    output: dict[str, Any] | None = None
    try:
        for _ in range(MAX_AGENT_STEPS):
            turn = provider.complete(
                system=system,
                messages=messages,
                tools=[{"name": t["name"], "description": t["description"], "parameters": t["parameters"]} for t in tools],
                model=settings_row.default_model,
                api_key=api_key,
            )
            prompt_tokens += turn.prompt_tokens
            completion_tokens += turn.completion_tokens
            if turn.tool_calls:
                if isinstance(provider, OpenAiProvider) and _provider_override is None:
                    messages.append(
                        {
                            "role": "assistant",
                            "content": turn.assistant_text,
                            "tool_calls": [
                                {
                                    "id": call.id,
                                    "type": "function",
                                    "function": {
                                        "name": call.name,
                                        "arguments": json.dumps(call.arguments),
                                    },
                                }
                                for call in turn.tool_calls
                            ],
                        }
                    )
                    for call in turn.tool_calls:
                        result = _invoke_tool_safe(db, principal, call, allowed)
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.id,
                                "content": json.dumps(_truncate(result), default=str),
                            }
                        )
                else:
                    tool_results = []
                    for call in turn.tool_calls:
                        result = _invoke_tool_safe(db, principal, call, allowed)
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": call.id,
                                "content": json.dumps(_truncate(result), default=str),
                            }
                        )
                    assistant_content: list[dict[str, Any]] = []
                    if turn.assistant_text:
                        assistant_content.append({"type": "text", "text": turn.assistant_text})
                    assistant_content.extend(
                        {
                            "type": "tool_use",
                            "id": call.id,
                            "name": call.name,
                            "input": call.arguments,
                        }
                        for call in turn.tool_calls
                    )
                    messages.append({"role": "assistant", "content": assistant_content})
                    messages.append({"role": "user", "content": tool_results})
                continue
            output = turn.parsed_json or _parse_json_object(turn.assistant_text)
            break
        if output is None:
            raise ValueError("The model did not return a structured result")
        if task_id == "draft_fair_roster":
            proposals = output.get("proposals") if isinstance(output.get("proposals"), list) else []
            output["proposals"] = _validate_draft_proposals(
                db,
                organization_id=user.organization_id,
                planning_period_id=planning_period_id,
                shift_group_id=shift_group_id,
                proposals=proposals,
            )
        output = _attach_validation(
            db,
            organization_id=user.organization_id,
            planning_period_id=planning_period_id,
            shift_group_id=shift_group_id,
            output=output,
        )
        run.status = "succeeded"
        run.output_json = output
        run.error_message = None
    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)
        if isinstance(exc, (ValueError, PermissionError)):
            raise
        raise ValueError(str(exc)) from exc
    finally:
        run.prompt_tokens = prompt_tokens
        run.completion_tokens = completion_tokens
        run.completed_at = datetime.now(UTC)
        emit_langfuse_trace(
            trace_id=run.langfuse_trace_id or new_trace_id(),
            name=f"ai.{task_id}",
            user_id=str(user.id),
            metadata={
                "organization_id": user.organization_id,
                "task_id": task_id,
                "planning_period_id": planning_period_id,
                "shift_group_id": shift_group_id,
                "model": settings_row.default_model,
                "provider": settings_row.provider,
            },
            input_payload={"planning_period_id": planning_period_id, "shift_group_id": shift_group_id},
            output_payload=_truncate(run.output_json) if run.output_json else {"error": run.error_message},
            usage={"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
        )
        db.flush()
        db.commit()
        db.refresh(run)
    return run


def get_ai_run(db: Session, *, user: User, run_id: int) -> AiTaskRun:
    run = db.get(AiTaskRun, run_id)
    if run is None or run.organization_id != user.organization_id:
        raise ValueError("AI run not found")
    return run


def apply_roster_draft(
    db: Session,
    *,
    user: User,
    run_id: int,
    roster_slot_ids: list[int],
) -> dict[str, Any]:
    run = get_ai_run(db, user=user, run_id=run_id)
    if run.task_id != "draft_fair_roster":
        raise ValueError("Only roster draft runs can be applied")
    if run.status != "succeeded" or not isinstance(run.output_json, dict):
        raise ValueError("AI run has no applyable proposals")
    assert_planning_shift_group_scope(db, user, run.shift_group_id)
    if run.shift_group_id is None:
        raise ValueError("shift_group_id is required")
    status_row = get_shift_group_planning_status(
        db,
        planning_period_id=run.planning_period_id,
        shift_group_id=run.shift_group_id,
        organization_id=user.organization_id,
    )
    if status_row is not None and status_row.status == "published":
        raise ValueError("Cannot assign while this shift group is published")
    proposals = run.output_json.get("proposals") if isinstance(run.output_json.get("proposals"), list) else []
    by_slot = {
        int(item["roster_slot_id"]): int(item["team_member_id"])
        for item in proposals
        if isinstance(item, dict) and "roster_slot_id" in item and "team_member_id" in item
    }
    actor = f"user:{user.id}"
    applied: list[int] = []
    errors: list[dict[str, Any]] = []
    wanted = set(roster_slot_ids)
    for slot_id in wanted:
        team_member_id = by_slot.get(slot_id)
        if team_member_id is None:
            errors.append({"roster_slot_id": slot_id, "error": "Proposal not found for this slot"})
            continue
        try:
            upsert_roster_slot_assignment(
                db,
                RosterSlotAssignmentUpsert(roster_slot_id=slot_id, team_member_id=team_member_id),
                organization_id=user.organization_id,
                actor=actor,
                source="ai",
            )
            applied.append(slot_id)
        except Exception as exc:
            errors.append({"roster_slot_id": slot_id, "error": str(exc)})
    already = [int(item) for item in (run.applied_assignment_ids or [])]
    run.applied_assignment_ids = sorted(set(already) | set(applied))
    db.commit()
    return {"applied_slot_ids": applied, "errors": errors}


def run_to_read(run: AiTaskRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "task_id": run.task_id,
        "status": run.status,
        "planning_period_id": run.planning_period_id,
        "shift_group_id": run.shift_group_id,
        "output": run.output_json,
        "error_message": run.error_message,
        "prompt_tokens": run.prompt_tokens,
        "completion_tokens": run.completion_tokens,
        "applied_assignment_ids": run.applied_assignment_ids or [],
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }
