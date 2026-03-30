"""Regression tests for light processing detail controls."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image, ImageChops, ImageSequence, ImageStat  # noqa: E402

from image_engine_app.engine.models import SettingsState  # noqa: E402
from image_engine_app.engine.process.light_steps import _apply_alpha_rules, _apply_color_adjust, _apply_detail, _apply_edges, apply_light_processing  # noqa: E402


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

    def test_temperature_adjust_warms_and_cools_channels(self) -> None:
        src = Image.new("RGB", (1, 1), (120, 120, 120))

        warm_settings = SettingsState()
        warm_settings.color.temperature = 0.75
        warm = _apply_color_adjust(src, warm_settings)

        cool_settings = SettingsState()
        cool_settings.color.temperature = -0.75
        cool = _apply_color_adjust(src, cool_settings)

        self.assertGreater(warm.getpixel((0, 0))[0], src.getpixel((0, 0))[0])
        self.assertLess(warm.getpixel((0, 0))[2], src.getpixel((0, 0))[2])
        self.assertLess(cool.getpixel((0, 0))[0], src.getpixel((0, 0))[0])
        self.assertGreater(cool.getpixel((0, 0))[2], src.getpixel((0, 0))[2])

    def test_curves_adjust_lifts_midtones(self) -> None:
        src = Image.new("RGB", (1, 1), (128, 128, 128))
        settings = SettingsState()
        settings.color.curves = {"rgb": [[0, 0], [128, 180], [255, 255]]}

        out = _apply_color_adjust(src, settings)

        self.assertGreater(out.getpixel((0, 0))[0], 128)
        self.assertGreater(out.getpixel((0, 0))[1], 128)
        self.assertGreater(out.getpixel((0, 0))[2], 128)


class LightAlphaTests(unittest.TestCase):
    def test_edge_controls_keep_rgba_processing_alive(self) -> None:
        src = Image.new("RGBA", (8, 8), (10, 20, 30, 0))
        for y in range(2, 6):
            for x in range(2, 6):
                src.putpixel((x, y), (220, 60, 60, 255))

        settings = SettingsState()
        settings.edges.antialias = 0.4
        settings.edges.edge_refine = 0.2
        settings.edges.feather_px = 1.0
        settings.edges.grow_shrink_px = 1.0

        out = _apply_edges(src, settings)

        self.assertEqual("RGBA", out.mode)
        self.assertEqual(src.size, out.size)
        self.assertGreater(out.getpixel((3, 3))[3], 0)

    def test_white_background_mode_removes_white_pixels(self) -> None:
        src = Image.new("RGB", (3, 1), (255, 255, 255))
        src.putpixel((1, 0), (40, 120, 200))

        settings = SettingsState()
        settings.alpha.background_removal_mode = "white"
        settings.alpha.remove_white_bg = True

        out = _apply_alpha_rules(src, settings)

        self.assertEqual("RGBA", out.mode)
        self.assertEqual(0, out.getpixel((0, 0))[3])
        self.assertGreater(out.getpixel((1, 0))[3], 0)

    def test_white_background_mode_off_keeps_rgb_image_unchanged(self) -> None:
        src = Image.new("RGB", (4, 4), (255, 255, 255))
        settings = SettingsState()
        settings.alpha.background_removal_mode = "off"
        settings.alpha.remove_white_bg = False

        out = _apply_alpha_rules(src, settings)

        self.assertEqual("RGB", out.mode)
        self.assertEqual(src.tobytes(), out.tobytes())

    def test_black_background_mode_removes_black_pixels(self) -> None:
        src = Image.new("RGB", (3, 1), (0, 0, 0))
        src.putpixel((1, 0), (230, 210, 40))

        settings = SettingsState()
        settings.alpha.background_removal_mode = "black"

        out = _apply_alpha_rules(src, settings)

        self.assertEqual("RGBA", out.mode)
        self.assertEqual(0, out.getpixel((0, 0))[3])
        self.assertGreater(out.getpixel((1, 0))[3], 0)

    def test_edge_connected_cutout_preserves_interior_white_detail(self) -> None:
        src = Image.new("RGB", (5, 5), (255, 255, 255))
        for y in range(1, 4):
            for x in range(1, 4):
                src.putpixel((x, y), (20, 90, 180))
        src.putpixel((2, 2), (255, 255, 255))

        settings = SettingsState()
        settings.alpha.background_removal_mode = "white"

        out = _apply_alpha_rules(src, settings)

        self.assertEqual(0, out.getpixel((0, 0))[3])
        self.assertGreater(out.getpixel((2, 2))[3], 0)

    def test_apply_light_processing_preserves_animation_when_output_is_gif(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            src = Path(temp_dir) / "src.gif"
            out = Path(temp_dir) / "preview.gif"

            frame_a = Image.new("RGB", (12, 12), (255, 255, 255))
            frame_b = Image.new("RGB", (12, 12), (255, 255, 255))
            for y in range(3, 9):
                for x in range(3, 9):
                    frame_a.putpixel((x, y), (255, 0, 0))
                    frame_b.putpixel((x, y), (0, 255, 0))
            frame_a.save(
                src,
                format="GIF",
                save_all=True,
                append_images=[frame_b],
                duration=[80, 120],
                loop=0,
            )

            settings = SettingsState()
            settings.alpha.background_removal_mode = "white"

            result = apply_light_processing(source_path=src, output_path=out, settings=settings)

            self.assertEqual(out, result.output_path)
            self.assertEqual((12, 12), result.size)

            with Image.open(out) as image:
                self.assertTrue(bool(getattr(image, "is_animated", False)))
                self.assertGreaterEqual(int(getattr(image, "n_frames", 1)), 2)
                frames = [frame.convert("RGBA") for frame in ImageSequence.Iterator(image)]
                self.assertEqual(0, frames[0].getpixel((0, 0))[3])
                self.assertNotEqual(frames[0].getpixel((5, 5)), frames[1].getpixel((5, 5)))

    def test_apply_light_processing_keeps_animated_preview_canvas_stable_when_gif_settings_resize(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            src = Path(temp_dir) / "src.gif"
            out = Path(temp_dir) / "preview.gif"

            frame_a = Image.new("RGBA", (12, 12), (255, 255, 255, 255))
            frame_b = Image.new("RGBA", (12, 12), (255, 255, 255, 255))
            for y in range(2, 10):
                for x in range(2, 10):
                    frame_a.putpixel((x, y), (255, 0, 0, 255))
                    frame_b.putpixel((x, y), (0, 0, 255, 255))
            frame_a.save(
                src,
                format="GIF",
                save_all=True,
                append_images=[frame_b],
                duration=[90, 90],
                loop=0,
            )

            settings = SettingsState()
            settings.pixel.resize_percent = 200.0

            result = apply_light_processing(source_path=src, output_path=out, settings=settings)

            self.assertEqual((24, 24), result.size)
            with Image.open(out) as image:
                self.assertEqual((12, 12), image.size)


if __name__ == "__main__":
    unittest.main()


