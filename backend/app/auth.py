"""Auth helpers — Bearer token for user agents, HTTP Basic for admin."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import settings
from app.db import get_db
from app.models_db import User
from app.services.users import get_user_by_token

basic = HTTPBasic()


def require_admin(creds: Annotated[HTTPBasicCredentials, Depends(basic)]) -> str:
    ok_user = secrets.compare_digest(creds.username, settings.admin_user)
    ok_pass = secrets.compare_digest(creds.password, settings.admin_pass)
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return creds.username


def _extract_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return authorization.split(None, 1)[1].strip()


async def require_user(
    authorization: Annotated[str | None, Header()] = None,
    db=Depends(get_db),
) -> User:
    token = _extract_token(authorization)
    user = await get_user_by_token(db, token)
    if user is None or not user.active:
        raise HTTPException(status_code=401, detail="Invalid or inactive token")
    return user
