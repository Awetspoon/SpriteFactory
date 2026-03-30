"""Local file/folder ingestion core functions (Prompt 3)."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
from typing import Iterable

from image_engine_app.engine.detect.format_detect import detect_format_from_signature
from image_engine_app.engine.models.asset_record import AssetFormat, AssetRecord, SourceType


SUPPORTED_FORMATS_BY_EXTENSION: dict[str, AssetFormat] = {
    ".jpg": AssetFormat.JPG,
    ".jpeg": AssetFormat.JPG,
    ".png": AssetFormat.PNG,
    ".webp": AssetFormat.WEBP,
    ".tif": AssetFormat.TIFF,
    ".tiff": AssetFormat.TIFF,
    ".bmp": AssetFormat.BMP,
    ".ico": AssetFormat.ICO,
    ".gif": AssetFormat.GIF,
}

LOCAL_SIGNATURE_READ_BYTES = 64


@dataclass(frozen=True)
class LocalScanCandidate:
    """Resolved local file discovered from an input file or folder."""

    source_path: Path
    root_path: Path
    relative_path: Path
    source_type: SourceType


@dataclass
class LocalIngestQueueEntry:
    """Queue entry produced by local ingest before downstream processing."""

    asset: AssetRecord
    queue_path: str
    content_hash: str


@dataclass
class LocalIngestResult:
    """Output bundle for local ingestion scans."""

    queue: list[LocalIngestQueueEntry] = field(default_factory=list)
    duplicates: list[Path] = field(default_factory=list)
    unsupported: list[Path] = field(default_factory=list)


def detect_format_from_extension(path: Path) -> AssetFormat | None:
    """Resolve a supported format from file extension (case-insensitive)."""

    return SUPPORTED_FORMATS_BY_EXTENSION.get(path.suffix.lower())


def detect_format_from_file_signature(path: Path, *, header_bytes: int = LOCAL_SIGNATURE_READ_BYTES) -> AssetFormat | None:
    """Resolve format only when extension is supported and magic signature matches."""

    by_ext = detect_format_from_extension(path)
    if by_ext is None:
        return None

    read_len = max(12, int(header_bytes))
    try:
        with path.open("rb") as handle:
            header = handle.read(read_len)
    except OSError:
        return None

    by_sig = detect_format_from_signature(header)
    if by_sig is AssetFormat.UNKNOWN:
        return None
    if by_sig is not by_ext:
        return None
    return by_sig


def scan_local_files(sources: Iterable[str | Path], *, recursive: bool = True) -> list[LocalScanCandidate]:
    """Expand local files/folders into a deterministic list of file candidates."""

    candidates: list[LocalScanCandidate] = []
    for source in sources:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Local ingest source does not exist: {path}")

        if path.is_file():
            candidates.append(
                LocalScanCandidate(
                    source_path=path.resolve(),
                    root_path=path.resolve().parent,
                    relative_path=Path(path.name),
                    source_type=SourceType.FILE,
                )
            )
            continue

        if not path.is_dir():
            continue

        root = path.resolve()
        walker = root.rglob("*") if recursive else root.glob("*")
        files = sorted((p for p in walker if p.is_file()), key=lambda p: p.as_posix().lower())
        for file_path in files:
            resolved = file_path.resolve()
            candidates.append(
                LocalScanCandidate(
                    source_path=resolved,
                    root_path=root,
                    relative_path=resolved.relative_to(root),
                    source_type=SourceType.FOLDER_ITEM,
                )
            )

    return candidates


def compute_file_hash(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Compute SHA-256 for duplicate detection."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _queue_path_for_candidate(
    candidate: LocalScanCandidate,
    *,
    preserve_structure: bool,
) -> str:
    if not preserve_structure:
        return candidate.source_path.name

    if candidate.source_type is SourceType.FOLDER_ITEM:
        return (Path(candidate.root_path.name) / candidate.relative_path).as_posix()

    return candidate.relative_path.as_posix()


def build_local_ingest_queue(
    sources: Iterable[str | Path],
    *,
    recursive: bool = True,
    preserve_structure: bool = True,
    flatten: bool = False,
    dedupe_by_hash: bool = True,
) -> LocalIngestResult:
    """
    Build local ingest queue entries from files/folders.

    `preserve_structure=True` keeps folder-relative paths in `queue_path`.
    `flatten=True` forces filename-only queue paths.
    """

    if flatten:
        preserve_structure = False

    result = LocalIngestResult()
    seen_hashes: dict[str, Path] = {}

    for candidate in scan_local_files(sources, recursive=recursive):
        file_format = detect_format_from_file_signature(candidate.source_path)
        if file_format is None:
            result.unsupported.append(candidate.source_path)
            continue

        file_hash = compute_file_hash(candidate.source_path)
        if dedupe_by_hash and file_hash in seen_hashes:
            result.duplicates.append(candidate.source_path)
            continue
        seen_hashes.setdefault(file_hash, candidate.source_path)

        asset = AssetRecord(
            source_type=candidate.source_type,
            source_uri=str(candidate.source_path),
            original_name=candidate.source_path.name,
            format=file_format,
        )
        result.queue.append(
            LocalIngestQueueEntry(
                asset=asset,
                queue_path=_queue_path_for_candidate(
                    candidate,
                    preserve_structure=preserve_structure,
                ),
                content_hash=file_hash,
            )
        )

    return result

