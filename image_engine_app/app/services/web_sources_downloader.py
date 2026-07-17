"""Download, cache, resolve, and import files selected in Web Sources."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import re
from typing import Callable
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse
from urllib.request import Request, urlopen

from image_engine_app.app.paths import AppPaths
from image_engine_app.app.web_sources_models import (
    Confidence,
    ImportTarget,
    SmartOptions,
    WebItem,
    coerce_smart_options,
)
from image_engine_app.engine.ingest.import_result import ImportIssueKind, ImportResult
from image_engine_app.engine.ingest.url_ingest import DownloadCancelledError, DownloadGuards, UrlIngestError, validate_url
from image_engine_app.engine.ingest.web_sources_rules import (
    ALLOWED_ARCHIVE_EXTS_DEFAULT,
    ALLOWED_IMAGE_EXTS_DEFAULT,
    dedupe_key,
    guess_import_target,
    normalize_ext,
    suggested_name_from_url,
)
from image_engine_app.engine.ingest.webpage_scan import WebpageScanCancelledError, WebpageScanFilters
from image_engine_app.engine.ingest.zip_extract import ZipExtractError, extract_images_only
from image_engine_app.engine.models import SourceType


BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_WIKI_FILE_PAGE_MARKERS = ("/wiki/file:", "/wiki/file%3a", "/wiki/image:", "/wiki/image%3a")
_DIRECT_MEDIA_HOST_HINTS = ("static.wikia.nocookie.net", "vignette.wikia.nocookie.net", "images.wikia.com")
_DIRECT_MEDIA_PATH_HINTS = ("/images/", "/thumb/", "/revision/", "/latest")
_SITE_ASSET_HINTS = (
    "logo",
    "wordmark",
    "site-logo",
    "wiki-wordmark",
    "fandom-",
    "favicon",
    "apple-touch-icon",
    "community-central",
    "wds-icons",
    "social",
    "facebook",
    "twitter",
    "discord",
    "youtube",
    "avatar",
)


@dataclass
class WebSourcesDownloader:
    """Download selected files without owning page scans or UI state."""

    app_paths: AppPaths | None
    scan_webpage_images: Callable[..., object]
    import_url_source: Callable[..., object]
    import_cached_files: Callable[..., ImportResult]

    def download_items(
        self,
        items: list[WebItem],
        target: ImportTarget,
        *,
        smart: SmartOptions,
        guards: DownloadGuards | None = None,
        opener=None,
        progress_callback=None,
        cancel_requested=None,
    ) -> ImportResult:
        smart_opts = coerce_smart_options(smart)
        active_guards = guards or DownloadGuards(max_bytes=25 * 1024 * 1024, max_pixels=64_000_000)
        result = ImportResult()
        seen_batch_keys: set[str] = set()
        total_items = max(1, int(len(items)))

        def _emit_progress(done_count: int, message: str) -> None:
            if progress_callback is None:
                return
            try:
                progress_callback(
                    max(0, min(int(done_count), total_items)),
                    total_items,
                    str(message),
                )
            except Exception:
                return

        def _is_cancel_requested() -> bool:
            if cancel_requested is None:
                return False
            try:
                return bool(cancel_requested())
            except Exception:
                return False

        def _looks_like_cancel_error(exc: Exception) -> bool:
            return isinstance(exc, (DownloadCancelledError, WebpageScanCancelledError))

        _emit_progress(0, "Preparing downloads...")

        for index, item in enumerate(items, start=1):
            if _is_cancel_requested():
                result.cancelled = True
                _emit_progress(max(0, index - 1), "Download cancelled by user")
                break

            if not isinstance(item, WebItem) or not item.url.strip():
                result.add_issue(ImportIssueKind.SKIPPED, f"item {index}", "invalid web item")
                _emit_progress(index, f"Skipped invalid item ({index}/{total_items})")
                continue

            effective_target = self.resolve_web_import_target(default_target=target, item=item, smart=smart_opts)
            canonical_url = self.canonicalize_download_url(item.url) or item.url
            source_page = str(item.source_page or item.url or canonical_url).strip()
            name = self.resolve_web_item_name(item.name, item.url)
            try:
                download_url = self.resolve_download_url(
                    item=item,
                    canonical_url=canonical_url,
                    source_page=source_page,
                    opener=opener,
                    cancel_requested=cancel_requested,
                )
            except Exception as exc:
                if _looks_like_cancel_error(exc) or _is_cancel_requested():
                    result.cancelled = True
                    _emit_progress(max(0, index - 1), "Download cancelled by user")
                    break
                result.add_issue(ImportIssueKind.FAILED, name, exc)
                _emit_progress(index, f"Failed: {name}")
                continue
            _emit_progress(index - 1, f"Downloading {index}/{total_items}: {name}")

            item_key = dedupe_key(f"{effective_target.value}:{name}:{canonical_url}")
            if smart_opts.skip_duplicates and item_key in seen_batch_keys:
                result.add_issue(ImportIssueKind.SKIPPED, name, "duplicate in selection")
                _emit_progress(index, f"Skipped duplicate: {name}")
                continue
            seen_batch_keys.add(item_key)

            ext = normalize_ext(canonical_url) or normalize_ext(item.url)

            if ext in ALLOWED_ARCHIVE_EXTS_DEFAULT:
                if not smart_opts.allow_zip:
                    result.add_issue(ImportIssueKind.SKIPPED, name, "ZIP imports are disabled")
                    _emit_progress(index, f"Skipped ZIP (disabled): {name}")
                    continue
                if smart_opts.skip_duplicates and self.is_cached_web_url(canonical_url, effective_target):
                    result.add_issue(ImportIssueKind.SKIPPED, name, "already downloaded")
                    _emit_progress(index, f"Skipped duplicate: {name}")
                    continue

                try:
                    zip_cache_dir = self.web_target_cache_dir(effective_target) / "_zip"
                    zip_path = self.download_zip_to_cache(
                        canonical_url,
                        zip_cache_dir,
                        max_bytes=active_guards.max_bytes,
                        opener=opener,
                        cancel_requested=cancel_requested,
                    )
                    extract_root = self.web_target_cache_dir(effective_target) / "_zip_extract" / zip_path.stem
                    extracted_paths = extract_images_only(
                        str(zip_path),
                        str(extract_root),
                        allowed_exts=set(ALLOWED_IMAGE_EXTS_DEFAULT),
                    )
                    if not extracted_paths:
                        result.add_issue(ImportIssueKind.FAILED, name, "ZIP contained no supported images")
                        _emit_progress(index, f"Failed ZIP: {name}")
                        continue

                    archive_result = self.import_cached_files(
                        file_paths=[Path(extracted) for extracted in extracted_paths],
                        source_uri=canonical_url,
                        target=effective_target,
                        confidence=item.confidence,
                        source_page=source_page,
                    )
                    result.extend(archive_result)
                    if result.cancelled or _is_cancel_requested():
                        result.cancelled = True
                        break
                    _emit_progress(index, f"Imported ZIP: {name} ({len(archive_result.assets)} file(s))")
                except (UrlIngestError, ZipExtractError, OSError, ValueError) as exc:
                    if _looks_like_cancel_error(exc) or _is_cancel_requested():
                        result.cancelled = True
                        _emit_progress(max(0, index - 1), "Download cancelled by user")
                        break
                    result.add_issue(ImportIssueKind.FAILED, name, exc)
                    _emit_progress(index, f"Failed: {name}")

                if result.cancelled:
                    break
                continue

            if smart_opts.skip_duplicates:
                cached_path = self.find_cached_web_file(canonical_url, effective_target)
                if cached_path is not None:
                    cached_result = self.import_cached_files(
                        file_paths=[cached_path],
                        source_uri=canonical_url,
                        target=effective_target,
                        confidence=item.confidence,
                        source_page=source_page,
                        display_name=name,
                        reused=True,
                    )
                    result.extend(cached_result)
                    _emit_progress(index, f"Loaded cached: {name}")
                    continue

            try:
                request_headers = {"Accept": "image/*,*/*;q=0.8"}
                if source_page:
                    request_headers = self._download_request_headers(
                        download_url=download_url,
                        source_page=source_page,
                    )

                imported = self.import_url_source(
                    download_url,
                    cache_key_url=canonical_url,
                    guards=active_guards,
                    opener=opener,
                    display_name=name,
                    source_type=SourceType.WEBPAGE_ITEM,
                    classification_tags=[
                        f"web_target:{effective_target.value}",
                        f"web_confidence:{item.confidence.value}",
                    ],
                    cache_subdir=self.web_target_cache_subdir(effective_target),
                    stream_preview=False,
                    request_headers=request_headers,
                    allow_webpage_fallback=True,
                    cancel_requested=cancel_requested,
                )
                if not isinstance(imported, ImportResult):
                    raise UrlIngestError(f"Import returned an invalid result for {name}")
                asset = imported.primary_asset
                if asset is None:
                    raise UrlIngestError(f"Import returned no asset for {name}")
                if source_page and f"web_source:{source_page}" not in asset.classification_tags:
                    asset.classification_tags.append(f"web_source:{source_page}")
                if canonical_url != item.url and "web_canonicalized:fandom_file_redirect" not in asset.classification_tags:
                    asset.classification_tags.append("web_canonicalized:fandom_file_redirect")
                if download_url != canonical_url and "web_resolved:direct_media" not in asset.classification_tags:
                    asset.classification_tags.append("web_resolved:direct_media")
                result.extend(imported)
                _emit_progress(index, f"Imported: {asset.original_name or name}")
            except Exception as exc:
                if _looks_like_cancel_error(exc) or _is_cancel_requested():
                    result.cancelled = True
                    _emit_progress(max(0, index - 1), "Download cancelled by user")
                    break
                result.add_issue(ImportIssueKind.FAILED, name, exc)
                _emit_progress(index, f"Failed: {name}")

        if result.cancelled:
            done_count = min(
                total_items,
                max(0, len(result.downloaded) + len(result.reused) + len(result.skipped) + len(result.failed)),
            )
            _emit_progress(done_count, "Download cancelled by user")
        else:
            _emit_progress(total_items, "Download complete")

        return result

    @staticmethod
    def _is_fandom_host(host: str) -> bool:
        lowered = str(host or "").lower()
        return any(token in lowered for token in ("fandom.com", "wikia.com", "wikia.nocookie.net"))

    @classmethod
    def _looks_like_wiki_file_page(cls, url: str) -> bool:
        lowered = str(url or "").lower()
        return any(marker in lowered for marker in _WIKI_FILE_PAGE_MARKERS)

    @staticmethod
    def _origin(url: str) -> str:
        parsed = urlparse(str(url or "").strip())
        if not parsed.scheme or not parsed.netloc:
            return ""
        return f"{parsed.scheme}://{parsed.netloc}/"

    @classmethod
    def _download_request_headers(cls, *, download_url: str, source_page: str) -> dict[str, str]:
        headers = {
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": source_page,
        }

        parsed_download = urlparse(download_url)
        parsed_source = urlparse(source_page)
        same_wiki_family = cls._is_fandom_host(parsed_download.netloc) or cls._is_fandom_host(parsed_source.netloc)
        if same_wiki_family:
            headers["User-Agent"] = BROWSER_USER_AGENT
            origin = cls._origin(source_page)
            if origin:
                headers["Origin"] = origin.rstrip("/")
        return headers

    @staticmethod
    def _name_tokens(value: str | None) -> set[str]:
        cleaned = WebSourcesDownloader.strip_media_namespace(value).lower().strip()
        cleaned = re.sub(r"\.[a-z0-9]{2,5}$", "", cleaned)
        cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
        return {token for token in cleaned.split() if token}

    @classmethod
    def _media_candidate_score(cls, *, candidate_url: str, requested_name: str, width: int | None, height: int | None) -> int:
        parsed = urlparse(candidate_url)
        lowered = unquote(parsed.path or "").lower()
        host = (parsed.netloc or "").lower()
        path_name = Path(lowered).name
        requested_tokens = cls._name_tokens(requested_name)
        candidate_tokens = cls._name_tokens(path_name)

        score = 0
        if cls._is_fandom_host(host):
            score += 40
        if any(hint in host for hint in _DIRECT_MEDIA_HOST_HINTS):
            score += 60
        if any(hint in lowered for hint in _DIRECT_MEDIA_PATH_HINTS):
            score += 25
        if normalize_ext(candidate_url) in ALLOWED_IMAGE_EXTS_DEFAULT:
            score += 20

        if requested_tokens:
            overlap = requested_tokens & candidate_tokens
            if overlap:
                score += 35 + (len(overlap) * 6)
            requested_stem = "_".join(sorted(requested_tokens))
            candidate_stem = re.sub(r"[^a-z0-9]+", "_", Path(path_name).stem.lower())
            if requested_stem and requested_stem == candidate_stem:
                score += 80
            elif requested_stem and requested_stem in candidate_stem:
                score += 40

        if width and height:
            pixels = max(0, int(width) * int(height))
            if pixels >= 64 * 64:
                score += 10

        lowered_full = f"{host}{lowered}"
        if any(marker in lowered_full for marker in _SITE_ASSET_HINTS):
            score -= 120
        if "/wiki/" in lowered and not any(hint in lowered for hint in _DIRECT_MEDIA_PATH_HINTS):
            score -= 60
        return score

    def _resolve_best_media_url_from_page(
        self,
        *,
        page_url: str,
        requested_name: str,
        opener=None,
        cancel_requested=None,
    ) -> str | None:
        try:
            scan = self.scan_webpage_images(
                page_url,
                max_depth=0,
                same_domain_only=False,
                max_pages=1,
                dedupe_images=True,
                filters=WebpageScanFilters(
                    allowed_extensions=set(ALLOWED_IMAGE_EXTS_DEFAULT),
                    dedupe=True,
                    include_srcset=True,
                    include_anchor_image_links=True,
                ),
                opener=opener,
                cancel_requested=cancel_requested,
            )
        except Exception:
            return None

        best_url: str | None = None
        best_score: int | None = None
        for hit in getattr(scan, "images", ()):
            candidate_url = str(getattr(hit, "url", "") or "").strip()
            if not candidate_url:
                continue
            score = self._media_candidate_score(
                candidate_url=candidate_url,
                requested_name=requested_name,
                width=getattr(hit, "width", None),
                height=getattr(hit, "height", None),
            )
            if best_score is None or score > best_score:
                best_score = score
                best_url = candidate_url

        if best_score is None or best_score < 20:
            return None
        return best_url

    def resolve_download_url(
        self,
        *,
        item: WebItem,
        canonical_url: str,
        source_page: str,
        opener=None,
        cancel_requested=None,
    ) -> str:
        requested_name = self.resolve_web_item_name(item.name, source_page or item.url or canonical_url)
        page_candidates: list[str] = []
        for candidate in (source_page, item.url, canonical_url):
            text = str(candidate or "").strip()
            if not text or text in page_candidates:
                continue
            if self._looks_like_wiki_file_page(text):
                page_candidates.append(text)

        for page_url in page_candidates:
            resolved = self._resolve_best_media_url_from_page(
                page_url=page_url,
                requested_name=requested_name,
                opener=opener,
                cancel_requested=cancel_requested,
            )
            if resolved:
                return resolved

        return canonical_url

    @staticmethod
    def resolve_web_item_name(candidate_name: str | None, url: str) -> str:
        fallback_name = suggested_name_from_url(url)
        parsed = urlparse(url)
        decoded_path_name = unquote(Path(parsed.path).name or "")
        query_name = WebSourcesDownloader.name_from_query(parsed.query)

        candidates = [
            WebSourcesDownloader.strip_media_namespace(candidate_name),
            WebSourcesDownloader.strip_media_namespace(fallback_name),
            WebSourcesDownloader.strip_media_namespace(decoded_path_name),
            WebSourcesDownloader.strip_media_namespace(query_name),
        ]

        chosen = next(
            (name for name in candidates if name and not WebSourcesDownloader.is_generic_web_name(name)),
            "",
        )
        if not chosen:
            chosen = next((name for name in candidates if name), "download")

        if not Path(chosen).suffix:
            ext_candidate = next((Path(name).suffix for name in candidates if name and Path(name).suffix), "")
            if ext_candidate:
                chosen = f"{chosen}{ext_candidate.lower()}"

        if chosen.lower().startswith(("special_redirect_file_", "special:redirect_file_")):
            chosen = chosen.split("_", 3)[-1]

        if WebSourcesDownloader.url_indicates_shiny(url):
            stem = Path(chosen).stem
            ext = Path(chosen).suffix
            if "shiny" not in stem.lower():
                chosen = f"{stem}_shiny{ext}"

        return chosen

    @staticmethod
    def name_from_query(query: str) -> str:
        if not query:
            return ""
        try:
            params = parse_qs(query, keep_blank_values=False)
        except Exception:
            return ""
        for key in ("filename", "file", "name", "download", "image", "img", "asset", "sprite"):
            values = params.get(key, ())
            for value in values:
                decoded = unquote(str(value or "")).strip()
                if decoded:
                    return decoded
        return ""

    @staticmethod
    def clean_web_name(value: str | None) -> str:
        if value is None:
            return ""
        cleaned = unquote(str(value)).replace("\r", " ").replace("\n", " ").strip()
        return re.sub(r"\s+", " ", cleaned)

    @staticmethod
    def is_generic_web_name(name: str) -> bool:
        stem = Path(name).stem.lower().strip()
        if not stem:
            return True
        stem_words = re.sub(r"[_\-]+", " ", stem).strip()
        generic_stems = {
            "thumbnail",
            "enlarge image",
            "view image",
            "open image",
            "click image",
            "download",
            "image",
            "sprite",
            "icon",
            "item",
            "file",
        }
        if stem_words in generic_stems:
            return True
        if len(stem) >= 24 and re.fullmatch(r"[0-9a-f]{24,}", stem):
            return True
        return False

    @staticmethod
    def url_indicates_shiny(url: str) -> bool:
        lowered = (url or "").lower()
        return any(
            marker in lowered
            for marker in ("/shiny", "shiny-sprite", "_shiny", "-shiny", "shiny=", "shiny%20", "shiny%2d")
        )

    @staticmethod
    def context_indicates_items(*values: object) -> bool:
        combined = " ".join(str(value or "") for value in values).lower()
        if not combined.strip():
            return False
        item_markers = (
            "item sprite",
            "item sprites",
            "category:item",
            "category:item_sprites",
            "/item",
            "item=",
            "bag sprite",
            "bag sprites",
        )
        return any(marker in combined for marker in item_markers)

    @staticmethod
    def resolve_web_import_target(
        *,
        default_target: ImportTarget,
        item: WebItem,
        smart: SmartOptions,
    ) -> ImportTarget:
        if not smart.auto_sort:
            return default_target
        try:
            ext = str(getattr(item, "ext", "") or "").strip().lower()
            if ext == ".gif":
                return ImportTarget.ANIMATED

            base_name = WebSourcesDownloader.resolve_web_item_name(item.name, item.url)
            guessed = guess_import_target(base_name)
            if guessed is ImportTarget.ANIMATED:
                return ImportTarget.ANIMATED
            if guessed is ImportTarget.SHINY:
                return ImportTarget.SHINY
            if guessed is ImportTarget.ITEMS:
                return ImportTarget.ITEMS
            if WebSourcesDownloader.context_indicates_items(item.name, item.url, item.source_page):
                return ImportTarget.ITEMS
            return default_target
        except Exception:
            return default_target

    def web_target_cache_subdir(self, target: ImportTarget) -> str:
        return f"web_sources/{target.value}"

    def web_target_cache_dir(self, target: ImportTarget) -> Path:
        base_cache = self.app_paths.cache if self.app_paths is not None else (Path(".") / "cache")
        return base_cache / "web_sources" / target.value

    def find_cached_web_file(self, url: str, target: ImportTarget) -> Path | None:
        try:
            normalized = validate_url(url)
        except Exception:
            return None

        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        cache_dir = self.web_target_cache_dir(target)
        if not cache_dir.exists():
            return None

        candidates: list[Path] = []
        for path in cache_dir.rglob(f"{digest}.*"):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix in ALLOWED_IMAGE_EXTS_DEFAULT:
                candidates.append(path)

        if not candidates:
            return None

        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[0]

    def is_cached_web_url(self, url: str, target: ImportTarget) -> bool:
        try:
            normalized = validate_url(url)
        except Exception:
            return False

        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        cache_dir = self.web_target_cache_dir(target)
        if not cache_dir.exists():
            return False
        return any(cache_dir.rglob(f"{digest}.*"))

    @staticmethod
    def download_zip_to_cache(
        url: str,
        cache_dir: Path,
        *,
        max_bytes: int | None,
        timeout: float = 20.0,
        opener=None,
        cancel_requested=None,
    ) -> Path:
        normalized = validate_url(url)
        cache_dir.mkdir(parents=True, exist_ok=True)

        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        final_path = cache_dir / f"{digest}.zip"
        temp_path = cache_dir / f"{digest}.zip.part"

        request = Request(normalized, headers={"User-Agent": "ImageEngine/0.1 (Web Sources ZIP)"})
        open_fn = opener or urlopen

        total_bytes = 0
        try:
            response_obj = open_fn(request, timeout=timeout)
            with response_obj as response, temp_path.open("wb") as handle:
                while True:
                    if cancel_requested is not None and bool(cancel_requested()):
                        raise DownloadCancelledError("Download cancelled by user")
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if max_bytes is not None and total_bytes > max_bytes:
                        raise UrlIngestError(f"ZIP download exceeded max_bytes={max_bytes}")
                    handle.write(chunk)

            if final_path.exists():
                final_path.unlink()
            temp_path.replace(final_path)
            return final_path
        except Exception as exc:
            if temp_path.exists():
                temp_path.unlink()
            if isinstance(exc, UrlIngestError):
                raise
            raise UrlIngestError(f"ZIP download failed: {exc}") from exc

    @staticmethod
    def extract_archive_urls(html: str, *, base_url: str, allowed_archives: set[str]) -> list[str]:
        class _ArchiveParser(HTMLParser):
            def __init__(self) -> None:
                super().__init__(convert_charrefs=True)
                self.links: list[str] = []

            def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
                if tag.lower() != "a":
                    return
                attr_map = {name.lower(): (value or "") for name, value in attrs}
                href = attr_map.get("href", "").strip()
                if not href:
                    return
                self.links.append(urljoin(base_url, href))

        parser = _ArchiveParser()
        parser.feed(html)

        out: list[str] = []
        seen: set[str] = set()
        for link in parser.links:
            ext = normalize_ext(link)
            if ext not in allowed_archives or ext not in ALLOWED_ARCHIVE_EXTS_DEFAULT:
                continue
            if link in seen:
                continue
            seen.add(link)
            out.append(link)
        return out

    @staticmethod
    def strip_media_namespace(name: str | None) -> str:
        cleaned = WebSourcesDownloader.clean_web_name(name)
        if not cleaned:
            return ""
        lowered = cleaned.lower()
        for prefix in ("file:", "image:"):
            if lowered.startswith(prefix):
                return cleaned[len(prefix):].lstrip()
        return cleaned

    @staticmethod
    def _fandom_redirect_name(name: str) -> str:
        cleaned = WebSourcesDownloader.strip_media_namespace(name)
        if not cleaned:
            return ""
        return cleaned.replace(" ", "_")

    @staticmethod
    def fandom_file_name_from_url(url: str) -> str:
        parsed = urlparse(str(url or "").strip())
        try:
            params = parse_qs(parsed.query or "", keep_blank_values=False)
        except Exception:
            params = {}

        for key in ("file", "filename", "image", "img", "asset", "sprite"):
            for value in params.get(key, ()):
                redirect_name = WebSourcesDownloader._fandom_redirect_name(unquote(str(value or "")).strip())
                if redirect_name:
                    return redirect_name

        path = unquote(parsed.path or "")
        lowered_path = path.lower()
        for marker in ("/wiki/file:", "/wiki/image:"):
            if marker in lowered_path:
                index = lowered_path.rfind(marker)
                tail = path[index + len(marker):]
                redirect_name = WebSourcesDownloader._fandom_redirect_name(
                    tail.split("/", 1)[0].split("#", 1)[0].split("?", 1)[0]
                )
                if redirect_name:
                    return redirect_name
        return ""

    @staticmethod
    def canonicalize_download_url(url: str) -> str:
        raw = str(url or "").strip()
        if not raw:
            return ""
        parsed = urlparse(raw)
        host = (parsed.netloc or "").lower()
        if not host or not any(token in host for token in ("fandom.com", "wikia.com")):
            return raw
        redirect_name = WebSourcesDownloader.fandom_file_name_from_url(raw)
        if not redirect_name:
            return raw
        safe_name = quote(redirect_name, safe="._-()")
        scheme = parsed.scheme or "https"
        return f"{scheme}://{parsed.netloc}/wiki/Special:Redirect/file/{safe_name}"

