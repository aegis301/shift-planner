from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from itsdangerous import BadSignature, URLSafeTimedSerializer
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
serializer = URLSafeTimedSerializer(settings.session_secret, salt="shift-planner-session")
SESSION_MAX_AGE_SECONDS = int(timedelta(days=7).total_seconds())

SESSION_PAYLOAD_VERSION = 2
SESSION_KIND_USER = "user"
SESSION_KIND_ACCOUNT = "account"


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
            "iat": datetime.now(timezone.utc).isoformat(),
        }
    )


def create_account_session_token(account_id: int) -> str:
    return serializer.dumps(
        {
            "v": SESSION_PAYLOAD_VERSION,
            "typ": SESSION_KIND_ACCOUNT,
            "sub": account_id,
            "iat": datetime.now(timezone.utc).isoformat(),
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
