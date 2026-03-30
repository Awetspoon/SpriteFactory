"""Tests for the UI action controller used by the Prompt 16 main window shell."""

from __future__ import annotations

import io
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile
from urllib.error import URLError

from image_engine_app.app.paths import ensure_app_paths  # noqa: E402
from image_engine_app.app.ui_controller import ImageEngineUIController  # noqa: E402
from image_engine_app.app.web_sources_models import Confidence, ImportTarget, SmartOptions, WebItem  # noqa: E402
from image_engine_app.app.preset_store import PresetStore  # noqa: E402
from image_engine_app.engine.analyze.recommend import RecommendationInput, build_recommendations  # noqa: E402
from image_engine_app.engine.ingest.webpage_scan import WebpageScanCancelledError, WebpageScanFilters  # noqa: E402
from image_engine_app.engine.models import (  # noqa: E402
    ApplyTarget,
    AssetFormat,
    AssetRecord,
    AnalysisSummary,
    Capabilities,
    EditMode,
    ExportProfile,
    ExportFormat,
    HeavyJobSpec,
    HeavyJobStatus,
    HeavyTool,
    SourceType,
    ScaleMethod,
)
from image_engine_app.engine.process.presets_apply import PresetApplyError  # noqa: E402
from image_engine_app.engine.process.performance_backend import (  # noqa: E402
    PerformanceAvailability,
    PerformanceBackend,
    PerformanceModeResolution,
)


def _fake_png(width: int, height: int, *, payload: bytes = b"DATA") -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"\x08\x06\x00\x00\x00"
    ihdr = b"\x00\x00\x00\rIHDR" + ihdr_data + b"\x00\x00\x00\x00"
    idat = len(payload).to_bytes(4, "big") + b"IDAT" + payload + b"\x00\x00\x00\x00"
    iend = b"\x00\x00\x00\x00IEND\x00\x00\x00\x00"
    return signature + ihdr + idat + iend



def _fake_jpg(payload: bytes = b"DATA") -> bytes:
    return b"\xff\xd8\xff\xe0" + payload + b"\xff\xd9"


def _fake_gif_animated() -> bytes:
    from PIL import Image  # local import keeps baseline dependencies stable for non-GIF tests

    frames = [
        Image.new("RGBA", (12, 10), (250, 30, 30, 255)),
        Image.new("RGBA", (12, 10), (30, 250, 30, 255)),
    ]
    buffer = io.BytesIO()
    frames[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=[80, 120],
        loop=0,
    )
    return buffer.getvalue()


def _pillow_available() -> bool:
    try:
        from PIL import Image  # noqa: F401
        return True
    except Exception:
        return False


class _FakeResponse:
    def __init__(self, data: bytes, content_type: str) -> None:
        self._data = data
        self._offset = 0
        self.headers = {"Content-Type": content_type}

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


def _asset(*, mode: EditMode = EditMode.SIMPLE) -> AssetRecord:
    asset = AssetRecord(
        id="asset-ui-001",
        source_type=SourceType.FILE,
        source_uri="C:/demo/sprite.png",
        original_name="sprite.png",
        format=AssetFormat.PNG,
        capabilities=Capabilities(has_alpha=True, is_animated=False, is_sheet=False, is_ico_bundle=False),
        dimensions_original=(64, 64),
        dimensions_current=(128, 128),
        dimensions_final=(256, 256),
    )
    asset.edit_state.mode = mode
    asset.edit_state.apply_target = ApplyTarget.BOTH
    asset.edit_state.sync_current_final = True
    asset.edit_state.settings.export.export_profile = ExportProfile.APP_ASSET
    return asset


class _RecordingPerformanceBackend(PerformanceBackend):
    def __init__(self, *, availability: PerformanceAvailability) -> None:
        super().__init__(availability=availability)
        self.calls: list[tuple[str, str]] = []

    def run_heavy_job(self, job: HeavyJobSpec, *, requested_mode: str) -> PerformanceModeResolution:
        self.calls.append((job.id, requested_mode))
        return super().run_heavy_job(job, requested_mode=requested_mode)


