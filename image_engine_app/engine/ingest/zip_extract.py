"""Safe image-only ZIP extraction shared by every import route.

Rules:
- Only extracts allowed image extensions
- Prevents Zip Slip (path traversal)
- Returns list of extracted file paths
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path, PurePosixPath

from image_engine_app.engine.ingest.formats import SUPPORTED_IMAGE_EXTENSIONS


class ZipExtractError(RuntimeError):
    pass


def _is_safe_member(member_name: str) -> bool:
    normalized = str(member_name or "").replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute():
        return False
    if any(part in {"", ".", ".."} for part in path.parts):
        return False
    return True


def extract_images_only(
    zip_path: str,
    out_dir: str,
    *,
    allowed_exts: set[str] | None = None,
    max_files: int = 5000,
    max_uncompressed_bytes: int = 512 * 1024 * 1024,
    max_member_bytes: int = 128 * 1024 * 1024,
) -> list[str]:
    allowed = {str(ext).lower() for ext in (allowed_exts or SUPPORTED_IMAGE_EXTENSIONS)}
    output_root = Path(out_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    extracted: list[str] = []
    seen_targets: set[str] = set()
    total_uncompressed = 0

    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            for info in archive.infolist():
                name = info.filename
                if not name or name.endswith("/"):
                    continue
                if not _is_safe_member(name):
                    continue

                ext = Path(name).suffix.lower()
                if ext not in allowed:
                    continue

                if len(extracted) >= max(1, int(max_files)):
                    raise ZipExtractError(f"ZIP contains more than {max_files} supported files")
                if int(info.file_size) > max(1, int(max_member_bytes)):
                    raise ZipExtractError(f"ZIP member is too large: {name}")
                total_uncompressed += max(0, int(info.file_size))
                if total_uncompressed > max(1, int(max_uncompressed_bytes)):
                    raise ZipExtractError("ZIP expands beyond the safe uncompressed-size limit")

                relative_path = Path(*PurePosixPath(name.replace("\\", "/")).parts)
                target_path = (output_root / relative_path).resolve()
                try:
                    target_path.relative_to(output_root)
                except ValueError:
                    continue

                target_key = str(target_path).casefold()
                if target_key in seen_targets:
                    continue
                seen_targets.add(target_key)

                target_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as src, target_path.open("wb") as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 1024)
                extracted.append(str(target_path))
    except ZipExtractError:
        raise
    except (zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError) as e:
        raise ZipExtractError(f"Bad ZIP file: {zip_path}") from e

    return extracted


