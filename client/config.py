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
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger("cluezero.config")


def _executable_dir() -> Path:
    """Directory where the running binary (or script) lives."""
    if getattr(sys, "frozen", False):  # PyInstaller
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _load_ini() -> dict:
    """Read config.ini from the binary's directory (if present)."""
    cfg_path = _executable_dir() / "config.ini"
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


def log_dir() -> Path:
    """Per-user log directory — created on first access."""
    home = Path.home()
    base = home / ".cluezero"
    base.mkdir(parents=True, exist_ok=True)
    return base
