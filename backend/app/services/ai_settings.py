from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OrganizationAiSettings
from app.services.ai_credentials import api_key_last4, decrypt_api_key, encrypt_api_key

AI_TASK_IDS = ("summarize_wishes", "explain_validation", "draft_fair_roster")
AI_PROVIDERS = ("anthropic", "openai")
ALLOWED_MODELS = {
    "anthropic": (
        "claude-sonnet-4-5",
        "claude-haiku-4-5",
        "claude-3-5-haiku-latest",
        "claude-3-5-sonnet-latest",
    ),
    "openai": (
        "gpt-4.1-mini",
        "gpt-4.1",
        "gpt-4o-mini",
        "gpt-4o",
    ),
}


def _default_enabled_tasks() -> list[str]:
    return list(AI_TASK_IDS)


def get_or_create_ai_settings(db: Session, *, organization_id: int) -> OrganizationAiSettings:
    row = db.scalar(
        select(OrganizationAiSettings).where(OrganizationAiSettings.organization_id == organization_id)
    )
    if row is not None:
        return row
    row = OrganizationAiSettings(
        organization_id=organization_id,
        provider="anthropic",
        default_model="claude-sonnet-4-5",
        enabled_task_ids=_default_enabled_tasks(),
        is_enabled=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def settings_to_public(row: OrganizationAiSettings, *, include_last4: bool) -> dict[str, Any]:
    tasks = [item for item in (row.enabled_task_ids or []) if item in AI_TASK_IDS]
    payload = {
        "provider": row.provider,
        "default_model": row.default_model,
        "enabled_task_ids": tasks or _default_enabled_tasks(),
        "monthly_token_budget": row.monthly_token_budget,
        "is_enabled": row.is_enabled,
        "has_api_key": bool(row.encrypted_api_key),
        "assistant_ready": bool(row.is_enabled and row.encrypted_api_key),
    }
    if include_last4:
        payload["key_last4"] = row.key_last4
    return payload


def update_ai_settings(
    db: Session,
    *,
    organization_id: int,
    provider: str | None = None,
    default_model: str | None = None,
    enabled_task_ids: list[str] | None = None,
    monthly_token_budget: int | None = None,
    is_enabled: bool | None = None,
    api_key: str | None = None,
    clear_api_key: bool = False,
) -> OrganizationAiSettings:
    row = get_or_create_ai_settings(db, organization_id=organization_id)
    next_provider = provider if provider is not None else row.provider
    if next_provider not in AI_PROVIDERS:
        raise ValueError("Unsupported AI provider")
    next_model = default_model if default_model is not None else row.default_model
    allowed = ALLOWED_MODELS[next_provider]
    if next_model not in allowed:
        raise ValueError("Model is not in the organization allowlist")
    if enabled_task_ids is not None:
        cleaned = [item for item in enabled_task_ids if item in AI_TASK_IDS]
        if not cleaned:
            raise ValueError("At least one AI task must stay enabled")
        row.enabled_task_ids = cleaned
    row.provider = next_provider
    row.default_model = next_model
    if monthly_token_budget is not None:
        if monthly_token_budget < 0:
            raise ValueError("monthly_token_budget must be >= 0")
        row.monthly_token_budget = monthly_token_budget
    if is_enabled is not None:
        row.is_enabled = is_enabled
    if clear_api_key:
        row.encrypted_api_key = None
        row.key_last4 = None
    elif api_key is not None and api_key.strip():
        row.encrypted_api_key = encrypt_api_key(api_key)
        row.key_last4 = api_key_last4(api_key)
    db.commit()
    db.refresh(row)
    return row


def load_decrypted_api_key(row: OrganizationAiSettings) -> str:
    if not row.encrypted_api_key:
        raise ValueError("Organization has no AI API key")
    return decrypt_api_key(row.encrypted_api_key)
