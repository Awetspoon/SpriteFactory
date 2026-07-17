"""Application-facing wrappers around the shared asset export engine."""

from __future__ import annotations

from pathlib import Path

from image_engine_app.app.paths import AppPaths
from image_engine_app.engine.export.asset_export import (
    AssetExportOptions,
    export_asset as run_asset_export,
    predict_asset_export as predict_with_engine,
)
from image_engine_app.engine.export.exporters import ExportResult
from image_engine_app.engine.export.size_predictor import ExportPredictorResult


def predict_asset_export(asset: object) -> ExportPredictorResult:
    """Compute the live prediction from the same plan used for real export."""

    return predict_with_engine(asset)


def format_asset_export_prediction(asset: object) -> str:
    """Return the compact export prediction shown in the main output bar."""

    prediction = predict_asset_export(asset).prediction
    return f"{prediction.predicted_format.upper()} {prediction.predicted_bytes:,}B"


def export_asset(
    asset: object,
    *,
    app_paths: AppPaths | None = None,
    export_dir: str | Path | None = None,
) -> ExportResult:
    """Export one interactive asset using the shared engine workflow."""

    target_dir = Path(export_dir or (app_paths.exports if app_paths is not None else "."))
    outcome = run_asset_export(
        asset,
        AssetExportOptions(
            export_dir=target_dir,
            name_template="{stem}",
            group_outputs=False,
            overwrite_existing=False,
        ),
    )
    return outcome.result
