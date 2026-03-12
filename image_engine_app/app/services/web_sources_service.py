"""Web Sources orchestration service.

Extracted from UI controller to keep web scan/download logic modular and testable.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import re
from typing import Callable
from urllib.parse import parse_qs, unquote, urljoin, urlparse
from urllib.request import Request, urlopen

from app.paths import AppPaths
from app.web_sources_models import (
    Confidence,
    DownloadReport,
    ImportTarget,
    ScanResults,
    SmartOptions,
    WebItem,
    coerce_smart_options,
    coerce_web_item,
)
from engine.ingest.url_ingest import DownloadCancelledError, DownloadGuards, UrlIngestError, validate_url
from engine.ingest.web_sources_rules import (
    ALLOWED_ARCHIVE_EXTS_DEFAULT,
    ALLOWED_IMAGE_EXTS_DEFAULT,
    confidence_for,
    dedupe_key,
    guess_import_target,
    normalize_ext,
    suggested_name_from_url,
)
from engine.ingest.webpage_scan import WebpageScanCancelledError, WebpageScanFilters, fetch_html
from engine.ingest.zip_extract import ZipExtractError, extract_images_only
from engine.models import AssetRecord, SourceType


@dataclass
class WebSourcesService:
    """Service for Web Sources registry, scan, and download orchestration."""

    app_paths: AppPaths | None
    scan_webpage_images: Callable[..., object]
    import_url_source: Callable[..., object]
    build_web_asset_from_file: Callable[..., AssetRecord]

    def load_registry(self, registry: list[dict] | None) -> list[dict]:
        return self.sanitize_registry(registry)

    def scan_area(
        self,
        area_url: str,
        *,
        allowed_exts: set[str] | None = None,
        show_likely: bool = False,
        opener=None,
        cancel_requested=None,
    ) -> ScanResults:
        normalized_area_url = validate_url(str(area_url or "").strip())

        if callable(cancel_requested) and bool(cancel_requested()):
            raise WebpageScanCancelledError("Scan cancelled")

        merged_allowed = {ext.lower() for ext in (allowed_exts or set())}
        if not merged_allowed:
            merged_allowed.update(ALLOWED_IMAGE_EXTS_DEFAULT)
            merged_allowed.update(ALLOWED_ARCHIVE_EXTS_DEFAULT)

        direct_ext = normalize_ext(normalized_area_url)
        direct_confidence = confidence_for(normalized_area_url, allowed_exts=merged_allowed)
        if direct_confidence is Confidence.DIRECT and direct_ext in merged_allowed:
            name = self.resolve_web_item_name(suggested_name_from_url(normalized_area_url), normalized_area_url)
            return ScanResults(
                items=(
                    WebItem(
                        url=normalized_area_url,
                        name=name,
                        ext=direct_ext,
                        confidence=Confidence.DIRECT,
                        preview_url=normalized_area_url,
                        source_page=normalized_area_url,
                    ),
                ),
                filtered_count=0,
            )

        image_allowed = {ext for ext in merged_allowed if ext in ALLOWED_IMAGE_EXTS_DEFAULT}
        if not image_allowed:
            image_allowed = set(ALLOWED_IMAGE_EXTS_DEFAULT)

        scan = self.scan_webpage_images(
            normalized_area_url,
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
            if callable(cancel_requested) and bool(cancel_requested()):
                raise WebpageScanCancelledError("Scan cancelled")

            url = str(getattr(hit, "url", "")).strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            confidence = confidence_for(url, allowed_exts=merged_allowed)
            if confidence is Confidence.UNKNOWN:
                filtered += 1
                continue

            suggested = str(getattr(hit, "suggested_name", "") or "").strip()
            name = self.resolve_web_item_name(suggested, url)
            ext = normalize_ext(url)
            candidate_item = WebItem(
                url=url,
                name=name,
                ext=ext,
                confidence=confidence,
                preview_url=url,
                source_page=str(getattr(hit, "source_page_url", "") or normalized_area_url),
            )
            if confidence is Confidence.DIRECT:
                direct_items.append(candidate_item)
            else:
                likely_items.append(candidate_item)

        if show_likely:
            items: list[WebItem] = [*direct_items, *likely_items]
        elif direct_items:
            items = list(direct_items)
            filtered += len(likely_items)
        else:
            # Fallback: if no direct links are present, keep likely links visible.
            items = list(likely_items)

        if any(ext in merged_allowed for ext in ALLOWED_ARCHIVE_EXTS_DEFAULT):
            try:
                html = fetch_html(normalized_area_url, opener=opener, cancel_requested=cancel_requested)
                for archive_url in self.extract_archive_urls(
                    html,
                    base_url=normalized_area_url,
                    allowed_archives=merged_allowed,
                ):
                    if callable(cancel_requested) and bool(cancel_requested()):
                        raise WebpageScanCancelledError("Scan cancelled")
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
                            source_page=normalized_area_url,
                        )
                    )
            except WebpageScanCancelledError:
                raise
            except Exception:
                # Keep scan usable even when HTML fetch for archive links fails.
                pass

        return ScanResults(items=tuple(items), filtered_count=filtered)

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
    ) -> DownloadReport:
        smart_opts = coerce_smart_options(smart)
        active_guards = guards or DownloadGuards(max_bytes=25 * 1024 * 1024, max_pixels=64_000_000)

        downloaded: list[str] = []
        skipped: list[str] = []
        failed: list[str] = []
        assets: list[AssetRecord] = []

        seen_batch_keys: set[str] = set()
        total_items = max(1, int(len(items)))
        cancelled = False

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
            return isinstance(exc, DownloadCancelledError)

        _emit_progress(0, "Preparing downloads...")

        for index, raw_item in enumerate(items, start=1):
            if _is_cancel_requested():
                cancelled = True
                _emit_progress(max(0, index - 1), "Download cancelled by user")
                break

            item = coerce_web_item(raw_item)
            if item is None or not item.url.strip():
                _emit_progress(index, f"Skipped invalid item ({index}/{total_items})")
                continue

            effective_target = self.resolve_web_import_target(default_target=target, item=item, smart=smart_opts)
            name = self.resolve_web_item_name(item.name, item.url)
            _emit_progress(index - 1, f"Downloading {index}/{total_items}: {name}")

            item_key = dedupe_key(f"{effective_target.value}:{name}:{item.url}")
            if smart_opts.skip_duplicates and item_key in seen_batch_keys:
                skipped.append(name)
                _emit_progress(index, f"Skipped duplicate: {name}")
                continue
            seen_batch_keys.add(item_key)

            ext = normalize_ext(item.url)

            if ext in ALLOWED_ARCHIVE_EXTS_DEFAULT:
                if not smart_opts.allow_zip:
                    skipped.append(name)
                    _emit_progress(index, f"Skipped ZIP (disabled): {name}")
                    continue
                if smart_opts.skip_duplicates and self.is_cached_web_url(item.url, effective_target):
                    skipped.append(name)
                    _emit_progress(index, f"Skipped duplicate: {name}")
                    continue

                try:
                    zip_cache_dir = self.web_target_cache_dir(effective_target) / "_zip"
                    zip_path = self.download_zip_to_cache(
                        item.url,
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
                        failed.append(f"{name}: zip had no supported images")
                        _emit_progress(index, f"Failed ZIP: {name}")
                        continue

                    imported_from_zip = 0
                    for extracted in extracted_paths:
                        if _is_cancel_requested():
                            cancelled = True
                            _emit_progress(max(0, index - 1), "Download cancelled by user")
                            break

                        extracted_path = Path(extracted)
                        extracted_key = dedupe_key(f"{effective_target.value}:{extracted_path.name}")
                        if smart_opts.skip_duplicates and extracted_key in seen_batch_keys:
                            skipped.append(extracted_path.name)
                            continue
                        seen_batch_keys.add(extracted_key)

                        asset = self.build_web_asset_from_file(
                            file_path=extracted_path,
                            source_uri=item.url,
                            target=effective_target,
                            confidence=item.confidence,
                            source_page=item.source_page,
                        )
                        assets.append(asset)
                        downloaded.append(asset.original_name or extracted_path.name)
                        imported_from_zip += 1

                    if cancelled:
                        break

                    _emit_progress(index, f"Imported ZIP: {name} ({imported_from_zip} file(s))")
                except (UrlIngestError, ZipExtractError, OSError, ValueError) as exc:
                    if _looks_like_cancel_error(exc) or _is_cancel_requested():
                        cancelled = True
                        _emit_progress(max(0, index - 1), "Download cancelled by user")
                        break
                    failed.append(f"{name}: {exc}")
                    _emit_progress(index, f"Failed: {name}")

                if cancelled:
                    break
                continue

            if smart_opts.skip_duplicates:
                cached_path = self.find_cached_web_file(item.url, effective_target)
                if cached_path is not None:
                    skipped.append(name)
                    cached_asset = self.build_web_asset_from_file(
                        file_path=cached_path,
                        source_uri=item.url,
                        target=effective_target,
                        confidence=item.confidence,
                        source_page=item.source_page,
                        display_name=name,
                    )
                    assets.append(cached_asset)
                    _emit_progress(index, f"Loaded cached: {name}")
                    continue

            try:
                request_headers = {"Accept": "image/*,*/*;q=0.8"}
                if item.source_page:
                    request_headers["Referer"] = str(item.source_page)

                summary = self.import_url_source(
                    item.url,
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
                asset = getattr(summary, "asset", None)
                if asset is None:
                    raise UrlIngestError(f"Import returned no asset for {name}")
                if item.source_page and f"web_source:{item.source_page}" not in asset.classification_tags:
                    asset.classification_tags.append(f"web_source:{item.source_page}")
                assets.append(asset)
                downloaded.append(asset.original_name or name)
                _emit_progress(index, f"Imported: {asset.original_name or name}")
            except Exception as exc:
                if _looks_like_cancel_error(exc) or _is_cancel_requested():
                    cancelled = True
                    _emit_progress(max(0, index - 1), "Download cancelled by user")
                    break
                failed.append(f"{name}: {exc}")
                _emit_progress(index, f"Failed: {name}")

        if cancelled:
            done_count = min(total_items, max(0, len(downloaded) + len(skipped) + len(failed)))
            _emit_progress(done_count, "Download cancelled by user")
        else:
            _emit_progress(total_items, "Download complete")

        return DownloadReport(
            downloaded=tuple(downloaded),
            skipped=tuple(skipped),
            failed=tuple(failed),
            assets=tuple(assets),
            cancelled=cancelled,
        )

    @staticmethod
    def resolve_web_item_name(candidate_name: str | None, url: str) -> str:
        fallback_name = suggested_name_from_url(url)
        parsed = urlparse(url)
        decoded_path_name = unquote(Path(parsed.path).name or "")
        query_name = WebSourcesService.name_from_query(parsed.query)

        candidates = [
            WebSourcesService.clean_web_name(candidate_name),
            WebSourcesService.clean_web_name(fallback_name),
            WebSourcesService.clean_web_name(decoded_path_name),
            WebSourcesService.clean_web_name(query_name),
        ]

        chosen = next(
            (name for name in candidates if name and not WebSourcesService.is_generic_web_name(name)),
            "",
        )
        if not chosen:
            chosen = next((name for name in candidates if name), "download")

        if not Path(chosen).suffix:
            ext_candidate = next((Path(name).suffix for name in candidates if name and Path(name).suffix), "")
            if ext_candidate:
                chosen = f"{chosen}{ext_candidate.lower()}"

        if WebSourcesService.url_indicates_shiny(url):
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

            base_name = WebSourcesService.resolve_web_item_name(item.name, item.url)
            guessed = guess_import_target(base_name)
            if guessed is ImportTarget.ANIMATED:
                return ImportTarget.ANIMATED
            if guessed is ImportTarget.SHINY:
                return ImportTarget.SHINY
            if guessed is ImportTarget.ITEMS:
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
    def sanitize_registry(raw: object) -> list[dict]:
        if not isinstance(raw, list):
            return []

        sanitized: list[dict] = []
        for source in raw:
            if not isinstance(source, dict):
                continue
            source_id = str(source.get("id", "")).strip()
            name = str(source.get("name", "")).strip() or source_id or "Website"
            if not source_id:
                source_id = dedupe_key(name).replace(" ", "_")

            raw_areas = source.get("areas")
            if not isinstance(raw_areas, list):
                raw_areas = []
            areas: list[dict] = []
            for area in raw_areas:
                if not isinstance(area, dict):
                    continue
                area_url = str(area.get("url", "")).strip()
                if not area_url:
                    continue
                area_id = str(area.get("id", "")).strip()
                label = str(area.get("label", "")).strip() or area_id or "Area"
                if not area_id:
                    area_id = dedupe_key(label).replace(" ", "_")
                areas.append({"id": area_id, "label": label, "url": area_url})

            if not areas:
                continue

            sanitized.append({"id": source_id, "name": name, "areas": areas})

        return sanitized



