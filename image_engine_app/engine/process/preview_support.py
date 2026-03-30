"""Shared light-preview and export-source helpers for asset workflows."""

from __future__ import annotations

from dataclasses import dataclass
import shutil
from pathlib import Path

from image_engine_app.engine.models import ApplyTarget, AssetFormat, ExportFormat, SettingsState
from image_engine_app.engine.process.light_steps import LightProcessError, LightStepUnavailable, apply_light_processing


@dataclass(frozen=True)
class ExportSourceResolution:
    """Resolved export source plus whether light settings still need to be applied."""

    source_path: str | None
    light_settings: SettingsState | None = None
    uses_derived_preview: bool = False


def preview_extension_for_asset(asset: object) -> str:
    """Return the preferred preview file extension for the asset."""

    asset_format = getattr(asset, "format", None)
    capabilities = getattr(asset, "capabilities", None)
    is_animated = bool(getattr(capabilities, "is_animated", False))
    return ".gif" if (asset_format is AssetFormat.GIF and is_animated) else ".png"


def render_light_pipeline_preview(
    asset: object,
    *,
    derived_cache_dir: str | Path | None,
    final_only: bool = False,
) -> bool:
    """Render the light pipeline into derived preview files for an asset."""

    if derived_cache_dir is None:
        return False

    source = _resolve_local_light_source(asset)
    if source is None:
        return False

    try:
        base_dir = Path(derived_cache_dir)
    except Exception:
        return False

    derived_dir = base_dir / "derived" / str(getattr(asset, "id", "asset"))
    current_out = derived_dir / f"current{preview_extension_for_asset(asset)}"
    final_out = derived_dir / f"final{preview_extension_for_asset(asset)}"

    edit_state = getattr(asset, "edit_state", None)
    settings = getattr(edit_state, "settings", None)
    target = getattr(edit_state, "apply_target", ApplyTarget.BOTH)
    target_value = getattr(target, "value", ApplyTarget.BOTH.value)
    sync_enabled = bool(getattr(edit_state, "sync_current_final", True))

    try:
        if final_only:
            result = apply_light_processing(source_path=source, output_path=final_out, settings=settings)
            setattr(asset, "derived_final_path", str(result.output_path))
            setattr(asset, "dimensions_final", result.size)
            return True

        if sync_enabled or target_value == ApplyTarget.BOTH.value:
            result = apply_light_processing(source_path=source, output_path=final_out, settings=settings)
            setattr(asset, "derived_final_path", str(result.output_path))

            current_out.parent.mkdir(parents=True, exist_ok=True)
            mirrored_current = final_out
            if final_out.exists():
                try:
                    shutil.copy2(final_out, current_out)
                    mirrored_current = current_out
                except Exception:
                    mirrored_current = final_out

            setattr(asset, "derived_current_path", str(mirrored_current))
            setattr(asset, "dimensions_current", result.size)
            setattr(asset, "dimensions_final", result.size)
            return True

        if target_value == ApplyTarget.FINAL.value:
            result = apply_light_processing(source_path=source, output_path=final_out, settings=settings)
            setattr(asset, "derived_final_path", str(result.output_path))
            setattr(asset, "dimensions_final", result.size)
            return True

        result = apply_light_processing(source_path=source, output_path=current_out, settings=settings)
        setattr(asset, "derived_current_path", str(result.output_path))
        setattr(asset, "dimensions_current", result.size)
        return True

    except LightStepUnavailable:
        return False
    except LightProcessError:
        raise
    except Exception as exc:
        raise LightProcessError(str(exc)) from exc


def select_export_source_path(asset: object) -> str | None:
    """Choose the best available source path for export."""

    derived = getattr(asset, "derived_final_path", None)
    derived_current = getattr(asset, "derived_current_path", None)
    cache = getattr(asset, "cache_path", None)
    source_uri = getattr(asset, "source_uri", None)

    export_settings = getattr(getattr(getattr(asset, "edit_state", None), "settings", None), "export", None)
    export_format = getattr(export_settings, "format", None)
    capabilities = getattr(asset, "capabilities", None)
    is_animated = bool(getattr(capabilities, "is_animated", False))

    if export_format in {ExportFormat.GIF, ExportFormat.AUTO} and is_animated:
        return _first_non_empty(cache, source_uri, derived, derived_current)

    return _first_non_empty(derived, derived_current, cache, source_uri)


def resolve_export_source(asset: object) -> ExportSourceResolution:
    """Resolve the best export source and whether raw-source export still needs light settings."""

    source_path = select_export_source_path(asset)
    if source_path is None:
        return ExportSourceResolution(source_path=None, light_settings=None, uses_derived_preview=False)

    if _matches_any_path(
        source_path,
        getattr(asset, "derived_final_path", None),
        getattr(asset, "derived_current_path", None),
    ):
        return ExportSourceResolution(source_path=source_path, light_settings=None, uses_derived_preview=True)

    if _asset_has_light_edits(asset):
        settings = getattr(getattr(asset, "edit_state", None), "settings", None)
        if isinstance(settings, SettingsState):
            return ExportSourceResolution(source_path=source_path, light_settings=settings, uses_derived_preview=False)

    return ExportSourceResolution(source_path=source_path, light_settings=None, uses_derived_preview=False)


def _resolve_local_light_source(asset: object) -> str | None:
    for candidate in (getattr(asset, "cache_path", None), getattr(asset, "source_uri", None)):
        if not isinstance(candidate, str) or not candidate.strip():
            continue
        try:
            path = Path(candidate)
        except Exception:
            continue
        if path.exists() and path.is_file():
            return str(path)
    return None


def _first_non_empty(*values: object) -> str | None:
    for value in values:
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, str) and value:
            return value
    return None


def _asset_has_light_edits(asset: object) -> bool:
    settings = getattr(getattr(asset, "edit_state", None), "settings", None)
    if not isinstance(settings, SettingsState):
        return False

    defaults = SettingsState()
    return any(
        section != default_section
        for section, default_section in (
            (settings.pixel, defaults.pixel),
            (settings.color, defaults.color),
            (settings.detail, defaults.detail),
            (settings.cleanup, defaults.cleanup),
            (settings.edges, defaults.edges),
            (settings.alpha, defaults.alpha),
            (settings.ai, defaults.ai),
        )
    )


def _matches_any_path(value: str, *candidates: object) -> bool:
    normalized = _normalize_pathish(value)
    if normalized is None:
        return False
    for candidate in candidates:
        candidate_normalized = _normalize_pathish(candidate)
        if candidate_normalized is not None and candidate_normalized == normalized:
            return True
    return False


def _normalize_pathish(value: object) -> str | None:
    if isinstance(value, Path):
        raw = str(value)
    elif isinstance(value, str):
        raw = value
    else:
        return None

    cleaned = raw.strip()
    if not cleaned:
        return None
    return cleaned.replace("\\", "/").lower()
