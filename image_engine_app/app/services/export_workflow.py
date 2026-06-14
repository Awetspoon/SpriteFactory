"""Export prediction and execution helpers for asset workflows."""

from __future__ import annotations

from pathlib import Path

from image_engine_app.app.paths import AppPaths
from image_engine_app.app.services.asset_profile_service import AssetProfileService
from image_engine_app.engine.export.exporters import ExportRequest, ExportResult, export_image
from image_engine_app.engine.export.naming import ensure_unique_path, safe_stem as export_safe_stem
from image_engine_app.engine.export.size_predictor import (
    ExportPredictorInput,
    ExportPredictorResult,
    predict_export_size,
)
from image_engine_app.engine.process.preview_support import resolve_export_source


def predict_asset_export(asset: object) -> ExportPredictorResult:
    """Compute live export size prediction for an asset."""

    width, height = _asset_dimensions(asset)
    edit_state = getattr(asset, "edit_state", None)
    settings = getattr(edit_state, "settings", None)
    export_settings = getattr(settings, "export", None)
    capabilities = getattr(asset, "capabilities", None)
    has_alpha = bool(getattr(capabilities, "has_alpha", False))
    is_animated = bool(getattr(capabilities, "is_animated", False))

    return predict_export_size(
        ExportPredictorInput(
            width=width,
            height=height,
            export_settings=export_settings,
            has_alpha=has_alpha,
            is_animated=is_animated,
            frame_count=8 if is_animated else 1,
            complexity=0.5,
        )
    )


def format_asset_export_prediction(asset: object) -> str:
    """Return the UI label text for the current live export prediction."""

    predictor = predict_asset_export(asset)
    pred = predictor.prediction
    return f"{pred.predicted_format.upper()} {pred.predicted_bytes:,}B"


def export_asset(
    asset: object,
    *,
    app_paths: AppPaths | None = None,
    export_dir: str | Path | None = None,
) -> ExportResult:
    """Export an asset into the configured exports directory."""

    target_dir = Path(export_dir or (app_paths.exports if app_paths is not None else "."))
    target_dir.mkdir(parents=True, exist_ok=True)

    prediction = predict_asset_export(asset)
    fmt_str = prediction.prediction.predicted_format
    ext = AssetProfileService.extension_for_format(fmt_str)
    stem = export_safe_stem(getattr(asset, "original_name", None) or getattr(asset, "id", "asset"))
    output_path = ensure_unique_path(target_dir / f"{stem}{ext}", overwrite_existing=False)
    export_source = resolve_export_source(asset)

    width, height = _asset_dimensions(asset)
    edit_state = getattr(asset, "edit_state", None)
    settings = getattr(edit_state, "settings", None)
    export_settings = getattr(settings, "export", None)
    capabilities = getattr(asset, "capabilities", None)
    has_alpha = bool(getattr(capabilities, "has_alpha", False))
    is_animated = bool(getattr(capabilities, "is_animated", False))
    asset_id = str(getattr(asset, "id", "asset"))

    return export_image(
        ExportRequest(
            output_path=output_path,
            source_path=export_source.source_path,
            width=width,
            height=height,
            export_settings=export_settings,
            asset_id=asset_id,
            frame_count=8 if is_animated else 1,
            has_alpha=has_alpha,
            light_settings=export_source.light_settings,
        )
    )


def _asset_dimensions(asset: object) -> tuple[int, int]:
    width, height = (
        getattr(asset, "dimensions_final", None)
        or getattr(asset, "dimensions_current", None)
        or getattr(asset, "dimensions_original", None)
        or (1, 1)
    )
    return max(1, int(width)), max(1, int(height))
