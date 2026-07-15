"""Behavior tests for controls that directly affect encoded output."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageSequence

from image_engine_app.engine.export.exporters import ExportRequest, _build_save_kwargs, export_image
from image_engine_app.engine.models import (
    ChromaSubsampling,
    ExportFormat,
    ExportSettings,
    GifSettings,
)


class ExportControlBehaviorTests(unittest.TestCase):
    def test_png_compression_and_jpeg_chroma_map_to_encoder_options(self) -> None:
        png = ExportSettings(format=ExportFormat.PNG, compression_level=4)
        jpeg = ExportSettings(
            format=ExportFormat.JPG,
            chroma_subsampling=ChromaSubsampling.CS_444,
        )

        self.assertEqual(4, _build_save_kwargs(ExportFormat.PNG, png)["compress_level"])
        self.assertEqual(0, _build_save_kwargs(ExportFormat.JPG, jpeg)["subsampling"])

    def test_dpi_and_metadata_controls_change_jpeg_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.jpg"
            kept = root / "kept.jpg"
            stripped = root / "stripped.jpg"

            exif = Image.Exif()
            exif[270] = "Sprite Factory metadata test"
            Image.new("RGB", (18, 14), (40, 120, 210)).save(source, format="JPEG", exif=exif)

            keep_result = export_image(
                ExportRequest(
                    output_path=kept,
                    source_path=source,
                    width=18,
                    height=14,
                    export_settings=ExportSettings(format=ExportFormat.JPG, strip_metadata=False),
                    dpi=144,
                )
            )
            strip_result = export_image(
                ExportRequest(
                    output_path=stripped,
                    source_path=source,
                    width=18,
                    height=14,
                    export_settings=ExportSettings(format=ExportFormat.JPG, strip_metadata=True),
                    dpi=96,
                )
            )

            self.assertTrue(keep_result.success)
            self.assertTrue(strip_result.success)
            with Image.open(kept) as image:
                self.assertEqual("Sprite Factory metadata test", image.getexif().get(270))
                self.assertAlmostEqual(144.0, float(image.info["dpi"][0]), delta=1.0)
            with Image.open(stripped) as image:
                self.assertIsNone(image.getexif().get(270))
                self.assertAlmostEqual(96.0, float(image.info["dpi"][0]), delta=1.0)

    def test_gif_controls_set_timing_loop_and_palette(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.gif"
            output = root / "output.gif"

            frames: list[Image.Image] = []
            for offset in (0, 37):
                frame = Image.new("RGB", (16, 16))
                for y in range(16):
                    for x in range(16):
                        frame.putpixel((x, y), ((x * 17 + offset) % 256, (y * 17) % 256, ((x + y) * 9) % 256))
                frames.append(frame)
            frames[0].save(
                source,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                duration=[80, 120],
                loop=0,
            )

            result = export_image(
                ExportRequest(
                    output_path=output,
                    source_path=source,
                    width=16,
                    height=16,
                    export_settings=ExportSettings(format=ExportFormat.GIF),
                    gif_settings=GifSettings(
                        frame_delay_ms=150,
                        loop=False,
                        palette_size=16,
                        dither_strength=0.0,
                        frame_optimize=False,
                    ),
                    frame_count=2,
                )
            )

            self.assertTrue(result.success)
            with Image.open(output) as image:
                self.assertTrue(bool(getattr(image, "is_animated", False)))
                self.assertIsNone(image.info.get("loop"))
                exported_frames = list(ImageSequence.Iterator(image))
                self.assertEqual([150, 150], [int(frame.info.get("duration", 0)) for frame in exported_frames])
                for frame in exported_frames:
                    colors = frame.convert("RGB").getcolors(maxcolors=256)
                    self.assertIsNotNone(colors)
                    self.assertLessEqual(len(colors or []), 16)


if __name__ == "__main__":
    unittest.main()
