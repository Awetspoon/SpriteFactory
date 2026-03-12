"""V3 workspace state use-cases for tab ordering, pinning, and section windows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from image_engine_v3.domain.models import WorkspaceAsset, WorkspaceState


@dataclass(frozen=True)
class WorkspaceTabRenderItem:
    """Presentation-neutral tab item projection for workspace tabs."""

    asset_id: str
    label: str
    tooltip: str
    pinned: bool = False


@dataclass(frozen=True)
class WorkspaceTabRenderState:
    """Prepared workspace tab render payload for presentation adapters."""

    items: list[WorkspaceTabRenderItem]
    active_asset_id: str | None
    total_count: int
    window_start: int
    window_size: int


class WorkspaceStateService:
    """Owns workspace ordering and section-window state transitions."""

    def select_asset(self, state: WorkspaceState, asset_id: str) -> bool:
        asset = self.find_workspace_asset(state, asset_id)
        if asset is None:
            return False
        if state.active_asset_id == asset.id:
            return False
        self._set_active_asset(state, asset.id)
        return True

    def close_asset(self, state: WorkspaceState, asset_id: str) -> bool:
        asset = self.find_workspace_asset(state, asset_id)
        if asset is None:
            return False

        ordered_before = self.ordered_assets(state)
        removed_index = next((idx for idx, item in enumerate(ordered_before) if item.id == asset_id), -1)

        state.assets = [item for item in state.assets if item.id != asset_id]

        session = state.session
        if session is not None:
            session.tab_order = [tab_id for tab_id in session.tab_order if tab_id != asset_id]
            session.pinned_tabs.discard(asset_id)

        if state.active_asset_id == asset_id:
            ordered_after = self.ordered_assets(state)
            target_id: str | None = None
            if ordered_after:
                next_index = removed_index if removed_index >= 0 else 0
                if next_index >= len(ordered_after):
                    next_index = len(ordered_after) - 1
                target_id = ordered_after[next_index].id
            self._set_active_asset(state, target_id)
        elif session is not None and session.active_tab_asset_id == asset_id:
            session.active_tab_asset_id = state.active_asset_id

        self.visible_assets(state, ordered_assets=self.ordered_assets(state), active_id=state.active_asset_id)
        return True

    def toggle_pin(self, state: WorkspaceState, asset_id: str) -> str:
        session = state.session
        if session is None:
            return "Pin/unpin requires an active session"

        if asset_id in session.pinned_tabs:
            session.pinned_tabs.remove(asset_id)
            action = "Unpinned"
        else:
            session.pinned_tabs.add(asset_id)
            action = "Pinned"

        asset = self.find_workspace_asset(state, asset_id)
        if asset is not None:
            self._set_active_asset(state, asset.id)

        ordered_assets = self.ordered_assets(state)
        index = next((idx for idx, item in enumerate(ordered_assets) if item.id == asset_id), None)
        if index is not None:
            max_tabs = self._normalized_window_size(state.window_size)
            state.window_start = (index // max_tabs) * max_tabs

        self.visible_assets(state, ordered_assets=ordered_assets, active_id=state.active_asset_id)
        return f"{action} tab: {asset_id}"

    def request_window_section(self, state: WorkspaceState, start_index: int) -> bool:
        ordered_assets = self.ordered_assets(state)
        total = len(ordered_assets)
        max_tabs = self._normalized_window_size(state.window_size)
        if total <= max_tabs:
            return False

        last_section_start = self.max_workspace_window_start(total=total, window_size=max_tabs)
        requested_start = max(0, int(start_index))
        new_start = min(last_section_start, (requested_start // max_tabs) * max_tabs)
        if new_start == int(state.window_start):
            return False

        state.window_start = new_start
        target = ordered_assets[new_start]
        self._set_active_asset(state, target.id)
        return True

    def shift_window(self, state: WorkspaceState, direction: int) -> bool:
        ordered_assets = self.ordered_assets(state)
        total = len(ordered_assets)
        max_tabs = self._normalized_window_size(state.window_size)
        if total <= max_tabs:
            return False

        step = max_tabs if direction >= 0 else -max_tabs
        last_section_start = self.max_workspace_window_start(total=total, window_size=max_tabs)
        new_start = max(0, min(last_section_start, int(state.window_start) + step))
        new_start = (new_start // max_tabs) * max_tabs
        if new_start == int(state.window_start):
            return False

        state.window_start = new_start
        target = ordered_assets[new_start]
        self._set_active_asset(state, target.id)
        return True

    def sync_workspace_tabs(self, state: WorkspaceState) -> WorkspaceTabRenderState:
        ordered_assets = self.ordered_assets(state)
        window_start, visible_assets = self.visible_assets(
            state,
            ordered_assets=ordered_assets,
            active_id=state.active_asset_id,
        )

        session = state.session
        pinned_ids = set(session.pinned_tabs) if session is not None else set()
        ordered_index_by_id = {asset.id: idx for idx, asset in enumerate(ordered_assets)}

        items = [
            WorkspaceTabRenderItem(
                asset_id=asset.id,
                label=self.format_workspace_tab_label(asset, ordered_index=ordered_index_by_id.get(asset.id, 0)),
                tooltip=self.workspace_tab_tooltip(asset),
                pinned=(asset.id in pinned_ids),
            )
            for asset in visible_assets
        ]

        return WorkspaceTabRenderState(
            items=items,
            active_asset_id=state.active_asset_id,
            total_count=len(ordered_assets),
            window_start=window_start,
            window_size=self._normalized_window_size(state.window_size),
        )

    def ordered_assets(self, state: WorkspaceState) -> list[WorkspaceAsset]:
        assets = list(state.assets)
        session = state.session
        if session is None:
            return assets

        if not session.tab_order:
            ordered = assets
        else:
            by_id = {asset.id: asset for asset in assets}
            ordered: list[WorkspaceAsset] = []
            seen: set[str] = set()

            for asset_id in session.tab_order:
                asset = by_id.get(asset_id)
                if asset is None:
                    continue
                ordered.append(asset)
                seen.add(asset_id)

            for asset in assets:
                if asset.id in seen:
                    continue
                ordered.append(asset)

        pinned_ids = set(session.pinned_tabs)
        if not pinned_ids:
            return ordered

        pinned_assets = [asset for asset in ordered if asset.id in pinned_ids]
        unpinned_assets = [asset for asset in ordered if asset.id not in pinned_ids]
        return pinned_assets + unpinned_assets

    def visible_assets(
        self,
        state: WorkspaceState,
        *,
        ordered_assets: list[WorkspaceAsset] | None = None,
        active_id: str | None = None,
    ) -> tuple[int, list[WorkspaceAsset]]:
        ordered = list(ordered_assets) if ordered_assets is not None else self.ordered_assets(state)

        total = len(ordered)
        max_tabs = self._normalized_window_size(state.window_size)
        if total <= max_tabs:
            state.window_start = 0
            return 0, ordered

        last_section_start = self.max_workspace_window_start(total=total, window_size=max_tabs)
        start = max(0, min(int(state.window_start), last_section_start))
        start = (start // max_tabs) * max_tabs

        active_target = active_id if active_id is not None else state.active_asset_id
        active_index: int | None = None
        if active_target is not None:
            active_index = next((i for i, asset in enumerate(ordered) if asset.id == active_target), None)

        if active_index is not None and (active_index < start or active_index >= start + max_tabs):
            start = (active_index // max_tabs) * max_tabs
            start = max(0, min(start, last_section_start))

        state.window_start = start
        end = min(total, start + max_tabs)
        return start, ordered[start:end]

    @staticmethod
    def max_workspace_window_start(*, total: int, window_size: int) -> int:
        if total <= 0:
            return 0
        section_size = max(1, int(window_size))
        return ((total - 1) // section_size) * section_size

    @classmethod
    def format_workspace_tab_label(cls, asset: WorkspaceAsset, *, ordered_index: int) -> str:
        raw_name = (asset.original_name or "").strip() or asset.id

        if cls.is_hash_like_name(raw_name):
            source_name = Path(urlparse(asset.source_uri).path).name.strip()
            if source_name and not cls.is_hash_like_name(source_name):
                raw_name = source_name
            else:
                ext = Path(raw_name).suffix.lower()
                fallback_name = f"web_asset_{ordered_index + 1}"
                raw_name = f"{fallback_name}{ext}" if ext else fallback_name

        return cls.elide_middle(raw_name, max_len=40)

    @staticmethod
    def workspace_tab_tooltip(asset: WorkspaceAsset) -> str:
        name = (asset.original_name or "").strip() or asset.id
        source = (asset.source_uri or "").strip()
        if source:
            return f"{name}\n{source}"
        return name

    @staticmethod
    def is_hash_like_name(name: str) -> bool:
        stem = Path(name).stem.lower().strip()
        if len(stem) < 24:
            return False
        hex_count = sum(1 for char in stem if char in "0123456789abcdef")
        return (hex_count / len(stem)) >= 0.9

    @staticmethod
    def elide_middle(text: str, *, max_len: int) -> str:
        value = text.strip()
        if len(value) <= max_len:
            return value
        head = max(6, (max_len - 3) // 2)
        tail = max(6, max_len - 3 - head)
        return f"{value[:head]}...{value[-tail:]}"

    @staticmethod
    def find_workspace_asset(state: WorkspaceState, asset_id: str) -> WorkspaceAsset | None:
        for asset in state.assets:
            if asset.id == asset_id:
                return asset
        return None

    @staticmethod
    def _normalized_window_size(window_size: int) -> int:
        return max(1, int(window_size))

    @staticmethod
    def _set_active_asset(state: WorkspaceState, asset_id: str | None) -> None:
        state.active_asset_id = asset_id
        if state.session is not None:
            state.session.active_tab_asset_id = asset_id
