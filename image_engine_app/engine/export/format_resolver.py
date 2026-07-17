"""Single format and extension resolver for every export workflow."""

from __future__ import annotations

from image_engine_app.engine.export.profiles import get_profile_rule
from image_engine_app.engine.models import ExportFormat, ExportSettings


_FORMAT_EXTENSIONS: dict[ExportFormat, str] = {
    ExportFormat.JPG: ".jpg",
    ExportFormat.PNG: ".png",
    ExportFormat.WEBP: ".webp",
    ExportFormat.GIF: ".gif",
    ExportFormat.ICO: ".ico",
    ExportFormat.TIFF: ".tiff",
    ExportFormat.BMP: ".bmp",
}


def resolve_export_format(
    export_settings: ExportSettings,
    *,
    has_alpha: bool,
    is_animated: bool = False,
    frame_count: int = 1,
) -> ExportFormat:
    """Resolve AUTO using animation first, then the selected profile."""

    selected = export_settings.format
    if selected is not ExportFormat.AUTO:
        return selected
    if is_animated or int(frame_count or 1) > 1:
        return ExportFormat.GIF
    return get_profile_rule(export_settings.export_profile).default_format


def extension_for_export_format(value: ExportFormat | str) -> str:
    """Return the canonical filename extension for a resolved format."""

    try:
        file_format = value if isinstance(value, ExportFormat) else ExportFormat(str(value).lower())
    except (TypeError, ValueError):
        return ".bin"
    return _FORMAT_EXTENSIONS.get(file_format, ".bin")
