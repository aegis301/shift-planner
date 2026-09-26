import re

from fastapi.routing import APIRoute

from app.api.file_responses import FILE_MEDIA_TYPES
from app.main import app
from app.scripts.export_openapi import render_openapi

_OPERATION_ID = re.compile(r"^[a-z_]+$")


def _success_media_types(route: APIRoute) -> set[str]:
    media: set[str] = set()
    for status, meta in (route.responses or {}).items():
        code = status if isinstance(status, int) else None
        if code is not None and code >= 400:
            continue
        if not isinstance(meta, dict):
            continue
        content = meta.get("content")
        if isinstance(content, dict):
            media.update(str(key) for key in content)
    return media


def _is_file_download(route: APIRoute) -> bool:
    media = _success_media_types(route)
    return bool(media) and media <= FILE_MEDIA_TYPES


def test_export_openapi_is_stable():
    assert render_openapi() == render_openapi()


def test_operation_ids_are_unique_and_readable():
    seen: dict[str, str] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        operation_id = route.unique_id
        assert _OPERATION_ID.match(operation_id), operation_id
        previous = seen.get(operation_id)
        assert previous is None, f"{operation_id} used by {previous} and {route.path}"
        seen[operation_id] = route.path


def test_json_routes_declare_a_response_model():
    missing: list[str] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.response_model is not None:
            continue
        if route.status_code == 204:
            continue
        if _is_file_download(route):
            continue
        missing.append(f"{route.methods} {route.path}")
    assert missing == []
