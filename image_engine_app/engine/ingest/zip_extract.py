"""Safe ZIP extraction for Web Sources.

Rules:
- Only extracts allowed image extensions
- Prevents Zip Slip (path traversal)
- Returns list of extracted file paths
"""

from __future__ import annotations

import os
import zipfile
from pathlib import Path

from image_engine_app.engine.ingest.web_sources_rules import ALLOWED_IMAGE_EXTS_DEFAULT


class ZipExtractError(RuntimeError):
    pass


def _is_safe_member(member_name: str) -> bool:
    # No absolute paths, no traversal
    p = Path(member_name)
    if p.is_absolute():
        return False
    parts = p.parts
    if any(part in ("..", "") for part in parts):
        return False
    return True


def extract_images_only(zip_path: str, out_dir: str, *, allowed_exts: set[str] | None = None) -> list[str]:
    allowed = allowed_exts or set(ALLOWED_IMAGE_EXTS_DEFAULT)
    os.makedirs(out_dir, exist_ok=True)

    extracted: list[str] = []

    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            for info in z.infolist():
                name = info.filename
                if not name or name.endswith("/"):
                    continue
                if not _is_safe_member(name):
                    continue

                ext = Path(name).suffix.lower()
                if ext not in allowed:
                    continue

                target_path = Path(out_dir) / Path(name).name
                with z.open(info) as src, open(target_path, "wb") as dst:
                    dst.write(src.read())
                extracted.append(str(target_path))
    except zipfile.BadZipFile as e:
        raise ZipExtractError(f"Bad ZIP file: {zip_path}") from e

    return extracted


