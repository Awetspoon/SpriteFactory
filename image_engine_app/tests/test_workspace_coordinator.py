"""Workspace coordinator tests for tab ordering and section-window behavior."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.models import AssetRecord, SessionState  # noqa: E402
from ui.main_window.workspace_coordinator import WorkspaceCoordinator  # noqa: E402


def _asset(asset_id: str) -> AssetRecord:
    return AssetRecord(id=asset_id, original_name=f"{asset_id}.png", source_uri=f"file:///{asset_id}.png")


def _session(*, tab_order: list[str], pinned_tabs: set[str]) -> SessionState:
    return SessionState(
        session_id="session-test",
        opened_at=datetime.now(timezone.utc),
        active_tab_asset_id=(tab_order[0] if tab_order else None),
        tab_order=list(tab_order),
        pinned_tabs=set(pinned_tabs),
        batch_queue=[],
        macros=[],
        last_export_dir=None,
    )


class _FakeUIState:
    def __init__(self, session: SessionState | None, active_asset: AssetRecord | None) -> None:
        self.session = session
        self.active_asset = active_asset
        self.set_active_asset_calls = 0

    def set_active_asset(self, asset: AssetRecord | None) -> None:
        self.set_active_asset_calls += 1
        self.active_asset = asset


class _FakeAssetTabs:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def set_tabs(self, items, **kwargs) -> None:  # noqa: ANN001
        self.calls.append({"items": list(items), "kwargs": dict(kwargs)})


class _FakeWindow:
    def __init__(self, *, assets: list[AssetRecord], session: SessionState | None) -> None:
        self._workspace_assets = list(assets)
        self._workspace_tab_window_start = 0
        self._workspace_tab_window_size = 100
        self.ui_state = _FakeUIState(session=session, active_asset=(assets[0] if assets else None))
        self.asset_tabs = _FakeAssetTabs()
        self.status_messages: list[str] = []

    def _sync_session_active_asset(self, asset: AssetRecord | None) -> None:
        if self.ui_state.session is not None:
            self.ui_state.session.active_tab_asset_id = asset.id if asset is not None else None

    def _status(self, text: str) -> None:
        self.status_messages.append(text)

    def _sync_batch_dialog_items(self) -> None:
        return

    def _refresh_export_prediction(self) -> None:
        return


class WorkspaceCoordinatorTests(unittest.TestCase):
    def test_ordered_workspace_assets_applies_pin_priority_without_tab_order(self) -> None:
        assets = [_asset("asset-a"), _asset("asset-b"), _asset("asset-c")]
        session = _session(tab_order=[], pinned_tabs={"asset-c"})
        window = _FakeWindow(assets=assets, session=session)

        coordinator = WorkspaceCoordinator(window)
        ordered = coordinator.ordered_workspace_assets()

        self.assertEqual(["asset-c", "asset-a", "asset-b"], [asset.id for asset in ordered])

    def test_visible_workspace_assets_returns_all_when_under_window_limit(self) -> None:
        assets = [_asset(f"asset-{idx:03d}") for idx in range(80)]
        session = _session(tab_order=[asset.id for asset in assets], pinned_tabs=set())
        window = _FakeWindow(assets=assets, session=session)
        window._workspace_tab_window_start = 200

        coordinator = WorkspaceCoordinator(window)
        ordered = coordinator.ordered_workspace_assets()
        start, visible = coordinator.visible_workspace_assets(ordered, active_id=None)

        self.assertEqual(0, start)
        self.assertEqual(0, window._workspace_tab_window_start)
        self.assertEqual(80, len(visible))

    def test_asset_selection_heals_stale_state_when_service_reports_no_change(self) -> None:
        assets = [_asset("asset-a"), _asset("asset-b")]
        session = _session(tab_order=[asset.id for asset in assets], pinned_tabs=set())
        session.active_tab_asset_id = "asset-b"
        window = _FakeWindow(assets=assets, session=session)
        window.ui_state.active_asset = None

        coordinator = WorkspaceCoordinator(window)
        coordinator.on_workspace_asset_selected("asset-b")

        self.assertIsNotNone(window.ui_state.active_asset)
        self.assertEqual("asset-b", window.ui_state.active_asset.id)
        self.assertEqual(1, window.ui_state.set_active_asset_calls)
        self.assertTrue(window.asset_tabs.calls)
        self.assertEqual("asset-b", window.asset_tabs.calls[-1]["kwargs"]["active_asset_id"])
    def test_pin_request_moves_target_into_visible_window_section(self) -> None:
        assets = [_asset(f"asset-{idx:03d}") for idx in range(150)]
        session = _session(tab_order=[asset.id for asset in assets], pinned_tabs=set())
        window = _FakeWindow(assets=assets, session=session)
        window._workspace_tab_window_start = 100

        coordinator = WorkspaceCoordinator(window)
        coordinator.on_workspace_pin_requested("asset-120")

        self.assertIn("asset-120", session.pinned_tabs)
        self.assertIsNotNone(window.ui_state.active_asset)
        self.assertEqual("asset-120", window.ui_state.active_asset.id)
        self.assertEqual(0, window._workspace_tab_window_start)
        self.assertTrue(window.asset_tabs.calls)
        self.assertEqual(1, window.ui_state.set_active_asset_calls)

        last_call = window.asset_tabs.calls[-1]
        self.assertEqual(0, last_call["kwargs"]["window_start"])
        self.assertEqual(150, last_call["kwargs"]["total_count"])
        self.assertEqual(100, len(last_call["items"]))

    def test_pin_request_large_workspace_avoids_duplicate_active_syncs(self) -> None:
        assets = [_asset(f"asset-{idx:04d}") for idx in range(1025)]
        session = _session(tab_order=[asset.id for asset in assets], pinned_tabs=set())
        window = _FakeWindow(assets=assets, session=session)
        window._workspace_tab_window_start = 900

        coordinator = WorkspaceCoordinator(window)
        coordinator.on_workspace_pin_requested("asset-1000")

        self.assertIn("asset-1000", session.pinned_tabs)
        self.assertEqual("asset-1000", window.ui_state.active_asset.id)
        self.assertEqual(1, window.ui_state.set_active_asset_calls)
        self.assertTrue(window.asset_tabs.calls)

        first_pin_render = window.asset_tabs.calls[-1]
        self.assertEqual(1025, first_pin_render["kwargs"]["total_count"])
        self.assertEqual(100, len(first_pin_render["items"]))

        coordinator.on_workspace_pin_requested("asset-1000")
        self.assertNotIn("asset-1000", session.pinned_tabs)
        self.assertEqual(1, window.ui_state.set_active_asset_calls)


if __name__ == "__main__":
    unittest.main()
