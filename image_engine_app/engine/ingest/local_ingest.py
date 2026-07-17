"""Deterministic local file, folder, and ZIP ingestion."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import tempfile
from typing import Iterable

from image_engine_app.engine.detect.format_detect import detect_format_from_signature
from image_engine_app.engine.ingest.formats import SUPPORTED_FORMATS_BY_EXTENSION
from image_engine_app.engine.ingest.import_result import (
    ImportIssueKind,
    ImportResult,
    ImportedAsset,
)
from image_engine_app.engine.ingest.zip_extract import ZipExtractError, extract_images_only
from image_engine_app.engine.models.asset_record import AssetFormat, AssetRecord, SourceType

LOCAL_SIGNATURE_READ_BYTES = 64


@dataclass(frozen=True)
class LocalScanCandidate:
    """Resolved file discovered from a selected file or folder."""

    source_path: Path
    root_path: Path
    relative_path: Path
    source_type: SourceType
    archive_path: Path | None = None


def detect_format_from_extension(path: Path) -> AssetFormat | None:
    return SUPPORTED_FORMATS_BY_EXTENSION.get(path.suffix.lower())


def detect_format_from_file_signature(
    path: Path,
    *,
    header_bytes: int = LOCAL_SIGNATURE_READ_BYTES,
) -> AssetFormat | None:
    """Accept a file only when its extension and signature agree."""

    by_ext = detect_format_from_extension(path)
    if by_ext is None:
        return None

    try:
        with path.open("rb") as handle:
            header = handle.read(max(12, int(header_bytes)))
    except OSError:
        return None

    by_signature = detect_format_from_signature(header)
    if by_signature is AssetFormat.UNKNOWN or by_signature is not by_ext:
        return None
    return by_signature


def scan_local_files(
    sources: Iterable[str | Path],
    *,
    recursive: bool = True,
) -> list[LocalScanCandidate]:
    """Expand selected files/folders into a stable, case-insensitive order."""

    candidates: list[LocalScanCandidate] = []
    for source in sources:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Local ingest source does not exist: {path}")

        if path.is_file():
            resolved = path.resolve()
            candidates.append(
                LocalScanCandidate(
                    source_path=resolved,
                    root_path=resolved.parent,
                    relative_path=Path(resolved.name),
                    source_type=SourceType.FILE,
                )
            )
            continue

        if not path.is_dir():
            continue

        root = path.resolve()
        walker = root.rglob("*") if recursive else root.glob("*")
        files = sorted(
            (item for item in walker if item.is_file()),
            key=lambda item: item.as_posix().casefold(),
        )
        candidates.extend(
            LocalScanCandidate(
                source_path=file_path.resolve(),
                root_path=root,
                relative_path=file_path.resolve().relative_to(root),
                source_type=SourceType.FOLDER_ITEM,
            )
            for file_path in files
        )
    return candidates


def compute_file_hash(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def ingest_local_sources(
    sources: Iterable[str | Path],
    *,
    recursive: bool = True,
    preserve_structure: bool = True,
    flatten: bool = False,
    dedupe_by_hash: bool = True,
    archive_extract_root: str | Path | None = None,
) -> ImportResult:
    """Resolve local files, folders, and ZIPs into one raw import result."""

    if flatten:
        preserve_structure = False

    result = ImportResult()
    candidates: list[LocalScanCandidate] = []
    for source in sources:
        try:
            candidates.extend(scan_local_files([source], recursive=recursive))
        except (OSError, ValueError) as exc:
            result.add_issue(ImportIssueKind.FAILED, source, exc)

    expanded: list[LocalScanCandidate] = []
    for candidate in candidates:
        if candidate.source_path.suffix.lower() != ".zip":
            expanded.append(candidate)
            continue
        _expand_archive(candidate, expanded, result, archive_extract_root=archive_extract_root)

    seen_hashes: dict[str, Path] = {}
    for candidate in expanded:
        file_format = detect_format_from_file_signature(candidate.source_path)
        if file_format is None:
            result.add_issue(
                ImportIssueKind.UNSUPPORTED,
                candidate.source_path,
                "unsupported or mismatched image",
            )
            continue

        try:
            content_hash = compute_file_hash(candidate.source_path)
            file_size = int(candidate.source_path.stat().st_size)
        except OSError as exc:
            result.add_issue(ImportIssueKind.FAILED, candidate.source_path, exc)
            continue

        if dedupe_by_hash and content_hash in seen_hashes:
            result.add_issue(
                ImportIssueKind.DUPLICATE,
                candidate.source_path,
                f"same content as {seen_hashes[content_hash]}",
            )
            continue
        seen_hashes.setdefault(content_hash, candidate.source_path)

        source_uri = str(candidate.archive_path or candidate.source_path)
        tags: list[str] = []
        if candidate.archive_path is not None:
            tags.extend(
                [
                    f"archive_source:{candidate.archive_path}",
                    f"archive_member:{candidate.relative_path.as_posix()}",
                ]
            )

        asset = AssetRecord(
            source_type=candidate.source_type,
            source_uri=source_uri,
            cache_path=(str(candidate.source_path) if candidate.archive_path is not None else None),
            original_name=candidate.source_path.name,
            format=file_format,
            classification_tags=tags,
        )
        result.entries.append(
            ImportedAsset(
                asset=asset,
                source=source_uri,
                local_path=candidate.source_path,
                queue_path=_queue_path(candidate, preserve_structure=preserve_structure),
                content_hash=content_hash,
                detected_format=file_format.value,
                bytes_received=file_size,
            )
        )

    return result


def _expand_archive(
    candidate: LocalScanCandidate,
    expanded: list[LocalScanCandidate],
    result: ImportResult,
    *,
    archive_extract_root: str | Path | None,
) -> None:
    try:
        archive_hash = compute_file_hash(candidate.source_path)
        root = Path(
            archive_extract_root
            or (Path(tempfile.gettempdir()) / "SpriteFactory" / "local_archives")
        )
        extract_dir = root / archive_hash[:20]
        extracted_paths = extract_images_only(
            str(candidate.source_path),
            str(extract_dir),
            allowed_exts=set(SUPPORTED_FORMATS_BY_EXTENSION),
        )
    except (OSError, ValueError, ZipExtractError) as exc:
        result.add_issue(ImportIssueKind.FAILED, candidate.source_path, exc)
        return

    if not extracted_paths:
        result.add_issue(ImportIssueKind.UNSUPPORTED, candidate.source_path, "ZIP contains no supported images")
        return

    archive_prefix = candidate.relative_path.with_suffix("")
    for extracted in sorted(extracted_paths, key=str.casefold):
        extracted_path = Path(extracted).resolve()
        try:
            member_path = extracted_path.relative_to(extract_dir.resolve())
        except ValueError:
            result.add_issue(ImportIssueKind.FAILED, extracted_path, "archive member escaped extraction folder")
            continue
        expanded.append(
            LocalScanCandidate(
                source_path=extracted_path,
                root_path=candidate.root_path,
                relative_path=archive_prefix / member_path,
                source_type=candidate.source_type,
                archive_path=candidate.source_path,
            )
        )


def _queue_path(candidate: LocalScanCandidate, *, preserve_structure: bool) -> str:
    if not preserve_structure:
        return candidate.source_path.name
    if candidate.source_type is SourceType.FOLDER_ITEM:
        return (Path(candidate.root_path.name) / candidate.relative_path).as_posix()
    return candidate.relative_path.as_posix()
