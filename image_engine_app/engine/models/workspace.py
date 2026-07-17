"""Workspace state shared by application services and presentation code."""

from __future__ import annotations

from dataclasses import dataclass, field

from .asset_record import AssetRecord
from .session_state import SessionState


@dataclass
class WorkspaceState:
    """Live workspace state used by tab and section-window operations."""

    assets: list[AssetRecord] = field(default_factory=list)
    active_asset_id: str | None = None
    session: SessionState | None = None
    window_start: int = 0
    window_size: int = 100
