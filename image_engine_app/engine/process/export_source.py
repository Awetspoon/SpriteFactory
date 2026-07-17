"""Resolve whether export should use a derived preview or process the source."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from image_engine_app.engine.models import ExportFormat, SettingsState
from image_engine_app.engine.process.edit_impact import has_visible_settings_changes


@dataclass(frozen=True)
class ExportSourceResolution:
    """Resolved export path and any edits that still need to be rendered."""

    source_path: str | None
    processing_settings: SettingsState | None = None
    uses_derived_preview: bool = False


def select_export_source_path(asset: object) -> str | None:
    """Choose the best available local or source path for export."""

    derived_final = getattr(asset, "derived_final_path", None)
    cache = getattr(asset, "cache_path", None)
    source_uri = getattr(asset, "source_uri", None)
    export_settings = getattr(getattr(getattr(asset, "edit_state", None), "settings", None), "export", None)
    export_format = getattr(export_settings, "format", None)
    is_animated = bool(getattr(getattr(asset, "capabilities", None), "is_animated", False))

    # Animated exports use the source container so every frame remains available.
    if export_format in {ExportFormat.GIF, ExportFormat.AUTO} and is_animated:
        return _first_available_path(cache, source_uri, derived_final)
    return _first_available_path(derived_final, cache, source_uri)


def resolve_export_source(asset: object) -> ExportSourceResolution:
    """Resolve a path and whether source pixels still need the current edits."""

    source_path = select_export_source_path(asset)
    if source_path is None:
        return ExportSourceResolution(source_path=None)

    if _matches_any_path(
        source_path,
        getattr(asset, "derived_final_path", None),
    ):
        return ExportSourceResolution(source_path=source_path, uses_derived_preview=True)

    if _asset_has_visible_edits(asset):
        settings = getattr(getattr(asset, "edit_state", None), "settings", None)
        if isinstance(settings, SettingsState):
            return ExportSourceResolution(
                source_path=source_path,
                processing_settings=settings,
            )
    return ExportSourceResolution(source_path=source_path)


def _first_available_path(*values: object) -> str | None:
    candidates: list[str] = []
    for value in values:
        if isinstance(value, Path):
            raw = str(value).strip()
        elif isinstance(value, str):
            raw = value.strip()
        else:
            continue
        if raw:
            candidates.append(raw)

    for candidate in candidates:
        try:
            path = Path(candidate)
        except (OSError, ValueError):
            continue
        if path.exists() and path.is_file():
            return candidate
    return candidates[0] if candidates else None


def _asset_has_visible_edits(asset: object) -> bool:
    settings = getattr(getattr(asset, "edit_state", None), "settings", None)
    if not isinstance(settings, SettingsState):
        return False

    return has_visible_settings_changes(settings)


def _matches_any_path(value: str, *candidates: object) -> bool:
    normalized = _normalize_path(value)
    if normalized is None:
        return False
    return any(
        candidate_path == normalized
        for candidate in candidates
        if (candidate_path := _normalize_path(candidate)) is not None
    )


def _normalize_path(value: object) -> str | None:
    if isinstance(value, Path):
        raw = str(value)
    elif isinstance(value, str):
        raw = value
    else:
        return None
    cleaned = raw.strip()
    return cleaned.replace("\\", "/").lower() if cleaned else None
