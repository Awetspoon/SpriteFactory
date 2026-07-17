"""Supported image formats shared by every ingestion adapter."""

from __future__ import annotations

from image_engine_app.engine.models import AssetFormat


SUPPORTED_FORMATS_BY_EXTENSION: dict[str, AssetFormat] = {
    ".jpg": AssetFormat.JPG,
    ".jpeg": AssetFormat.JPG,
    ".png": AssetFormat.PNG,
    ".webp": AssetFormat.WEBP,
    ".tif": AssetFormat.TIFF,
    ".tiff": AssetFormat.TIFF,
    ".bmp": AssetFormat.BMP,
    ".ico": AssetFormat.ICO,
    ".gif": AssetFormat.GIF,
}

SUPPORTED_IMAGE_EXTENSIONS = frozenset(SUPPORTED_FORMATS_BY_EXTENSION)
