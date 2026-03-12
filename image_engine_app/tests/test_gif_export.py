"""Tests for animated GIF export frame preservation (Step 13)."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.export.exporters import ExportRequest, export_image  # noqa: E402
from engine.models import ExportFormat, ExportSettings  # noqa: E402


def _pillow_available() -> bool:
    try:
        from PIL import Image  # noqa: F401
        return True
    except Exception:
        return False


@unittest.skipUnless(_pillow_available(), "Pillow required for animated GIF export test.")
class AnimatedGifExportTests(unittest.TestCase):
    def test_export_preserves_frames(self) -> None:
        from PIL import Image  # type: ignore

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "src.gif"
            out = tmp_path / "out.gif"

            # Create a tiny 2-frame animated GIF.
            f1 = Image.new("RGBA", (16, 16), (255, 0, 0, 255))
            f2 = Image.new("RGBA", (16, 16), (0, 255, 0, 255))
            f1.save(
                src,
                format="GIF",
                save_all=True,
                append_images=[f2],
                duration=[80, 120],
                loop=0,
            )

            settings = ExportSettings(format=ExportFormat.GIF)
            result = export_image(
                ExportRequest(
                    output_path=out,
                    source_path=src,
                    width=16,
                    height=16,
                    export_settings=settings,
                    asset_id="test",
                    frame_count=2,
                    has_alpha=True,
                )
            )

            self.assertTrue(result.success)
            self.assertFalse(result.is_stub)
            self.assertTrue(out.exists())
            self.assertGreater(result.bytes_written, 0)

            with Image.open(out) as im:
                self.assertTrue(bool(getattr(im, "is_animated", False)))
                self.assertGreaterEqual(int(getattr(im, "n_frames", 1)), 2)

    def test_export_auto_format_preserves_animated_gif(self) -> None:
        from PIL import Image  # type: ignore

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "src_auto.gif"
            out = tmp_path / "out_auto.gif"

            f1 = Image.new("RGBA", (12, 12), (255, 0, 0, 255))
            f2 = Image.new("RGBA", (12, 12), (0, 0, 255, 255))
            f1.save(
                src,
                format="GIF",
                save_all=True,
                append_images=[f2],
                duration=[70, 90],
                loop=0,
            )

            settings = ExportSettings(format=ExportFormat.AUTO)
            result = export_image(
                ExportRequest(
                    output_path=out,
                    source_path=src,
                    width=12,
                    height=12,
                    export_settings=settings,
                    asset_id="auto-test",
                    frame_count=2,
                    has_alpha=True,
                )
            )

            self.assertTrue(result.success)
            self.assertEqual(result.format, ExportFormat.GIF)
            self.assertFalse(result.is_stub)
            self.assertTrue(out.exists())
            with Image.open(out) as im:
                self.assertTrue(bool(getattr(im, "is_animated", False)))
                self.assertGreaterEqual(int(getattr(im, "n_frames", 1)), 2)
