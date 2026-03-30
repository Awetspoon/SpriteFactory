"""Filename helpers for export naming and collision handling."""

from __future__ import annotations

from pathlib import Path
import re


_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def safe_stem(name: str) -> str:
    """Return a filesystem-safe filename stem.

    - strips directory parts
    - removes unsafe characters
    - avoids Windows reserved device names
    """
    stem = Path(name).stem or "asset"
    stem = stem.strip().strip(".")  # avoid hidden/empty stems
    # allow letters, digits, dash, underscore
    stem = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in stem)
    stem = re.sub(r"_+", "_", stem).strip("_") or "asset"
    if stem.upper() in _WINDOWS_RESERVED:
        stem = f"{stem}_file"
    return stem


def safe_filename_fragment(value: str) -> str:
    """Sanitize a template-rendered fragment for safe filename use (no extension)."""
    value = value.strip().strip(".")
    value = value.replace("\\", "_").replace("/", "_")
    value = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)
    value = re.sub(r"_+", "_", value).strip("_") or "asset"
    if value.upper() in _WINDOWS_RESERVED:
        value = f"{value}_file"
    return value


def render_name_template(
    template: str,
    *,
    index: int,
    stem: str,
    group: str = "",
    asset_id: str = "",
    preset: str = "",
) -> str:
    """Render a naming template into a safe filename stem.

    Supported placeholders:
      - {index} (1-based int). You may format: {index:03d}
      - {stem} sanitized stem from original name
      - {group} export group key (png/webp/gifs/...)
      - {asset_id} full asset id
      - {asset_id8} first 8 chars of asset id
      - {preset} last applied preset name (sanitized)
    """
    tpl = (template or "").strip() or "{index:03d}_{stem}"
    ctx = {
        "index": int(index),
        "stem": safe_filename_fragment(stem),
        "group": safe_filename_fragment(group) if group else "",
        "asset_id": safe_filename_fragment(asset_id) if asset_id else "",
        "asset_id8": safe_filename_fragment(asset_id[:8]) if asset_id else "",
        "preset": safe_filename_fragment(preset) if preset else "",
    }
    try:
        rendered = tpl.format(**ctx)
    except Exception:
        # fall back to a safe default if user template is invalid
        rendered = f"{ctx['index']:03d}_{ctx['stem']}"

    rendered = safe_filename_fragment(rendered)
    # keep stems from getting too long (Windows path limits)
    return rendered[:140].rstrip("_") or "asset"


def ensure_unique_path(path: Path, *, overwrite_existing: bool = False) -> Path:
    """Return a unique path by suffixing __N if needed."""
    if overwrite_existing or not path.exists():
        return path

    parent = path.parent
    stem = path.stem
    suffix = path.suffix
    # If stem already ends with __N, keep base stem for consistent increments.
    base = re.sub(r"__\d+$", "", stem)
    for n in range(2, 1000):
        candidate = parent / f"{base}__{n}{suffix}"
        if not candidate.exists():
            return candidate
    # Last resort: use a hash-based suffix
    candidate = parent / f"{base}__{abs(hash(str(path))) % 999999}{suffix}"
    return candidate

