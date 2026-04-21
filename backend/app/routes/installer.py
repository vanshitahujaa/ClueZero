"""Per-user installer scripts + binary downloads."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.services.users import get_user_by_token

logger = logging.getLogger("cluezero.installer")
router = APIRouter(tags=["installer"])

_templates_dir = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))

DEFAULT_HOTKEY = "ctrl+shift+o"


async def _lookup_user(db: AsyncSession, token: str):
    user = await get_user_by_token(db, token)
    if user is None or not user.active:
        raise HTTPException(status_code=404, detail="Unknown or inactive token")
    return user


@router.get("/installer/{token}.bat", response_class=PlainTextResponse)
async def installer_bat(token: str, db: Annotated[AsyncSession, Depends(get_db)]):
    user = await _lookup_user(db, token)
    body = templates.get_template("installer.bat.j2").render(
        server_public_url=settings.server_public_url,
        token=user.token,
        hotkey=DEFAULT_HOTKEY,
        name=user.name,
    )
    return PlainTextResponse(content=body, media_type="application/bat")


@router.get("/installer/{token}.sh", response_class=PlainTextResponse)
async def installer_sh(token: str, db: Annotated[AsyncSession, Depends(get_db)]):
    user = await _lookup_user(db, token)
    body = templates.get_template("installer.sh.j2").render(
        server_public_url=settings.server_public_url,
        token=user.token,
        hotkey=DEFAULT_HOTKEY,
        name=user.name,
    )
    return PlainTextResponse(content=body, media_type="text/x-shellscript")


# ── Binary serving ────────────────────────────────────────────────────────

_STATIC = Path(__file__).resolve().parent.parent.parent / "static"


@router.get("/binary/windows")
async def binary_windows():
    path = _STATIC / "agent.exe"
    if not path.exists():
        raise HTTPException(status_code=404, detail="agent.exe not built yet — see client/build/")
    return FileResponse(str(path), media_type="application/octet-stream", filename="agent.exe")


@router.get("/binary/linux")
async def binary_linux():
    path = _STATIC / "agent-linux"
    if not path.exists():
        raise HTTPException(status_code=404, detail="agent-linux not built yet — see client/build/")
    return FileResponse(str(path), media_type="application/octet-stream", filename="agent")


@router.get("/binary/darwin")
async def binary_darwin():
    path = _STATIC / "agent-darwin"
    if not path.exists():
        raise HTTPException(status_code=404, detail="agent-darwin not built yet — see client/build/build-macos.sh")
    return FileResponse(str(path), media_type="application/octet-stream", filename="agent")
