"""Web Sources smart rules (low-bloat).

This module is intentionally deterministic (no guessing AI).
It supports:
- confidence scoring
- bucket auto-detection
- simple de-dupe key
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, unquote, urlparse

from app.web_sources_models import Confidence, ImportTarget


ALLOWED_IMAGE_EXTS_DEFAULT = {".png", ".gif", ".webp", ".jpg", ".jpeg"}
ALLOWED_ARCHIVE_EXTS_DEFAULT = {".zip"}
_SUPPORTED_EXTS = ALLOWED_IMAGE_EXTS_DEFAULT | ALLOWED_ARCHIVE_EXTS_DEFAULT | {".bmp", ".ico", ".tif", ".tiff"}

_EXT_QUERY_KEYS = (
    "filename",
    "file",
    "name",
    "download",
    "image",
    "img",
    "asset",
    "sprite",
    "format",
    "ext",
    "extension",
    "type",
    "mime",
)

_LIKELY_PATH_HINTS = (
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
    "/icon",
)

_LIKELY_QUERY_HINTS = (
    "image=",
    "img=",
    "sprite=",
    "asset=",
    "file=",
    "filename=",
    "download=",
    "attachment=",
    "format=",
    "ext=",
    "mime=",
    "do=download",
)


@dataclass(frozen=True)
class BucketKeywords:
    shiny: tuple[str, ...] = ("shiny", "_shiny", "-shiny")
    animated: tuple[str, ...] = ("animated", "anim")
    items: tuple[str, ...] = ("item", "items", "icon", "icons", "ball", "pokeball")


def normalize_ext(path_or_url: str) -> str:
    raw = str(path_or_url or "").strip()
    if not raw:
        return ""

    parsed = urlparse(raw)
    path_ext = Path(parsed.path or "").suffix.lower()
    if path_ext in _SUPPORTED_EXTS:
        return path_ext

    try:
        params = parse_qs(parsed.query or "", keep_blank_values=False)
    except Exception:
        params = {}

    for key in _EXT_QUERY_KEYS:
        values = params.get(key, ())
        for value in values:
            inferred = _infer_ext_token(value)
            if inferred:
                return inferred

    return ""


def _infer_ext_token(value: object) -> str:
    text = unquote(str(value or "")).strip().lower()
    if not text:
        return ""

    if text.startswith("image/"):
        text = text.split("/", 1)[1]

    if text in {"jpg", "jpeg"}:
        return ".jpg"
    if text in {"png", "gif", "webp", "zip", "bmp", "ico", "tif", "tiff"}:
        return ".tiff" if text == "tif" else f".{text}"

    suffix = Path(text.split("?")[0].split("#")[0]).suffix.lower()
    if suffix in _SUPPORTED_EXTS:
        return suffix

    return ""


def confidence_for(url: str, *, allowed_exts: set[str]) -> Confidence:
    ext = normalize_ext(url)
    if ext in allowed_exts:
        return Confidence.DIRECT

    lowered = str(url or "").lower()
    parsed = urlparse(lowered)
    path = unquote(parsed.path or "").lower()
    query = unquote(parsed.query or "").lower()
    host = (parsed.netloc or "").lower()

    if any(hint in path for hint in _LIKELY_PATH_HINTS):
        return Confidence.LIKELY
    if any(hint in query for hint in _LIKELY_QUERY_HINTS):
        return Confidence.LIKELY
    if host.startswith(("img.", "images.", "cdn.", "media.")):
        return Confidence.LIKELY
    return Confidence.UNKNOWN


def suggested_name_from_url(url: str) -> str:
    parsed = urlparse(url)
    path_name = unquote(Path(parsed.path).name).strip()
    if path_name:
        return path_name

    params = parse_qs(parsed.query or "", keep_blank_values=False)
    for key in ("filename", "file", "name", "download", "image", "img", "asset", "sprite"):
        values = params.get(key, ())
        for value in values:
            decoded = unquote(str(value or "")).strip()
            if decoded:
                return decoded

    return "download"


def guess_import_target(filename: str, *, keywords: BucketKeywords | None = None) -> ImportTarget:
    kw = keywords or BucketKeywords()
    f = filename.lower()
    if any(k in f for k in kw.shiny):
        return ImportTarget.SHINY
    # GIF strongly implies animated
    if f.endswith(".gif") or any(k in f for k in kw.animated):
        return ImportTarget.ANIMATED
    if any(k in f for k in kw.items):
        return ImportTarget.ITEMS
    return ImportTarget.NORMAL


def dedupe_key(filename: str) -> str:
    """Stable key for duplicate checking (can evolve later).

    v1 uses normalized filename only (good enough and predictable).
    """
    return re.sub(r"\s+", " ", filename.strip().lower())


def filter_allowed(urls: Iterable[str], *, allowed_exts: set[str]) -> tuple[list[str], int]:
    kept: list[str] = []
    filtered = 0
    seen = set()

    for u in urls:
        if not u:
            continue
        if u in seen:
            continue
        seen.add(u)

        ext = normalize_ext(u)
        if ext and ext in allowed_exts:
            kept.append(u)
        else:
            filtered += 1

    return kept, filtered
