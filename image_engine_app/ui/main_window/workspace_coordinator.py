"""Workspace tab workflow coordinator for the main window."""

from __future__ import annotations

from typing import Any

from engine.models import AssetRecord
from image_engine_v3.application import WorkspaceStateService
from image_engine_v3.domain.models import WorkspaceAsset, WorkspaceState
from image_engine_v3.infrastructure import LegacyWorkspaceStateAdapter
from ui.main_window.asset_tabs import AssetTabItem


class WorkspaceCoordinator:
    """Owns workspace-tab interactions, ordering, and sectioned rendering."""

    def __init__(self, window: Any) -> None:
        self._window = window
        self._state_service = WorkspaceStateService()
        self._state_adapter = LegacyWorkspaceStateAdapter()

    def on_workspace_asset_selected(self, asset_id: str) -> None:
        state = self._build_workspace_state()
        asset = self.find_workspace_asset(asset_id)
        if asset is None:
            return

        selected = self._state_service.select_asset(state, asset_id)
        if not selected and state.active_asset_id != asset_id:
            # Heal stale state when UI/session drift leaves the clicked tab unsynced.
            state.active_asset_id = asset_id
            if state.session is not None:
                state.session.active_tab_asset_id = asset_id

        self._render_tabs_from_state(state)
        asset = self.find_workspace_asset(asset_id)
        self._window._status(f"Active asset: {(asset.original_name or asset.id) if asset is not None else asset_id}")

    def on_workspace_asset_close_requested(self, asset_id: str) -> None:
        asset = self.find_workspace_asset(asset_id)
        if asset is None:
            return

        state = self._build_workspace_state()
        if not self._state_service.close_asset(state, asset_id):
            return

        self._render_tabs_from_state(state, update_assets=True)
        self._window._sync_batch_dialog_items()
        self._window._refresh_export_prediction()
        self._window._status(f"Removed asset: {asset.original_name or asset.id}")

    def on_workspace_pin_requested(self, asset_id: str) -> None:
        if self._window.ui_state.session is None:
            self._window._status("Pin/unpin requires an active session")
            return

        state = self._build_workspace_state()
        status_text = self._state_service.toggle_pin(state, asset_id)

        self._render_tabs_from_state(state)
        self._window._status(status_text)

    def on_workspace_prev_window_requested(self) -> None:
        self.shift_workspace_tab_window(-1)

    def on_workspace_next_window_requested(self) -> None:
        self.shift_workspace_tab_window(1)

    def on_workspace_window_section_requested(self, start_index: int) -> None:
        state = self._build_workspace_state()
        if not self._state_service.request_window_section(state, start_index):
            return

        self._render_tabs_from_state(state)

    def shift_workspace_tab_window(self, direction: int) -> None:
        state = self._build_workspace_state()
        if not self._state_service.shift_window(state, direction):
            return

        self._render_tabs_from_state(state)

    def sync_workspace_tabs(self) -> None:
        state = self._build_workspace_state()
        self._render_tabs_from_state(state)

    def visible_workspace_assets(
        self,
        ordered_assets: list[AssetRecord],
        *,
        active_id: str | None,
    ) -> tuple[int, list[AssetRecord]]:
        state = self._build_workspace_state()
        ordered_workspace = [
            WorkspaceAsset(
                id=asset.id,
                original_name=asset.original_name or "",
                source_uri=asset.source_uri or "",
            )
            for asset in ordered_assets
        ]

        start, visible_workspace = self._state_service.visible_assets(
            state,
            ordered_assets=ordered_workspace,
            active_id=active_id,
        )
        self._window._workspace_tab_window_start = int(state.window_start)

        by_id = {asset.id: asset for asset in ordered_assets}
        visible = [by_id[asset.id] for asset in visible_workspace if asset.id in by_id]
        return start, visible

    def ordered_workspace_assets(self) -> list[AssetRecord]:
        state = self._build_workspace_state()
        ordered_workspace = self._state_service.ordered_assets(state)

        by_id = {asset.id: asset for asset in self._window._workspace_assets}
        return [by_id[asset.id] for asset in ordered_workspace if asset.id in by_id]

    def find_workspace_asset(self, asset_id: str) -> AssetRecord | None:
        for asset in self._window._workspace_assets:
            if asset.id == asset_id:
                return asset
        return None

    def _build_workspace_state(self) -> WorkspaceState:
        return self._state_adapter.from_legacy(
            assets=list(self._window._workspace_assets),
            session=self._window.ui_state.session,
            active_asset=self._window.ui_state.active_asset,
            window_start=int(getattr(self._window, "_workspace_tab_window_start", 0)),
            window_size=max(1, int(getattr(self._window, "_workspace_tab_window_size", 100))),
        )

    def _sync_from_workspace_state(self, state: WorkspaceState, *, update_assets: bool) -> None:
        if update_assets:
            keep_ids = [asset.id for asset in state.assets]
            by_id = {asset.id: asset for asset in self._window._workspace_assets}
            self._window._workspace_assets = [by_id[asset_id] for asset_id in keep_ids if asset_id in by_id]

        self._window._workspace_tab_window_start = int(state.window_start)
        self._state_adapter.sync_session_back(state, self._window.ui_state.session)

        active_asset = self._state_adapter.resolve_active_asset(state, self._window._workspace_assets)
        if self._window.ui_state.active_asset is not active_asset:
            self._window.ui_state.set_active_asset(active_asset)

    def _render_tabs_from_state(self, state: WorkspaceState, *, update_assets: bool = False) -> None:
        render = self._state_service.sync_workspace_tabs(state)
        self._sync_from_workspace_state(state, update_assets=update_assets)

        items = [
            AssetTabItem(
                asset_id=item.asset_id,
                label=item.label,
                tooltip=item.tooltip,
                pinned=item.pinned,
            )
            for item in render.items
        ]
        self._window.asset_tabs.set_tabs(
            items,
            active_asset_id=render.active_asset_id,
            total_count=render.total_count,
            window_start=render.window_start,
            window_size=render.window_size,
        )
