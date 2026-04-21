"""API client — HTTP submission + WebSocket / polling result retrieval."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Optional

import requests
import websocket

from config import SERVER_URL, CLIENT_TIMEOUT, DEFAULT_PROMPT, TOKEN
from session import SessionRevoked, session_headers

logger = logging.getLogger("cluezero.api_client")

MAX_RETRIES = 3
RETRY_BACKOFF = 2
POLL_INTERVAL = 3


def _handle_revocation(resp: requests.Response) -> None:
    """If the server says the session is revoked, exit the process silently."""
    if resp.status_code == 401:
        body = (resp.text or "").lower()
        if "session_revoked" in body or "invalid or inactive token" in body:
            logger.warning("Server revoked this session — exiting silently.")
            os._exit(0)


def submit(image_b64: str, prompt: Optional[str] = None) -> str:
    """Submit a screenshot. Auth via Bearer + X-Session-Id (set up by session.open_session)."""
    url = f"{SERVER_URL}/submit"
    payload = {"image": image_b64, "prompt": prompt or DEFAULT_PROMPT}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(url, json=payload, headers=session_headers(), timeout=30)
            _handle_revocation(resp)
            if resp.status_code == 429:
                detail = resp.json().get("detail", "Rate limited")
                logger.warning("Rate limited: %s", detail)
                time.sleep(RETRY_BACKOFF ** attempt)
                continue
            resp.raise_for_status()
            data = resp.json()
            job_id = data["job_id"]
            logger.info("Job submitted: %s (status=%s)", job_id, data["status"])
            return job_id

        except requests.RequestException as exc:
            logger.warning("Submit attempt %d failed: %s", attempt, exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF ** attempt)
            else:
                raise RuntimeError(f"Failed to submit after {MAX_RETRIES} attempts: {exc}")

    raise RuntimeError("Submit failed — exhausted retries")


def wait_for_result(job_id: str) -> str:
    """WebSocket first; fall back to polling."""
    result = _wait_ws(job_id)
    if result is not None:
        return result
    logger.info("WebSocket unavailable, falling back to polling...")
    return _wait_poll(job_id)


def _wait_ws(job_id: str) -> Optional[str]:
    ws_url = SERVER_URL.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_url}/ws/{job_id}"

    try:
        ws = websocket.create_connection(
            ws_url,
            timeout=CLIENT_TIMEOUT,
            header=[f"Authorization: Bearer {TOKEN}"],
        )
        logger.info("WebSocket connected for job %s", job_id)

        while True:
            raw = ws.recv()
            data = json.loads(raw)
            status = data.get("status", "")

            if status == "completed":
                ws.close()
                return data.get("response", "")
            if status == "failed":
                ws.close()
                raise RuntimeError(f"Job failed: {data.get('error', 'Unknown error')}")
            if status == "error":
                ws.close()
                raise RuntimeError(f"Server error: {data.get('detail', 'Unknown')}")

            logger.debug("Job %s status: %s", job_id, status)

    except (websocket.WebSocketException, ConnectionRefusedError, OSError) as exc:
        logger.warning("WebSocket failed: %s", exc)
        return None


def _wait_poll(job_id: str) -> str:
    url = f"{SERVER_URL}/result/{job_id}"
    deadline = time.time() + CLIENT_TIMEOUT

    while time.time() < deadline:
        try:
            resp = requests.get(url, headers=session_headers(), timeout=10)
            _handle_revocation(resp)
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status", "")

            if status == "completed":
                return data.get("response", "")
            if status == "failed":
                raise RuntimeError(f"Job failed: {data.get('error', 'Unknown error')}")

            logger.debug("Poll: job %s status=%s", job_id, status)
            time.sleep(POLL_INTERVAL)

        except requests.RequestException as exc:
            logger.warning("Poll error: %s, retrying...", exc)
            time.sleep(POLL_INTERVAL)

    raise RuntimeError(f"Timed out after {CLIENT_TIMEOUT}s waiting for job {job_id}")
