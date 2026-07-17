"""Derived Final-preview rendering for an asset."""

from __future__ import annotations

from pathlib import Path

from image_engine_app.engine.models import AssetFormat, SettingsState
from image_engine_app.engine.process.errors import ProcessingError, ProcessingUnavailable
from image_engine_app.engine.process.source_renderer import render_source_preview


def preview_extension_for_asset(asset: object) -> str:
    """Return the preview container required by a static or animated asset."""

    asset_format = getattr(asset, "format", None)
    capabilities = getattr(asset, "capabilities", None)
    is_animated = bool(getattr(capabilities, "is_animated", False))
    return ".gif" if asset_format is AssetFormat.GIF and is_animated else ".png"


def render_asset_preview(
    asset: object,
    *,
    derived_cache_dir: str | Path | None,
    output_stem: str = "final",
) -> bool:
    """Render the asset's current edit settings into its derived Final preview."""

    if derived_cache_dir is None:
        return False
    source = _resolve_local_source(asset)
    if source is None:
        return False

    settings = getattr(getattr(asset, "edit_state", None), "settings", None)
    if not isinstance(settings, SettingsState):
        return False

    try:
        derived_dir = Path(derived_cache_dir) / "derived" / str(getattr(asset, "id", "asset"))
        output = derived_dir / f"{_safe_output_stem(output_stem)}{preview_extension_for_asset(asset)}"
        result = render_source_preview(source_path=source, output_path=output, settings=settings)
        setattr(asset, "derived_final_path", str(result.output_path))
        setattr(asset, "dimensions_final", result.logical_size)
        return True
    except ProcessingUnavailable:
        return False
    except ProcessingError:
        raise
    except Exception as exc:
        raise ProcessingError(str(exc)) from exc


def _safe_output_stem(raw_value: object) -> str:
    """Keep internal preview variants inside the asset's derived directory."""

    value = str(raw_value or "final").strip()
    safe = "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in value)
    return safe or "final"


def _resolve_local_source(asset: object) -> str | None:
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
