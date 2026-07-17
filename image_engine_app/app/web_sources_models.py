"""Stable application contracts for the Web Sources workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse, urlunparse

from image_engine_app.engine.ingest.web_sources_types import Confidence, ImportTarget


class ScanOrigin(str, Enum):
    ENTERED = "entered"
    SAVED = "saved"
    LINKED = "linked"


@dataclass(frozen=True)
class WebItem:
    url: str
    name: str
    ext: str
    confidence: Confidence
    preview_url: str | None = None
    source_page: str | None = None


@dataclass(frozen=True)
class WebIndexLink:
    label: str
    url: str
    source_page: str | None = None


@dataclass(frozen=True)
class WebPageBookmark:
    """One page the user wants to keep in the Saved Library."""

    url: str
    label: str | None = None


@dataclass(frozen=True)
class SavedWebPage:
    id: str
    label: str
    url: str


@dataclass(frozen=True)
class SavedWebsite:
    id: str
    name: str
    pages: tuple[SavedWebPage, ...] = ()


@dataclass(frozen=True)
class SmartOptions:
    show_likely: bool = False
    auto_sort: bool = True
    skip_duplicates: bool = True
    allow_zip: bool = True


@dataclass(frozen=True)
class WebScanRequest:
    """One scan request shared by entered, saved, and discovered pages."""

    urls: tuple[str, ...]
    smart: SmartOptions = field(default_factory=SmartOptions)
    origin: ScanOrigin = ScanOrigin.ENTERED
    website_id: str | None = None
    page_id: str | None = None


@dataclass(frozen=True)
class WebScanPlan:
    """Validated, deduplicated page list prepared before network work starts."""

    request: WebScanRequest
    urls: tuple[str, ...]
    requested_count: int
    page_limit: int

    @property
    def requires_confirmation(self) -> bool:
        return self.requested_count > self.page_limit

    @property
    def was_capped(self) -> bool:
        return self.requested_count > len(self.urls)


@dataclass(frozen=True)
class WebLinkDiscoveryRequest:
    url: str
    website_id: str | None = None
    page_id: str | None = None


@dataclass(frozen=True)
class WebDownloadRequest:
    items: tuple[WebItem, ...]
    smart: SmartOptions = field(default_factory=SmartOptions)
    target: ImportTarget = ImportTarget.NORMAL
    website_id: str | None = None
    page_id: str | None = None


@dataclass(frozen=True)
class WebDiagnosticsRequest:
    url: str


@dataclass(frozen=True)
class WebSavePagesRequest:
    pages: tuple[WebPageBookmark, ...]


@dataclass(frozen=True)
class WebRemoveSavedPageRequest:
    website_id: str
    page_id: str


@dataclass(frozen=True)
class WebRemoveSavedWebsiteRequest:
    website_id: str


@dataclass(frozen=True)
class ScanResults:
    items: tuple[WebItem, ...]
    filtered_count: int = 0
    failed_pages: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScanMergeResult:
    """Outcome of adding one scan to the persistent Found Files basket."""

    results: ScanResults
    added_count: int = 0
    duplicate_count: int = 0


@dataclass(frozen=True)
class WebSourcesState:
    """Complete non-visual state for one Web Sources workspace."""

    websites: tuple[SavedWebsite, ...] = ()
    selected_website_id: str | None = None
    selected_page_id: str | None = None
    smart: SmartOptions = field(default_factory=SmartOptions)
    linked_pages: tuple[WebIndexLink, ...] = ()
    found_files: tuple[WebItem, ...] = ()
    latest_scan: ScanResults = field(default_factory=lambda: ScanResults(items=()))


@dataclass(frozen=True)
class WebSourcesMutation:
    state: WebSourcesState
    message: str


@dataclass(frozen=True)
class WebScanOutcome:
    state: WebSourcesState
    latest: ScanResults
    merge: ScanMergeResult


@dataclass(frozen=True)
class WebDiscoveryOutcome:
    state: WebSourcesState
    links: tuple[WebIndexLink, ...]


def merge_scan_results(existing: ScanResults, incoming: ScanResults) -> ScanMergeResult:
    """Merge file URLs while preserving the order in which they were discovered."""

    merged_items = list(existing.items)
    seen = {_scan_item_key(item) for item in merged_items}
    added_count = 0
    duplicate_count = 0

    for item in incoming.items:
        key = _scan_item_key(item)
        if key in seen:
            duplicate_count += 1
            continue
        seen.add(key)
        merged_items.append(item)
        added_count += 1

    return ScanMergeResult(
        results=ScanResults(
            items=tuple(merged_items),
            filtered_count=int(incoming.filtered_count or 0),
            failed_pages=tuple(incoming.failed_pages or ()),
        ),
        added_count=added_count,
        duplicate_count=duplicate_count,
    )


def coerce_smart_options(value: object) -> SmartOptions:
    if isinstance(value, SmartOptions):
        return value
    if isinstance(value, dict):
        return SmartOptions(
            show_likely=bool(value.get("show_likely", False)),
            auto_sort=bool(value.get("auto_sort", True)),
            skip_duplicates=bool(value.get("skip_duplicates", True)),
            allow_zip=bool(value.get("allow_zip", True)),
        )
    return SmartOptions()


def _scan_item_key(item: WebItem) -> str:
    raw_url = str(item.url or "").strip()
    parsed = urlparse(raw_url)
    if not parsed.scheme or not parsed.netloc:
        return raw_url.casefold()
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path,
            parsed.params,
            parsed.query,
            "",
        )
    )
