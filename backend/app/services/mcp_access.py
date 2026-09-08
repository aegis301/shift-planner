from __future__ import annotations

import base64
import hashlib
import hmac
import json
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from app.core.config import settings
from app.services.authz import ROLE_ADMIN, ROLE_PLANNER

AccessNeed = Literal["planning", "admin"]

MCP_TOKEN_TTL = timedelta(minutes=15)


@dataclass(frozen=True)
class McpPrincipal:
    user_id: int
    organization_id: int
    role: str
    shift_group_ids: tuple[int, ...] = field(default_factory=tuple)
    is_break_glass: bool = False

    @property
    def is_admin(self) -> bool:
        return self.is_break_glass or self.role == ROLE_ADMIN

    @property
    def can_plan(self) -> bool:
        return self.is_admin or self.role == ROLE_PLANNER


_current_principal: ContextVar[McpPrincipal | None] = ContextVar("mcp_principal", default=None)


def get_current_principal() -> McpPrincipal | None:
    return _current_principal.get()


def set_current_principal(principal: McpPrincipal | None) -> None:
    _current_principal.set(principal)


def mcp_jwt_secret() -> str:
    secret = (settings.mcp_jwt_secret or "").strip()
    if secret:
        return secret
    return settings.session_secret


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    pad = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + pad)


def mint_mcp_access_token(
    *,
    user_id: int,
    organization_id: int,
    role: str,
    shift_group_ids: list[int] | tuple[int, ...],
    ttl: timedelta = MCP_TOKEN_TTL,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "typ": "mcp",
        "sub": user_id,
        "org": organization_id,
        "role": role,
        "sg": [int(item) for item in shift_group_ids],
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = (
        f"{_b64url_encode(json.dumps(header, separators=(',', ':')).encode())}."
        f"{_b64url_encode(json.dumps(payload, separators=(',', ':')).encode())}"
    )
    digest = hmac.new(mcp_jwt_secret().encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url_encode(digest)}"


def _parse_jwt(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise PermissionError("Invalid MCP access token")
    signing_input = f"{parts[0]}.{parts[1]}"
    expected = hmac.new(mcp_jwt_secret().encode(), signing_input.encode(), hashlib.sha256).digest()
    try:
        actual = _b64url_decode(parts[2])
    except Exception as exc:
        raise PermissionError("Invalid MCP access token") from exc
    if not hmac.compare_digest(expected, actual):
        raise PermissionError("Invalid MCP access token")
    try:
        payload = json.loads(_b64url_decode(parts[1]))
    except Exception as exc:
        raise PermissionError("Invalid MCP access token") from exc
    if not isinstance(payload, dict) or payload.get("typ") != "mcp":
        raise PermissionError("Invalid MCP access token")
    exp = payload.get("exp")
    if not isinstance(exp, int) or exp < int(datetime.now(UTC).timestamp()):
        raise PermissionError("MCP access token expired")
    return payload


def resolve_mcp_principal(token: str) -> McpPrincipal:
    if not token:
        raise PermissionError("MCP authentication required")
    if hmac.compare_digest(token, settings.mcp_admin_token):
        org_id = settings.mcp_organization_id
        if org_id is None:
            org_id = settings.default_organization_id
        return McpPrincipal(
            user_id=0,
            organization_id=int(org_id),
            role=ROLE_ADMIN,
            shift_group_ids=(),
            is_break_glass=True,
        )
    payload = _parse_jwt(token)
    try:
        user_id = int(payload["sub"])
        organization_id = int(payload["org"])
        role = str(payload["role"])
        raw_groups = payload.get("sg") or []
        shift_group_ids = tuple(int(item) for item in raw_groups)
    except (KeyError, TypeError, ValueError) as exc:
        raise PermissionError("Invalid MCP access token") from exc
    return McpPrincipal(
        user_id=user_id,
        organization_id=organization_id,
        role=role,
        shift_group_ids=shift_group_ids,
    )


def require_mcp_access(token: str, *, need: AccessNeed = "planning") -> McpPrincipal:
    principal = resolve_mcp_principal(token)
    if need == "admin" and not principal.is_admin:
        raise PermissionError("Admin MCP access required")
    if need == "planning" and not principal.can_plan:
        raise PermissionError("Planning MCP access required")
    set_current_principal(principal)
    return principal


def require_token(token: str) -> None:
    require_mcp_access(token, need="admin")


def fallback_organization_id() -> int:
    if settings.mcp_organization_id is not None:
        return settings.mcp_organization_id
    return settings.default_organization_id


def mcp_organization_id() -> int:
    principal = get_current_principal()
    if principal is not None:
        return principal.organization_id
    return fallback_organization_id()


def assert_mcp_read_scope(shift_group_id: int | None) -> None:
    principal = get_current_principal()
    if principal is None:
        raise PermissionError("MCP authentication required")
    if principal.is_admin:
        return
    if shift_group_id is None:
        raise PermissionError("shift_group_id is required")
    if shift_group_id not in principal.shift_group_ids:
        raise PermissionError("Not a member of this shift group")
