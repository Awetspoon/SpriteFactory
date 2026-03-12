"""Webpage image extraction / URL harvest logic (Prompt 5)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from html.parser import HTMLParser
from pathlib import Path
import re
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import ProxyHandler, Request, build_opener, urlopen


SUPPORTED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".tif",
    ".tiff",
    ".bmp",
    ".ico",
    ".gif",
}

USER_AGENT = "ImageEngine/0.1 (Prompt5 Webpage Scan)"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class WebpageScanCancelledError(Exception):
    """Raised when webpage scanning is cancelled by the caller/UI."""


def _is_cancel_requested(cancel_requested: Callable[[], bool] | None) -> bool:
    if cancel_requested is None:
        return False
    try:
        return bool(cancel_requested())
    except Exception:
        return False



def _is_socket_access_denied(exc: Exception) -> bool:
    reason = getattr(exc, "reason", exc)
    win_error = getattr(reason, "winerror", None)
    if win_error == 10013:
        return True

    message = str(reason or exc).lower()
    return "winerror 10013" in message or "forbidden by its access permissions" in message


def _open_with_socket_fallback(
    request: Request,
    *,
    timeout: float,
    opener: Callable[..., object] | None,
) -> object:
    open_fn = opener or urlopen
    try:
        return open_fn(request, timeout=timeout)
    except Exception as exc:
        if opener is not None or not _is_socket_access_denied(exc):
            raise

        direct_opener = build_opener(ProxyHandler({}))
        return direct_opener.open(request, timeout=timeout)


def _origin_url(page_url: str) -> str:
    parsed = urlparse(page_url)
    if not parsed.scheme or not parsed.netloc:
        return page_url
    return f"{parsed.scheme}://{parsed.netloc}/"


def _html_request_header_profiles(page_url: str) -> list[dict[str, str]]:
    origin = _origin_url(page_url)
    return [
        {
            "User-Agent": BROWSER_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "identity",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": origin,
        },
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "identity",
            "Referer": origin,
        },
    ]


def _is_retryable_fetch_error(exc: Exception) -> bool:
    if isinstance(exc, HTTPError):
        code = int(getattr(exc, "code", 0) or 0)
        return code in {401, 403, 406, 408, 429} or code >= 500
    if isinstance(exc, URLError):
        return True
    return _is_socket_access_denied(exc)


def _charset_from_content_type(content_type: str | None) -> str | None:
    if not content_type:
        return None
    match = re.search(r"charset\s*=\s*([^\s;]+)", content_type, flags=re.IGNORECASE)
    if not match:
        return None
    return str(match.group(1)).strip().strip("\"")


def _decode_html_payload(payload: bytes, *, content_type: str | None) -> str:
    preferred = _charset_from_content_type(content_type)
    if preferred:
        try:
            return payload.decode(preferred, errors="replace")
        except (LookupError, ValueError):
            pass

    for encoding in ("utf-8", "latin-1"):
        try:
            return payload.decode(encoding, errors="replace")
        except (LookupError, ValueError):
            continue
    return payload.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class HarvestedImageUrl:
    """Image URL discovered from a webpage, plus lightweight metadata when available."""

    url: str
    source_tag: str
    width: int | None = None
    height: int | None = None
    alt: str | None = None

    # Naming / grouping hints (used by Webpage Scan UI for auto-naming + folder grouping).
    source_page_url: str | None = None
    suggested_name: str | None = None
    suggested_group: str | None = None


@dataclass
class WebpageScanFilters:
    """Filters that can be applied without downloading image binaries."""

    allowed_extensions: set[str] | None = None
    min_width: int | None = None
    min_height: int | None = None
    dedupe: bool = True
    include_srcset: bool = True
    include_anchor_image_links: bool = True


@dataclass
class WebpageScanResult:
    """Webpage scan output including accepted and filtered URLs."""

    page_url: str
    images: list[HarvestedImageUrl] = field(default_factory=list)
    filtered_out: list[HarvestedImageUrl] = field(default_factory=list)
    pages_scanned: int = 0


class _ImageUrlHTMLParser(HTMLParser):
    _STYLE_URL_RE = re.compile(r"url\((['\"]?)([^\)\"']+)\1\)", re.IGNORECASE)

    def __init__(
        self,
        base_url: str,
        *,
        include_srcset: bool = True,
        include_anchor_image_links: bool = True,
    ) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.include_srcset = include_srcset
        self.include_anchor_image_links = include_anchor_image_links
        self.candidates: list[HarvestedImageUrl] = []

    def _append_candidate(
        self,
        raw_url: str,
        *,
        source_tag: str,
        width: int | None = None,
        height: int | None = None,
        alt: str | None = None,
    ) -> None:
        candidate = str(raw_url or "").strip()
        if not candidate:
            return
        self.candidates.append(
            HarvestedImageUrl(
                url=_normalize_url(candidate, self.base_url),
                source_tag=source_tag,
                width=width,
                height=height,
                alt=alt,
                source_page_url=self.base_url,
            )
        )

    def _append_style_urls(self, style_value: str, *, source_tag: str) -> None:
        for match in self._STYLE_URL_RE.finditer(style_value or ""):
            url_value = str(match.group(2) or "").strip()
            if not url_value:
                continue
            self._append_candidate(url_value, source_tag=source_tag)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_name = tag.lower()
        attr_map = {name.lower(): (value or "") for name, value in attrs}

        style_attr = attr_map.get("style", "")
        if style_attr:
            self._append_style_urls(style_attr, source_tag=f"{tag_name}[style]")

        if tag_name == "img":
            width = _parse_int(attr_map.get("width"))
            height = _parse_int(attr_map.get("height"))
            alt = attr_map.get("alt") or None
            for key in (
                "src",
                "data-src",
                "data-original",
                "data-lazy-src",
                "data-full",
                "data-image",
                "data-url",
                "data-fileurl",
            ):
                value = attr_map.get(key, "")
                if not value:
                    continue
                self._append_candidate(value, source_tag=f"img[{key}]", width=width, height=height, alt=alt)

            if self.include_srcset:
                for key in ("srcset", "data-srcset"):
                    srcset = attr_map.get(key, "")
                    if not srcset:
                        continue
                    for item_url in _parse_srcset_urls(srcset, self.base_url):
                        self._append_candidate(item_url, source_tag=f"img[{key}]", alt=alt)
            return

        if tag_name in {"source", "video"}:
            for key in ("src", "data-src", "poster"):
                value = attr_map.get(key, "")
                if not value:
                    continue
                self._append_candidate(value, source_tag=f"{tag_name}[{key}]")

            if self.include_srcset:
                for key in ("srcset", "data-srcset"):
                    srcset = attr_map.get(key, "")
                    if not srcset:
                        continue
                    for item_url in _parse_srcset_urls(srcset, self.base_url):
                        self._append_candidate(item_url, source_tag=f"{tag_name}[{key}]")
            return

        if tag_name == "meta":
            meta_key = (attr_map.get("property") or attr_map.get("name") or "").strip().lower()
            if meta_key in {
                "og:image",
                "og:image:url",
                "og:image:secure_url",
                "twitter:image",
                "twitter:image:src",
            }:
                content = attr_map.get("content", "")
                if content:
                    self._append_candidate(content, source_tag=f"meta[{meta_key}]")
            return

        if tag_name == "link":
            href = attr_map.get("href", "")
            if not href:
                return
            rel_tokens = {
                token.strip().lower()
                for token in str(attr_map.get("rel", "")).split()
                if token.strip()
            }
            normalized = _normalize_url(href, self.base_url)
            if (
                _looks_like_media_url(normalized)
                or "icon" in rel_tokens
                or "apple-touch-icon" in rel_tokens
                or "image_src" in rel_tokens
            ):
                self._append_candidate(href, source_tag="link[href]")
            return

        if tag_name == "a":
            if not self.include_anchor_image_links:
                return
            href = attr_map.get("href", "")
            if not href:
                return
            normalized = _normalize_url(href, self.base_url)
            if _looks_like_media_url(normalized):
                self._append_candidate(href, source_tag="a[href]")

def _parse_int(raw: str | None) -> int | None:
    if not raw:
        return None
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return None
    return int(digits)


def _parse_srcset_urls(srcset: str, base_url: str) -> list[str]:
    urls: list[str] = []
    for part in srcset.split(","):
        item = part.strip()
        if not item:
            continue
        first_token = item.split()[0]
        urls.append(_normalize_url(first_token, base_url))
    return urls


def _normalize_url(candidate: str, base_url: str) -> str:
    return urljoin(base_url, candidate.strip())


def _extension_from_url(url: str) -> str:
    path = urlparse(url).path
    return Path(path).suffix.lower()


def _looks_like_image_url(url: str) -> bool:
    return _extension_from_url(url) in SUPPORTED_IMAGE_EXTENSIONS


_LIKELY_URL_HINTS = (
    "/image",
    "/images",
    "/img",
    "/sprite",
    "/sprites",
    "/media",
    "/upload",
    "/uploads",
    "/attachment",
    "/attachments",
    "/file",
    "/files",
    "/download",
    "/thumb",
    "/thumbnail",
    "image=",
    "img=",
    "sprite=",
    "asset=",
    "file=",
    "filename=",
    "download=",
    "do=download",
    "format=",
    "ext=",
)


def _looks_like_media_url(url: str) -> bool:
    if _looks_like_image_url(url):
        return True

    lowered = str(url or "").lower()
    parsed = urlparse(lowered)
    path = parsed.path or ""
    query = parsed.query or ""

    if any(hint in path for hint in _LIKELY_URL_HINTS):
        return True
    if any(hint in query for hint in _LIKELY_URL_HINTS):
        return True

    host = parsed.netloc.lower()
    return host.startswith(("img.", "images.", "cdn.", "media."))

def _safe_slug(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    # Keep alnum + - _ ; collapse spaces to underscores
    out: list[str] = []
    prev_us = False
    for ch in raw:
        if ch.isalnum():
            out.append(ch)
            prev_us = False
        elif ch in {"-", "_"}:
            out.append(ch)
            prev_us = False
        else:
            if not prev_us:
                out.append("_")
                prev_us = True
    slug = "".join(out).strip("_")
    # Avoid empty
    return slug or "item"


def _suggest_group_from_page(page_url: str) -> str:
    parsed = urlparse(page_url)
    path = (parsed.path or "").strip("/")
    host = (parsed.netloc or "site").split(":")[0]

    if not path:
        return _safe_slug(host).lower()

    parts = [p for p in path.split("/") if p]

    # Common PokemonDB pattern: /pokedex/<name>
    if "pokedex" in parts:
        idx = parts.index("pokedex")
        if idx + 1 < len(parts):
            return _safe_slug(parts[idx + 1]).lower()

    # Otherwise last path segment
    tail = parts[-1]
    if tail.lower() in {"index", "home"} and len(parts) >= 2:
        tail = parts[-2]

    return _safe_slug(tail).lower()


_GENERIC_ALT_TOKENS = {
    "sprite",
    "image",
    "thumbnail",
    "enlarge",
    "zoom",
    "view",
    "open",
    "click",
    "preview",
    "full",
    "size",
}


def _looks_hash_like_stem(stem: str) -> bool:
    value = (stem or "").strip().lower()
    if len(value) < 12:
        return False

    if re.fullmatch(r"[0-9a-f]{12,}", value):
        return True

    if len(value) >= 24 and re.fullmatch(r"[a-z0-9_-]{24,}", value):
        vowels = sum(1 for ch in value if ch in "aeiou")
        return vowels <= max(1, len(value) // 12)

    return False


def _is_generic_alt_text(alt_text: str) -> bool:
    cleaned = _safe_slug(alt_text).lower()
    if not cleaned:
        return True

    tokens = [token for token in cleaned.split("_") if token]
    if not tokens:
        return True

    if all(token in _GENERIC_ALT_TOKENS for token in tokens):
        return True

    return False


def _suggest_name(img: HarvestedImageUrl) -> str:
    alt = (img.alt or "").strip()
    url_path = urlparse(img.url).path
    ext = Path(url_path).suffix.lower() or ".png"

    url_stem = _safe_slug(Path(url_path).stem).lower()
    alt_stem = _safe_slug(alt).lower()

    if url_stem and not _looks_hash_like_stem(url_stem):
        chosen = url_stem
    elif alt_stem and not _is_generic_alt_text(alt):
        chosen = alt_stem
    else:
        chosen = url_stem or alt_stem or "download"

    return f"{chosen}{ext}"


def _annotate(img: HarvestedImageUrl) -> HarvestedImageUrl:
    page = img.source_page_url or ""
    group = img.suggested_group or (_suggest_group_from_page(page) if page else None)
    name = img.suggested_name or _suggest_name(img)
    return replace(img, suggested_group=group, suggested_name=name)


def fetch_html(
    page_url: str,
    *,
    timeout: float = 10.0,
    opener: Callable[..., object] | None = None,
    cancel_requested: Callable[[], bool] | None = None,
) -> str:
    """Fetch webpage HTML for scanning."""

    if _is_cancel_requested(cancel_requested):
        raise WebpageScanCancelledError("Scan cancelled")

    last_error: Exception | None = None
    header_profiles = _html_request_header_profiles(page_url)

    for attempt_index, headers in enumerate(header_profiles):
        if _is_cancel_requested(cancel_requested):
            raise WebpageScanCancelledError("Scan cancelled")

        request = Request(page_url, headers=headers)
        try:
            response_obj = _open_with_socket_fallback(request, timeout=timeout, opener=opener)
            with response_obj as response:
                if _is_cancel_requested(cancel_requested):
                    raise WebpageScanCancelledError("Scan cancelled")

                content_type = None
                response_headers = getattr(response, "headers", None)
                if response_headers is not None and hasattr(response_headers, "get"):
                    content_type = response_headers.get("Content-Type")
                if content_type:
                    lowered_type = content_type.lower()
                    if all(marker not in lowered_type for marker in ("html", "xml", "text/plain")):
                        raise ValueError(f"Expected HTML response, got {content_type!r}")

                raw = response.read()
                if _is_cancel_requested(cancel_requested):
                    raise WebpageScanCancelledError("Scan cancelled")
                return _decode_html_payload(raw, content_type=content_type)
        except WebpageScanCancelledError:
            raise
        except Exception as exc:
            last_error = exc
            should_retry = (
                attempt_index + 1 < len(header_profiles)
                and _is_retryable_fetch_error(exc)
            )
            if not should_retry:
                break

    if last_error is not None:
        raise last_error
    raise RuntimeError("Failed to fetch webpage HTML")


def extract_image_urls_from_html(
    html: str,
    *,
    base_url: str,
    filters: WebpageScanFilters | None = None,
) -> WebpageScanResult:
    """Extract and filter image URLs from HTML text."""

    parser = _ImageUrlHTMLParser(
        base_url=base_url,
        include_srcset=bool((filters or WebpageScanFilters()).include_srcset),
        include_anchor_image_links=bool((filters or WebpageScanFilters()).include_anchor_image_links),
    )
    parser.feed(html)

    active_filters = filters or WebpageScanFilters()
    allowed_exts = (
        {ext.lower() for ext in active_filters.allowed_extensions}
        if active_filters.allowed_extensions is not None
        else SUPPORTED_IMAGE_EXTENSIONS
    )

    result = WebpageScanResult(page_url=base_url)
    dedupe_urls = bool(getattr(active_filters, "dedupe", True))
    seen_urls: set[str] = set()

    for candidate in parser.candidates:
        if dedupe_urls:
            if candidate.url in seen_urls:
                continue
            seen_urls.add(candidate.url)

        ext = _extension_from_url(candidate.url)
        passes = True
        if ext and ext not in allowed_exts:
            passes = False

        if passes and active_filters.min_width is not None and candidate.width is not None:
            if candidate.width < active_filters.min_width:
                passes = False

        if passes and active_filters.min_height is not None and candidate.height is not None:
            if candidate.height < active_filters.min_height:
                passes = False

        annotated = _annotate(candidate)
        if passes:
            result.images.append(annotated)
        else:
            result.filtered_out.append(annotated)

    return result


def _extract_links_from_html(html: str, *, base_url: str) -> list[str]:
    """Extract normalized hyperlinks from HTML for depth scanning."""

    class _LinkParser(HTMLParser):
        def __init__(self, base_url: str) -> None:
            super().__init__(convert_charrefs=True)
            self.base_url = base_url
            self.links: list[str] = []

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag.lower() != "a":
                return
            attr_map = {name.lower(): (value or "") for name, value in attrs}
            href = attr_map.get("href")
            if not href:
                return
            self.links.append(_normalize_url(href, self.base_url))

    parser = _LinkParser(base_url=base_url)
    parser.feed(html)
    # de-dupe but keep order
    seen: set[str] = set()
    out: list[str] = []
    for u in parser.links:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def scan_webpage_for_images(
    page_url: str,
    *,
    filters: WebpageScanFilters | None = None,
    timeout: float = 10.0,
    opener: Callable[..., object] | None = None,
    max_depth: int = 0,
    same_domain_only: bool = True,
    max_pages: int = 50,
    max_images: int | None = None,
    dedupe_images: bool = True,
    cancel_requested: Callable[[], bool] | None = None,
) -> WebpageScanResult:
    """Fetch a webpage and extract image URLs.

    If max_depth > 0, this performs a bounded breadth-first crawl:
    - depth 0: the seed page only
    - depth 1: seed + pages linked from seed
    - depth 2: seed + linked pages + their links
    """

    seed = page_url
    active_filters = filters or WebpageScanFilters()

    if max_depth <= 0:
        html = fetch_html(seed, timeout=timeout, opener=opener, cancel_requested=cancel_requested)
        result = extract_image_urls_from_html(html, base_url=seed, filters=active_filters)
        result.pages_scanned = 1
        if max_images is not None and len(result.images) > max_images:
            result.filtered_out.extend(result.images[max_images:])
            result.images = result.images[:max_images]
        return result

    seed_host = urlparse(seed).netloc.lower()
    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(seed, 0)]
    agg = WebpageScanResult(page_url=seed)
    seen_images: set[str] = set()

    while queue and len(visited) < max_pages:
        if _is_cancel_requested(cancel_requested):
            raise WebpageScanCancelledError("Scan cancelled")

        url, depth = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)

        try:
            html = fetch_html(url, timeout=timeout, opener=opener, cancel_requested=cancel_requested)
        except WebpageScanCancelledError:
            raise
        except Exception:
            # Skip pages that fail to load
            continue

        page_result = extract_image_urls_from_html(html, base_url=url, filters=active_filters)
        for img in page_result.images:
            if dedupe_images:
                if img.url in seen_images:
                    continue
                seen_images.add(img.url)
            agg.images.append(img)
            if max_images is not None and len(agg.images) >= max_images:
                break
        agg.filtered_out.extend(page_result.filtered_out)

        if depth >= max_depth:
            continue

        for link in _extract_links_from_html(html, base_url=url):
            if same_domain_only:
                if urlparse(link).netloc.lower() != seed_host:
                    continue
            # Avoid re-adding obvious non-html (images / mailto / etc.)
            scheme = urlparse(link).scheme.lower()
            if scheme not in ("http", "https", ""):
                continue
            if _looks_like_image_url(link):
                continue
            queue.append((link, depth + 1))

    agg.pages_scanned = len(visited)
    return agg


def depth_scan_webpages_stub(
    seed_urls: list[str],
    *,
    max_depth: int = 1,
    filters: WebpageScanFilters | None = None,
    timeout: float = 10.0,
    opener: Callable[..., object] | None = None,
    same_domain_only: bool = True,
    max_pages: int = 50,
    max_images: int | None = None,
    dedupe_images: bool = True,
    cancel_requested: Callable[[], bool] | None = None,
) -> list[WebpageScanResult]:
    """Backward-compat wrapper for older depth-scan integrations.

    New integrations should call scan_webpage_for_images(..., max_depth=...).
    """

    results: list[WebpageScanResult] = []
    for seed in seed_urls:
        url = str(seed or "").strip()
        if not url:
            continue
        results.append(
            scan_webpage_for_images(
                url,
                filters=filters,
                timeout=timeout,
                opener=opener,
                max_depth=max_depth,
                same_domain_only=same_domain_only,
                max_pages=max_pages,
                max_images=max_images,
                dedupe_images=dedupe_images,
                cancel_requested=cancel_requested,
            )
        )
    return results








