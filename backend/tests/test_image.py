"""Tests for the image optimisation pipeline."""

import base64
import io

import pytest
from PIL import Image


def _make_image(width: int, height: int, color: str = "blue") -> str:
    """Create a test image and return base64."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")  # intentionally PNG to test conversion
    return base64.b64encode(buf.getvalue()).decode("ascii")


class TestOptimizeImage:
    def test_resize_large_image(self):
        from app.services.image import optimize_image

        large_b64 = _make_image(1920, 1080)
        opt_b64, img_hash = optimize_image(large_b64)

        # Decode and check size
        opt_bytes = base64.b64decode(opt_b64)
        img = Image.open(io.BytesIO(opt_bytes))
        assert max(img.size) <= 720  # should be resized
        assert img.format == "JPEG"  # should be JPEG

    def test_small_image_passthrough(self):
        from app.services.image import optimize_image

        small_b64 = _make_image(200, 150)
        opt_b64, img_hash = optimize_image(small_b64)

        opt_bytes = base64.b64decode(opt_b64)
        img = Image.open(io.BytesIO(opt_bytes))
        # Small image should keep its size
        assert img.size == (200, 150)

    def test_hash_consistency(self):
        from app.services.image import optimize_image

        b64 = _make_image(300, 300, "green")
        _, hash1 = optimize_image(b64)
        _, hash2 = optimize_image(b64)
        assert hash1 == hash2  # same input → same hash

    def test_different_images_different_hash(self):
        from app.services.image import optimize_image

        _, hash1 = optimize_image(_make_image(300, 300, "red"))
        _, hash2 = optimize_image(_make_image(300, 300, "green"))
        assert hash1 != hash2

    def test_rgba_conversion(self):
        """RGBA images should be converted to RGB for JPEG."""
        from app.services.image import optimize_image

        img = Image.new("RGBA", (100, 100), (255, 0, 0, 128))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        opt_b64, _ = optimize_image(b64)
        opt_bytes = base64.b64decode(opt_b64)
        result = Image.open(io.BytesIO(opt_bytes))
        assert result.mode == "RGB"
