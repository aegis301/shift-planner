from datetime import datetime, timedelta, timezone

from itsdangerous import BadSignature, URLSafeTimedSerializer
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
serializer = URLSafeTimedSerializer(settings.session_secret, salt="shift-planner-session")
SESSION_MAX_AGE_SECONDS = int(timedelta(days=7).total_seconds())


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return pwd_context.verify(password, hashed_password)


def create_session_token(user_id: int) -> str:
    return serializer.dumps({"sub": user_id, "iat": datetime.now(timezone.utc).isoformat()})


def verify_session_token(token: str) -> int | None:
    try:
        payload = serializer.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
    except BadSignature:
        return None
    sub = payload.get("sub")
    return int(sub) if sub is not None else None
