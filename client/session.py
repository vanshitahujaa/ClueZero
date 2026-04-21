"""Client-side session state: open + heartbeat + silent-exit-on-revoke."""

from __future__ import annotations

import logging
import os
import platform
import socket
import threading
import time
from typing import Optional

import requests

from config import SERVER_URL, TOKEN

logger = logging.getLogger("cluezero.session")

_state_lock = threading.Lock()
_session_id: Optional[str] = None
_heartbeat_interval: int = 30
_shutdown_event = threading.Event()
_heartbeat_thread: Optional[threading.Thread] = None


class SessionRevoked(RuntimeError):
    """Raised when the server rejects this agent in favour of a newer one."""


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {TOKEN}"}


def session_headers() -> dict:
    with _state_lock:
        sid = _session_id
    if sid is None:
        raise RuntimeError("Session not opened")
    return {**_auth_headers(), "X-Session-Id": sid}


def open_session() -> str:
    """POST /session/open; stores the returned session_id. Revokes prior sessions for this token."""
    global _session_id, _heartbeat_interval

    if not TOKEN:
        raise RuntimeError("TOKEN is not configured (missing in config.ini)")

    payload = {
        "platform": platform.system(),
        "machine_hint": socket.gethostname(),
    }
    resp = requests.post(
        f"{SERVER_URL}/session/open",
        json=payload,
        headers=_auth_headers(),
        timeout=15,
    )
    if resp.status_code == 401:
        raise SessionRevoked(f"Server rejected token: {resp.text}")
    resp.raise_for_status()
    data = resp.json()
    with _state_lock:
        _session_id = data["session_id"]
        _heartbeat_interval = max(15, int(data.get("heartbeat_seconds", 30)))
    logger.info("Session opened (heartbeat every %ds)", _heartbeat_interval)
    return _session_id  # type: ignore[return-value]


def _heartbeat_loop() -> None:
    while not _shutdown_event.is_set():
        try:
            resp = requests.post(
                f"{SERVER_URL}/session/ping",
                headers=session_headers(),
                timeout=10,
            )
            if resp.status_code == 401:
                logger.warning("Session revoked by server — shutting down silently.")
                _shutdown_event.set()
                os._exit(0)  # silent exit, as per spec
            resp.raise_for_status()
        except SessionRevoked:
            os._exit(0)
        except Exception as exc:
            logger.debug("Heartbeat error (will retry): %s", exc)

        _shutdown_event.wait(_heartbeat_interval)


def start_heartbeat() -> None:
    global _heartbeat_thread
    if _heartbeat_thread and _heartbeat_thread.is_alive():
        return
    _heartbeat_thread = threading.Thread(target=_heartbeat_loop, daemon=True, name="heartbeat")
    _heartbeat_thread.start()


def stop() -> None:
    _shutdown_event.set()
