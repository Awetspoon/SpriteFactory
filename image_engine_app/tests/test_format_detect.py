"""Tests for format detection and capability heuristics using synthetic bytes."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


from image_engine_app.engine.detect.capabilities import detect_capabilities  # noqa: E402
from image_engine_app.engine.detect.format_detect import (  # noqa: E402
    detect_format,
    detect_format_from_extension,
    detect_format_from_signature,
    signature_matches_format,
)
from image_engine_app.engine.models import AssetFormat  # noqa: E402


def _png_header(width: int, height: int, *, color_type: int = 2, extra: bytes = b"") -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = (
        width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08"
        + bytes([color_type])
        + b"\x00\x00\x00"
    )
    ihdr = b"\x00\x00\x00\rIHDR" + ihdr_data + b"\x00\x00\x00\x00"
    return signature + ihdr + extra


def _gif_header(*, frames: int = 1, transparent: bool = False) -> bytes:
    base = bytearray(b"GIF89a" + b"\x10\x00\x10\x00" + b"\x80\x00\x00" + b"\x00\x00\x00" + b"\xff\xff\xff")
    gce_packed = b"\x01" if transparent else b"\x00"
    frame_block = b"\x21\xf9\x04" + gce_packed + b"\x00\x00\x00\x00" + b"\x2c" + b"\x00" * 9
    for _ in range(frames):
        base.extend(frame_block)
    base.extend(b";")
    return bytes(base)


class FormatDetectTests(unittest.TestCase):
    def test_detect_format_from_extension_case_insensitive(self) -> None:
        self.assertEqual(detect_format_from_extension("sprite.PNG"), AssetFormat.PNG)
        self.assertEqual(detect_format_from_extension("photo.JpEg"), AssetFormat.JPG)
        self.assertEqual(detect_format_from_extension("unknown.xyz"), AssetFormat.UNKNOWN)

    def test_detect_format_from_signature_supported_headers(self) -> None:
        self.assertEqual(
            detect_format_from_signature(_png_header(8, 8)),
            AssetFormat.PNG,
        )
        self.assertEqual(detect_format_from_signature(b"GIF89a" + b"\x00" * 10), AssetFormat.GIF)
        self.assertEqual(detect_format_from_signature(b"\xff\xd8\xff\xe0" + b"\x00" * 8), AssetFormat.JPG)
        self.assertEqual(detect_format_from_signature(b"BM" + b"\x00" * 10), AssetFormat.BMP)
        self.assertEqual(
            detect_format_from_signature(b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 8),
            AssetFormat.WEBP,
        )
        self.assertEqual(
            detect_format_from_signature(b"\x00\x00\x01\x00\x01\x00" + b"\x00" * 8),
            AssetFormat.ICO,
        )
        self.assertEqual(
            detect_format_from_signature(b"II*\x00" + b"\x00" * 8),
            AssetFormat.TIFF,
        )
        self.assertEqual(detect_format_from_signature(b"not-an-image"), AssetFormat.UNKNOWN)

    def test_detect_format_prefers_signature_over_extension(self) -> None:
        jpeg_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 32
        self.assertEqual(
            detect_format(path_or_name="actually.png", header_bytes=jpeg_bytes),
            AssetFormat.JPG,
        )
        self.assertTrue(signature_matches_format(AssetFormat.JPG, jpeg_bytes))
        self.assertFalse(signature_matches_format(AssetFormat.PNG, jpeg_bytes))


class CapabilityDetectTests(unittest.TestCase):
    def test_png_alpha_and_apng_animation_detection(self) -> None:
        header = _png_header(64, 64, color_type=6, extra=b"acTL")
        caps = detect_capabilities(
            AssetFormat.PNG,
            header_bytes=header,
            dimensions=(64, 64),
            file_name="icon_rgba.png",
        )
        self.assertTrue(caps.has_alpha)
        self.assertTrue(caps.is_animated)
        self.assertFalse(caps.is_ico_bundle)
        self.assertFalse(caps.is_sheet)

    def test_gif_animation_and_transparency_heuristics(self) -> None:
        header = _gif_header(frames=2, transparent=True)
        caps = detect_capabilities(AssetFormat.GIF, header_bytes=header, dimensions=(32, 32))
        self.assertTrue(caps.is_animated)
        self.assertTrue(caps.has_alpha)
        self.assertFalse(caps.is_ico_bundle)

    def test_webp_alpha_flag_and_ico_bundle_detection(self) -> None:
        webp = b"RIFF\x1a\x00\x00\x00WEBPVP8X\x0a\x00\x00\x00\x10" + b"\x00" * 9
        webp_caps = detect_capabilities(AssetFormat.WEBP, header_bytes=webp, dimensions=(128, 128))
        self.assertTrue(webp_caps.has_alpha)
        self.assertFalse(webp_caps.is_animated)

        ico_bundle = b"\x00\x00\x01\x00\x02\x00" + b"\x00" * 32
        ico_caps = detect_capabilities(AssetFormat.ICO, header_bytes=ico_bundle, dimensions=(256, 256))
        self.assertTrue(ico_caps.is_ico_bundle)

    def test_sprite_sheet_heuristic_by_dimensions_or_name(self) -> None:
        by_dimensions = detect_capabilities(
            AssetFormat.PNG,
            header_bytes=_png_header(512, 128, color_type=2),
            dimensions=(512, 128),
        )
        self.assertTrue(by_dimensions.is_sheet)

        by_name = detect_capabilities(
            AssetFormat.PNG,
            header_bytes=_png_header(64, 64, color_type=2),
            dimensions=(64, 64),
            file_name="enemy_sheet.png",
        )
        self.assertTrue(by_name.is_sheet)


if __name__ == "__main__":
    unittest.main()



