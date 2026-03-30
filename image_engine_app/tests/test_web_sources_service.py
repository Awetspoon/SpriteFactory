"""Focused tests for Web Sources direct-media resolution and stable cache usage."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest

from image_engine_app.app.paths import ensure_app_paths  # noqa: E402
from image_engine_app.app.services.web_sources_service import WebSourcesService  # noqa: E402
from image_engine_app.app.web_sources_models import Confidence, ImportTarget, SmartOptions, WebItem  # noqa: E402
from image_engine_app.engine.models import AssetRecord, AssetFormat, SourceType  # noqa: E402


class WebSourcesServiceTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()


