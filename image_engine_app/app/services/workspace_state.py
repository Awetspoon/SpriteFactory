"""Workspace ordering, selection, pinning, and section-window behavior."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from image_engine_app.engine.models import AssetRecord, WorkspaceState


@dataclass(frozen=True)
class WorkspaceTabRenderItem:
    """Presentation-neutral description of one workspace tab."""

    asset_id: str
    label: str
    tooltip: str
    pinned: bool = False


@dataclass(frozen=True)
class WorkspaceTabRenderState:
    """Prepared workspace-tab state for the UI layer."""

    items: list[WorkspaceTabRenderItem]
    active_asset_id: str | None
    total_count: int
    window_start: int
    window_size: int


@dataclass(frozen=True)
class WorkspaceIntakeResult:
    """Outcome of adding or restoring assets into workspace state."""

    added_assets: tuple[AssetRecord, ...]
    duplicate_ids: tuple[str, ...]
    active_asset_id: str | None


class WorkspaceStateService:
    """Own workspace ordering and section-window state transitions."""

    def add_assets(
        self,
        state: WorkspaceState,
        assets: list[AssetRecord],
        *,
        set_active: bool,
    ) -> WorkspaceIntakeResult:
        """Add unique assets and update session order and visible section once."""

        existing_ids = {asset.id for asset in state.assets}
        added: list[AssetRecord] = []
        duplicate_ids: list[str] = []
        session = state.session
        tab_ids = set(session.tab_order) if session is not None else set()

        for asset in assets:
            if asset.id in existing_ids:
                duplicate_ids.append(asset.id)
                continue
            state.assets.append(asset)
            existing_ids.add(asset.id)
            added.append(asset)
            if session is not None and asset.id not in tab_ids:
                session.tab_order.append(asset.id)
                tab_ids.add(asset.id)

        target_id = state.active_asset_id
        if set_active and added:
            # Enter a newly imported/downloaded batch at its beginning. Selecting
            # the final item forced large intakes to open on their final section.
            target_id = added[0].id
        elif target_id not in existing_ids:
            ordered = self.ordered_assets(state)
            target_id = ordered[0].id if ordered else None
        self._set_active_asset(state, target_id)

        ordered = self.ordered_assets(state)
        self.visible_assets(state, ordered_assets=ordered, active_id=target_id)
        return WorkspaceIntakeResult(
            added_assets=tuple(added),
            duplicate_ids=tuple(duplicate_ids),
            active_asset_id=target_id,
        )

    def replace_assets(
        self,
        state: WorkspaceState,
        assets: list[AssetRecord],
        *,
        preferred_active_id: str | None,
    ) -> WorkspaceIntakeResult:
        """Replace workspace assets while healing stale persisted tab state."""

        unique_assets: list[AssetRecord] = []
        seen_ids: set[str] = set()
        duplicate_ids: list[str] = []
        for asset in assets:
            if asset.id in seen_ids:
                duplicate_ids.append(asset.id)
                continue
            seen_ids.add(asset.id)
            unique_assets.append(asset)

        state.assets = unique_assets
        state.window_start = 0
        session = state.session
        if session is not None:
            ordered_ids: list[str] = []
            ordered_seen: set[str] = set()
            for asset_id in session.tab_order:
                if asset_id in seen_ids and asset_id not in ordered_seen:
                    ordered_ids.append(asset_id)
                    ordered_seen.add(asset_id)
            ordered_ids.extend(asset.id for asset in unique_assets if asset.id not in ordered_seen)
            session.tab_order = ordered_ids
            session.pinned_tabs.intersection_update(seen_ids)

        target_id = preferred_active_id if preferred_active_id in seen_ids else None
        if target_id is None:
            ordered = self.ordered_assets(state)
            target_id = ordered[0].id if ordered else None
        self._set_active_asset(state, target_id)
        self.visible_assets(state, ordered_assets=self.ordered_assets(state), active_id=target_id)
        return WorkspaceIntakeResult(
            added_assets=tuple(unique_assets),
            duplicate_ids=tuple(duplicate_ids),
            active_asset_id=target_id,
        )

    def select_asset(self, state: WorkspaceState, asset_id: str) -> bool:
        asset = self.find_workspace_asset(state, asset_id)
        if asset is None or state.active_asset_id == asset.id:
            return False
        self._set_active_asset(state, asset.id)
        return True

    def close_asset(self, state: WorkspaceState, asset_id: str) -> bool:
        asset = self.find_workspace_asset(state, asset_id)
        if asset is None:
            return False

        ordered_before = self.ordered_assets(state)
        removed_index = next((index for index, item in enumerate(ordered_before) if item.id == asset_id), -1)
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
                target_id = ordered_after[min(next_index, len(ordered_after) - 1)].id
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
        index = next((index for index, item in enumerate(ordered_assets) if item.id == asset_id), None)
        if index is not None:
            window_size = self._normalized_window_size(state.window_size)
            state.window_start = (index // window_size) * window_size

        self.visible_assets(state, ordered_assets=ordered_assets, active_id=state.active_asset_id)
        return f"{action} tab: {asset_id}"

    def request_window_section(self, state: WorkspaceState, start_index: int) -> bool:
        ordered_assets = self.ordered_assets(state)
        total = len(ordered_assets)
        window_size = self._normalized_window_size(state.window_size)
        if total <= window_size:
            return False

        last_start = self.max_workspace_window_start(total=total, window_size=window_size)
        requested_start = max(0, int(start_index))
        new_start = min(last_start, (requested_start // window_size) * window_size)
        if new_start == int(state.window_start):
            return False

        state.window_start = new_start
        self._set_active_asset(state, ordered_assets[new_start].id)
        return True

    def shift_window(self, state: WorkspaceState, direction: int) -> bool:
        ordered_assets = self.ordered_assets(state)
        total = len(ordered_assets)
        window_size = self._normalized_window_size(state.window_size)
        if total <= window_size:
            return False

        step = window_size if direction >= 0 else -window_size
        last_start = self.max_workspace_window_start(total=total, window_size=window_size)
        new_start = max(0, min(last_start, int(state.window_start) + step))
        new_start = (new_start // window_size) * window_size
        if new_start == int(state.window_start):
            return False

        state.window_start = new_start
        self._set_active_asset(state, ordered_assets[new_start].id)
        return True

    def sync_workspace_tabs(self, state: WorkspaceState) -> WorkspaceTabRenderState:
        ordered_assets = self.ordered_assets(state)
        window_start, visible_assets = self.visible_assets(
            state,
            ordered_assets=ordered_assets,
            active_id=state.active_asset_id,
        )
        pinned_ids = set(state.session.pinned_tabs) if state.session is not None else set()
        indexes = {asset.id: index for index, asset in enumerate(ordered_assets)}

        items = [
            WorkspaceTabRenderItem(
                asset_id=asset.id,
                label=self.format_workspace_tab_label(asset, ordered_index=indexes.get(asset.id, 0)),
                tooltip=self.workspace_tab_tooltip(asset),
                pinned=asset.id in pinned_ids,
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

    def ordered_assets(self, state: WorkspaceState) -> list[AssetRecord]:
        assets = list(state.assets)
        session = state.session
        if session is None:
            return assets

        if not session.tab_order:
            ordered = assets
        else:
            by_id = {asset.id: asset for asset in assets}
            ordered = []
            seen: set[str] = set()
            for asset_id in session.tab_order:
                asset = by_id.get(asset_id)
                if asset is not None:
                    ordered.append(asset)
                    seen.add(asset_id)
            ordered.extend(asset for asset in assets if asset.id not in seen)

        pinned_ids = set(session.pinned_tabs)
        if not pinned_ids:
            return ordered
        return [asset for asset in ordered if asset.id in pinned_ids] + [
            asset for asset in ordered if asset.id not in pinned_ids
        ]

    def visible_assets(
        self,
        state: WorkspaceState,
        *,
        ordered_assets: list[AssetRecord] | None = None,
        active_id: str | None = None,
    ) -> tuple[int, list[AssetRecord]]:
        ordered = list(ordered_assets) if ordered_assets is not None else self.ordered_assets(state)
        total = len(ordered)
        window_size = self._normalized_window_size(state.window_size)
        if total <= window_size:
            state.window_start = 0
            return 0, ordered

        last_start = self.max_workspace_window_start(total=total, window_size=window_size)
        start = max(0, min(int(state.window_start), last_start))
        start = (start // window_size) * window_size

        active_target = active_id if active_id is not None else state.active_asset_id
        active_index = next(
            (index for index, asset in enumerate(ordered) if asset.id == active_target),
            None,
        )
        if active_index is not None and not start <= active_index < start + window_size:
            start = max(0, min((active_index // window_size) * window_size, last_start))

        state.window_start = start
        return start, ordered[start : min(total, start + window_size)]

    @staticmethod
    def max_workspace_window_start(*, total: int, window_size: int) -> int:
        if total <= 0:
            return 0
        section_size = max(1, int(window_size))
        return ((total - 1) // section_size) * section_size

    @classmethod
    def format_workspace_tab_label(cls, asset: AssetRecord, *, ordered_index: int) -> str:
        raw_name = (asset.original_name or "").strip() or asset.id
        if cls.is_hash_like_name(raw_name):
            source_name = Path(urlparse(asset.source_uri).path).name.strip()
            if source_name and not cls.is_hash_like_name(source_name):
                raw_name = source_name
            else:
                extension = Path(raw_name).suffix.lower()
                fallback = f"web_asset_{ordered_index + 1}"
                raw_name = f"{fallback}{extension}" if extension else fallback
        return cls.elide_middle(raw_name, max_len=40)

    @staticmethod
    def workspace_tab_tooltip(asset: AssetRecord) -> str:
        name = (asset.original_name or "").strip() or asset.id
        source = (asset.source_uri or "").strip()
        return f"{name}\n{source}" if source else name

    @staticmethod
    def is_hash_like_name(name: str) -> bool:
        stem = Path(name).stem.lower().strip()
        if len(stem) < 24:
            return False
        hex_count = sum(1 for character in stem if character in "0123456789abcdef")
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
    def find_workspace_asset(state: WorkspaceState, asset_id: str | None) -> AssetRecord | None:
        if asset_id is None:
            return None
        return next((asset for asset in state.assets if asset.id == asset_id), None)

    @staticmethod
    def _normalized_window_size(window_size: int) -> int:
        return max(1, int(window_size))

    @staticmethod
    def _set_active_asset(state: WorkspaceState, asset_id: str | None) -> None:
        state.active_asset_id = asset_id
        if state.session is not None:
            state.session.active_tab_asset_id = asset_id
