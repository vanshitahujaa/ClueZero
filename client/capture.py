"""Screenshot capture — in-memory processing, no disk writes."""

import base64
import io
import logging

import mss
from PIL import Image

from config import IMAGE_QUALITY, IMAGE_MAX_RESOLUTION

logger = logging.getLogger("cluezero.capture")


def capture_screenshot() -> str:
    """
    Capture the primary monitor, compress to JPEG, and return base64.

    The image is processed entirely in memory:
      1. mss grabs a raw screenshot
      2. PIL resizes to ≤ MAX_RESOLUTION
      3. Compressed JPEG at configured quality
      4. Returned as a base64 string
    """
    with mss.mss() as sct:
        # Grab primary monitor (index 1 = first monitor, 0 = all)
        monitor = sct.monitors[1]
        raw = sct.grab(monitor)

    # Convert to PIL Image
    img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    # Resize if needed
    max_res = IMAGE_MAX_RESOLUTION
    if max(img.size) > max_res:
        img.thumbnail((max_res, max_res), Image.LANCZOS)
        logger.debug("Screenshot resized to %s", img.size)

    # Compress to JPEG in memory
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=IMAGE_QUALITY, optimize=True)

    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    logger.info(
        "Screenshot captured: %dx%d → %d KB (base64)",
        raw.size.width,
        raw.size.height,
        len(b64) // 1024,
    )
    return b64
