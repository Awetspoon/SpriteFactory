"""Tests for source-faithful imported-asset profile hydration."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from PIL import Image

from image_engine_app.app.services import AssetProfileService
from image_engine_app.engine.models import (
    AssetFormat,
    AssetRecord,
    ExportFormat,
    ExportProfile,
    ScaleMethod,
    SourceType,
)


def _asset(path: Path, *, file_format: AssetFormat) -> AssetRecord:
    asset = AssetRecord(
        id=f"profile-{file_format.value}",
        source_type=SourceType.FILE,
        source_uri=str(path),
        cache_path=str(path),
        original_name=path.name,
        format=file_format,
    )
    asset.edit_state.settings.cleanup.denoise = 0.8
    asset.edit_state.settings.detail.sharpen_amount = 0.7
    asset.edit_state.settings.ai.upscale_factor = 4.0
    asset.edit_state.settings.export.export_profile = ExportProfile.APP_ASSET
    asset.edit_state.settings.export.format = ExportFormat.PNG
    return asset


class AssetProfileServiceTests(unittest.TestCase):
    def test_static_source_metadata_is_loaded_without_starting_enhancements(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sprite.png"
            Image.new("RGBA", (64, 40), (20, 80, 180, 120)).save(
                source,
                format="PNG",
                dpi=(144, 144),
            )
            asset = _asset(source, file_format=AssetFormat.PNG)

            AssetProfileService().hydrate_imported_asset(asset)

            self.assertEqual((64, 40), asset.dimensions_original)
            self.assertEqual((64, 40), asset.dimensions_current)
            self.assertEqual((64, 40), asset.dimensions_final)
            self.assertTrue(asset.capabilities.has_alpha)
            self.assertFalse(asset.capabilities.is_animated)
            self.assertEqual("RGBA", asset.source_metadata.color_mode)
            self.assertEqual(144, asset.source_metadata.dpi)
            self.assertEqual(1, asset.source_metadata.frame_count)
            self.assertIsNone(asset.source_metadata.loop_count)
            self.assertEqual(144, asset.edit_state.settings.pixel.dpi)
            self.assertEqual(ScaleMethod.LANCZOS, asset.edit_state.settings.pixel.scale_method)
            self.assertFalse(asset.edit_state.settings.pixel.pixel_snap)
            self.assertEqual(0.0, asset.edit_state.settings.cleanup.denoise)
            self.assertEqual(0.0, asset.edit_state.settings.detail.sharpen_amount)
            self.assertEqual(1.0, asset.edit_state.settings.ai.upscale_factor)
            self.assertEqual(ExportProfile.WEB, asset.edit_state.settings.export.export_profile)
            self.assertEqual(ExportFormat.AUTO, asset.edit_state.settings.export.format)
            self.assertGreater(len(asset.recommendations.suggested_presets), 0)

    def test_gif_source_keeps_original_timing_and_loop_count_as_its_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sprite.gif"
            frames = [
                Image.new("RGBA", (16, 12), (255, 0, 0, 255)),
                Image.new("RGBA", (16, 12), (0, 255, 0, 255)),
            ]
            frames[0].save(
                source,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                duration=[80, 120],
                loop=2,
                transparency=0,
            )
            asset = _asset(source, file_format=AssetFormat.GIF)

            AssetProfileService().hydrate_imported_asset(asset)

            self.assertTrue(asset.capabilities.is_animated)
            self.assertTrue(asset.capabilities.has_alpha)
            self.assertEqual(2, asset.source_metadata.frame_count)
            self.assertEqual(2, asset.source_metadata.loop_count)
            self.assertEqual(0, asset.edit_state.settings.gif.frame_delay_ms)
            self.assertTrue(asset.edit_state.settings.gif.loop)
            self.assertEqual(2, asset.edit_state.settings.gif.loop_count)
            self.assertEqual(256, asset.edit_state.settings.gif.palette_size)
            self.assertEqual(0.0, asset.edit_state.settings.gif.dither_strength)

    def test_non_looping_gif_is_detected_as_non_looping(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "once.gif"
            frames = [
                Image.new("RGB", (10, 10), (255, 0, 0)),
                Image.new("RGB", (10, 10), (0, 255, 0)),
            ]
            frames[0].save(
                source,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                duration=90,
            )
            asset = _asset(source, file_format=AssetFormat.GIF)

            AssetProfileService().hydrate_imported_asset(asset)

            self.assertFalse(asset.edit_state.settings.gif.loop)
            self.assertIsNone(asset.edit_state.settings.gif.loop_count)
            self.assertEqual(2, asset.source_metadata.frame_count)
            self.assertIsNone(asset.source_metadata.loop_count)


if __name__ == "__main__":
    unittest.main()
