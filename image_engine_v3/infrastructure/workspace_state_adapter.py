"""Legacy adapter between v2 workspace/session models and v3 workspace state."""

from __future__ import annotations

from engine.models import AssetRecord, SessionState
from image_engine_v3.domain.models import WorkspaceAsset, WorkspaceSession, WorkspaceState


class LegacyWorkspaceStateAdapter:
    """Converts between legacy workspace/session objects and v3 workspace state."""

    @staticmethod
    def from_legacy(
        *,
        assets: list[AssetRecord],
        session: SessionState | None,
        active_asset: AssetRecord | None,
        window_start: int,
        window_size: int,
    ) -> WorkspaceState:
        workspace_assets = [
            WorkspaceAsset(
                id=asset.id,
                original_name=getattr(asset, "original_name", "") or "",
                source_uri=getattr(asset, "source_uri", "") or "",
            )
            for asset in assets
        ]

        workspace_session: WorkspaceSession | None = None
        if session is not None:
            workspace_session = WorkspaceSession(
                active_tab_asset_id=session.active_tab_asset_id,
                tab_order=list(session.tab_order),
                pinned_tabs=set(session.pinned_tabs),
            )

        active_asset_id = active_asset.id if active_asset is not None else None
        if active_asset_id is None and workspace_session is not None:
            active_asset_id = workspace_session.active_tab_asset_id

        return WorkspaceState(
            assets=workspace_assets,
            active_asset_id=active_asset_id,
            session=workspace_session,
            window_start=max(0, int(window_start)),
            window_size=max(1, int(window_size)),
        )

    @staticmethod
    def sync_session_back(state: WorkspaceState, session: SessionState | None) -> None:
        if session is None:
            return

        session.active_tab_asset_id = state.active_asset_id
        if state.session is None:
            return

        session.tab_order = list(state.session.tab_order)
        session.pinned_tabs = set(state.session.pinned_tabs)

    @staticmethod
    def resolve_active_asset(state: WorkspaceState, assets: list[AssetRecord]) -> AssetRecord | None:
        if state.active_asset_id is None:
            return None
        for asset in assets:
            if asset.id == state.active_asset_id:
                return asset
        return None
