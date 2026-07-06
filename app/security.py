from __future__ import annotations

from typing import Annotated

from fastapi import Header, HTTPException, status

from app.config import get_settings


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
