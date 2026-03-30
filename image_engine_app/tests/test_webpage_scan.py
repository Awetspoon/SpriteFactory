"""Tests for webpage image extraction and URL harvest logic."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError


from image_engine_app.engine.ingest.webpage_scan import (  # noqa: E402
    WebpageScanCancelledError,
    WebpageScanFilters,
    extract_image_urls_from_html,
    fetch_html,
    scan_webpages_depth,
    scan_webpage_for_images,
)


HTML_SAMPLE = """
<!doctype html>
<html>
  <body>
    <img src="/images/a.png" width="64" height="64" alt="A">
    <img src="/images/tiny.png" width="8" height="8">
    <img src="https://cdn.example.com/b.jpg?ver=1" width="16" height="16">
    <img data-src="lazy/c.webp" width="128" height="96">
    <img src="/images/a.png" width="64" height="64">
    <img src="/images/not_supported.svg" width="200" height="200">
    <a href="downloads/icon.ico">Download ICO</a>
    <source srcset="/responsive/x1.png 1x, /responsive/x2.png 2x">
  </body>
</html>
"""


class _FakeResponse:
    def __init__(self, data: bytes, content_type: str = "text/html; charset=utf-8") -> None:
        self._data = data
        self.headers = {"Content-Type": content_type}

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            return self._data
        return self._data[:size]

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class WebpageScanTests(unittest.TestCase):

    def test_extract_image_urls_resolves_and_dedupes(self) -> None:
        result = extract_image_urls_from_html(
            HTML_SAMPLE,
            base_url="https://example.com/gallery/page.html",
        )

        urls = [item.url for item in result.images]
        self.assertIn("https://example.com/images/a.png", urls)
        self.assertIn("https://cdn.example.com/b.jpg?ver=1", urls)
        self.assertIn("https://example.com/gallery/lazy/c.webp", urls)
        self.assertIn("https://example.com/gallery/downloads/icon.ico", urls)
        self.assertIn("https://example.com/responsive/x1.png", urls)
        self.assertIn("https://example.com/responsive/x2.png", urls)
        self.assertEqual(urls.count("https://example.com/images/a.png"), 1)
        self.assertIn(
            "https://example.com/images/not_supported.svg",
            [item.url for item in result.filtered_out],
        )

    def test_filters_apply_extension_and_html_size_attrs(self) -> None:
        result = extract_image_urls_from_html(
            HTML_SAMPLE,
            base_url="https://example.com/gallery/page.html",
            filters=WebpageScanFilters(
                allowed_extensions={".png", ".ico"},
                min_width=32,
                min_height=32,
            ),
        )

        urls = [item.url for item in result.images]
        self.assertEqual(set(urls), {
            "https://example.com/images/a.png",
            "https://example.com/gallery/downloads/icon.ico",
            "https://example.com/responsive/x1.png",
            "https://example.com/responsive/x2.png",
        })

        filtered_urls = [item.url for item in result.filtered_out]
        self.assertIn("https://cdn.example.com/b.jpg?ver=1", filtered_urls)
        self.assertIn("https://example.com/images/tiny.png", filtered_urls)


    def test_can_disable_srcset_collection(self) -> None:
        result = extract_image_urls_from_html(
            HTML_SAMPLE,
            base_url="https://example.com/gallery/page.html",
            filters=WebpageScanFilters(include_srcset=False),
        )
        urls = [item.url for item in result.images]
        # srcset-derived responsive URLs should not be present
        self.assertNotIn("https://example.com/responsive/x1.png", urls)
        self.assertNotIn("https://example.com/responsive/x2.png", urls)

    def test_fetch_html_retries_without_proxy_on_winerror_10013(self) -> None:
        calls = {"primary": 0, "fallback": 0}

        def primary_urlopen(request, timeout=0):  # noqa: ANN001
            _ = (request, timeout)
            calls["primary"] += 1
            raise URLError(OSError(10013, "An attempt was made to access a socket in a way forbidden by its access permissions"))

        class _DirectOpener:
            def open(self, request, timeout=0):  # noqa: ANN001
                _ = (request, timeout)
                calls["fallback"] += 1
                return _FakeResponse(b"<html><body><img src='/images/a.png'></body></html>")

        with patch("image_engine_app.engine.ingest.webpage_scan.urlopen", primary_urlopen), patch(
            "image_engine_app.engine.ingest.webpage_scan.build_opener",
            lambda *_args, **_kwargs: _DirectOpener(),
        ):
            html = fetch_html("https://example.com/gallery/page.html")

        self.assertIn("/images/a.png", html)
        self.assertEqual(1, calls["primary"])
        self.assertEqual(1, calls["fallback"])

    def test_fetch_html_retries_on_http_403_with_alternate_headers(self) -> None:
        attempts = {"count": 0}

        def opener(request, timeout=0):  # noqa: ANN001
            _ = timeout
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise HTTPError(
                    url=request.full_url,
                    code=403,
                    msg="Forbidden",
                    hdrs=None,
                    fp=None,
                )
            return _FakeResponse(b"<html><body><img src=\"/images/retry.png\"></body></html>")

        html = fetch_html("https://example.com/gallery/page.html", opener=opener)

        self.assertIn("/images/retry.png", html)
        self.assertEqual(2, attempts["count"])

    def test_scan_webpage_for_images_fetches_html_with_mocked_opener(self) -> None:
        def opener(request, timeout=0):  # noqa: ANN001
            _ = (request, timeout)
            return _FakeResponse(HTML_SAMPLE.encode("utf-8"))

        result = scan_webpage_for_images(
            "https://example.com/gallery/page.html",
            opener=opener,
        )

        self.assertGreaterEqual(len(result.images), 6)
        self.assertEqual(result.page_url, "https://example.com/gallery/page.html")

    def test_scan_webpage_for_images_respects_cancel_callback(self) -> None:
        calls = {"count": 0}

        def opener(request, timeout=0):  # noqa: ANN001
            _ = (request, timeout)
            calls["count"] += 1
            return _FakeResponse(HTML_SAMPLE.encode("utf-8"))

        with self.assertRaises(WebpageScanCancelledError):
            scan_webpage_for_images(
                "https://example.com/gallery/page.html",
                opener=opener,
                cancel_requested=lambda: True,
            )

        self.assertEqual(0, calls["count"])

    def test_extract_image_urls_collects_meta_link_and_likely_anchor_urls(self) -> None:
        html = (
            "<html><head>"
            "<meta property='og:image' content='/media/cover?id=7'>"
            "<link rel='apple-touch-icon' href='/icons/app-icon.png'>"
            "</head><body>"
            "<a href='/files/1234/?do=download'>Download sprite</a>"
            "</body></html>"
        )

        result = extract_image_urls_from_html(html, base_url="https://example.com/gallery")
        urls = {item.url for item in result.images}

        self.assertIn("https://example.com/media/cover?id=7", urls)
        self.assertIn("https://example.com/icons/app-icon.png", urls)
        self.assertIn("https://example.com/files/1234/?do=download", urls)

    def test_scan_accepts_text_plain_html_content_type(self) -> None:
        html = "<html><body><img src='/sprites/a.png'></body></html>".encode("utf-8")

        def opener(request, timeout=0):  # noqa: ANN001
            _ = (request, timeout)
            return _FakeResponse(html, "text/plain; charset=utf-8")

        result = scan_webpage_for_images(
            "https://example.com/gallery/page.html",
            opener=opener,
        )

        urls = {item.url for item in result.images}
        self.assertIn("https://example.com/sprites/a.png", urls)

    def test_max_images_caps_results(self) -> None:
        def opener(request, timeout=0):
            _ = (request, timeout)
            return _FakeResponse(HTML_SAMPLE.encode("utf-8"))

        result = scan_webpage_for_images(
            "https://example.com/gallery/page.html",
            opener=opener,
            max_images=2,
        )
        self.assertEqual(len(result.images), 2)

    def test_depth_scan_sets_suggested_group_and_name(self) -> None:
        pages: dict[str, str] = {
            "https://example.com/sprites": "<html><body><a href='/pokedex/pikachu'>Pikachu</a></body></html>",
            "https://example.com/pokedex/pikachu": "<html><body><img src='/images/pikachu.png' alt='Pikachu'></body></html>",
        }

        def opener(request, timeout=0):  # noqa: ANN001
            url = getattr(request, 'full_url', None)
            if not url and hasattr(request, 'get_full_url'):
                url = request.get_full_url()
            html = pages.get(str(url), "<html></html>")
            return _FakeResponse(html.encode('utf-8'))

        result = scan_webpage_for_images(
            "https://example.com/sprites",
            opener=opener,
            max_depth=1,
            same_domain_only=True,
            max_pages=10,
        )

        pikachu = [img for img in result.images if img.url.endswith('/images/pikachu.png')]
        self.assertEqual(len(pikachu), 1)
        img = pikachu[0]
        self.assertEqual(img.source_page_url, "https://example.com/pokedex/pikachu")
        self.assertEqual(img.suggested_group, "pikachu")
        self.assertTrue((img.suggested_name or "").endswith("pikachu.png"))


    def test_suggest_name_prefers_url_stem_over_generic_alt(self) -> None:
        html = "<html><body><img src='/images/shiny-sprite/venusaur-f.gif' alt='Enlarge image'></body></html>"
        result = extract_image_urls_from_html(html, base_url="https://projectpokemon.org/gallery")
        self.assertEqual(len(result.images), 1)
        self.assertEqual(result.images[0].suggested_name, "venusaur-f.gif")

    def test_suggest_name_uses_alt_when_url_stem_looks_hashed(self) -> None:
        html = "<html><body><img src='/images/a6b87e5850a2397b8a6594a5cf735b5d.png' alt='Bulbasaur'></body></html>"
        result = extract_image_urls_from_html(html, base_url="https://example.com/gallery")
        self.assertEqual(len(result.images), 1)
        self.assertEqual(result.images[0].suggested_name, "bulbasaur.png")

    def test_depth_scan_routes_to_scan_function(self) -> None:
        def opener(request, timeout=0):  # noqa: ANN001
            _ = (request, timeout)
            return _FakeResponse(HTML_SAMPLE.encode("utf-8"))

        results = scan_webpages_depth(
            ["https://example.com/gallery/page.html"],
            max_depth=1,
            opener=opener,
        )

        self.assertEqual(len(results), 1)
        self.assertGreaterEqual(len(results[0].images), 6)
        self.assertGreaterEqual(results[0].pages_scanned, 1)


if __name__ == "__main__":
    unittest.main()










