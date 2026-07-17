"""Tests for the one edit-state and Final-preview application workflow."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from image_engine_app.app.services import AssetEditService
from image_engine_app.engine.models import AssetFormat, AssetRecord, ExportProfile
from image_engine_app.engine.process.edit_baseline import capture_detected_settings
from image_engine_app.engine.process.edit_impact import EditImpact, has_visible_settings_changes, setting_impact


def _source_asset(root: Path) -> AssetRecord:
    source = root / "source.png"
    Image.new("RGBA", (12, 8), (50, 100, 200, 255)).save(source, format="PNG")
    asset = AssetRecord(
        id="edit-service-asset",
        original_name="source.png",
        source_uri=str(source),
        cache_path=str(source),
        format=AssetFormat.PNG,
        dimensions_original=(12, 8),
        dimensions_current=(12, 8),
        dimensions_final=(12, 8),
    )
    capture_detected_settings(asset)
    return asset


class AssetEditServiceTests(unittest.TestCase):
    def test_visible_control_rebuilds_final_without_replacing_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            asset = _source_asset(root)
            service = AssetEditService(derived_cache_dir=root / "cache")

            result = service.update_setting(asset, "color", "brightness", 0.25)

            self.assertTrue(result.changed)
            self.assertEqual(EditImpact.PREVIEW, result.impact)
            self.assertTrue(result.preview_rendered)
            self.assertEqual(str(root / "source.png"), asset.cache_path)
            self.assertTrue(Path(asset.derived_final_path).exists())
            self.assertNotEqual(Path(asset.cache_path), Path(asset.derived_final_path))

    def test_visible_control_can_defer_final_render_for_responsive_ui(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            asset = _source_asset(root)
            service = AssetEditService(derived_cache_dir=root / "cache")
            service.update_setting(asset, "color", "brightness", 0.1)
            self.assertIsNotNone(asset.derived_final_path)

            result = service.update_setting(
                asset,
                "detail",
                "sharpen_amount",
                0.8,
                refresh_final=False,
            )

            self.assertTrue(result.changed)
            self.assertEqual(EditImpact.PREVIEW, result.impact)
            self.assertFalse(result.preview_attempted)
            self.assertIsNone(asset.derived_final_path)
            self.assertAlmostEqual(0.8, asset.edit_state.settings.detail.sharpen_amount)

    def test_dpi_is_export_only_and_keeps_existing_final(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            asset = _source_asset(root)
            service = AssetEditService(derived_cache_dir=root / "cache")
            initial = service.update_setting(asset, "color", "brightness", 0.1)
            final_path = asset.derived_final_path

            result = service.update_setting(asset, "pixel", "dpi", 300)

            self.assertTrue(initial.preview_rendered)
            self.assertEqual(EditImpact.EXPORT_ONLY, result.impact)
            self.assertFalse(result.preview_attempted)
            self.assertEqual(final_path, asset.derived_final_path)
            self.assertEqual(300, asset.edit_state.settings.pixel.dpi)

    def test_export_profile_changes_encoding_without_rebuilding_final(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            asset = _source_asset(root)
            service = AssetEditService(derived_cache_dir=root / "cache")
            service.refresh_final(asset)
            final_path = asset.derived_final_path

            result = service.set_export_profile(asset, ExportProfile.PRINT)

            self.assertTrue(result.changed)
            self.assertEqual(EditImpact.EXPORT_ONLY, result.impact)
            self.assertFalse(result.preview_attempted)
            self.assertEqual(final_path, asset.derived_final_path)
            self.assertEqual(ExportProfile.PRINT, asset.edit_state.settings.export.export_profile)

    def test_background_mode_keeps_legacy_alias_consistent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            asset = _source_asset(root)
            service = AssetEditService(derived_cache_dir=root / "cache")

            service.update_setting(asset, "alpha", "background_removal_mode", "white")
            self.assertEqual("white", asset.edit_state.settings.alpha.background_removal_mode)
            self.assertTrue(asset.edit_state.settings.alpha.remove_white_bg)

            service.update_setting(asset, "alpha", "background_removal_mode", "off")
            self.assertEqual("off", asset.edit_state.settings.alpha.background_removal_mode)
            self.assertFalse(asset.edit_state.settings.alpha.remove_white_bg)

    def test_reset_restores_source_controls_and_reuses_the_exact_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            asset = _source_asset(root)
            service = AssetEditService(derived_cache_dir=root / "cache")
            service.update_setting(asset, "color", "contrast", 0.4)

            result = service.reset_to_detected(asset)

            self.assertTrue(result.changed)
            self.assertFalse(result.preview_attempted)
            self.assertEqual(0.0, asset.edit_state.settings.color.contrast)
            self.assertIsNone(asset.derived_final_path)
            self.assertEqual((12, 8), asset.dimensions_final)

    def test_reset_selected_control_preserves_other_edits(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            asset = _source_asset(root)
            service = AssetEditService(derived_cache_dir=root / "cache")
            service.update_setting(asset, "color", "brightness", 0.3, refresh_final=False)
            service.update_setting(asset, "color", "contrast", 0.4, refresh_final=False)

            result = service.reset_settings_to_detected(
                asset,
                (("color", "brightness"),),
                refresh_final=False,
            )

            self.assertTrue(result.changed)
            self.assertEqual(EditImpact.PREVIEW, result.impact)
            self.assertEqual(0.0, asset.edit_state.settings.color.brightness)
            self.assertEqual(0.4, asset.edit_state.settings.color.contrast)

    def test_ensure_final_uses_source_until_an_edit_requires_a_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            asset = _source_asset(root)
            service = AssetEditService(derived_cache_dir=root / "cache")

            initial = service.ensure_final(asset)
            self.assertFalse(initial.preview_attempted)
            self.assertIsNone(asset.derived_final_path)

            service.update_setting(
                asset,
                "color",
                "brightness",
                0.2,
                refresh_final=False,
            )
            self.assertTrue(service.ensure_final(asset).preview_rendered)
            final_path = asset.derived_final_path

            result = service.ensure_final(asset)

            self.assertFalse(result.preview_attempted)
            self.assertEqual(final_path, asset.derived_final_path)

    def test_replace_edit_state_can_skip_final_for_batch_preparation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            asset = _source_asset(root)
            service = AssetEditService(derived_cache_dir=root / "cache")
            replacement = deepcopy(asset.edit_state)
            replacement.settings.detail.clarity = 0.2

            result = service.replace_edit_state(asset, replacement, refresh_final=False)

            self.assertTrue(result.changed)
            self.assertFalse(result.preview_attempted)
            self.assertIsNone(asset.derived_final_path)
            self.assertAlmostEqual(0.2, asset.edit_state.settings.detail.clarity)

    def test_visible_change_rules_are_shared_and_validate_fields(self) -> None:
        asset = AssetRecord()
        self.assertEqual(EditImpact.EXPORT_ONLY, setting_impact("pixel", "dpi"))
        self.assertEqual(EditImpact.PREVIEW, setting_impact("gif", "frame_delay_ms"))
        self.assertFalse(has_visible_settings_changes(asset.edit_state.settings))
        asset.edit_state.settings.export.quality = 30
        self.assertFalse(has_visible_settings_changes(asset.edit_state.settings))
        asset.edit_state.settings.color.gamma = 1.2
        self.assertTrue(has_visible_settings_changes(asset.edit_state.settings))
        with self.assertRaises(ValueError):
            setting_impact("pixel", "not_real")


if __name__ == "__main__":
    unittest.main()
