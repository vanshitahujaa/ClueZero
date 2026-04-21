"""Admin panel — user CRUD + per-user usage. HTTP Basic gated."""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.config import settings
from app.db import get_db
from app.services import users as users_svc
from app.services import billing as billing_svc

logger = logging.getLogger("cluezero.admin")
router = APIRouter(prefix="/admin", tags=["admin"])

_templates_dir = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


def _windows_install_cmd(server_url: str, token: str) -> str:
    """Quote-free one-liner: a UTF-16-LE base64 payload via -EncodedCommand.

    Works identically when pasted into cmd.exe, Win+R, or an already-open
    PowerShell prompt — no `\\"` escaping that only cmd can strip.
    """
    ps1_url = f"{server_url.rstrip('/')}/installer/{token}.ps1"
    ps_script = (
        "$p = Join-Path $env:TEMP 'clz_install.ps1'; "
        f"(New-Object Net.WebClient).DownloadFile('{ps1_url}', $p); "
        "& $p"
    )
    encoded = base64.b64encode(ps_script.encode("utf-16-le")).decode("ascii")
    return (
        r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe "
        f"-NoProfile -ExecutionPolicy Bypass -EncodedCommand {encoded}"
    )


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def admin_index(
    request: Request,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    users = await users_svc.list_users(db)
    usage_map = await billing_svc.all_usage(db)
    rows = []
    for u in users:
        usage = usage_map.get(
            u.id,
            billing_svc.UserUsage(
                user_id=u.id, job_count=0, tokens_in=0, tokens_out=0,
                cost_usd=0, last_used=None,
            ),
        )
        rows.append({
            "user": u,
            "usage": usage,
            "win_cmd": _windows_install_cmd(settings.server_public_url, u.token),
        })

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "users": rows,
            "server_public_url": settings.server_public_url,
            "model": settings.llm_model,
            "in_price": settings.llm_input_price_per_1k,
            "out_price": settings.llm_output_price_per_1k,
        },
    )


@router.post("/users")
async def admin_create_user(
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    name: Annotated[str, Form()] = "",
):
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    u = await users_svc.create_user(db, name)
    logger.info("Admin created user id=%s name=%s", u.id, u.name)
    return RedirectResponse(url="/admin/", status_code=303)


@router.post("/users/{user_id}/regenerate")
async def admin_regenerate(
    user_id: int,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    u = await users_svc.regenerate_token(db, user_id)
    if u is None:
        raise HTTPException(status_code=404, detail="User not found")
    logger.info("Admin regenerated token user=%s", user_id)
    return RedirectResponse(url="/admin/", status_code=303)


@router.post("/users/{user_id}/toggle")
async def admin_toggle(
    user_id: int,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    existing = await users_svc.get_user_by_id(db, user_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="User not found")
    await users_svc.set_active(db, user_id, not existing.active)
    return RedirectResponse(url="/admin/", status_code=303)


@router.post("/users/{user_id}/delete")
async def admin_delete(
    user_id: int,
    _admin: Annotated[str, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    ok = await users_svc.delete_user(db, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    logger.info("Admin deleted user=%s", user_id)
    return RedirectResponse(url="/admin/", status_code=303)
