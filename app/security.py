from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import Header, HTTPException, status

from app.config import get_settings

_ABSOLUTE_PATH = re.compile(
    r"(?:\\\\[^\\/\r\n]+[\\/][^\r\n]*|\b[a-zA-Z]:[\\/][^\r\n]*|"
    r"(?<![A-Za-z0-9:/])/(?:[^/\s'\"<>]+/)*[^/\s'\"<>),;\]}]+)"
)
_OWNED_API_URL = re.compile(
    r"/api/runs/\d+/(?:assets/\d+|uploads/\d+|exports/(?:markdown|json|zip))"
)
_PRIVATE_PATH_KEYS = frozenset({"path", "file_path", "reference_path"})


def require_api_token(
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    expected = get_settings().api_token
    if not expected:
        return

    bearer_token = None
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer":
            bearer_token = token

    if bearer_token == expected or x_api_key == expected:
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def redact_internal_error(value: str | None) -> str | None:
    if value is None:
        return None
    if _ABSOLUTE_PATH.search(value):
        return "workflow execution failed; internal path redacted"
    return value


def redact_absolute_paths(value: str) -> str:
    """Redact any string containing a non-public absolute filesystem path.

    Redacting the complete field prevents path fragments with spaces from
    surviving a substring replacement. Exact workbench URLs are public IDs,
    not filesystem paths, and remain usable.
    """
    matches = list(_ABSOLUTE_PATH.finditer(value))
    if not matches:
        return value
    if all(_OWNED_API_URL.fullmatch(match.group(0)) for match in matches):
        return value
    return "[internal path redacted]"


def sanitize_public_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: sanitize_public_payload(item)
            for key, item in value.items()
            if key not in _PRIVATE_PATH_KEYS
        }
    if isinstance(value, list):
        return [sanitize_public_payload(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_public_payload(item) for item in value]
    if isinstance(value, str):
        return redact_absolute_paths(value)
    return value


def owned_final_package(run_id: int, value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    kinds = {"markdown_url": "markdown", "json_url": "json", "zip_url": "zip"}
    public = {
        key: expected
        for key, kind in kinds.items()
        if value.get(key) == (expected := f"/api/runs/{run_id}/exports/{kind}")
    }
    return public or None
