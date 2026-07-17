"""Tests for the shared new-asset preparation boundary."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from image_engine_app.app.services import AssetImportService, AssetProfileService, ImportAssetContext
from image_engine_app.engine.ingest.import_result import ImportIssueKind, ImportResult
from image_engine_app.engine.models import SourceType


class AssetImportServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = AssetImportService(profiles=AssetProfileService())

    def test_cached_web_file_is_prepared_with_one_source_context(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "cached.png"
            Image.new("RGBA", (18, 12), (10, 20, 30, 255)).save(path)

            result = self.service.import_cached_files(
                [path],
                context=ImportAssetContext(
                    source_type=SourceType.WEBPAGE_ITEM,
                    source_uri="https://example.com/gallery/sprite.png",
                    classification_tags=("web_target:normal", "web_source:https://example.com/gallery"),
                    display_name="hero.png",
                    reused=True,
                ),
            )

            asset = result.primary_asset
            self.assertIsNotNone(asset)
            self.assertEqual(SourceType.WEBPAGE_ITEM, asset.source_type)
            self.assertEqual("https://example.com/gallery/sprite.png", asset.source_uri)
            self.assertEqual(str(path), asset.cache_path)
            self.assertEqual("hero.png", asset.original_name)
            self.assertEqual((18, 12), asset.dimensions_original)
            self.assertIn("web_target:normal", asset.classification_tags)
            self.assertIsNotNone(asset.detected_settings)
            self.assertEqual(asset.detected_settings, asset.edit_state.settings)
            self.assertEqual(1.0, asset.edit_state.settings.ai.upscale_factor)
            self.assertEqual(0.0, asset.edit_state.settings.cleanup.denoise)
            self.assertEqual(0.0, asset.edit_state.settings.detail.sharpen_amount)
            self.assertEqual(("hero.png",), result.reused)

    def test_preparation_preserves_ingest_issues_when_no_asset_is_created(self) -> None:
        result = ImportResult()
        result.add_issue(ImportIssueKind.UNSUPPORTED, "readme.txt", "not an image")

        prepared = self.service.prepare_new_result(result)

        self.assertIs(prepared, result)
        self.assertEqual((), prepared.assets)
        self.assertEqual(("readme.txt",), prepared.unsupported)


if __name__ == "__main__":
    unittest.main()
