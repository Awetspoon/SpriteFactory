"""Core domain model seeds for Sprite Factory v3 scaffold."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AssetId:
    """Strongly-typed asset identifier for v3 domain APIs."""

    value: str


@dataclass(frozen=True)
class SessionId:
    """Strongly-typed session identifier for v3 domain APIs."""

    value: str


@dataclass
class WorkspaceAsset:
    """Minimal workspace asset projection used by v3 workspace state logic."""

    id: str
    original_name: str = ""
    source_uri: str = ""


@dataclass
class WorkspaceSession:
    """Subset of session state required for workspace tab behavior."""

    active_tab_asset_id: str | None = None
    tab_order: list[str] = field(default_factory=list)
    pinned_tabs: set[str] = field(default_factory=set)


@dataclass
class WorkspaceState:
    """Workspace state snapshot consumed by v3 workspace use-cases."""

    assets: list[WorkspaceAsset] = field(default_factory=list)
    active_asset_id: str | None = None
    session: WorkspaceSession | None = None
    window_start: int = 0
    window_size: int = 100
