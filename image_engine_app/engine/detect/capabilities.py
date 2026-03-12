"""Capability flag detection heuristics (Prompt 6)."""

from __future__ import annotations

from engine.models import AssetFormat, Capabilities


def detect_capabilities(
    file_format: AssetFormat,
    *,
    header_bytes: bytes = b"",
    dimensions: tuple[int, int] | None = None,
    file_name: str | None = None,
) -> Capabilities:
    """Compute capability flags using lightweight format heuristics."""

    return Capabilities(
        has_alpha=_detect_has_alpha(file_format, header_bytes),
        is_animated=_detect_is_animated(file_format, header_bytes),
        is_sheet=_detect_is_sheet(dimensions, file_name=file_name),
        is_ico_bundle=_detect_is_ico_bundle(file_format, header_bytes),
    )


def _detect_has_alpha(file_format: AssetFormat, header_bytes: bytes) -> bool:
    if file_format is AssetFormat.PNG:
        if len(header_bytes) > 25 and header_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            color_type = header_bytes[25]
            if color_type in {4, 6}:  # grayscale+alpha, RGBA
                return True
        if b"tRNS" in header_bytes:
            return True
        return False

    if file_format is AssetFormat.WEBP:
        if b"VP8X" in header_bytes:
            idx = header_bytes.find(b"VP8X")
            if idx != -1 and idx + 8 < len(header_bytes):
                flags = header_bytes[idx + 8]
                if flags & 0x10:
                    return True
        if b"ALPH" in header_bytes:
            return True
        return False

    if file_format is AssetFormat.GIF:
        # GIF transparency exists but is index-based; simple header-only detection is unreliable.
        return b"\x21\xf9\x04" in header_bytes and any(
            (header_bytes[i + 3] & 0x01)
            for i in range(len(header_bytes) - 7)
            if header_bytes[i : i + 3] == b"\x21\xf9\x04"
        )

    return False


def _detect_is_animated(file_format: AssetFormat, header_bytes: bytes) -> bool:
    if file_format is AssetFormat.GIF:
        # Count image descriptor separators; >1 usually means multiple frames.
        return header_bytes.count(b"\x2c") > 1

    if file_format is AssetFormat.PNG:
        # APNG contains an animation control chunk.
        return b"acTL" in header_bytes

    if file_format is AssetFormat.WEBP:
        return b"ANIM" in header_bytes

    return False


def _detect_is_ico_bundle(file_format: AssetFormat, header_bytes: bytes) -> bool:
    if file_format is not AssetFormat.ICO:
        return False
    if len(header_bytes) < 6:
        return False
    reserved = int.from_bytes(header_bytes[0:2], "little")
    icon_type = int.from_bytes(header_bytes[2:4], "little")
    count = int.from_bytes(header_bytes[4:6], "little")
    return reserved == 0 and icon_type == 1 and count > 1


def _detect_is_sheet(
    dimensions: tuple[int, int] | None,
    *,
    file_name: str | None = None,
) -> bool:
    if file_name:
        lowered = file_name.lower()
        if "sprite_sheet" in lowered or "spritesheet" in lowered or "sheet" in lowered:
            return True

    if dimensions is None:
        return False

    width, height = dimensions
    if width <= 0 or height <= 0:
        return False

    long_side = max(width, height)
    short_side = min(width, height)

    # Heuristic: unusually long aspect or large grid-like canvases are likely sheets.
    if short_side > 0 and (long_side / short_side) >= 4.0 and long_side >= 256:
        return True

    common_cell_sizes = (8, 16, 24, 32, 48, 64)
    if width >= 128 and height >= 128:
        divisible_pairs = sum(
            1 for size in common_cell_sizes if width % size == 0 and height % size == 0
        )
        if divisible_pairs >= 2:
            return True

    return False

