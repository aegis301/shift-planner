from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    SESSION_KIND_ACCOUNT,
    SESSION_KIND_USER,
    compose_refresh_token,
    create_access_token,
    hash_refresh_token,
    new_refresh_secret,
    parse_refresh_token,
    verify_access_token,
)
from app.models import Account, AuthDeviceSession, AuthRefreshToken, User

PLATFORMS = frozenset({"ios", "android", "web", "other"})
REASON_REFRESH_REUSE = "refresh_reuse"
REASON_PASSWORD_CHANGE = "password_change"
REASON_ADMIN_PASSWORD_RESET = "admin_password_reset"
REASON_ACCOUNT_DELETED = "account_deleted"
REASON_MEMBERSHIP_REMOVED = "membership_removed"
REASON_CLIENT = "client"
REASON_USER = "user"


class BearerRejected(Exception):
    pass


class RefreshRejected(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    expires_in: int
    device_session_id: int


@dataclass(frozen=True)
class DeviceSessionView:
    id: int
    name: str
    platform: str
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    current: bool


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _refresh_lifetime() -> timedelta:
    return timedelta(days=settings.refresh_token_ttl_days)


def _session_is_usable(row: AuthDeviceSession, now: datetime) -> bool:
    if row.revoked_at is not None:
        return False
    return _as_utc(row.expires_at) > now


def _issue_refresh_row(db: Session, device_session_id: int, now: datetime) -> str:
    secret = new_refresh_secret()
    raw = compose_refresh_token(device_session_id, secret)
    db.add(
        AuthRefreshToken(
            device_session_id=device_session_id,
            token_hash=hash_refresh_token(raw),
            issued_at=now,
            rotated_at=None,
        )
    )
    return raw


def _access_for_session(row: AuthDeviceSession) -> str:
    if row.user_id is not None:
        return create_access_token(
            device_session_id=row.id, kind=SESSION_KIND_USER, subject_id=row.user_id
        )
    return create_access_token(
        device_session_id=row.id, kind=SESSION_KIND_ACCOUNT, subject_id=row.account_id
    )


def _issued(row: AuthDeviceSession, refresh_token: str) -> IssuedTokens:
    return IssuedTokens(
        access_token=_access_for_session(row),
        refresh_token=refresh_token,
        expires_in=settings.access_token_ttl_seconds,
        device_session_id=row.id,
    )


def issue_device_session(
    db: Session,
    *,
    account: Account,
    user: User | None,
    device_name: str,
    platform: str,
) -> IssuedTokens:
    if platform not in PLATFORMS:
        raise ValueError("Invalid platform")
    name = device_name.strip()
    if name == "" or len(name) > 128:
        raise ValueError("Invalid device name")
    if user is not None and user.account_id != account.id:
        raise ValueError("Membership does not belong to this account")
    now = _utcnow()
    row = AuthDeviceSession(
        account_id=account.id,
        user_id=user.id if user is not None else None,
        name=name,
        platform=platform,
        created_at=now,
        last_used_at=now,
        expires_at=now + _refresh_lifetime(),
    )
    db.add(row)
    db.flush()
    raw = _issue_refresh_row(db, row.id, now)
    db.commit()
    db.refresh(row)
    return _issued(row, raw)


def refresh_device_session(db: Session, raw_token: str) -> IssuedTokens:
    parsed = parse_refresh_token(raw_token)
    if parsed is None:
        raise RefreshRejected("unknown")
    session_id, _secret = parsed
    device = db.get(AuthDeviceSession, session_id)
    if device is None:
        raise RefreshRejected("unknown")
    digest = hash_refresh_token(raw_token)
    row = db.scalar(select(AuthRefreshToken).where(AuthRefreshToken.token_hash == digest))
    if row is None or row.device_session_id != device.id:
        raise RefreshRejected("unknown")
    now = _utcnow()
    if row.rotated_at is not None:
        if device.revoked_at is None:
            device.revoked_at = now
            device.revoked_reason = REASON_REFRESH_REUSE
        db.commit()
        raise RefreshRejected("reused")
    if device.revoked_at is not None:
        raise RefreshRejected("revoked")
    if _as_utc(device.expires_at) <= now:
        raise RefreshRejected("expired")
    row.rotated_at = now
    raw = _issue_refresh_row(db, device.id, now)
    device.last_used_at = now
    device.expires_at = now + _refresh_lifetime()
    db.commit()
    db.refresh(device)
    return _issued(device, raw)


def authenticate_bearer(db: Session, token: str) -> tuple[User | Account, int]:
    subject = verify_access_token(token)
    if subject is None:
        raise BearerRejected()
    device = db.get(AuthDeviceSession, subject.device_session_id)
    now = _utcnow()
    if device is None or not _session_is_usable(device, now):
        raise BearerRejected()
    if subject.kind == SESSION_KIND_USER:
        if device.user_id != subject.subject_id:
            raise BearerRejected()
        user = db.get(User, subject.subject_id)
        if user is None or not user.is_active or user.account_id != device.account_id:
            raise BearerRejected()
        return user, device.id
    if subject.kind != SESSION_KIND_ACCOUNT or device.user_id is not None:
        raise BearerRejected()
    if device.account_id != subject.subject_id:
        raise BearerRejected()
    account = db.get(Account, subject.subject_id)
    if account is None:
        raise BearerRejected()
    return account, device.id


def reissue_access_token(db: Session, *, device_session_id: int, user: User) -> str:
    device = db.get(AuthDeviceSession, device_session_id)
    now = _utcnow()
    if device is None or not _session_is_usable(device, now):
        raise BearerRejected()
    if device.account_id != user.account_id or not user.is_active:
        raise BearerRejected()
    device.user_id = user.id
    device.last_used_at = now
    db.commit()
    return create_access_token(device_session_id=device.id, kind=SESSION_KIND_USER, subject_id=user.id)


def revoke_device_session(
    db: Session, *, device_session_id: int, account_id: int, reason: str, commit: bool = True
) -> bool:
    row = db.get(AuthDeviceSession, device_session_id)
    if row is None or row.account_id != account_id:
        return False
    if row.revoked_at is None:
        row.revoked_at = _utcnow()
        row.revoked_reason = reason
    if commit:
        db.commit()
    return True


def revoke_account_device_sessions(db: Session, account_id: int, reason: str) -> None:
    now = _utcnow()
    rows = db.scalars(
        select(AuthDeviceSession).where(
            AuthDeviceSession.account_id == account_id,
            AuthDeviceSession.revoked_at.is_(None),
        )
    ).all()
    for row in rows:
        row.revoked_at = now
        row.revoked_reason = reason


def revoke_membership_device_sessions(db: Session, user_id: int, reason: str) -> None:
    now = _utcnow()
    rows = db.scalars(
        select(AuthDeviceSession).where(
            AuthDeviceSession.user_id == user_id,
            AuthDeviceSession.revoked_at.is_(None),
        )
    ).all()
    for row in rows:
        row.revoked_at = now
        row.revoked_reason = reason


def list_device_sessions(
    db: Session, *, account_id: int, current_device_session_id: int | None
) -> list[DeviceSessionView]:
    now = _utcnow()
    rows = db.scalars(
        select(AuthDeviceSession)
        .where(AuthDeviceSession.account_id == account_id, AuthDeviceSession.revoked_at.is_(None))
        .order_by(AuthDeviceSession.created_at.desc(), AuthDeviceSession.id.desc())
    ).all()
    views: list[DeviceSessionView] = []
    for row in rows:
        if _as_utc(row.expires_at) <= now:
            continue
        views.append(
            DeviceSessionView(
                id=row.id,
                name=row.name,
                platform=row.platform,
                created_at=_as_utc(row.created_at),
                last_used_at=_as_utc(row.last_used_at),
                expires_at=_as_utc(row.expires_at),
                revoked_at=None,
                current=row.id == current_device_session_id,
            )
        )
    return views
