"""Web Sources models.

Keep these dataclasses small and stable so UI + controller stay patch-safe.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, unquote, urlparse

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


@dataclass(frozen=True)
class WebItem:
    url: str
    name: str
    ext: str
    confidence: Confidence
    preview_url: str | None = None
    source_page: str | None = None


@dataclass(frozen=True)
class SmartOptions:
    show_likely: bool = False
    auto_sort: bool = False
    skip_duplicates: bool = True
    allow_zip: bool = True


@dataclass(frozen=True)
class ScanResults:
    items: tuple[WebItem, ...]
    filtered_count: int = 0


@dataclass(frozen=True)
class DownloadReport:
    downloaded: tuple[str, ...]
    skipped: tuple[str, ...]
    failed: tuple[str, ...]
    assets: tuple["AssetRecord", ...] = ()
    cancelled: bool = False


def coerce_import_target(value: object, *, default: ImportTarget = ImportTarget.NORMAL) -> ImportTarget:
    if isinstance(value, ImportTarget):
        return value
    try:
        return ImportTarget(str(value))
    except Exception:
        return default


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


def coerce_web_item(value: object) -> WebItem | None:
    if isinstance(value, WebItem):
        return value
    if not isinstance(value, dict):
        return None

    url = str(value.get("url", "")).strip()
    if not url:
        return None

    confidence_raw = str(value.get("confidence", Confidence.DIRECT.value)).strip().lower()
    try:
        confidence = Confidence(confidence_raw)
    except Exception:
        confidence = Confidence.DIRECT

    base_name = _name_from_url(url)
    ext = str(value.get("ext", "")).strip().lower() or _ext_from_url(url)

    return WebItem(
        url=url,
        name=str(value.get("name", "")).strip() or base_name,
        ext=ext,
        confidence=confidence,
        preview_url=(str(value.get("preview_url")) if value.get("preview_url") else None),
        source_page=(str(value.get("source_page")) if value.get("source_page") else None),
    )


def coerce_web_items(raw: object) -> list[WebItem]:
    if not isinstance(raw, list):
        return []

    out: list[WebItem] = []
    for entry in raw:
        item = coerce_web_item(entry)
        if item is not None:
            out.append(item)
    return out


def _name_from_url(url: str) -> str:
    parsed = urlparse(url)
    path_name = unquote(Path(parsed.path).name).strip()
    if path_name:
        return path_name

    params = parse_qs(parsed.query or "", keep_blank_values=False)
    for key in ("filename", "file", "name", "download", "image", "img", "asset", "sprite"):
        for value in params.get(key, ()):
            decoded = unquote(str(value or "")).strip()
            if decoded:
                return decoded

    return "download"

def _ext_from_url(url: str) -> str:
    base = url.split("?")[0].split("#")[0]
    return Path(base).suffix.lower()





