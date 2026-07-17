"""Shared result contract for every asset import route."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from image_engine_app.engine.models import AssetRecord


class ImportIssueKind(str, Enum):
    """Stable categories used by local, archive, URL, and web imports."""

    DUPLICATE = "duplicate"
    UNSUPPORTED = "unsupported"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True)
class ImportIssue:
    """One source that could not produce a newly imported asset."""

    kind: ImportIssueKind
    source: str
    reason: str = ""

    @property
    def message(self) -> str:
        source = str(self.source or "").strip()
        reason = str(self.reason or "").strip()
        if source and reason:
            return f"{source}: {reason}"
        return source or reason


@dataclass
class ImportedAsset:
    """One prepared workspace asset plus source-level import metadata."""

    asset: AssetRecord
    source: str
    local_path: Path | None = None
    queue_path: str = ""
    content_hash: str = ""
    detected_format: str | None = None
    bytes_received: int = 0
    dimensions: tuple[int, int] | None = None
    reused: bool = False
    preview_detected_format: str | None = None
    preview_dimensions: tuple[int, int] | None = None
    preview_bytes_sampled: int | None = None
    preview_truncated: bool | None = None

    @property
    def display_name(self) -> str:
        return str(self.asset.original_name or self.source or self.asset.id)


@dataclass
class ImportResult:
    """Single result used by local files, folders, ZIPs, URLs, and web downloads."""

    entries: list[ImportedAsset] = field(default_factory=list)
    issues: list[ImportIssue] = field(default_factory=list)
    cancelled: bool = False

    @property
    def assets(self) -> tuple[AssetRecord, ...]:
        return tuple(entry.asset for entry in self.entries)

    @property
    def primary_entry(self) -> ImportedAsset | None:
        return self.entries[0] if self.entries else None

    @property
    def primary_asset(self) -> AssetRecord | None:
        entry = self.primary_entry
        return entry.asset if entry is not None else None

    @property
    def downloaded(self) -> tuple[str, ...]:
        return tuple(entry.display_name for entry in self.entries if not entry.reused)

    @property
    def reused(self) -> tuple[str, ...]:
        return tuple(entry.display_name for entry in self.entries if entry.reused)

    @property
    def duplicates(self) -> tuple[str, ...]:
        return self._issue_sources(ImportIssueKind.DUPLICATE)

    @property
    def unsupported(self) -> tuple[str, ...]:
        return self._issue_sources(ImportIssueKind.UNSUPPORTED)

    @property
    def skipped(self) -> tuple[str, ...]:
        explicit = self._issue_sources(ImportIssueKind.SKIPPED)
        return (*self.duplicates, *explicit)

    @property
    def failed(self) -> tuple[str, ...]:
        return tuple(
            issue.message
            for issue in self.issues
            if issue.kind is ImportIssueKind.FAILED
        )

    def add_issue(self, kind: ImportIssueKind, source: object, reason: object = "") -> None:
        self.issues.append(
            ImportIssue(
                kind=kind,
                source=str(source or ""),
                reason=str(reason or ""),
            )
        )

    def extend(self, other: "ImportResult") -> None:
        self.entries.extend(other.entries)
        self.issues.extend(other.issues)
        self.cancelled = self.cancelled or other.cancelled

    def _issue_sources(self, kind: ImportIssueKind) -> tuple[str, ...]:
        return tuple(issue.source for issue in self.issues if issue.kind is kind)
