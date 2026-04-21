"""ClueZero Desktop Agent — compiled binary entry point.

Runs silently in the background:
  * Opens a server session (LIFO revokes any older session for this token).
  * Listens for the configured global hotkey.
  * On trigger: captures a screenshot, submits it, waits for result,
    copies to clipboard, fires a desktop notification.
  * Heartbeats the server. On revocation (newer agent took over) or
    inactive/invalid token: exits silently with code 0 — no user-visible noise.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

# Ensure client/ is on the path when running as a plain script.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import HOTKEY, log_dir  # noqa: E402

# ── Logging (silent; file-only) ───────────────────────────────────────────
# force=True wins over any handlers config.py's import-time logging may have
# caused; this is the ONE place the root logger should be configured.
_log_file = log_dir() / "agent.log"
try:
    _log_file.parent.mkdir(parents=True, exist_ok=True)
    _handler = RotatingFileHandler(str(_log_file), maxBytes=512_000, backupCount=3, encoding="utf-8")
except Exception:
    # Extremely defensive: if home dir isn't writable for any reason, fall
    # back to a stream handler so logging at least doesn't crash the agent.
    _handler = logging.StreamHandler()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[_handler],
    force=True,
)
logger = logging.getLogger("cluezero.agent")
logger.info("Log file: %s", _log_file)


def on_hotkey_triggered():
    """Full pipeline: capture → submit → wait → clipboard."""
    try:
        from capture import capture_screenshot
        from api_client import submit, wait_for_result
        from clipboard import copy_to_clipboard, notify_desktop

        logger.info("--- Pipeline started ---")
        image_b64 = capture_screenshot()
        job_id = submit(image_b64)
        logger.info("Waiting for AI response (job=%s)...", job_id)
        result = wait_for_result(job_id)
        copy_to_clipboard(result)
        notify_desktop("ClueZero", f"Response ready ({len(result)} chars) — in clipboard.")
        logger.info("Pipeline complete (%d chars)", len(result))

    except SystemExit:
        raise
    except Exception as exc:
        logger.exception("Pipeline failed: %s", exc)
        try:
            from clipboard import notify_desktop
            notify_desktop("ClueZero", f"Error: {exc}")
        except Exception:
            pass


def main() -> int:
    from session import SessionRevoked, open_session, start_heartbeat

    logger.info("ClueZero agent starting up (hotkey=%s)", HOTKEY)

    try:
        open_session()
    except SessionRevoked as exc:
        logger.warning("Startup rejected: %s — exiting silently.", exc)
        return 0
    except Exception as exc:
        logger.exception("Could not open session — exiting: %s", exc)
        return 1

    start_heartbeat()

    from hotkey import HotkeyListener
    listener = HotkeyListener(callback=on_hotkey_triggered, hotkey=HOTKEY)
    listener.start()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception:
        import traceback
        logging.getLogger("cluezero.fatal").error("FATAL CRASH:\n%s", traceback.format_exc())
        sys.exit(1)
