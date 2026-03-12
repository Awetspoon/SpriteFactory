"""Tests for export profile rules, stub exporters, and live size prediction."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.export.exporters import ExportRequest, export_image_stub  # noqa: E402
from engine.export.profiles import apply_profile_defaults, get_profile_rule, profile_comparison_formats  # noqa: E402
from engine.export.size_predictor import ExportPredictorInput, predict_export_size  # noqa: E402
from engine.models import ExportFormat, ExportProfile, ExportSettings  # noqa: E402


class ExportProfileTests(unittest.TestCase):
    def test_profile_rules_expose_defaults_and_comparison_formats(self) -> None:
        web_rule = get_profile_rule(ExportProfile.WEB)
        self.assertEqual(web_rule.default_format, ExportFormat.WEBP)
        self.assertEqual(web_rule.default_quality, 82)
        self.assertIn(ExportFormat.PNG, profile_comparison_formats(ExportProfile.WEB))

        settings = ExportSettings(
            export_profile=ExportProfile.WEB,
            format=ExportFormat.AUTO,
            quality=0,
            compression_level=-1,
            strip_metadata=False,
        )
        updated = apply_profile_defaults(settings)
        self.assertEqual(updated.format, ExportFormat.WEBP)
        self.assertEqual(updated.quality, 82)
        self.assertEqual(updated.compression_level, 6)
        self.assertTrue(updated.strip_metadata)


class ExportPredictorTests(unittest.TestCase):
    def test_predictor_auto_web_profile_generates_comparison_and_threshold_warning(self) -> None:
        settings = ExportSettings(
            export_profile=ExportProfile.WEB,
            format=ExportFormat.AUTO,
            quality=85,
            compression_level=6,
        )
        result = predict_export_size(
            ExportPredictorInput(
                width=1920,
                height=1080,
                export_settings=settings,
                has_alpha=False,
                is_animated=False,
                complexity=0.7,
                threshold_bytes=120_000,
            )
        )

        self.assertEqual(result.prediction.predicted_format, "webp")
        self.assertGreater(result.prediction.predicted_bytes, 0)
        self.assertTrue(0.0 <= result.prediction.confidence <= 1.0)
        comparison_formats = {entry.format for entry in result.prediction.comparison}
        self.assertTrue({"jpg", "webp", "png"}.issubset(comparison_formats))
        self.assertGreaterEqual(len(result.warnings), 1)
        self.assertIn("exceeds threshold", result.warnings[0])
        self.assertIn(result.compression_efficiency_rating, {"excellent", "good", "fair", "poor"})

    def test_predictor_alpha_prefers_png_for_app_asset_auto(self) -> None:
        settings = ExportSettings(
            export_profile=ExportProfile.APP_ASSET,
            format=ExportFormat.AUTO,
            quality=100,
            compression_level=4,
        )
        result = predict_export_size(
            ExportPredictorInput(
                width=512,
                height=512,
                export_settings=settings,
                has_alpha=True,
                complexity=0.3,
            )
        )
        self.assertEqual(result.prediction.predicted_format, "png")
        self.assertFalse(any("alpha transparency" in warning for warning in result.warnings))

    def test_predictor_warns_when_jpeg_selected_with_alpha(self) -> None:
        settings = ExportSettings(
            export_profile=ExportProfile.WEB,
            format=ExportFormat.JPG,
            quality=75,
            compression_level=6,
        )
        result = predict_export_size(
            ExportPredictorInput(
                width=256,
                height=256,
                export_settings=settings,
                has_alpha=True,
                complexity=0.4,
                threshold_bytes=100,
            )
        )

        self.assertEqual(result.prediction.predicted_format, "jpg")
        self.assertTrue(any("alpha transparency" in warning for warning in result.warnings))
        self.assertTrue(any("exceeds threshold" in warning for warning in result.warnings))


class ExporterStubTests(unittest.TestCase):
    def test_exporter_stub_writes_placeholder_file(self) -> None:
        settings = ExportSettings(
            export_profile=ExportProfile.APP_ASSET,
            format=ExportFormat.PNG,
            quality=100,
            compression_level=4,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = Path(temp_dir) / "sprite.png"
            result = export_image_stub(
                ExportRequest(
                    output_path=out_path,
                    width=128,
                    height=128,
                    export_settings=settings,
                    asset_id="asset-001",
                    frame_count=1,
                    has_alpha=True,
                )
            )

            self.assertTrue(result.success)
            self.assertEqual(result.format, ExportFormat.PNG)
            self.assertTrue(out_path.exists())
            self.assertGreater(result.bytes_written, 0)

            payload = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertTrue(payload["stub_export"])
            self.assertEqual(payload["format"], "png")
            self.assertEqual(payload["asset_id"], "asset-001")
            self.assertEqual(payload["width"], 128)
            self.assertTrue(payload["has_alpha"])


if __name__ == "__main__":
    unittest.main()

