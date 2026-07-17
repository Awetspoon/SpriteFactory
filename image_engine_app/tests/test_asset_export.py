"""Tests for the shared asset export plan used by interactive and Batch output."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from image_engine_app.engine.export.asset_export import (
    AssetExportOptions,
    build_asset_export_plan,
    export_asset,
)
from image_engine_app.engine.export.format_resolver import (
    extension_for_export_format,
    resolve_export_format,
)
from image_engine_app.engine.models import (
    AssetFormat,
    AssetRecord,
    Capabilities,
    ExportFormat,
    ExportProfile,
    ExportSettings,
    SourceType,
)


def _asset(source: Path, *, has_alpha: bool = True) -> AssetRecord:
    return AssetRecord(
        id="asset-shared-export",
        source_type=SourceType.FILE,
        source_uri=str(source),
        cache_path=str(source),
        original_name=source.name,
        format=AssetFormat.PNG,
        capabilities=Capabilities(
            has_alpha=has_alpha,
            is_animated=False,
            is_sheet=False,
            is_ico_bundle=False,
        ),
        dimensions_original=(10, 8),
        dimensions_current=(10, 8),
        dimensions_final=(10, 8),
    )


class ExportFormatResolverTests(unittest.TestCase):
    def test_auto_uses_animation_then_profile_defaults(self) -> None:
        web = ExportSettings(export_profile=ExportProfile.WEB, format=ExportFormat.AUTO)
        app = ExportSettings(export_profile=ExportProfile.APP_ASSET, format=ExportFormat.AUTO)
        print_settings = ExportSettings(export_profile=ExportProfile.PRINT, format=ExportFormat.AUTO)

        self.assertEqual(
            ExportFormat.GIF,
            resolve_export_format(web, has_alpha=True, is_animated=True, frame_count=8),
        )
        self.assertEqual(
            ExportFormat.WEBP,
            resolve_export_format(web, has_alpha=True),
        )
        self.assertEqual(
            ExportFormat.PNG,
            resolve_export_format(app, has_alpha=True),
        )
        self.assertEqual(
            ExportFormat.TIFF,
            resolve_export_format(print_settings, has_alpha=False),
        )

    def test_extension_mapping_has_one_canonical_result(self) -> None:
        self.assertEqual(".jpg", extension_for_export_format(ExportFormat.JPG))
        self.assertEqual(".tiff", extension_for_export_format("tiff"))
        self.assertEqual(".bin", extension_for_export_format("unknown"))


class AssetExportPlanTests(unittest.TestCase):
    def test_plan_format_prediction_and_extension_always_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "sprite.png"
            source.write_bytes(b"not-needed-for-planning")
            asset = _asset(source)
            asset.edit_state.settings.export.export_profile = ExportProfile.WEB
            asset.edit_state.settings.export.format = ExportFormat.AUTO

            plan = build_asset_export_plan(
                asset,
                AssetExportOptions(export_dir=root / "exports"),
            )

            self.assertEqual(ExportFormat.WEBP, plan.resolved_format)
            self.assertEqual("webp", plan.prediction.prediction.predicted_format)
            self.assertEqual(".webp", plan.output_path.suffix)
            self.assertEqual(ExportFormat.WEBP, plan.request.export_settings.format)

    def test_group_and_name_template_are_resolved_in_the_shared_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "enemy sprite.png"
            source.write_bytes(b"fixture")
            asset = _asset(source)
            asset.edit_state.settings.export.export_profile = ExportProfile.APP_ASSET

            plan = build_asset_export_plan(
                asset,
                AssetExportOptions(
                    export_dir=root / "exports",
                    group_outputs=True,
                    name_template="{group}_{index:03d}_{stem}",
                    index=7,
                ),
            )

            self.assertEqual("png", plan.output_group)
            self.assertEqual("png_007_enemy_sprite.png", plan.output_path.name)
            self.assertEqual("png", plan.output_path.parent.name)

    def test_real_export_uses_the_same_resized_dimensions_as_prediction(self) -> None:
        try:
            from PIL import Image
        except Exception:
            self.skipTest("Pillow required for real shared export test")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "sprite.png"
            Image.new("RGBA", (10, 8), (40, 120, 210, 255)).save(source, format="PNG")
            asset = _asset(source)
            asset.edit_state.settings.export.export_profile = ExportProfile.APP_ASSET
            asset.edit_state.settings.export.format = ExportFormat.AUTO
            asset.edit_state.settings.pixel.resize_percent = 200.0
            asset.edit_state.settings.ai.upscale_factor = 2.0

            outcome = export_asset(
                asset,
                AssetExportOptions(export_dir=root / "exports"),
            )

            self.assertTrue(outcome.result.success)
            self.assertEqual((40, 32), (outcome.plan.request.width, outcome.plan.request.height))
            self.assertEqual("png", outcome.plan.prediction.prediction.predicted_format)
            self.assertEqual(ExportFormat.PNG, outcome.result.format)
            with Image.open(outcome.result.output_path) as exported:
                self.assertEqual((40, 32), exported.size)


if __name__ == "__main__":
    unittest.main()
