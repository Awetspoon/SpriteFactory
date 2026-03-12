"""Application contracts for Sprite Factory v3 scaffold."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from image_engine_v3.domain.models import SessionId, WorkspaceAsset, WorkspaceState


class SessionRepository(Protocol):
    """Port contract for saving/loading session payloads in v3."""

    def save(self, session_id: SessionId, payload: dict[str, Any]) -> Path:
        ...

    def load(self, session_id: SessionId) -> dict[str, Any] | None:
        ...


class WorkspaceRepository(Protocol):
    """Port contract for saving/loading workspace bundles in v3."""

    def save_workspace(
        self,
        *,
        session_payload: dict[str, Any],
        assets_payload: list[dict[str, Any]],
        autosave: bool = False,
        name: str | None = None,
    ) -> Path:
        ...

    def load_workspace(self, path: str | Path) -> dict[str, Any]:
        ...

    def load_latest_autosave_workspace(self) -> dict[str, Any] | None:
        ...


class WorkspaceStateServiceContract(Protocol):
    """Port contract for workspace ordering and section-window state transitions."""

    def ordered_assets(self, state: WorkspaceState) -> list[WorkspaceAsset]:
        ...

    def visible_assets(
        self,
        state: WorkspaceState,
        *,
        ordered_assets: list[WorkspaceAsset] | None = None,
        active_id: str | None = None,
    ) -> tuple[int, list[WorkspaceAsset]]:
        ...

    def select_asset(self, state: WorkspaceState, asset_id: str) -> bool:
        ...

    def close_asset(self, state: WorkspaceState, asset_id: str) -> bool:
        ...

    def toggle_pin(self, state: WorkspaceState, asset_id: str) -> str:
        ...

    def request_window_section(self, state: WorkspaceState, start_index: int) -> bool:
        ...

    def shift_window(self, state: WorkspaceState, direction: int) -> bool:
        ...

    def sync_workspace_tabs(self, state: WorkspaceState) -> Any:
        ...
