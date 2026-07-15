"""Web Sources models.

Keep these dataclasses small and stable so UI + controller contracts stay safe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING
from urllib.parse import urlparse, urlunparse

if TYPE_CHECKING:
    from image_engine_app.engine.models import AssetRecord


class Confidence(str, Enum):
    DIRECT = "direct"      # ends with a known extension
    LIKELY = "likely"      # img/srcset hints but no clean extension
    UNKNOWN = "unknown"    # not used in v1 UI by default


class ImportTarget(str, Enum):
    NORMAL = "normal"
    SHINY = "shiny"
    ANIMATED = "animated"
    ITEMS = "items"


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
class SmartOptions:
    show_likely: bool = False
    auto_sort: bool = False
    skip_duplicates: bool = True
    allow_zip: bool = True


@dataclass(frozen=True)
class WebScanRequest:
    """One scan contract shared by entered, saved, and discovered page URLs."""

    urls: tuple[str, ...]
    smart: SmartOptions = field(default_factory=SmartOptions)
    origin: ScanOrigin = ScanOrigin.ENTERED
    website_id: str | None = None
    area_id: str | None = None


@dataclass(frozen=True)
class WebLinkDiscoveryRequest:
    url: str
    website_id: str | None = None
    area_id: str | None = None


@dataclass(frozen=True)
class WebDownloadRequest:
    items: tuple[WebItem, ...]
    smart: SmartOptions = field(default_factory=SmartOptions)
    target: ImportTarget = ImportTarget.NORMAL
    website_id: str | None = None
    area_id: str | None = None


@dataclass(frozen=True)
class WebDiagnosticsRequest:
    url: str


@dataclass(frozen=True)
class ScanResults:
    items: tuple[WebItem, ...]
    filtered_count: int = 0
    failed_pages: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScanMergeResult:
    """Outcome of adding one scan into the persistent Found Files basket."""

    results: ScanResults
    added_count: int = 0
    duplicate_count: int = 0


def merge_scan_results(existing: ScanResults, incoming: ScanResults) -> ScanMergeResult:
    """Merge scan items by normalized URL while preserving discovery order."""

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


class FoundFilesStore:
    """Single source of truth for the persistent Found Files basket."""

    def __init__(self) -> None:
        self._results = ScanResults(items=())

    @property
    def results(self) -> ScanResults:
        return self._results

    @property
    def items(self) -> tuple[WebItem, ...]:
        return self._results.items

    def replace(self, results: ScanResults) -> None:
        self._results = results

    def add(self, results: ScanResults) -> ScanMergeResult:
        outcome = merge_scan_results(self._results, results)
        self._results = outcome.results
        return outcome

    def clear(self) -> None:
        self._results = ScanResults(items=())


@dataclass(frozen=True)
class DownloadReport:
    downloaded: tuple[str, ...]
    skipped: tuple[str, ...]
    failed: tuple[str, ...]
    assets: tuple["AssetRecord", ...] = ()
    cancelled: bool = False


def coerce_smart_options(value: object) -> SmartOptions:
    if isinstance(value, SmartOptions):
        return value
    if isinstance(value, dict):
        return SmartOptions(
            show_likely=bool(value.get("show_likely", False)),
            auto_sort=bool(value.get("auto_sort", False)),
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
