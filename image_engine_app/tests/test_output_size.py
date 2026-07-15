"""Output-size chooser behavior tests."""

from __future__ import annotations

import unittest

from image_engine_app.engine.models import PixelSettings
from image_engine_app.engine.process.output_size import (
    CUSTOM_SIZE,
    ORIGINAL_SIZE,
    apply_output_size_choice,
    output_size_choice_for,
)


class OutputSizeTests(unittest.TestCase):
    def test_integer_scale_uses_real_resize_percent(self) -> None:
        pixel = PixelSettings(width=320, height=240)

        self.assertTrue(apply_output_size_choice(pixel, "scale_4x"))

        self.assertEqual(400.0, pixel.resize_percent)
        self.assertIsNone(pixel.width)
        self.assertIsNone(pixel.height)
        self.assertEqual("scale_4x", output_size_choice_for(pixel))

    def test_standard_height_preserves_ratio_by_leaving_width_auto(self) -> None:
        pixel = PixelSettings(resize_percent=275.0, width=640, height=480)

        self.assertTrue(apply_output_size_choice(pixel, "height_1080"))

        self.assertEqual(100.0, pixel.resize_percent)
        self.assertIsNone(pixel.width)
        self.assertEqual(1080, pixel.height)
        self.assertEqual("height_1080", output_size_choice_for(pixel))

    def test_original_clears_target_dimensions(self) -> None:
        pixel = PixelSettings(resize_percent=200.0, width=640, height=480)

        apply_output_size_choice(pixel, ORIGINAL_SIZE)

        self.assertEqual(100.0, pixel.resize_percent)
        self.assertIsNone(pixel.width)
        self.assertIsNone(pixel.height)
        self.assertEqual(ORIGINAL_SIZE, output_size_choice_for(pixel))

    def test_manual_dimensions_are_reported_as_custom(self) -> None:
        pixel = PixelSettings(width=512, height=None)

        self.assertEqual(CUSTOM_SIZE, output_size_choice_for(pixel))


if __name__ == "__main__":
    unittest.main()
