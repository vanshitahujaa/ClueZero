"""Image optimisation pipeline — resize, compress, and hash."""

import base64
import hashlib
import io
import logging

from PIL import Image

from app.config import settings

logger = logging.getLogger("cluezero.image")


def optimize_image(image_b64: str) -> tuple[str, str]:
    """
    Optimise a base64-encoded image:
      1. Decode → PIL Image
      2. Resize to ≤ MAX_RESOLUTION (preserving aspect ratio)
      3. Convert to JPEG at configured quality
      4. Re-encode to base64
      5. Compute perceptual hash for dedup

    Returns:
        (optimised_b64, image_hash)
    """
    raw_bytes = base64.b64decode(image_b64)
    img = Image.open(io.BytesIO(raw_bytes))

    # Convert RGBA/P → RGB for JPEG
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    # Resize if larger than max resolution
    max_res = settings.image_max_resolution
    if max(img.size) > max_res:
        img.thumbnail((max_res, max_res), Image.LANCZOS)
        logger.debug("Resized to %s", img.size)

    # Compress to JPEG
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=settings.image_quality, optimize=True)
    optimised_bytes = buf.getvalue()

    # Check size limit
    size_kb = len(optimised_bytes) / 1024
    if size_kb > settings.max_image_size_kb:
        # Aggressively reduce quality
        for q in (50, 40, 30):
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=q, optimize=True)
            optimised_bytes = buf.getvalue()
            size_kb = len(optimised_bytes) / 1024
            if size_kb <= settings.max_image_size_kb:
                break
        logger.debug("Final quality reduced, size=%.1f KB", size_kb)

    optimised_b64 = base64.b64encode(optimised_bytes).decode("ascii")

    # Hash for dedup (SHA-256 on the compressed bytes)
    image_hash = hashlib.sha256(optimised_bytes).hexdigest()

    logger.info(
        "Image optimised: %d→%d bytes (%.0f%% reduction), hash=%s",
        len(raw_bytes),
        len(optimised_bytes),
        (1 - len(optimised_bytes) / max(len(raw_bytes), 1)) * 100,
        image_hash[:12],
    )
    return optimised_b64, image_hash
