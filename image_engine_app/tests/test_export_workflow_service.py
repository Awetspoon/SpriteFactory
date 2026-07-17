"""Tests for extracted export prediction and execution helpers."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from image_engine_app.app.paths import ensure_app_paths
from image_engine_app.app.services import export_asset, format_asset_export_prediction, predict_asset_export
from image_engine_app.engine.models import (
    AssetFormat,
    AssetRecord,
    Capabilities,
    EditMode,
    ExportProfile,
    SourceType,
)


def _asset(*, mode: EditMode = EditMode.ADVANCED) -> AssetRecord:
    asset = AssetRecord(
        id="asset-export-001",
        source_type=SourceType.FILE,
        source_uri="C:/demo/sprite.png",
        original_name="sprite.png",
        format=AssetFormat.PNG,
        capabilities=Capabilities(has_alpha=True, is_animated=False, is_sheet=False, is_ico_bundle=False),
        dimensions_original=(64, 64),
        dimensions_current=(128, 128),
        dimensions_final=(256, 256),
    )
    asset.edit_state.mode = mode
    asset.edit_state.settings.export.export_profile = ExportProfile.APP_ASSET
    return asset


class ExportWorkflowServiceTests(unittest.TestCase):
    def test_prediction_text_matches_predicted_format(self) -> None:
        asset = _asset(mode=EditMode.ADVANCED)

        prediction = predict_asset_export(asset)
        label = format_asset_export_prediction(asset)

        self.assertGreater(prediction.prediction.predicted_bytes, 0)
        self.assertIn(prediction.prediction.predicted_format.upper(), label)

    def test_export_asset_uses_requested_output_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            output_dir = Path(temp_dir) / "manual-export"
            asset = _asset(mode=EditMode.ADVANCED)

            result = export_asset(asset, app_paths=paths, export_dir=output_dir)

            self.assertTrue(result.success)
            self.assertTrue(result.output_path.exists())
            self.assertEqual(result.output_path.parent, output_dir)
            self.assertTrue(result.is_stub)
