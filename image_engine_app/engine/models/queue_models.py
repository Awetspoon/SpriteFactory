"""Batch queue and progress models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from ._serialization import SerializableDataclass


class QueueItemStatus(str, Enum):
    """Status values for batch queue items."""

    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class QueueItem(SerializableDataclass):
    """Batch queue item from the v1.0.1 schema."""

    id: str
    asset_id: str
    status: QueueItemStatus
    progress: float
    notes: str | None = None


@dataclass
class JobState(SerializableDataclass):
    """Aggregate state of a running or queued job set."""

    total: int = 0
    queued: int = 0
    running: int = 0
    done: int = 0
    failed: int = 0
    cancelled: bool = False
    message: str | None = None
    updated_at: datetime | None = None


@dataclass
class ProgressEvent(SerializableDataclass):
    """Normalized progress payload used by UI and background workers."""

    event_type: str
    item_index: int
    item_total: int
    asset_id: str | None = None
    asset_label: str | None = None
    queue_status: str | None = None
    queue_progress: float | None = None
    overall_progress: float | None = None
    stage: str | None = None
    processed_count: int | None = None
    failed_count: int | None = None
    message: str | None = None
    timestamp: datetime | None = None
