"""Focused tests for Web Sources direct-media resolution and stable cache usage."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest

from image_engine_app.app.paths import ensure_app_paths  # noqa: E402
from image_engine_app.app.services.web_sources_service import WebSourcesService  # noqa: E402
from image_engine_app.app.web_sources_models import Confidence, ImportTarget, ScanResults, SmartOptions, WebItem  # noqa: E402
from image_engine_app.engine.models import AssetRecord, AssetFormat, SourceType  # noqa: E402


class WebSourcesServiceTests(unittest.TestCase):
    def test_discover_index_links_returns_same_site_category_pages(self) -> None:
        html = """
        <a href="/sprites/gen-1">HOME Sprites: Gen 1</a>
        <a href="/sprites/gen-2#top">HOME Sprites: Gen 2</a>
        <a href="https://other.example.com/sprites">Other Site</a>
        <a href="/sprites/bulbasaur.png">Direct Image</a>
        <a href="/sprites/gen-1">Duplicate</a>
        """

        def opener(_request, **_kwargs):  # noqa: ANN001
            return SimpleNamespace(
                headers={"Content-Type": "text/html; charset=utf-8"},
                read=lambda: html.encode("utf-8"),
                __enter__=lambda self: self,
                __exit__=lambda *_args: False,
            )

        class _Response:
            headers = {"Content-Type": "text/html; charset=utf-8"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return html.encode("utf-8")

        service = WebSourcesService(
            app_paths=None,
            scan_webpage_images=lambda *_args, **_kwargs: None,
            import_url_source=lambda *args, **kwargs: None,
            build_web_asset_from_file=lambda **kwargs: None,
        )

        links = service.discover_index_links(
            "https://example.com/index",
            opener=lambda *_args, **_kwargs: _Response(),
        )

        self.assertEqual(
            ["HOME Sprites: Gen 1", "HOME Sprites: Gen 2"],
            [link.label for link in links],
        )
        self.assertEqual(
            ["https://example.com/sprites/gen-1", "https://example.com/sprites/gen-2"],
            [link.url for link in links],
        )

    def test_scan_pages_merges_and_dedupes_results(self) -> None:
        service = WebSourcesService(
            app_paths=None,
            scan_webpage_images=lambda *_args, **_kwargs: None,
            import_url_source=lambda *args, **kwargs: None,
            build_web_asset_from_file=lambda **kwargs: None,
        )

        def scan_area(area_url, **_kwargs):  # noqa: ANN001
            if str(area_url).endswith("one"):
                return ScanResults(
                    items=(
                        WebItem(
                            url="https://cdn.example.com/a.png",
                            name="a.png",
                            ext=".png",
                            confidence=Confidence.DIRECT,
                            source_page=str(area_url),
                        ),
                    ),
                    filtered_count=1,
                )
            return ScanResults(
                items=(
                    WebItem(
                        url="https://cdn.example.com/a.png",
                        name="a.png",
                        ext=".png",
                        confidence=Confidence.DIRECT,
                        source_page=str(area_url),
                    ),
                    WebItem(
                        url="https://cdn.example.com/b.gif",
                        name="b.gif",
                        ext=".gif",
                        confidence=Confidence.DIRECT,
                        source_page=str(area_url),
                    ),
                ),
                filtered_count=2,
            )

        service.scan_area = scan_area  # type: ignore[method-assign]

        results = service.scan_pages(["https://example.com/one", "https://example.com/two"])

        self.assertEqual(["a.png", "b.gif"], [item.name for item in results.items])
        self.assertEqual(3, results.filtered_count)

    def test_scan_pages_skips_failed_pages_and_keeps_successful_results(self) -> None:
        service = WebSourcesService(
            app_paths=None,
            scan_webpage_images=lambda *_args, **_kwargs: None,
            import_url_source=lambda *args, **kwargs: None,
            build_web_asset_from_file=lambda **kwargs: None,
        )

        def scan_area(area_url, **_kwargs):  # noqa: ANN001
            if str(area_url).endswith("slow"):
                raise TimeoutError("timed out")
            return ScanResults(
                items=(
                    WebItem(
                        url="https://cdn.example.com/a.png",
                        name="a.png",
                        ext=".png",
                        confidence=Confidence.DIRECT,
                        source_page=str(area_url),
                    ),
                ),
                filtered_count=0,
            )

        service.scan_area = scan_area  # type: ignore[method-assign]

        results = service.scan_pages(["https://example.com/slow", "https://example.com/good"])

        self.assertEqual(["a.png"], [item.name for item in results.items])
        self.assertEqual(1, len(results.failed_pages))
        self.assertIn("https://example.com/slow", results.failed_pages[0])
        self.assertIn("timed out", results.failed_pages[0])

    def test_resolve_download_url_prefers_file_specific_candidate_over_logo(self) -> None:
        def scan_webpage_images(_page_url, **_kwargs):  # noqa: ANN001
            return SimpleNamespace(
                images=[
                    SimpleNamespace(
                        url="https://static.wikia.nocookie.net/pokemon/images/logo.png",
                        width=160,
                        height=90,
                    ),
                    SimpleNamespace(
                        url=(
                            "https://static.wikia.nocookie.net/pokemon/images/a/a2/"
                            "GB_Sounds_sprite.png/revision/latest?cb=20250312"
                        ),
                        width=500,
                        height=500,
                    ),
                ]
            )

        service = WebSourcesService(
            app_paths=None,
            scan_webpage_images=scan_webpage_images,
            import_url_source=lambda *args, **kwargs: None,
            build_web_asset_from_file=lambda **kwargs: None,
        )

        item = WebItem(
            url="https://pokemon.fandom.com/wiki/File:GB_Sounds_sprite.png",
            name="File:GB Sounds sprite.png",
            ext=".png",
            confidence=Confidence.DIRECT,
            source_page="https://pokemon.fandom.com/wiki/File:GB_Sounds_sprite.png",
        )

        resolved = service.resolve_download_url(
            item=item,
            canonical_url="https://pokemon.fandom.com/wiki/Special:Redirect/file/GB_Sounds_sprite.png",
            source_page="https://pokemon.fandom.com/wiki/File:GB_Sounds_sprite.png",
        )

        self.assertIn("GB_Sounds_sprite.png", resolved)
        self.assertIn("revision/latest", resolved)

    def test_download_items_uses_resolved_media_url_and_stable_canonical_cache_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            import_calls: list[dict] = []

            def scan_webpage_images(_page_url, **_kwargs):  # noqa: ANN001
                return SimpleNamespace(
                    images=[
                        SimpleNamespace(
                            url=(
                                "https://static.wikia.nocookie.net/pokemon/images/a/a2/"
                                "GB_Sounds_sprite.png/revision/latest?cb=20250312"
                            ),
                            width=500,
                            height=500,
                        )
                    ]
                )

            def import_url_source(url, **kwargs):  # noqa: ANN001
                import_calls.append({"url": url, **kwargs})
                asset = AssetRecord(
                    source_type=SourceType.WEBPAGE_ITEM,
                    source_uri=url,
                    cache_path=str(paths.cache / "web_sources" / "items" / "mock.png"),
                    original_name=str(kwargs.get("display_name") or "GB_Sounds_sprite.png"),
                    format=AssetFormat.PNG,
                )
                return SimpleNamespace(asset=asset)

            service = WebSourcesService(
                app_paths=paths,
                scan_webpage_images=scan_webpage_images,
                import_url_source=import_url_source,
                build_web_asset_from_file=lambda **kwargs: AssetRecord(
                    source_type=SourceType.WEBPAGE_ITEM,
                    source_uri=str(kwargs.get("source_uri") or ""),
                    cache_path=str(kwargs.get("file_path")),
                    original_name=str(kwargs.get("display_name") or Path(str(kwargs.get("file_path"))).name),
                    format=AssetFormat.PNG,
                ),
            )

            items = [
                WebItem(
                    url="https://pokemon.fandom.com/wiki/File:GB_Sounds_sprite.png",
                    name="File:GB Sounds sprite.png",
                    ext=".png",
                    confidence=Confidence.DIRECT,
                    source_page="https://pokemon.fandom.com/wiki/File:GB_Sounds_sprite.png",
                )
            ]

            report = service.download_items(
                items,
                ImportTarget.NORMAL,
                smart=SmartOptions(show_likely=False, auto_sort=True, skip_duplicates=False, allow_zip=True),
            )

            self.assertEqual(1, len(report.assets))
            self.assertEqual(0, len(report.failed))
            self.assertEqual(1, len(import_calls))
            self.assertIn("static.wikia.nocookie.net", import_calls[0]["url"])
            self.assertEqual(
                "https://pokemon.fandom.com/wiki/Special:Redirect/file/GB_Sounds_sprite.png",
                import_calls[0]["cache_key_url"],
            )
            headers = import_calls[0]["request_headers"]
            self.assertIn("User-Agent", headers)
            self.assertIn("Referer", headers)
            self.assertEqual(
                "https://pokemon.fandom.com/wiki/File:GB_Sounds_sprite.png",
                headers["Referer"],
            )

    def test_download_items_keeps_going_when_media_resolution_fails(self) -> None:
        imported_urls: list[str] = []

        def import_url_source(url, **_kwargs):  # noqa: ANN001
            imported_urls.append(url)
            return SimpleNamespace(
                asset=AssetRecord(
                    source_type=SourceType.WEBPAGE_ITEM,
                    source_uri=url,
                    cache_path="good.png",
                    original_name="good.png",
                    format=AssetFormat.PNG,
                )
            )

        service = WebSourcesService(
            app_paths=None,
            scan_webpage_images=lambda *_args, **_kwargs: None,
            import_url_source=import_url_source,
            build_web_asset_from_file=lambda **_kwargs: None,
        )

        def resolve_download_url(*, item, canonical_url, **_kwargs):  # noqa: ANN001
            if item.name == "bad.png":
                raise TimeoutError("media lookup timed out")
            return canonical_url

        service.resolve_download_url = resolve_download_url  # type: ignore[method-assign]
        items = [
            WebItem(
                url="https://example.com/bad.png",
                name="bad.png",
                ext=".png",
                confidence=Confidence.DIRECT,
            ),
            WebItem(
                url="https://example.com/good.png",
                name="good.png",
                ext=".png",
                confidence=Confidence.DIRECT,
            ),
        ]

        report = service.download_items(
            items,
            ImportTarget.NORMAL,
            smart=SmartOptions(show_likely=False, auto_sort=True, skip_duplicates=False, allow_zip=True),
        )

        self.assertEqual(["https://example.com/good.png"], imported_urls)
        self.assertEqual(1, len(report.assets))
        self.assertEqual(1, len(report.failed))
        self.assertIn("bad.png: media lookup timed out", report.failed[0])


if __name__ == "__main__":
    unittest.main()


