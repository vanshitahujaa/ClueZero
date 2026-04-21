"""Client configuration.

Precedence (highest first):
  1. config.ini sitting next to the executable/script (the one the per-user
     .bat/.sh writes at install time).
  2. Environment variables / .env.
  3. Hardcoded defaults.
"""

from __future__ import annotations

import configparser
import logging
import os
import platform
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger("cluezero.config")


def _executable_dir() -> Path:
    """Directory where the running binary (or script) lives."""
    if getattr(sys, "frozen", False):  # PyInstaller
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _config_path() -> Path:
    return _executable_dir() / "config.ini"


def _load_ini() -> dict:
    """Read config.ini from the binary's directory (if present)."""
    cfg_path = _config_path()
    out: dict = {}
    if cfg_path.exists():
        parser = configparser.ConfigParser()
        try:
            parser.read(cfg_path, encoding="utf-8")
            if "cluezero" in parser:
                out = dict(parser["cluezero"])
                logger.info("Loaded config.ini from %s", cfg_path)
        except Exception as exc:
            logger.warning("Failed to parse %s: %s", cfg_path, exc)
    return out


def _persist_device_id(device_id: str) -> None:
    """Append device_id=<uuid> to config.ini.

    Appends rather than rewriting so we preserve the exact `key=value` format
    the installer templates write — the PS1 agent on Windows parses the file
    with strict regex that rejects spaces around `=`.
    """
    cfg_path = _config_path()
    try:
        if cfg_path.exists():
            existing = cfg_path.read_text(encoding="utf-8")
            suffix = "" if existing.endswith("\n") else "\n"
            cfg_path.write_text(f"{existing}{suffix}device_id={device_id}\n", encoding="utf-8")
        else:
            cfg_path.write_text(f"[cluezero]\ndevice_id={device_id}\n", encoding="utf-8")
        logger.info("Persisted new device_id=%s to %s", device_id, cfg_path)
    except Exception as exc:
        logger.warning("Failed to persist device_id to %s: %s — will regenerate next run", cfg_path, exc)


load_dotenv()  # still accept env overrides for dev runs
_ini = _load_ini()


def _get(key: str, default: str = "") -> str:
    return _ini.get(key.lower()) or os.getenv(key.upper(), default)


SERVER_URL: str = _get("SERVER_URL", "http://localhost:8000").rstrip("/")
TOKEN: str = _get("TOKEN", "")
_DEFAULT_HOTKEY = "cmd+shift+o" if platform.system() == "Darwin" else "ctrl+shift+o"
HOTKEY: str = _get("HOTKEY", _DEFAULT_HOTKEY)
CLIENT_TIMEOUT: int = int(_get("CLIENT_TIMEOUT", "120"))
DEFAULT_PROMPT: str = _get(
    "DEFAULT_PROMPT",
    "If there is a coding problem visible in the screenshot, provide ONLY the raw code solution "
    "in the language shown. Do NOT include any explanations, do NOT include markdown formatting "
    "(like ```), and do NOT include comments in the code. Output purely the code required. "
    "If it's not a coding problem, answer as concisely as possible.",
)
IMAGE_QUALITY: int = int(_get("IMAGE_QUALITY", "65"))
IMAGE_MAX_RESOLUTION: int = int(_get("IMAGE_MAX_RESOLUTION", "720"))


def _resolve_device_id() -> str:
    """Stable per-install UUID. Generated once, persisted to config.ini next to the binary."""
    existing = _get("DEVICE_ID", "").strip()
    if existing:
        return existing
    new_id = uuid.uuid4().hex
    _persist_device_id(new_id)
    return new_id


DEVICE_ID: str = _resolve_device_id()


def log_dir() -> Path:
    """Per-user log directory — created on first access."""
    home = Path.home()
    base = home / ".cluezero"
    base.mkdir(parents=True, exist_ok=True)
    return base
