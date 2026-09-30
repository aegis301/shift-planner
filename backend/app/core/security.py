import hashlib
import secrets
from base64 import urlsafe_b64encode
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from itsdangerous import BadSignature, URLSafeTimedSerializer
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
serializer = URLSafeTimedSerializer(settings.session_secret, salt="shift-planner-session")
access_serializer = URLSafeTimedSerializer(settings.session_secret, salt="shift-planner-access")
SESSION_MAX_AGE_SECONDS = int(timedelta(days=7).total_seconds())

SESSION_PAYLOAD_VERSION = 2
SESSION_KIND_USER = "user"
SESSION_KIND_ACCOUNT = "account"
ACCESS_TOKEN_TYP = "access"


@dataclass(frozen=True)
class SessionSubject:
    kind: str
    id: int


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return pwd_context.verify(password, hashed_password)


def create_user_session_token(user_id: int) -> str:
    return serializer.dumps(
        {
            "v": SESSION_PAYLOAD_VERSION,
            "typ": SESSION_KIND_USER,
            "sub": user_id,
            "iat": datetime.now(UTC).isoformat(),
        }
    )


def create_account_session_token(account_id: int) -> str:
    return serializer.dumps(
        {
            "v": SESSION_PAYLOAD_VERSION,
            "typ": SESSION_KIND_ACCOUNT,
            "sub": account_id,
            "iat": datetime.now(UTC).isoformat(),
        }
    )


def create_session_token(user_id: int) -> str:
    return create_user_session_token(user_id)


def verify_session_subject(token: str) -> SessionSubject | None:
    try:
        payload = serializer.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
    except BadSignature:
        return None
    if not isinstance(payload, dict):
        return None
    typ = payload.get("typ")
    sub = payload.get("sub")
    if typ == SESSION_KIND_ACCOUNT and sub is not None:
        return SessionSubject(kind=SESSION_KIND_ACCOUNT, id=int(sub))
    if typ == SESSION_KIND_USER and sub is not None:
        return SessionSubject(kind=SESSION_KIND_USER, id=int(sub))
    if typ is None and payload.get("v") is None:
        if sub is None:
            return None
        return SessionSubject(kind=SESSION_KIND_USER, id=int(sub))
    return None


def verify_session_token(token: str) -> int | None:
    subj = verify_session_subject(token)
    if subj is None or subj.kind != SESSION_KIND_USER:
        return None
    return subj.id


@dataclass(frozen=True)
class AccessTokenSubject:
    device_session_id: int
    kind: str
    subject_id: int


def create_access_token(*, device_session_id: int, kind: str, subject_id: int) -> str:
    return access_serializer.dumps(
        {
            "typ": ACCESS_TOKEN_TYP,
            "sid": device_session_id,
            "kind": kind,
            "sub": subject_id,
            "iat": datetime.now(UTC).isoformat(),
        }
    )


def verify_access_token(token: str) -> AccessTokenSubject | None:
    try:
        payload = access_serializer.loads(token, max_age=settings.access_token_ttl_seconds)
    except BadSignature:
        return None
    if not isinstance(payload, dict) or payload.get("typ") != ACCESS_TOKEN_TYP:
        return None
    sid = payload.get("sid")
    kind = payload.get("kind")
    sub = payload.get("sub")
    if sid is None or sub is None or kind not in {SESSION_KIND_USER, SESSION_KIND_ACCOUNT}:
        return None
    return AccessTokenSubject(device_session_id=int(sid), kind=str(kind), subject_id=int(sub))


def new_refresh_secret() -> str:
    return urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")


def compose_refresh_token(device_session_id: int, secret: str) -> str:
    return f"{device_session_id}.{secret}"


def parse_refresh_token(token: str) -> tuple[int, str] | None:
    session_id, separator, secret = token.partition(".")
    if separator != "." or not session_id.isdigit() or secret == "":
        return None
    return int(session_id), secret


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
