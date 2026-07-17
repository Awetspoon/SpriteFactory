"""Page discovery and file-link scanning for Web Sources."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urljoin, urlparse

from image_engine_app.app.web_sources_models import (
    Confidence,
    ScanResults,
    WebIndexLink,
    WebItem,
)
from image_engine_app.engine.ingest.url_ingest import validate_url
from image_engine_app.engine.ingest.web_sources_rules import (
    ALLOWED_ARCHIVE_EXTS_DEFAULT,
    ALLOWED_IMAGE_EXTS_DEFAULT,
    confidence_for,
    normalize_ext,
    suggested_name_from_url,
)
from image_engine_app.engine.ingest.webpage_scan import (
    WebpageScanCancelledError,
    WebpageScanFilters,
    fetch_html,
)


class _IndexLinkParser(HTMLParser):
    def __init__(self, *, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: list[tuple[str, str]] = []
        self._href_stack: list[str | None] = []
        self._text_stack: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a":
            return
        attr_map = {name.casefold(): (value or "") for name, value in attrs}
        self._href_stack.append(str(attr_map.get("href", "")).strip() or None)
        self._text_stack.append([])

    def handle_data(self, data: str) -> None:
        if self._text_stack:
            self._text_stack[-1].append(str(data or ""))

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() != "a" or not self._href_stack:
            return
        href = self._href_stack.pop()
        text_parts = self._text_stack.pop() if self._text_stack else []
        if href:
            label = " ".join(" ".join(text_parts).split())
            self.links.append((label, urljoin(self.base_url, href)))


@dataclass
class WebSourcesScanner:
    """Scan pages without owning saved pages, downloads, or UI state."""

    scan_webpage_images: Callable[..., object]
    canonicalize_download_url: Callable[[str], str]
    resolve_web_item_name: Callable[[str | None, str], str]
    extract_archive_urls: Callable[..., list[str]]

    def scan_page(
        self,
        page_url: str,
        *,
        allowed_exts: set[str] | None = None,
        show_likely: bool = False,
        opener=None,
        cancel_requested=None,
    ) -> ScanResults:
        normalized_page_url = validate_url(str(page_url or "").strip())
        self._raise_if_cancelled(cancel_requested)

        merged_allowed = {ext.casefold() for ext in (allowed_exts or set())}
        if not merged_allowed:
            merged_allowed.update(ALLOWED_IMAGE_EXTS_DEFAULT)
            merged_allowed.update(ALLOWED_ARCHIVE_EXTS_DEFAULT)

        direct_ext = normalize_ext(normalized_page_url)
        direct_confidence = confidence_for(normalized_page_url, allowed_exts=merged_allowed)
        if direct_confidence is Confidence.DIRECT and direct_ext in merged_allowed:
            name = self.resolve_web_item_name(
                suggested_name_from_url(normalized_page_url),
                normalized_page_url,
            )
            return ScanResults(
                items=(
                    WebItem(
                        url=normalized_page_url,
                        name=name,
                        ext=direct_ext,
                        confidence=Confidence.DIRECT,
                        preview_url=normalized_page_url,
                        source_page=normalized_page_url,
                    ),
                )
            )

        image_allowed = {ext for ext in merged_allowed if ext in ALLOWED_IMAGE_EXTS_DEFAULT}
        if not image_allowed:
            image_allowed = set(ALLOWED_IMAGE_EXTS_DEFAULT)

        scan = self.scan_webpage_images(
            normalized_page_url,
            max_depth=0,
            same_domain_only=False,
            max_pages=1,
            dedupe_images=True,
            filters=WebpageScanFilters(
                allowed_extensions=image_allowed,
                dedupe=True,
                include_srcset=True,
                include_anchor_image_links=True,
            ),
            opener=opener,
            cancel_requested=cancel_requested,
        )

        direct_items: list[WebItem] = []
        likely_items: list[WebItem] = []
        seen_urls: set[str] = set()
        filtered = len(getattr(scan, "filtered_out", ()) or ())

        for hit in getattr(scan, "images", ()):
            self._raise_if_cancelled(cancel_requested)
            raw_url = str(getattr(hit, "url", "")).strip()
            if not raw_url:
                continue

            source_page = str(getattr(hit, "source_page_url", "") or normalized_page_url)
            url = self.canonicalize_download_url(raw_url) or raw_url
            if url in seen_urls:
                continue
            seen_urls.add(url)

            confidence = confidence_for(url, allowed_exts=merged_allowed)
            if confidence is Confidence.UNKNOWN:
                filtered += 1
                continue

            suggested = str(getattr(hit, "suggested_name", "") or "").strip()
            item = WebItem(
                url=url,
                name=self.resolve_web_item_name(suggested, raw_url),
                ext=normalize_ext(url) or normalize_ext(raw_url),
                confidence=confidence,
                preview_url=(url if url != raw_url else raw_url),
                source_page=(raw_url if url != raw_url else source_page),
            )
            if confidence is Confidence.DIRECT:
                direct_items.append(item)
            else:
                likely_items.append(item)

        if show_likely:
            items: list[WebItem] = [*direct_items, *likely_items]
        elif direct_items:
            items = list(direct_items)
            filtered += len(likely_items)
        else:
            items = list(likely_items)

        if any(ext in merged_allowed for ext in ALLOWED_ARCHIVE_EXTS_DEFAULT):
            try:
                html = fetch_html(
                    normalized_page_url,
                    opener=opener,
                    cancel_requested=cancel_requested,
                )
                for archive_url in self.extract_archive_urls(
                    html,
                    base_url=normalized_page_url,
                    allowed_archives=merged_allowed,
                ):
                    self._raise_if_cancelled(cancel_requested)
                    if archive_url in seen_urls:
                        continue
                    seen_urls.add(archive_url)
                    items.append(
                        WebItem(
                            url=archive_url,
                            name=suggested_name_from_url(archive_url),
                            ext=normalize_ext(archive_url),
                            confidence=Confidence.DIRECT,
                            preview_url=archive_url,
                            source_page=normalized_page_url,
                        )
                    )
            except WebpageScanCancelledError:
                raise
            except Exception:
                # Archive discovery is optional; image results remain usable.
                pass

        return ScanResults(items=tuple(items), filtered_count=filtered)

    def discover_links(
        self,
        index_url: str,
        *,
        opener=None,
        same_domain_only: bool = True,
        cancel_requested=None,
    ) -> tuple[WebIndexLink, ...]:
        normalized_url = validate_url(str(index_url or "").strip())
        self._raise_if_cancelled(cancel_requested)
        html = fetch_html(normalized_url, opener=opener, cancel_requested=cancel_requested)
        parser = _IndexLinkParser(base_url=normalized_url)
        parser.feed(html)

        seed_host = urlparse(normalized_url).netloc.casefold()
        seen: set[str] = set()
        links: list[WebIndexLink] = []
        for raw_label, raw_url in parser.links:
            self._raise_if_cancelled(cancel_requested)
            url = self._normalize_link_url(raw_url)
            if not url or url in seen:
                continue
            parsed = urlparse(url)
            if parsed.scheme.casefold() not in {"http", "https"}:
                continue
            if same_domain_only and parsed.netloc.casefold() != seed_host:
                continue
            if normalize_ext(url) in ALLOWED_IMAGE_EXTS_DEFAULT | ALLOWED_ARCHIVE_EXTS_DEFAULT:
                continue
            seen.add(url)
            links.append(
                WebIndexLink(
                    label=self._link_label(raw_label, url),
                    url=url,
                    source_page=normalized_url,
                )
            )
        return tuple(links)

    def scan_pages(
        self,
        page_urls: list[str],
        *,
        allowed_exts: set[str] | None = None,
        show_likely: bool = False,
        opener=None,
        progress_callback=None,
        cancel_requested=None,
    ) -> ScanResults:
        items: list[WebItem] = []
        seen_urls: set[str] = set()
        filtered_count = 0
        failed_pages: list[str] = []
        total_pages = len(page_urls)

        def emit_progress(done_count: int, message: str) -> None:
            if progress_callback is not None:
                progress_callback(done_count, total_pages, message)

        emit_progress(0, f"Preparing to scan {total_pages} page(s)...")
        for index, page_url in enumerate(page_urls, start=1):
            self._raise_if_cancelled(cancel_requested)
            normalized = str(page_url or "").strip()
            if not normalized:
                continue
            try:
                page_result = self.scan_page(
                    normalized,
                    allowed_exts=allowed_exts,
                    show_likely=show_likely,
                    opener=opener,
                    cancel_requested=cancel_requested,
                )
            except WebpageScanCancelledError:
                raise
            except Exception as exc:
                detail = " ".join(str(exc).split()) or exc.__class__.__name__
                failed_pages.append(f"{normalized}: {detail}")
                emit_progress(index, f"Page {index}/{total_pages} failed")
                continue

            filtered_count += int(page_result.filtered_count or 0)
            for item in page_result.items:
                key = self.canonicalize_download_url(item.url) or item.url
                if key in seen_urls:
                    continue
                seen_urls.add(key)
                items.append(item)
            emit_progress(index, f"Scanned page {index}/{total_pages}")

        return ScanResults(
            items=tuple(items),
            filtered_count=filtered_count,
            failed_pages=tuple(failed_pages),
        )

    @staticmethod
    def _raise_if_cancelled(cancel_requested) -> None:  # noqa: ANN001
        if callable(cancel_requested) and bool(cancel_requested()):
            raise WebpageScanCancelledError("Scan cancelled")

    @staticmethod
    def _normalize_link_url(raw_url: str) -> str:
        parsed = urlparse(str(raw_url or "").strip())
        if not parsed.scheme or not parsed.netloc:
            return ""
        return parsed._replace(fragment="").geturl()

    @staticmethod
    def _link_label(raw_label: str, url: str) -> str:
        label = " ".join(str(raw_label or "").split())
        if label:
            return label
        parsed = urlparse(str(url or "").strip())
        path_name = unquote(Path(parsed.path).name).strip()
        if path_name:
            return path_name.replace("-", " ").replace("_", " ").strip().title()
        return parsed.netloc or "Linked Page"
