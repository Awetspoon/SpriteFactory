"""Tests for rules-first content classification."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.classify.classifier import (  # noqa: E402
    ClassificationInput,
    classify_asset,
    classify_content,
)
from engine.models import AssetFormat, AssetRecord, Capabilities, SourceType  # noqa: E402


class ClassifierTests(unittest.TestCase):
    def test_classifies_pixel_art_sprite_sheet(self) -> None:
        result = classify_content(
            ClassificationInput(
                file_name="enemy_spritesheet.png",
                file_format=AssetFormat.PNG,
                dimensions=(512, 128),
                has_alpha=True,
                is_sheet=True,
                color_count_estimate=24,
            )
        )

        self.assertIn("sprite_sheet", result.tags)
        self.assertIn("pixel_art", result.tags)
        self.assertNotIn("photo", result.tags)
        self.assertEqual(result.tags[0], "sprite_sheet")

    def test_classifies_photo_from_lossy_large_image(self) -> None:
        result = classify_content(
            ClassificationInput(
                file_name="portrait_capture.jpg",
                file_format=AssetFormat.JPG,
                dimensions=(2048, 1536),
                has_alpha=False,
                color_count_estimate=20000,
            )
        )

        self.assertIn("photo", result.tags)
        self.assertNotIn("pixel_art", result.tags)
        self.assertNotIn("icon", result.tags)

    def test_classifies_icon_and_ui_by_filename_and_ico_bundle(self) -> None:
        result = classify_content(
            ClassificationInput(
                file_name="appicon_toolbar_ui.ico",
                file_format=AssetFormat.ICO,
                dimensions=(256, 256),
                has_alpha=True,
                is_ico_bundle=True,
            )
        )

        self.assertIn("icon", result.tags)
        self.assertIn("ui", result.tags)
        self.assertNotIn("photo", result.tags)

    def test_classify_asset_wrapper_uses_asset_metadata(self) -> None:
        asset = AssetRecord(
            source_type=SourceType.FILE,
            source_uri="C:/assets/grass_texture.png",
            original_name="grass_texture.png",
            format=AssetFormat.PNG,
            capabilities=Capabilities(has_alpha=False, is_animated=False, is_sheet=False, is_ico_bundle=False),
            dimensions_original=(1024, 1024),
            dimensions_current=(1024, 1024),
            dimensions_final=(1024, 1024),
        )

        result = classify_asset(asset, color_count_estimate=4096)
        self.assertIn("texture", result.tags)
        self.assertIn("photo", result.tags)  # high color count heuristic


if __name__ == "__main__":
    unittest.main()

