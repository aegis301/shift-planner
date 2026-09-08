from __future__ import annotations

import json
import logging
import uuid
from typing import Any
from urllib import error, request

from app.core.config import settings

logger = logging.getLogger(__name__)


def langfuse_enabled() -> bool:
    return bool(settings.langfuse_host.strip() and settings.langfuse_public_key and settings.langfuse_secret_key)


def new_trace_id() -> str:
    return uuid.uuid4().hex


def emit_langfuse_trace(
    *,
    trace_id: str,
    name: str,
    user_id: str,
    metadata: dict[str, Any],
    input_payload: dict[str, Any],
    output_payload: dict[str, Any] | None,
    usage: dict[str, int] | None = None,
) -> None:
    if not langfuse_enabled():
        return
    host = settings.langfuse_host.rstrip("/")
    body = {
        "batch": [
            {
                "id": uuid.uuid4().hex,
                "type": "trace-create",
                "timestamp": None,
                "body": {
                    "id": trace_id,
                    "name": name,
                    "userId": user_id,
                    "metadata": metadata,
                    "input": input_payload,
                    "output": output_payload,
                },
            }
        ]
    }
    if usage:
        body["batch"][0]["body"]["metadata"] = {**metadata, "usage": usage}
    payload = json.dumps(body).encode("utf-8")
    req = request.Request(
        f"{host}/api/public/ingestion",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Langfuse-Public-Key": settings.langfuse_public_key,
            "X-Langfuse-Secret-Key": settings.langfuse_secret_key,
        },
    )
    try:
        with request.urlopen(req, timeout=5) as response:
            response.read()
    except error.URLError:
        logger.warning("Langfuse ingest failed for trace %s", trace_id)
