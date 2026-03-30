"""Session, history, and workspace persistence models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ._serialization import SerializableDataclass
from .queue_models import QueueItem


class HistoryAffectsView(str, Enum):
    """Which preview view a history step affects."""

    CURRENT = "current"
    FINAL = "final"
    BOTH = "both"


@dataclass
class HistoryStep(SerializableDataclass):
    """Single history entry from the schema."""

    id: str
    timestamp: datetime
    label: str
    state_snapshot: dict
    affects_view: HistoryAffectsView


@dataclass
class HistoryState(SerializableDataclass):
    """Undo/redo history timeline state."""

    steps: list[HistoryStep] = field(default_factory=list)
    pointer: int = -1


@dataclass
class SessionState(SerializableDataclass):
    """Workspace/session persistence model."""

    session_id: str
    opened_at: datetime
    active_tab_asset_id: str | None = None
    tab_order: list[str] = field(default_factory=list)
    pinned_tabs: set[str] = field(default_factory=set)
    batch_queue: list[QueueItem] = field(default_factory=list)
    macros: list[str] = field(default_factory=list)
    last_export_dir: str | None = None


@dataclass
class TabState(SerializableDataclass):
    """Persisted metadata for a single workspace tab."""

    asset_id: str
    label: str
    pinned: bool = False
    active: bool = False
    window_index: int = 0
    hidden: bool = False
