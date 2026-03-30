"""Background source scan tests."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from PIL import Image

from image_engine_app.engine.analyze.background_scan import inspect_background_state
from image_engine_app.engine.models import BackgroundRemovalMode


class BackgroundScanTests(unittest.TestCase):
    def test_transparent_png_reports_existing_transparency(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "transparent.png"
            image = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
            image.putpixel((4, 4), (40, 180, 220, 255))
            image.save(image_path, format="PNG")

            result = inspect_background_state(image_path)

            self.assertTrue(result.can_inspect)
            self.assertTrue(result.has_transparent_pixels)
            self.assertIsNone(result.recommended_mode)

    def test_white_edge_background_recommends_white_cutout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "white-bg.png"
            image = Image.new("RGB", (12, 12), (255, 255, 255))
            for top in range(2, 10):
                for left in range(2, 10):
                    image.putpixel((left, top), (20, 120, 220))
            image.save(image_path, format="PNG")

            result = inspect_background_state(image_path)

            self.assertEqual(result.recommended_mode, BackgroundRemovalMode.WHITE)
            self.assertGreater(result.white_coverage_ratio, 0.05)

    def test_black_edge_background_recommends_black_cutout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "black-bg.png"
            image = Image.new("RGB", (12, 12), (0, 0, 0))
            for top in range(2, 10):
                for left in range(2, 10):
                    image.putpixel((left, top), (250, 210, 40))
            image.save(image_path, format="PNG")

            result = inspect_background_state(image_path)

            self.assertEqual(result.recommended_mode, BackgroundRemovalMode.BLACK)
            self.assertGreater(result.black_coverage_ratio, 0.05)


if __name__ == "__main__":
    unittest.main()
