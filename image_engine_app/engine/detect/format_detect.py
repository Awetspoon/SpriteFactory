"""Format detection by extension and signature (Prompt 6)."""

from __future__ import annotations

from pathlib import Path

from engine.models import AssetFormat


EXTENSION_TO_FORMAT: dict[str, AssetFormat] = {
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


def detect_format_from_extension(path_or_name: str | Path) -> AssetFormat:
    """Detect format using the file extension only."""

    suffix = Path(path_or_name).suffix.lower()
    return EXTENSION_TO_FORMAT.get(suffix, AssetFormat.UNKNOWN)


def detect_format_from_signature(header_bytes: bytes) -> AssetFormat:
    """Detect format using magic bytes / signature."""

    if header_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return AssetFormat.PNG
    if header_bytes.startswith((b"GIF87a", b"GIF89a")):
        return AssetFormat.GIF
    if header_bytes.startswith(b"\xff\xd8\xff"):
        return AssetFormat.JPG
    if header_bytes.startswith(b"BM"):
        return AssetFormat.BMP
    if header_bytes.startswith((b"II*\x00", b"MM\x00*")):
        return AssetFormat.TIFF
    if header_bytes.startswith(b"\x00\x00\x01\x00"):
        return AssetFormat.ICO
    if len(header_bytes) >= 12 and header_bytes[:4] == b"RIFF" and header_bytes[8:12] == b"WEBP":
        return AssetFormat.WEBP
    return AssetFormat.UNKNOWN


def detect_format(
    *,
    path_or_name: str | Path | None = None,
    header_bytes: bytes | None = None,
) -> AssetFormat:
    """
    Detect format using signature first (if available), then extension fallback.

    Signature wins when known because extensions can be incorrect.
    """

    if header_bytes:
        by_sig = detect_format_from_signature(header_bytes)
        if by_sig is not AssetFormat.UNKNOWN:
            return by_sig

    if path_or_name is not None:
        return detect_format_from_extension(path_or_name)

    return AssetFormat.UNKNOWN


def signature_matches_format(expected_format: AssetFormat, header_bytes: bytes) -> bool:
    """Check whether the signature matches the expected format."""

    detected = detect_format_from_signature(header_bytes)
    if detected is AssetFormat.UNKNOWN:
        return False
    return detected is expected_format

