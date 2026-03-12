"""Tests for URL ingestion download/cache behavior using mocked openers."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ingest.url_ingest import (  # noqa: E402
    DownloadGuards,
    FileSizeGuardError,
    MimeValidationError,
    ResolutionGuardError,
    SignatureValidationError,
    UrlIngestError,
    download_url_to_cache,
    parse_image_dimensions,
    stream_preview_mode_stub,
    validate_url,
)


def _fake_png(width: int, height: int, *, payload: bytes = b"DATA") -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = (
        width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x06\x00\x00\x00"
    )
    ihdr = b"\x00\x00\x00\rIHDR" + ihdr_data + b"\x00\x00\x00\x00"
    idat = len(payload).to_bytes(4, "big") + b"IDAT" + payload + b"\x00\x00\x00\x00"
    iend = b"\x00\x00\x00\x00IEND\x00\x00\x00\x00"
    return signature + ihdr + idat + iend


def _webp_chunk(kind: bytes, payload: bytes) -> bytes:
    body = kind + len(payload).to_bytes(4, "little") + payload
    if len(payload) % 2 == 1:
        body += b"\x00"
    return body


def _fake_webp_vp8x(
    width: int,
    height: int,
    *,
    prefix_chunks: list[tuple[bytes, bytes]] | None = None,
) -> bytes:
    chunks = b""
    if prefix_chunks:
        for kind, payload in prefix_chunks:
            chunks += _webp_chunk(kind, payload)

    payload = b"\x00\x00\x00\x00" + (width - 1).to_bytes(3, "little") + (height - 1).to_bytes(3, "little")
    chunks += _webp_chunk(b"VP8X", payload)
    riff_size = (4 + len(chunks)).to_bytes(4, "little")
    return b"RIFF" + riff_size + b"WEBP" + chunks


def _fake_ico_header(width: int, height: int) -> bytes:
    width_byte = 0 if width == 256 else width
    height_byte = 0 if height == 256 else height
    header = b"\x00\x00\x01\x00\x01\x00"
    entry = (
        bytes([width_byte, height_byte, 0, 0])
        + (1).to_bytes(2, "little")
        + (32).to_bytes(2, "little")
        + (0).to_bytes(4, "little")
        + (22).to_bytes(4, "little")
    )
    return header + entry


def _fake_tiff_le(width: int, height: int) -> bytes:
    header = b"II*\x00" + (8).to_bytes(4, "little")
    entry_count = (2).to_bytes(2, "little")
    width_entry = (256).to_bytes(2, "little") + (4).to_bytes(2, "little") + (1).to_bytes(4, "little") + width.to_bytes(4, "little")
    height_entry = (257).to_bytes(2, "little") + (4).to_bytes(2, "little") + (1).to_bytes(4, "little") + height.to_bytes(4, "little")
    next_ifd = (0).to_bytes(4, "little")
    return header + entry_count + width_entry + height_entry + next_ifd


class _FakeResponse:
    def __init__(self, data: bytes, headers: dict[str, str] | None = None) -> None:
        self._data = data
        self._offset = 0
        self.headers = headers or {}

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = len(self._data) - self._offset
        chunk = self._data[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class UrlIngestTests(unittest.TestCase):

    def test_validate_url_accepts_http_https_and_rejects_other_schemes(self) -> None:
        self.assertEqual(validate_url("https://example.com/a.png"), "https://example.com/a.png")
        self.assertEqual(validate_url("http://example.com/a.png"), "http://example.com/a.png")
        with self.assertRaises(Exception):
            validate_url("ftp://example.com/a.png")

    def test_download_url_to_cache_success(self) -> None:
        data = _fake_png(32, 16, payload=b"hello")

        def opener(request, timeout=0):  # noqa: ANN001
            _ = (request, timeout)
            return _FakeResponse(data, headers={"Content-Type": "image/png"})

        with tempfile.TemporaryDirectory() as temp_dir:
            asset = download_url_to_cache(
                "https://example.com/sprite.png",
                temp_dir,
                opener=opener,
            )

            self.assertTrue(asset.cache_path.exists())
            self.assertEqual(asset.detected_format, "png")
            self.assertEqual(asset.mime_type, "image/png")
            self.assertEqual(asset.dimensions, (32, 16))
            self.assertEqual(asset.bytes_downloaded, len(data))
            self.assertEqual(asset.cache_path.suffix, ".png")

    def test_download_uses_no_proxy_fallback_on_winerror_10013(self) -> None:
        data = _fake_png(12, 12)
        calls = {"primary": 0, "fallback": 0}

        def primary_urlopen(request, timeout=0):  # noqa: ANN001
            _ = (request, timeout)
            calls["primary"] += 1
            raise URLError(OSError(10013, "An attempt was made to access a socket in a way forbidden by its access permissions"))

        class _DirectOpener:
            def open(self, request, timeout=0):  # noqa: ANN001
                _ = (request, timeout)
                calls["fallback"] += 1
                return _FakeResponse(data, headers={"Content-Type": "image/png"})

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("engine.ingest.url_ingest.urlopen", primary_urlopen), patch(
                "engine.ingest.url_ingest.build_opener",
                lambda *_args, **_kwargs: _DirectOpener(),
            ):
                asset = download_url_to_cache(
                    "https://example.com/retry-fallback.png",
                    temp_dir,
                    retries=0,
                )

        self.assertEqual("png", asset.detected_format)
        self.assertEqual(1, calls["primary"])
        self.assertEqual(1, calls["fallback"])

    def test_download_retries_once_then_succeeds(self) -> None:
        data = _fake_png(8, 8)
        calls: list[str] = []
        sleeps: list[float] = []

        def opener(request, timeout=0):  # noqa: ANN001
            _ = (request, timeout)
            calls.append("call")
            if len(calls) == 1:
                raise URLError("temporary outage")
            return _FakeResponse(data, headers={"Content-Type": "image/png"})

        with tempfile.TemporaryDirectory() as temp_dir:
            asset = download_url_to_cache(
                "https://example.com/retry.png",
                temp_dir,
                retries=2,
                backoff_seconds=0.1,
                sleep_func=sleeps.append,
                opener=opener,
            )

            self.assertEqual(asset.detected_format, "png")
            self.assertEqual(len(calls), 2)
            self.assertEqual(sleeps, [0.1])

    def test_file_size_guard_blocks_download_and_cleans_partial(self) -> None:
        data = _fake_png(32, 32, payload=b"x" * 200)

        def opener(request, timeout=0):  # noqa: ANN001
            _ = (request, timeout)
            return _FakeResponse(data, headers={"Content-Type": "image/png"})

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(FileSizeGuardError):
                download_url_to_cache(
                    "https://example.com/too-big.png",
                    temp_dir,
                    guards=DownloadGuards(max_bytes=32),
                    retries=0,
                    opener=opener,
                )

            self.assertEqual(list(Path(temp_dir).iterdir()), [])

    def test_download_url_to_cache_can_cancel_stream(self) -> None:
        data = _fake_png(40, 40, payload=b"x" * 2048)
        checks = {"count": 0}

        def opener(request, timeout=0):  # noqa: ANN001
            _ = (request, timeout)
            return _FakeResponse(data, headers={"Content-Type": "image/png"})

        def cancel_requested() -> bool:
            checks["count"] += 1
            return checks["count"] >= 2

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(UrlIngestError) as exc_info:
                download_url_to_cache(
                    "https://example.com/cancel.png",
                    temp_dir,
                    retries=0,
                    chunk_size=32,
                    opener=opener,
                    cancel_requested=cancel_requested,
                )

            self.assertIn("cancelled", str(exc_info.exception).lower())
            self.assertEqual(list(Path(temp_dir).iterdir()), [])

    def test_resolution_guard_blocks_large_png(self) -> None:
        data = _fake_png(1000, 1000)

        def opener(request, timeout=0):  # noqa: ANN001
            _ = (request, timeout)
            return _FakeResponse(data, headers={"Content-Type": "image/png"})

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ResolutionGuardError):
                download_url_to_cache(
                    "https://example.com/huge.png",
                    temp_dir,
                    guards=DownloadGuards(max_pixels=100_000),
                    retries=0,
                    opener=opener,
                )

            self.assertEqual(list(Path(temp_dir).iterdir()), [])

    def test_resolution_guard_blocks_large_webp(self) -> None:
        data = _fake_webp_vp8x(600, 600)

        def opener(request, timeout=0):  # noqa: ANN001
            _ = (request, timeout)
            return _FakeResponse(data, headers={"Content-Type": "image/webp"})

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ResolutionGuardError):
                download_url_to_cache(
                    "https://example.com/huge.webp",
                    temp_dir,
                    guards=DownloadGuards(max_pixels=100_000),
                    retries=0,
                    opener=opener,
                )

            self.assertEqual(list(Path(temp_dir).iterdir()), [])

    def test_resolution_guard_blocks_large_ico(self) -> None:
        data = _fake_ico_header(256, 256)

        def opener(request, timeout=0):  # noqa: ANN001
            _ = (request, timeout)
            return _FakeResponse(data, headers={"Content-Type": "image/x-icon"})

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ResolutionGuardError):
                download_url_to_cache(
                    "https://example.com/icon.ico",
                    temp_dir,
                    guards=DownloadGuards(max_width=128),
                    retries=0,
                    opener=opener,
                )

            self.assertEqual(list(Path(temp_dir).iterdir()), [])

    def test_resolution_guard_blocks_large_tiff(self) -> None:
        data = _fake_tiff_le(640, 480)

        def opener(request, timeout=0):  # noqa: ANN001
            _ = (request, timeout)
            return _FakeResponse(data, headers={"Content-Type": "image/tiff"})

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ResolutionGuardError):
                download_url_to_cache(
                    "https://example.com/scan.tiff",
                    temp_dir,
                    guards=DownloadGuards(max_height=240),
                    retries=0,
                    opener=opener,
                )

            self.assertEqual(list(Path(temp_dir).iterdir()), [])

    def test_stream_preview_mode_returns_metadata(self) -> None:
        data = _fake_png(48, 24, payload=b"hello-preview")
        captured_ranges: list[str | None] = []

        def opener(request, timeout=0):  # noqa: ANN001
            _ = timeout
            captured_ranges.append(request.headers.get("Range"))
            return _FakeResponse(data, headers={"Content-Type": "image/png"})

        asset = stream_preview_mode_stub(
            "https://example.com/preview.png",
            max_preview_bytes=24,
            opener=opener,
        )

        self.assertEqual(asset.detected_format, "png")
        self.assertEqual(asset.mime_type, "image/png")
        self.assertEqual(asset.dimensions, (48, 24))
        self.assertEqual(asset.bytes_sampled, 24)
        self.assertTrue(asset.truncated)
        self.assertEqual(captured_ranges, ["bytes=0-23"])

    def test_stream_preview_mode_rejects_signature_mismatch(self) -> None:
        def opener(request, timeout=0):  # noqa: ANN001
            _ = (request, timeout)
            return _FakeResponse(b"not-an-image", headers={"Content-Type": "image/png"})

        with self.assertRaises(SignatureValidationError):
            stream_preview_mode_stub("https://example.com/bad.png", opener=opener)

    def test_download_allows_generic_octet_stream_when_signature_is_valid(self) -> None:
        data = _fake_png(22, 11, payload=b"octet")

        def opener(request, timeout=0):  # noqa: ANN001
            _ = (request, timeout)
            return _FakeResponse(data, headers={"Content-Type": "application/octet-stream"})

        with tempfile.TemporaryDirectory() as temp_dir:
            asset = download_url_to_cache(
                "https://example.com/sprite.bin",
                temp_dir,
                opener=opener,
            )

            self.assertEqual(asset.detected_format, "png")
            self.assertEqual(asset.dimensions, (22, 11))
            self.assertTrue(asset.cache_path.exists())

    def test_stream_preview_mode_rejects_mime_mismatch(self) -> None:
        data = _fake_png(16, 16)

        def opener(request, timeout=0):  # noqa: ANN001
            _ = (request, timeout)
            return _FakeResponse(data, headers={"Content-Type": "image/jpeg"})

        with self.assertRaises(MimeValidationError):
            stream_preview_mode_stub("https://example.com/wrong-mime", opener=opener)

    def test_parse_image_dimensions_webp_vp8x_after_metadata_chunk(self) -> None:
        # EXIF chunk first (odd length payload to exercise chunk padding), VP8X second.
        data = _fake_webp_vp8x(321, 123, prefix_chunks=[(b"EXIF", b"abc")])
        self.assertEqual(parse_image_dimensions(data, "webp"), (321, 123))

    def test_parse_image_dimensions_ico_uses_directory_entry(self) -> None:
        data = _fake_ico_header(256, 128)
        self.assertEqual(parse_image_dimensions(data, "ico"), (256, 128))

    def test_parse_image_dimensions_tiff_little_endian(self) -> None:
        data = _fake_tiff_le(640, 480)
        self.assertEqual(parse_image_dimensions(data, "tiff"), (640, 480))


if __name__ == "__main__":
    unittest.main()