class UIControllerTests(unittest.TestCase):

    def test_user_presets_load_upsert_delete(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            store = PresetStore(paths)
            from image_engine_app.engine.models import PresetModel, EditMode  # local import keeps file tidy

            store.save_user_presets(
                [
                    PresetModel(
                        name="User A",
                        description="demo",
                        settings_delta={"cleanup": {"denoise": 0.12}},
                        uses_heavy_tools=False,
                        requires_apply=False,
                        mode_min=EditMode.SIMPLE,
                    )
                ]
            )

            controller = ImageEngineUIController(app_paths=paths)
            self.assertIn("User A", controller.available_preset_names())
            self.assertTrue(controller.is_user_preset("User A"))

            # Upsert override and delete.
            controller.upsert_user_preset(
                PresetModel(
                    name="User A",
                    description="updated",
                    settings_delta={"detail": {"sharpen_amount": 0.25}},
                    uses_heavy_tools=False,
                    requires_apply=False,
                    mode_min=EditMode.SIMPLE,
                )
            )
            self.assertEqual(controller.get_preset("User A").description, "updated")
            self.assertTrue(controller.delete_user_preset("User A"))
            self.assertNotIn("User A", controller.available_preset_names())

    def test_import_local_sources_returns_assets_and_filters_duplicates(self) -> None:
        controller = ImageEngineUIController()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "a.png").write_bytes(_fake_png(8, 8, payload=b"same"))
            (root / "b.png").write_bytes(_fake_png(8, 8, payload=b"same"))
            (root / "c.jpg").write_bytes(_fake_jpg(b"jpg"))
            (root / "note.txt").write_text("x", encoding="utf-8")

            summary = controller.import_local_sources([root], preserve_structure=False)

            self.assertEqual(len(summary.assets), 2)
            self.assertEqual(len(summary.duplicates), 1)
            self.assertEqual(len(summary.unsupported), 1)
            self.assertEqual({asset.format for asset in summary.assets}, {AssetFormat.PNG, AssetFormat.JPG})

    def test_import_url_source_and_webpage_scan_with_mocked_openers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            controller = ImageEngineUIController(app_paths=paths)

            png_bytes = _fake_png(32, 16, payload=b"hello")
            url_summary = controller.import_url_source(
                "https://example.com/sprite.png",
                opener=lambda request, timeout=0: _FakeResponse(png_bytes, "image/png"),
            )
            self.assertEqual(url_summary.asset.source_type, SourceType.URL)
            self.assertEqual(url_summary.asset.format, AssetFormat.PNG)
            self.assertEqual(url_summary.asset.dimensions_original, (32, 16))
            self.assertEqual(url_summary.preview_detected_format, "png")
            self.assertEqual(url_summary.preview_dimensions, (32, 16))
            self.assertIsNotNone(url_summary.preview_bytes_sampled)
            self.assertTrue(Path(url_summary.asset.cache_path).exists())

            html = (
                "<html><body>"
                "<img src='/a.png'><img src='https://cdn.example.com/b.jpg'>"
                "<a href='c.webp'>webp</a>"
                "</body></html>"
            ).encode("utf-8")
            scan = controller.scan_webpage_images(
                "https://example.com/gallery",
                filters=WebpageScanFilters(allowed_extensions={".png", ".webp"}),
                opener=lambda request, timeout=0: _FakeResponse(html, "text/html; charset=utf-8"),
            )
            self.assertEqual({item.url for item in scan.images}, {
                "https://example.com/a.png",
                "https://example.com/c.webp",
            })
            self.assertEqual(len(scan.filtered_out), 1)

    def test_import_url_source_prefers_decoded_file_dimensions_over_download_hints(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            controller = ImageEngineUIController(app_paths=paths)

            cache_file = paths.cache / "web_sources" / "main" / "stale.png"
            cache_file.parent.mkdir(parents=True, exist_ok=True)

            from PIL import Image  # local import keeps baseline dependencies stable for non-image tests

            Image.new("RGBA", (96, 64), (20, 40, 60, 255)).save(cache_file, format="PNG")

            stale_download = SimpleNamespace(
                cache_path=cache_file,
                detected_format="png",
                bytes_downloaded=int(cache_file.stat().st_size),
                dimensions=(32, 16),
            )

            with patch("image_engine_app.app.ui_controller.download_url_to_cache", return_value=stale_download):
                summary = controller.import_url_source(
                    "https://example.com/stale.png",
                    stream_preview=False,
                )

            self.assertEqual(summary.asset.dimensions_original, (96, 64))
            self.assertEqual(summary.asset.dimensions_current, (96, 64))
            self.assertEqual(summary.asset.dimensions_final, (96, 64))
            self.assertEqual(summary.dimensions, (96, 64))


    def test_import_url_source_falls_back_when_stream_preview_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            controller = ImageEngineUIController(app_paths=paths)
            png_bytes = _fake_png(20, 10, payload=b"fallback")

            call_count = {"value": 0}

            def opener(request, timeout=0):  # noqa: ANN001
                _ = (request, timeout)
                call_count["value"] += 1
                if call_count["value"] == 1:
                    raise URLError("preview failed")
                return _FakeResponse(png_bytes, "image/png")

            summary = controller.import_url_source(
                "https://example.com/fallback.png",
                opener=opener,
            )

            self.assertEqual(summary.asset.format, AssetFormat.PNG)
            self.assertEqual(summary.dimensions, (20, 10))
            self.assertIsNone(summary.preview_detected_format)
            self.assertIsNone(summary.preview_dimensions)

    def test_import_url_source_can_disable_stream_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            controller = ImageEngineUIController(app_paths=paths)
            png_bytes = _fake_png(24, 12, payload=b"no-preview")
            call_count = {"value": 0}

            def opener(request, timeout=0):  # noqa: ANN001
                _ = (request, timeout)
                call_count["value"] += 1
                return _FakeResponse(png_bytes, "image/png")

            summary = controller.import_url_source(
                "https://example.com/no-preview.png",
                opener=opener,
                stream_preview=False,
            )

            self.assertEqual(call_count["value"], 1)
            self.assertEqual(summary.asset.format, AssetFormat.PNG)
            self.assertEqual(summary.dimensions, (24, 12))
            self.assertIsNone(summary.preview_detected_format)
            self.assertIsNone(summary.preview_dimensions)
            self.assertIsNone(summary.preview_bytes_sampled)
            self.assertIsNone(summary.preview_truncated)

    def test_import_url_source_sets_gif_animated_capability(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            controller = ImageEngineUIController(app_paths=paths)
            gif_bytes = _fake_gif_animated()

            summary = controller.import_url_source(
                "https://example.com/anim.gif",
                opener=lambda request, timeout=0: _FakeResponse(gif_bytes, "image/gif"),
                stream_preview=False,
            )

            self.assertEqual(summary.asset.format, AssetFormat.GIF)
            self.assertTrue(summary.asset.capabilities.is_animated)
            self.assertEqual(summary.asset.dimensions_original, (12, 10))

    def test_import_url_source_falls_back_from_webpage_to_first_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            controller = ImageEngineUIController(app_paths=paths)

            page_html = (
                "<html><body>"
                "<h1>Sprite Page</h1>"
                "<img src='/sprite.png'>"
                "</body></html>"
            ).encode("utf-8")
            png_bytes = _fake_png(14, 9, payload=b"page-fallback")

            def opener(request, timeout=0):  # noqa: ANN001
                _ = timeout
                url = str(getattr(request, "full_url", request))
                if url == "https://example.com/gallery/one":
                    return _FakeResponse(page_html, "text/html; charset=utf-8")
                if url == "https://example.com/sprite.png":
                    return _FakeResponse(png_bytes, "image/png")
                raise URLError(f"unexpected URL: {url}")

            summary = controller.import_url_source(
                "https://example.com/gallery/one",
                opener=opener,
                stream_preview=False,
                allow_webpage_fallback=True,
            )

            self.assertEqual(summary.asset.source_uri, "https://example.com/sprite.png")
            self.assertEqual(summary.asset.format, AssetFormat.PNG)
            self.assertEqual(summary.asset.dimensions_original, (14, 9))
            self.assertIn("url_fallback:webpage_first_image", summary.asset.classification_tags)

    def test_load_web_sources_registry_sanitizes_missing_ids(self) -> None:
        controller = ImageEngineUIController()
        registry = controller.load_web_sources_registry(
            [
                {
                    "name": "Demo Site",
                    "areas": [{"label": "Main Area", "url": "https://example.com/gallery"}],
                }
            ]
        )

        self.assertEqual(len(registry), 1)
        self.assertEqual(registry[0]["id"], "demo_site")
        self.assertEqual(registry[0]["areas"][0]["id"], "main_area")

    def test_scan_web_sources_area_filters_likely_and_detects_zip_links(self) -> None:
        controller = ImageEngineUIController()
        html = (
            "<html><body>"
            "<img src='https://cdn.example.com/a.png'>"
            "<img src='https://cdn.example.com/image?id=42'>"
            "<a href='/pack.zip'>ZIP</a>"
            "</body></html>"
        ).encode("utf-8")

        def opener(request, timeout=0):  # noqa: ANN001
            _ = (request, timeout)
            return _FakeResponse(html, "text/html; charset=utf-8")

        strict = controller.scan_web_sources_area(
            "https://example.com/gallery",
            show_likely=False,
            opener=opener,
        )
        strict_urls = {item.url for item in strict.items}
        self.assertIn("https://cdn.example.com/a.png", strict_urls)
        self.assertIn("https://example.com/pack.zip", strict_urls)
        self.assertNotIn("https://cdn.example.com/image?id=42", strict_urls)

        likely = controller.scan_web_sources_area(
            "https://example.com/gallery",
            show_likely=True,
            opener=opener,
        )
        likely_urls = {item.url for item in likely.items}
        self.assertIn("https://cdn.example.com/image?id=42", likely_urls)

    def test_scan_web_sources_area_falls_back_to_likely_when_no_direct_links(self) -> None:
        controller = ImageEngineUIController()
        html = "<html><body><img src='https://cdn.example.com/image?id=42'></body></html>".encode("utf-8")

        def opener(request, timeout=0):  # noqa: ANN001
            _ = (request, timeout)
            return _FakeResponse(html, "text/html; charset=utf-8")

        results = controller.scan_web_sources_area(
            "https://example.com/gallery",
            show_likely=False,
            opener=opener,
        )

        self.assertEqual(1, len(results.items))
        self.assertEqual("https://cdn.example.com/image?id=42", results.items[0].url)
        self.assertEqual(Confidence.LIKELY, results.items[0].confidence)

    def test_scan_web_sources_area_accepts_direct_url_without_html_scan(self) -> None:
        controller = ImageEngineUIController()

        def opener(request, timeout=0):  # noqa: ANN001
            raise AssertionError(f"HTML scan opener should not run for direct URLs: {request} {timeout}")

        results = controller.scan_web_sources_area(
            "https://cdn.example.com/sprite.png",
            show_likely=False,
            opener=opener,
        )

        self.assertEqual(1, len(results.items))
        self.assertEqual("https://cdn.example.com/sprite.png", results.items[0].url)
        self.assertEqual(Confidence.DIRECT, results.items[0].confidence)

    def test_scan_web_sources_area_can_be_cancelled(self) -> None:
        controller = ImageEngineUIController()

        with self.assertRaises(WebpageScanCancelledError):
            controller.scan_web_sources_area(
                "https://example.com/gallery",
                cancel_requested=lambda: True,
                opener=lambda request, timeout=0: _FakeResponse(b"<html></html>", "text/html; charset=utf-8"),
            )

    def test_download_web_sources_items_supports_png_zip_and_dedupe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            controller = ImageEngineUIController(app_paths=paths)

            png_bytes = _fake_png(18, 18, payload=b"web")
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("sprite_zip.png", _fake_png(10, 6, payload=b"zip"))
                archive.writestr("readme.txt", b"ignore")
            zip_bytes = zip_buffer.getvalue()

            def opener(request, timeout=0):  # noqa: ANN001
                _ = timeout
                url = str(getattr(request, "full_url", request))
                if url.endswith("sprite.png"):
                    return _FakeResponse(png_bytes, "image/png")
                if url.endswith("pack.zip"):
                    return _FakeResponse(zip_bytes, "application/zip")
                raise URLError(f"unexpected URL: {url}")

            items = [
                WebItem(
                    url="https://example.com/sprite.png",
                    name="sprite.png",
                    ext=".png",
                    confidence=Confidence.DIRECT,
                ),
                WebItem(
                    url="https://example.com/pack.zip",
                    name="pack.zip",
                    ext=".zip",
                    confidence=Confidence.DIRECT,
                ),
            ]

            progress_events: list[tuple[int, int, str]] = []

            report = controller.download_web_sources_items(
                items,
                ImportTarget.NORMAL,
                smart=SmartOptions(show_likely=False, auto_sort=False, skip_duplicates=True, allow_zip=True),
                opener=opener,
                progress_callback=lambda done, total, msg: progress_events.append((int(done), int(total), str(msg))),
            )

            self.assertEqual(len(report.failed), 0)
            self.assertEqual(len(report.skipped), 0)
            self.assertGreaterEqual(len(report.downloaded), 2)
            self.assertEqual(len(report.assets), 2)
            self.assertTrue(progress_events)
            self.assertEqual(progress_events[-1][0], progress_events[-1][1])
            self.assertIn("Download complete", progress_events[-1][2])
            report_second = controller.download_web_sources_items(
                items,
                ImportTarget.NORMAL,
                smart=SmartOptions(show_likely=False, auto_sort=False, skip_duplicates=True, allow_zip=True),
                opener=opener,
            )
            self.assertEqual(len(report_second.downloaded), 0)
            self.assertGreaterEqual(len(report_second.skipped), 2)
            cached_names = {asset.original_name for asset in report_second.assets}
            self.assertIn("sprite.png", cached_names)

    def test_download_web_sources_items_auto_sort_splits_gif_by_extension(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            controller = ImageEngineUIController(app_paths=paths)

            png_bytes = _fake_png(8, 8, payload=b"png")
            gif_bytes = _fake_gif_animated()

            def opener(request, timeout=0):  # noqa: ANN001
                _ = timeout
                url = str(getattr(request, "full_url", request))
                if url.endswith("sprite_no_ext"):
                    return _FakeResponse(gif_bytes, "image/gif")
                if url.endswith("sprite.png"):
                    return _FakeResponse(png_bytes, "image/png")
                raise URLError(f"unexpected URL: {url}")

            items = [
                WebItem(
                    url="https://example.com/sprite.png",
                    name="sprite.png",
                    ext=".png",
                    confidence=Confidence.DIRECT,
                ),
                WebItem(
                    url="https://example.com/sprite_no_ext",
                    name="sprite",
                    ext=".gif",
                    confidence=Confidence.DIRECT,
                ),
            ]

            report = controller.download_web_sources_items(
                items,
                ImportTarget.NORMAL,
                smart=SmartOptions(show_likely=False, auto_sort=True, skip_duplicates=False, allow_zip=True),
                opener=opener,
            )

            self.assertEqual(len(report.failed), 0)
            self.assertEqual(len(report.assets), 2)

            by_name = {asset.original_name: asset for asset in report.assets}
            self.assertIn("sprite.png", by_name)
            self.assertIn("sprite_no_ext", by_name)

            normal_tags = set(by_name["sprite.png"].classification_tags)
            gif_tags = set(by_name["sprite_no_ext"].classification_tags)
            self.assertIn("web_target:normal", normal_tags)
            self.assertIn("web_target:animated", gif_tags)

    def test_resolve_web_item_name_decodes_and_marks_shiny(self) -> None:
        name = ImageEngineUIController._resolve_web_item_name(
            "Enlarge image",
            "https://projectpokemon.org/images/shiny-sprite/venusaur-f.gif",
        )
        self.assertEqual(name, "venusaur-f_shiny.gif")

        query_name = ImageEngineUIController._resolve_web_item_name(
            None,
            "https://example.com/cdn/image?filename=charizard%20mega%20x%20shiny.gif",
        )
        self.assertEqual(query_name, "charizard mega x shiny.gif")

    def test_download_web_sources_items_skip_duplicates_keeps_distinct_urls_same_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            controller = ImageEngineUIController(app_paths=paths)

            png_a = _fake_png(10, 10, payload=b"a")
            png_b = _fake_png(10, 10, payload=b"b")

            def opener(request, timeout=0):  # noqa: ANN001
                _ = timeout
                url = str(getattr(request, "full_url", request))
                if url.endswith("sprite_a.png"):
                    return _FakeResponse(png_a, "image/png")
                if url.endswith("sprite_b.png"):
                    return _FakeResponse(png_b, "image/png")
                raise URLError(f"unexpected URL: {url}")

            items = [
                WebItem(
                    url="https://example.com/sprite_a.png",
                    name="download.png",
                    ext=".png",
                    confidence=Confidence.DIRECT,
                ),
                WebItem(
                    url="https://example.com/sprite_b.png",
                    name="download.png",
                    ext=".png",
                    confidence=Confidence.DIRECT,
                ),
            ]

            report = controller.download_web_sources_items(
                items,
                ImportTarget.NORMAL,
                smart=SmartOptions(show_likely=False, auto_sort=False, skip_duplicates=True, allow_zip=True),
                opener=opener,
            )

            self.assertEqual(len(report.failed), 0)
            self.assertEqual(len(report.assets), 2)
            self.assertEqual(len(report.skipped), 0)

    def test_download_web_sources_items_can_cancel_mid_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            controller = ImageEngineUIController(app_paths=paths)

            png_a = _fake_png(12, 12, payload=b"a")
            png_b = _fake_png(12, 12, payload=b"b")

            def opener(request, timeout=0):  # noqa: ANN001
                _ = timeout
                url = str(getattr(request, "full_url", request))
                if url.endswith("sprite_a.png"):
                    return _FakeResponse(png_a, "image/png")
                if url.endswith("sprite_b.png"):
                    return _FakeResponse(png_b, "image/png")
                raise URLError(f"unexpected URL: {url}")

            items = [
                WebItem(
                    url="https://example.com/sprite_a.png",
                    name="sprite_a.png",
                    ext=".png",
                    confidence=Confidence.DIRECT,
                ),
                WebItem(
                    url="https://example.com/sprite_b.png",
                    name="sprite_b.png",
                    ext=".png",
                    confidence=Confidence.DIRECT,
                ),
            ]

            cancel_state = {"requested": False}

            def progress_callback(done, total, message):  # noqa: ANN001
                _ = (done, total)
                if str(message).startswith("Imported:"):
                    cancel_state["requested"] = True

            report = controller.download_web_sources_items(
                items,
                ImportTarget.NORMAL,
                smart=SmartOptions(show_likely=False, auto_sort=False, skip_duplicates=False, allow_zip=True),
                opener=opener,
                progress_callback=progress_callback,
                cancel_requested=lambda: bool(cancel_state["requested"]),
            )

            self.assertTrue(report.cancelled)
            self.assertEqual(len(report.assets), 1)
            self.assertEqual(len(report.downloaded), 1)
            self.assertEqual(len(report.failed), 0)

    def test_apply_named_preset_clamps_and_queues_heavy_job(self) -> None:
        controller = ImageEngineUIController()
        asset = _asset(mode=EditMode.SIMPLE)

        summary = controller.apply_named_preset(asset, "Pixel Clean Upscale")

        self.assertEqual(summary.preset_name, "Pixel Clean Upscale")
        self.assertTrue(summary.requires_apply)
        self.assertEqual(summary.queued_heavy_jobs, 1)
        self.assertEqual(asset.edit_state.settings.ai.upscale_factor, 2.0)  # simple-mode clamp
        self.assertEqual(asset.edit_state.settings.export.export_profile.value, "app_asset")
        self.assertEqual(asset.edit_state.settings.export.format.value, "png")
        self.assertEqual(asset.edit_state.queued_heavy_jobs[0].tool, HeavyTool.AI_UPSCALE)
        self.assertEqual(asset.edit_state.queued_heavy_jobs[0].status, HeavyJobStatus.QUEUED)

    def test_apply_named_preset_rejects_incompatible_animated_gif(self) -> None:
        controller = ImageEngineUIController()
        asset = _asset(mode=EditMode.ADVANCED)
        asset.original_name = "battle_anim.gif"
        asset.format = AssetFormat.GIF
        asset.capabilities = Capabilities(has_alpha=True, is_animated=True, is_sheet=False, is_ico_bundle=False)
        asset.classification_tags = ["animation", "pixel_art"]

        with self.assertRaises(PresetApplyError):
            controller.apply_named_preset(asset, "Photo Recover")

    def test_available_preset_entries_filter_to_compatible_asset_types(self) -> None:
        controller = ImageEngineUIController()
        asset = _asset(mode=EditMode.ADVANCED)
        asset.original_name = "battle_anim.gif"
        asset.format = AssetFormat.GIF
        asset.capabilities = Capabilities(has_alpha=True, is_animated=True, is_sheet=False, is_ico_bundle=False)
        asset.classification_tags = ["animation", "pixel_art"]

        entries = controller.available_preset_entries(asset, compatible_only=True)
        names = [entry.name for entry in entries]

        self.assertIn("GIF Safe Cleanup", names)
        self.assertIn("GIF Outline Safe", names)
        self.assertNotIn("Sprite Sheet Prep", names)
        self.assertNotIn("Photo Recover", names)
        self.assertTrue(any("GIF" in entry.label for entry in entries if entry.name == "GIF Safe Cleanup"))

    def test_available_preset_entries_include_broader_scope_labels(self) -> None:
        controller = ImageEngineUIController()
        entries = {entry.name: entry for entry in controller.available_preset_entries()}

        self.assertIn("Sheet", entries["Sprite Sheet Prep"].label)
        self.assertIn("GIF", entries["GIF Safe Cleanup"].label)
        self.assertIn("Icon", entries["ICO Icon Polish"].label)
        self.assertIn("Texture", entries["Texture Repair"].label)
        self.assertIn("TIFF", entries["TIFF Print Clean"].label)
        self.assertIn("WEBP", entries["WEBP Photo Finish"].label)

    def test_detected_baseline_preset_skips_incompatible_animated_gif_suggestion(self) -> None:
        controller = ImageEngineUIController()
        asset = _asset(mode=EditMode.SIMPLE)
        asset.original_name = "battle_anim.gif"
        asset.format = AssetFormat.GIF
        asset.capabilities = Capabilities(has_alpha=True, is_animated=True, is_sheet=False, is_ico_bundle=False)
        asset.classification_tags = ["animation", "pixel_art"]
        asset.recommendations = build_recommendations(
            RecommendationInput(
                file_format=AssetFormat.GIF,
                classification_tags=["animation", "pixel_art"],
                analysis=AnalysisSummary(
                    blur_score=0.2,
                    noise_score=0.35,
                    compression_score=0.3,
                    edge_integrity_score=0.7,
                    resolution_need_score=0.8,
                    gif_palette_stress=0.4,
                    warnings=[],
                ),
                has_alpha=True,
                is_animated=True,
            )
        )

        controller._apply_detected_baseline_preset(asset)

        self.assertEqual(asset.edit_state.settings.export.format, ExportFormat.GIF)
        self.assertEqual(asset.edit_state.settings.export.palette_limit, 256)
        self.assertEqual(len(asset.edit_state.queued_heavy_jobs), 0)

    def test_reset_asset_settings_to_defaults_clears_custom_edits(self) -> None:
        controller = ImageEngineUIController()
        asset = _asset(mode=EditMode.ADVANCED)

        asset.edit_state.settings.pixel.resize_percent = 175.0
        asset.edit_state.settings.detail.clarity = 0.7
        asset.edit_state.settings.cleanup.denoise = 0.5
        asset.edit_state.settings.ai.deblur_strength = 0.6
        asset.dimensions_original = (48, 32)
        asset.dimensions_current = (120, 90)
        asset.dimensions_final = (120, 90)
        asset.edit_state.queued_heavy_jobs.append(HeavyJobSpec(tool=HeavyTool.AI_UPSCALE))

        controller.reset_asset_settings_to_defaults(asset)

        self.assertEqual(asset.edit_state.settings.pixel.resize_percent, 100.0)
        self.assertEqual(asset.edit_state.settings.detail.clarity, 0.0)
        self.assertEqual(asset.edit_state.settings.cleanup.denoise, 0.0)
        self.assertEqual(asset.edit_state.settings.ai.deblur_strength, 0.0)
        self.assertEqual(asset.dimensions_current, (48, 32))
        self.assertEqual(asset.dimensions_final, (48, 32))
        self.assertEqual(len(asset.edit_state.queued_heavy_jobs), 0)

    def test_apply_heavy_queue_runs_queued_jobs(self) -> None:
        controller = ImageEngineUIController()
        asset = _asset(mode=EditMode.ADVANCED)
        controller.apply_named_preset(asset, "Pixel Clean Upscale")

        completed = controller.apply_heavy_queue(asset)

        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0].status, HeavyJobStatus.DONE)
        self.assertEqual(asset.edit_state.queued_heavy_jobs[0].status, HeavyJobStatus.DONE)

    def test_set_performance_mode_falls_back_to_cpu_when_gpu_is_unavailable(self) -> None:
        backend = _RecordingPerformanceBackend(
            availability=PerformanceAvailability(
                cpu_available=True,
                gpu_available=False,
                gpu_backend_label=None,
                gpu_disabled_reason="GPU backend not installed",
            )
        )
        controller = ImageEngineUIController(performance_backend=backend)

        resolution = controller.set_performance_mode("gpu")

        self.assertEqual(resolution.requested_mode, "gpu")
        self.assertEqual(resolution.effective_mode, "cpu")
        self.assertEqual(controller.performance_mode, "cpu")

    def test_apply_heavy_queue_uses_selected_performance_mode(self) -> None:
        backend = _RecordingPerformanceBackend(
            availability=PerformanceAvailability(
                cpu_available=True,
                gpu_available=True,
                gpu_backend_label="Fake GPU",
                gpu_disabled_reason=None,
            )
        )
        controller = ImageEngineUIController(performance_backend=backend)
        asset = _asset(mode=EditMode.ADVANCED)
        controller.apply_named_preset(asset, "Pixel Clean Upscale")
        controller.set_performance_mode("gpu")

        completed = controller.apply_heavy_queue(asset)

        self.assertEqual(len(completed), 1)
        self.assertEqual(backend.calls, [(asset.edit_state.queued_heavy_jobs[0].id, "gpu")])
        self.assertEqual(asset.edit_state.queued_heavy_jobs[0].status, HeavyJobStatus.DONE)

    @unittest.skipUnless(_pillow_available(), "Pillow required for heavy queue render test.")
    def test_apply_heavy_queue_writes_real_derived_output(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            controller = ImageEngineUIController(app_paths=paths)

            src = Path(temp_dir) / "heavy_source.png"
            Image.new("RGBA", (10, 8), (60, 120, 220, 255)).save(src, format="PNG")

            asset = _asset(mode=EditMode.ADVANCED)
            asset.source_uri = str(src)
            asset.cache_path = str(src)
            asset.original_name = "heavy_source.png"
            asset.dimensions_original = (10, 8)
            asset.dimensions_current = (10, 8)
            asset.dimensions_final = (10, 8)
            asset.edit_state.settings.ai.upscale_factor = 2.0
            asset.edit_state.queued_heavy_jobs = [
                HeavyJobSpec(id="job-heavy-render", tool=HeavyTool.AI_UPSCALE, params={"factor": 2.0})
            ]

            completed = controller.apply_heavy_queue(asset)

            self.assertEqual(len(completed), 1)
            self.assertEqual(asset.edit_state.queued_heavy_jobs[0].status, HeavyJobStatus.DONE)
            self.assertTrue(isinstance(asset.derived_final_path, str) and Path(asset.derived_final_path).exists())
            self.assertTrue(isinstance(asset.derived_current_path, str) and Path(asset.derived_current_path).exists())
            self.assertGreaterEqual(asset.dimensions_final[0], 20)
            self.assertGreaterEqual(asset.dimensions_final[1], 16)

    def test_predict_and_export_active_asset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            controller = ImageEngineUIController(app_paths=paths)
            asset = _asset(mode=EditMode.ADVANCED)
            controller.apply_named_preset(asset, "Web Quick Export")

            prediction = controller.predict_export(asset)
            text = controller.format_prediction_text(asset)
            export_result = controller.export_active_asset(asset)

            self.assertGreater(prediction.prediction.predicted_bytes, 0)
            self.assertIn(prediction.prediction.predicted_format.upper(), text)
            self.assertTrue(export_result.success)
            self.assertTrue(export_result.output_path.exists())
            self.assertEqual(export_result.output_path.parent, paths.exports)
            self.assertTrue(export_result.is_stub)
            self.assertEqual("placeholder", export_result.fallback_kind)

    def test_export_active_asset_accepts_custom_export_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            controller = ImageEngineUIController(app_paths=paths)
            asset = _asset(mode=EditMode.ADVANCED)
            custom_dir = Path(temp_dir) / "manual-export"

            export_result = controller.export_active_asset(asset, export_dir=custom_dir)

            self.assertTrue(export_result.success)
            self.assertTrue(export_result.output_path.exists())
            self.assertEqual(export_result.output_path.parent, custom_dir)

    @unittest.skipUnless(_pillow_available(), "Pillow required for static edited export test.")
    def test_export_active_asset_applies_background_removal_without_derived_preview(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            controller = ImageEngineUIController(app_paths=paths)

            src = Path(temp_dir) / "cutout_source.png"
            image = Image.new("RGBA", (12, 12), (255, 255, 255, 255))
            for y in range(3, 9):
                for x in range(3, 9):
                    image.putpixel((x, y), (220, 40, 40, 255))
            image.save(src, format="PNG")

            asset = _asset(mode=EditMode.ADVANCED)
            asset.original_name = "cutout_source.png"
            asset.source_uri = str(src)
            asset.cache_path = str(src)
            asset.derived_final_path = None
            asset.derived_current_path = None
            asset.format = AssetFormat.PNG
            asset.capabilities = Capabilities(has_alpha=True, is_animated=False, is_sheet=False, is_ico_bundle=False)
            asset.dimensions_original = (12, 12)
            asset.dimensions_current = (12, 12)
            asset.dimensions_final = (12, 12)
            asset.edit_state.settings.export.format = ExportFormat.PNG
            asset.edit_state.settings.alpha.background_removal_mode = "white"

            export_result = controller.export_active_asset(asset)

            self.assertTrue(export_result.success)
            self.assertFalse(export_result.is_stub)
            with Image.open(export_result.output_path) as im:
                rgba = im.convert("RGBA")
                self.assertEqual(0, rgba.getpixel((0, 0))[3])
                self.assertGreater(rgba.getpixel((5, 5))[3], 0)

    @unittest.skipUnless(_pillow_available(), "Pillow required for animated GIF export test.")
    def test_export_active_asset_applies_background_removal_to_animated_gif(self) -> None:
        from PIL import Image, ImageSequence

        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            controller = ImageEngineUIController(app_paths=paths)

            src = Path(temp_dir) / "anim_cutout.gif"
            frame_a = Image.new("RGB", (12, 12), (255, 255, 255))
            frame_b = Image.new("RGB", (12, 12), (255, 255, 255))
            for y in range(3, 9):
                for x in range(3, 9):
                    frame_a.putpixel((x, y), (220, 40, 40))
                    frame_b.putpixel((x, y), (40, 220, 40))
            frame_a.save(
                src,
                format="GIF",
                save_all=True,
                append_images=[frame_b],
                duration=[80, 120],
                loop=0,
            )

            asset = _asset(mode=EditMode.ADVANCED)
            asset.original_name = "anim_cutout.gif"
            asset.source_uri = str(src)
            asset.cache_path = str(src)
            asset.format = AssetFormat.GIF
            asset.capabilities = Capabilities(has_alpha=True, is_animated=True, is_sheet=False, is_ico_bundle=False)
            asset.dimensions_original = (12, 12)
            asset.dimensions_current = (12, 12)
            asset.dimensions_final = (12, 12)
            asset.edit_state.settings.export.format = ExportFormat.GIF
            asset.edit_state.settings.alpha.background_removal_mode = "white"

            export_result = controller.export_active_asset(asset)

            self.assertTrue(export_result.success)
            self.assertTrue(export_result.output_path.exists())
            with Image.open(export_result.output_path) as im:
                self.assertTrue(bool(getattr(im, "is_animated", False)))
                for frame in ImageSequence.Iterator(im):
                    rgba = frame.convert("RGBA")
                    self.assertEqual(0, rgba.getpixel((0, 0))[3])
                    self.assertGreater(rgba.getpixel((5, 5))[3], 0)

    @unittest.skipUnless(_pillow_available(), "Pillow required for animated GIF preview test.")
    def test_apply_light_pipeline_preserves_animated_gif_preview(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            controller = ImageEngineUIController(app_paths=paths)

            src = Path(temp_dir) / "anim_preview.gif"
            frame_a = Image.new("RGB", (12, 12), (255, 255, 255))
            frame_b = Image.new("RGB", (12, 12), (255, 255, 255))
            for y in range(3, 9):
                for x in range(3, 9):
                    frame_a.putpixel((x, y), (220, 40, 40))
                    frame_b.putpixel((x, y), (40, 220, 40))
            frame_a.save(
                src,
                format="GIF",
                save_all=True,
                append_images=[frame_b],
                duration=[80, 120],
                loop=0,
            )

            asset = _asset(mode=EditMode.ADVANCED)
            asset.original_name = "anim_preview.gif"
            asset.source_uri = str(src)
            asset.cache_path = str(src)
            asset.format = AssetFormat.GIF
            asset.capabilities = Capabilities(has_alpha=True, is_animated=True, is_sheet=False, is_ico_bundle=False)
            asset.dimensions_original = (12, 12)
            asset.edit_state.settings.alpha.background_removal_mode = "white"

            wrote = controller.apply_light_pipeline(asset)

            self.assertTrue(wrote)
            self.assertTrue(str(asset.derived_current_path).endswith(".gif"))
            self.assertTrue(str(asset.derived_final_path).endswith(".gif"))

            with Image.open(asset.derived_final_path) as im:
                self.assertTrue(bool(getattr(im, "is_animated", False)))
                self.assertGreaterEqual(int(getattr(im, "n_frames", 1)), 2)


    def test_select_export_source_prefers_cache_for_auto_animated_asset(self) -> None:
        controller = ImageEngineUIController()
        asset = _asset(mode=EditMode.SIMPLE)
        asset.capabilities = Capabilities(has_alpha=True, is_animated=True, is_sheet=False, is_ico_bundle=False)
        asset.cache_path = "C:/cache/source_anim.gif"
        asset.derived_final_path = "C:/cache/final_preview.png"
        asset.edit_state.settings.export.format = ExportFormat.AUTO

        selected = controller._select_export_source_path(asset)

        self.assertEqual(selected, "C:/cache/source_anim.gif")

    def test_select_export_source_falls_back_to_source_uri(self) -> None:
        controller = ImageEngineUIController()
        asset = _asset(mode=EditMode.SIMPLE)
        asset.cache_path = None
        asset.derived_final_path = None
        asset.source_uri = "C:/assets/source_only.png"

        selected = controller._select_export_source_path(asset)

        self.assertEqual(selected, "C:/assets/source_only.png")

    def test_select_export_source_prefers_derived_current_when_final_missing(self) -> None:
        controller = ImageEngineUIController()
        asset = _asset(mode=EditMode.SIMPLE)
        asset.derived_final_path = None
        asset.derived_current_path = "C:/cache/current_preview.png"
        asset.cache_path = "C:/cache/original.png"

        selected = controller._select_export_source_path(asset)

        self.assertEqual(selected, "C:/cache/current_preview.png")

    @unittest.skipUnless(_pillow_available(), "Pillow required for real export path test.")
    def test_export_active_asset_uses_source_uri_when_cache_missing(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            source_path = Path(temp_dir) / "source.png"
            Image.new("RGBA", (24, 24), (20, 60, 180, 255)).save(source_path, format="PNG")

            controller = ImageEngineUIController(app_paths=paths)
            asset = _asset(mode=EditMode.ADVANCED)
            asset.source_uri = str(source_path)
            asset.cache_path = None
            asset.derived_final_path = None

            export_result = controller.export_active_asset(asset)

            self.assertTrue(export_result.success)
            self.assertFalse(export_result.is_stub)
            self.assertTrue(export_result.output_path.exists())

    def test_run_batch_via_controller(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            controller = ImageEngineUIController(app_paths=paths)
            a1 = _asset(mode=EditMode.SIMPLE)
            a1.id = "batch-a1"
            a1.original_name = "enemy_sprite.png"
            a1.dimensions_original = (64, 64)
            a1.dimensions_current = (64, 64)
            a1.dimensions_final = (64, 64)
            a2 = _asset(mode=EditMode.ADVANCED)
            a2.id = "batch-a2"
            a2.original_name = "photo.jpg"
            a2.format = AssetFormat.JPG
            a2.capabilities = Capabilities(has_alpha=False, is_animated=False, is_sheet=False, is_ico_bundle=False)
            a2.dimensions_original = (800, 600)
            a2.dimensions_current = (800, 600)
            a2.dimensions_final = (800, 600)

            events: list[object] = []
            report = controller.run_batch(
                [a1, a2],
                preview_skip_mode=True,
                auto_export=True,
                auto_preset=True,
                event_callback=events.append,
            )

            self.assertEqual(report.processed_count, 2)
            self.assertEqual(report.failed_count, 0)
            self.assertEqual(len(report.items), 2)
            self.assertTrue((paths.exports).exists())
            self.assertGreaterEqual(len(list(paths.exports.iterdir())), 2)
            self.assertEqual(getattr(events[0], "event_type", None), "batch_start")
            self.assertEqual(getattr(events[-1], "event_type", None), "batch_complete")

    def test_run_batch_via_controller_supports_cancel_callback(self) -> None:
        controller = ImageEngineUIController()
        asset = _asset(mode=EditMode.SIMPLE)
        asset.id = "batch-cancel-1"

        events: list[object] = []
        report = controller.run_batch(
            [asset],
            preview_skip_mode=True,
            auto_export=False,
            auto_preset=False,
            event_callback=events.append,
            cancel_requested=lambda: True,
        )

        self.assertTrue(report.cancelled)
        self.assertEqual(len(report.items), 0)
        self.assertEqual(getattr(events[0], "event_type", None), "batch_start")
        self.assertEqual(getattr(events[-1], "event_type", None), "batch_cancelled")

    def test_apply_named_preset_auto_upgrades_mode_when_required(self) -> None:
        controller = ImageEngineUIController()
        asset = _asset(mode=EditMode.SIMPLE)
        asset.original_name = "portrait.jpg"
        asset.format = AssetFormat.JPG
        asset.capabilities = Capabilities(has_alpha=False, is_animated=False, is_sheet=False, is_ico_bundle=False)
        asset.classification_tags = ["photo"]

        summary = controller.apply_named_preset(asset, "Photo Recover")

        self.assertEqual(summary.preset_name, "Photo Recover")
        self.assertEqual(asset.edit_state.mode, EditMode.ADVANCED)

    def test_import_url_source_hydrates_detected_baseline_controls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            controller = ImageEngineUIController(app_paths=paths)
            png_bytes = _fake_png(32, 16, payload=b"hydrate")

            summary = controller.import_url_source(
                "https://example.com/hero_sprite.png",
                opener=lambda request, timeout=0: _FakeResponse(png_bytes, "image/png"),
                stream_preview=False,
            )

            asset = summary.asset
            self.assertIn("pixel_art", set(asset.classification_tags))
            self.assertGreater(len(asset.recommendations.suggested_presets), 0)
            self.assertIn("Pixel Clean Upscale", [item.preset_name for item in asset.recommendations.suggested_presets])
            self.assertEqual(asset.edit_state.settings.ai.upscale_factor, 2.0)
            self.assertEqual(asset.edit_state.settings.export.export_profile, ExportProfile.APP_ASSET)
            self.assertEqual(asset.edit_state.settings.pixel.scale_method, ScaleMethod.NEAREST)
            self.assertTrue(asset.edit_state.settings.pixel.pixel_snap)
            self.assertGreater(asset.edit_state.settings.cleanup.denoise, 0.0)
            self.assertGreater(asset.edit_state.settings.detail.sharpen_amount, 0.0)
            self.assertEqual(len(asset.edit_state.queued_heavy_jobs), 0)

    def test_analysis_inference_clamps_and_prefills_controls(self) -> None:
        controller = ImageEngineUIController()
        asset = _asset(mode=EditMode.SIMPLE)
        asset.classification_tags = ["pixel_art"]
        asset.analysis = AnalysisSummary(
            blur_score=0.76,
            noise_score=0.62,
            compression_score=0.58,
            edge_integrity_score=0.48,
            resolution_need_score=0.95,
            gif_palette_stress=None,
            warnings=[],
        )

        controller._apply_analysis_inferred_control_defaults(asset)

        self.assertEqual(asset.edit_state.settings.pixel.scale_method, ScaleMethod.NEAREST)
        self.assertTrue(asset.edit_state.settings.pixel.pixel_snap)
        self.assertGreater(asset.edit_state.settings.cleanup.denoise, 0.0)
        self.assertGreater(asset.edit_state.settings.cleanup.artifact_removal, 0.0)
        self.assertGreater(asset.edit_state.settings.detail.sharpen_amount, 0.0)
        self.assertLessEqual(asset.edit_state.settings.ai.upscale_factor, 2.0)
        self.assertEqual(len(asset.edit_state.queued_heavy_jobs), 0)

    def test_upsert_user_preset_rejects_invalid_settings_delta(self) -> None:
        controller = ImageEngineUIController()
        from image_engine_app.engine.models import PresetModel, EditMode  # local import keeps file tidy

        with self.assertRaises(ValueError):
            controller.upsert_user_preset(
                PresetModel(
                    name="Broken Preset",
                    description="invalid key",
                    settings_delta={"not_a_real_group": {"value": 1}},
                    uses_heavy_tools=False,
                    requires_apply=False,
                    mode_min=EditMode.SIMPLE,
                )
            )


if __name__ == "__main__":
    unittest.main()













