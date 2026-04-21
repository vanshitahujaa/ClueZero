"""Cross-platform clipboard write + optional desktop notification."""

import logging
import platform

import pyperclip

logger = logging.getLogger("cluezero.clipboard")


def copy_to_clipboard(text: str) -> None:
    """Copy text to the system clipboard."""
    try:
        pyperclip.copy(text)
        logger.info("Result copied to clipboard (%d chars)", len(text))
    except Exception as exc:
        logger.error("Clipboard copy failed: %s", exc)
        # Fallback: print to stdout so user can still see it
        logger.error("CLIPBOARD COPY FAILED:\n%s", text)


def notify_desktop(title: str, message: str) -> None:
    """Send an optional desktop notification."""
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message[:256],  # some platforms truncate
            timeout=5,
        )
    except ImportError:
        logger.debug("plyer not installed — skipping desktop notification")
    except Exception as exc:
        logger.debug("Desktop notification failed: %s", exc)
