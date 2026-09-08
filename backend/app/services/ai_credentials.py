from __future__ import annotations

import base64
import hashlib
import re

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

_KEY_TAIL = re.compile(r"([A-Za-z0-9]{4})\s*$")


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.ai_credentials_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_api_key(plaintext: str) -> str:
    cleaned = plaintext.strip()
    if not cleaned:
        raise ValueError("API key is required")
    return _fernet().encrypt(cleaned.encode("utf-8")).decode("ascii")


def decrypt_api_key(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Could not decrypt stored API key") from exc


def api_key_last4(plaintext: str) -> str:
    match = _KEY_TAIL.search(plaintext.strip())
    if match:
        return match.group(1)
    return plaintext.strip()[-4:]
