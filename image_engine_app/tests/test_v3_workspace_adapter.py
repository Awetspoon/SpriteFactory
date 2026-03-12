"""Tests for v3 legacy workspace-state adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.models import AssetRecord, SessionState  # noqa: E402
from image_engine_v3.domain.models import WorkspaceSession, WorkspaceState  # noqa: E402
from image_engine_v3.infrastructure import LegacyWorkspaceStateAdapter  # noqa: E402


def _session(active_asset_id: str | None) -> SessionState:
    return SessionState(
        session_id="session-test",
        opened_at=datetime.now(timezone.utc),
        active_tab_asset_id=active_asset_id,
        tab_order=["asset-a", "asset-b"],
        pinned_tabs={"asset-b"},
        batch_queue=[],
        macros=[],
        last_export_dir=None,
    )


class V3WorkspaceAdapterTests(unittest.TestCase):
    def test_from_legacy_maps_assets_session_and_active_fallback(self) -> None:
        assets = [
            AssetRecord(id="asset-a", original_name="a.png", source_uri="file:///a.png"),
            AssetRecord(id="asset-b", original_name="b.png", source_uri="file:///b.png"),
        ]
        session = _session(active_asset_id="asset-b")

        state = LegacyWorkspaceStateAdapter.from_legacy(
            assets=assets,
            session=session,
            active_asset=None,
            window_start=120,
            window_size=100,
        )

        self.assertEqual(["asset-a", "asset-b"], [asset.id for asset in state.assets])
        self.assertEqual("asset-b", state.active_asset_id)
        self.assertIsNotNone(state.session)
        self.assertEqual(["asset-a", "asset-b"], state.session.tab_order)
        self.assertEqual({"asset-b"}, state.session.pinned_tabs)
        self.assertEqual(120, state.window_start)
        self.assertEqual(100, state.window_size)

    def test_sync_session_back_applies_v3_state_to_legacy_session(self) -> None:
        session = _session(active_asset_id="asset-a")
        state = WorkspaceState(
            active_asset_id="asset-b",
            session=WorkspaceSession(
                active_tab_asset_id="asset-b",
                tab_order=["asset-b", "asset-c"],
                pinned_tabs={"asset-c"},
            ),
        )

        LegacyWorkspaceStateAdapter.sync_session_back(state, session)

        self.assertEqual("asset-b", session.active_tab_asset_id)
        self.assertEqual(["asset-b", "asset-c"], session.tab_order)
        self.assertEqual({"asset-c"}, session.pinned_tabs)

    def test_resolve_active_asset_returns_matching_legacy_asset(self) -> None:
        assets = [AssetRecord(id="asset-a"), AssetRecord(id="asset-b")]
        state = WorkspaceState(active_asset_id="asset-b")

        active = LegacyWorkspaceStateAdapter.resolve_active_asset(state, assets)

        self.assertIsNotNone(active)
        self.assertEqual("asset-b", active.id)


if __name__ == "__main__":
    unittest.main()
