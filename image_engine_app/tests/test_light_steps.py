"""Regression tests for light processing detail controls."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PIL import Image, ImageChops, ImageStat  # noqa: E402

from engine.models import SettingsState  # noqa: E402
from engine.process.light_steps import _apply_alpha_rules, _apply_color_adjust, _apply_detail  # noqa: E402


class LightDetailTests(unittest.TestCase):
    def _sample_image(self) -> Image.Image:
        img = Image.new("RGB", (128, 128))
        pix = img.load()
        for y in range(128):
            for x in range(128):
                v = int((x / 127.0) * 180 + (y / 127.0) * 40)
                if (x // 8 + y // 8) % 2 == 0:
                    v = min(255, v + 20)
                pix[x, y] = (v, max(0, v - 30), min(255, v + 10))
        return img

    def _mean_and_max_diff(self, src: Image.Image, dst: Image.Image) -> tuple[float, int]:
        diff = ImageChops.difference(src.convert("RGB"), dst.convert("RGB"))
        stat = ImageStat.Stat(diff)
        mean = float(sum(stat.mean) / len(stat.mean))
        max_channel = int(max(ch[1] for ch in stat.extrema))
        return mean, max_channel

    def test_detail_noop_when_all_controls_zero(self) -> None:
        src = self._sample_image()
        settings = SettingsState()
        out = _apply_detail(src, settings)
        self.assertEqual(src.tobytes(), out.tobytes())

    def test_clarity_texture_are_non_destructive_without_sharpen(self) -> None:
        src = self._sample_image()
        settings = SettingsState()
        settings.detail.sharpen_amount = 0.0
        settings.detail.clarity = 0.1
        settings.detail.texture = 0.2

        out = _apply_detail(src, settings)
        mean_diff, max_diff = self._mean_and_max_diff(src, out)

        self.assertGreater(mean_diff, 0.0)
        self.assertLess(mean_diff, 5.0)
        self.assertLess(max_diff, 25)

    def test_negative_detail_values_soften_image_without_breaking(self) -> None:
        src = self._sample_image()
        settings = SettingsState()
        settings.detail.sharpen_amount = -0.8
        settings.detail.clarity = -0.4
        settings.detail.texture = -0.4

        out = _apply_detail(src, settings)
        mean_diff, max_diff = self._mean_and_max_diff(src, out)

        self.assertGreater(mean_diff, 0.0)
        self.assertLess(mean_diff, 12.0)
        self.assertLess(max_diff, 80)


class LightColorTests(unittest.TestCase):
    def test_gamma_adjust_does_not_modify_alpha_channel(self) -> None:
        src = Image.new("RGBA", (8, 8))
        pix = src.load()
        for y in range(8):
            for x in range(8):
                pix[x, y] = (40 + (x * 20), 80 + (y * 10), 120 + (x * 5), (x * 31 + y * 13) % 256)

        settings = SettingsState()
        settings.color.gamma = 2.0

        out = _apply_color_adjust(src, settings)

        src_alpha = src.split()[3]
        out_alpha = out.split()[3]
        self.assertEqual(src_alpha.tobytes(), out_alpha.tobytes())


class LightAlphaTests(unittest.TestCase):
    def test_white_background_mode_removes_white_pixels(self) -> None:
        src = Image.new("RGB", (3, 1), (255, 255, 255))
        src.putpixel((1, 0), (40, 120, 200))

        settings = SettingsState()
        settings.alpha.remove_white_bg = True

        out = _apply_alpha_rules(src, settings)

        self.assertEqual("RGBA", out.mode)
        self.assertEqual(0, out.getpixel((0, 0))[3])
        self.assertGreater(out.getpixel((1, 0))[3], 0)

    def test_white_background_mode_off_keeps_rgb_image_unchanged(self) -> None:
        src = Image.new("RGB", (4, 4), (255, 255, 255))
        settings = SettingsState()
        settings.alpha.remove_white_bg = False

        out = _apply_alpha_rules(src, settings)

        self.assertEqual("RGB", out.mode)
        self.assertEqual(src.tobytes(), out.tobytes())


if __name__ == "__main__":
    unittest.main()
