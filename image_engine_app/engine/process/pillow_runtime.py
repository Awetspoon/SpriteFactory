"""Lazy Pillow dependency loading for the processing engine."""

from __future__ import annotations

from image_engine_app.engine.process.errors import ProcessingUnavailable


def require_pillow():
    """Return the Pillow modules used by frame processing."""

    try:
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps  # type: ignore
    except Exception as exc:  # pragma: no cover - exercised only without Pillow
        raise ProcessingUnavailable("Pillow is required for image processing.") from exc
    return Image, ImageEnhance, ImageFilter, ImageOps
