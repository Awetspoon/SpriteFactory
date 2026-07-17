"""Tests for the active workspace state service."""

from __future__ import annotations

from datetime import datetime, timezone
import unittest

from image_engine_app.app.services import WorkspaceStateService
from image_engine_app.engine.models import AssetRecord, SessionState, WorkspaceState


def _asset(asset_id: str, *, source_uri: str = "") -> AssetRecord:
    return AssetRecord(
        id=asset_id,
        original_name=f"{asset_id}.png",
        source_uri=source_uri,
    )


def _session(*, tab_order: list[str], pinned_tabs: set[str]) -> SessionState:
    return SessionState(
        session_id="workspace-test",
        opened_at=datetime.now(timezone.utc),
        active_tab_asset_id=tab_order[0] if tab_order else None,
        tab_order=list(tab_order),
        pinned_tabs=set(pinned_tabs),
    )


class WorkspaceStateServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = WorkspaceStateService()

    def test_ordered_assets_applies_pin_priority_without_tab_order(self) -> None:
        assets = [_asset("asset-a"), _asset("asset-b"), _asset("asset-c")]
        state = WorkspaceState(
            assets=assets,
            session=_session(tab_order=[], pinned_tabs={"asset-c"}),
            active_asset_id="asset-a",
        )

        ordered = self.service.ordered_assets(state)

        self.assertEqual(["asset-c", "asset-a", "asset-b"], [asset.id for asset in ordered])
        self.assertIs(assets[2], ordered[0])

    def test_add_assets_selects_first_new_asset_and_opens_its_100_item_section(self) -> None:
        assets = [_asset(f"asset-{index:04d}") for index in range(1459)]
        session = _session(tab_order=[], pinned_tabs=set())
        state = WorkspaceState(session=session, window_size=100)

        outcome = self.service.add_assets(state, assets, set_active=True)

        self.assertEqual(1459, len(outcome.added_assets))
        self.assertEqual("asset-0000", outcome.active_asset_id)
        self.assertEqual("asset-0000", session.active_tab_asset_id)
        self.assertEqual(0, state.window_start)
        self.assertEqual([asset.id for asset in assets], session.tab_order)

    def test_replace_assets_heals_stale_session_ids_without_resetting_asset_edits(self) -> None:
        kept = _asset("asset-kept")
        kept.edit_state.settings.color.brightness = 0.35
        session = _session(
            tab_order=["missing", "asset-kept", "asset-kept"],
            pinned_tabs={"missing", "asset-kept"},
        )
        session.active_tab_asset_id = "missing"
        state = WorkspaceState(
            assets=[_asset("old")],
            session=session,
            active_asset_id="old",
            window_start=500,
            window_size=100,
        )

        outcome = self.service.replace_assets(
            state,
            [kept, kept],
            preferred_active_id=session.active_tab_asset_id,
        )

        self.assertEqual(("asset-kept",), tuple(asset.id for asset in outcome.added_assets))
        self.assertEqual(("asset-kept",), outcome.duplicate_ids)
        self.assertEqual(["asset-kept"], session.tab_order)
        self.assertEqual({"asset-kept"}, session.pinned_tabs)
        self.assertEqual("asset-kept", state.active_asset_id)
        self.assertEqual(0.35, state.assets[0].edit_state.settings.color.brightness)

    def test_visible_assets_returns_all_when_under_window_limit(self) -> None:
        assets = [_asset(f"asset-{index:03d}") for index in range(80)]
        state = WorkspaceState(
            assets=assets,
            session=_session(tab_order=[asset.id for asset in assets], pinned_tabs=set()),
            active_asset_id="asset-000",
            window_start=200,
            window_size=100,
        )

        start, visible = self.service.visible_assets(state)

        self.assertEqual(0, start)
        self.assertEqual(0, state.window_start)
        self.assertEqual(80, len(visible))

    def test_toggle_pin_updates_live_session_and_visible_section(self) -> None:
        assets = [_asset(f"asset-{index:03d}") for index in range(150)]
        session = _session(tab_order=[asset.id for asset in assets], pinned_tabs=set())
        state = WorkspaceState(
            assets=assets,
            session=session,
            active_asset_id="asset-000",
            window_start=100,
            window_size=100,
        )

        status = self.service.toggle_pin(state, "asset-120")
        render = self.service.sync_workspace_tabs(state)

        self.assertEqual("Pinned tab: asset-120", status)
        self.assertEqual("asset-120", state.active_asset_id)
        self.assertEqual("asset-120", session.active_tab_asset_id)
        self.assertIn("asset-120", session.pinned_tabs)
        self.assertEqual(0, render.window_start)
        self.assertEqual(150, render.total_count)
        self.assertEqual(100, len(render.items))
        self.assertEqual("asset-120", render.items[0].asset_id)

    def test_request_window_section_selects_section_start_asset(self) -> None:
        assets = [_asset(f"asset-{index:03d}") for index in range(150)]
        session = _session(tab_order=[asset.id for asset in assets], pinned_tabs=set())
        state = WorkspaceState(
            assets=assets,
            session=session,
            active_asset_id="asset-005",
            window_start=0,
            window_size=100,
        )

        changed = self.service.request_window_section(state, 120)

        self.assertTrue(changed)
        self.assertEqual(100, state.window_start)
        self.assertEqual("asset-100", state.active_asset_id)
        self.assertEqual("asset-100", session.active_tab_asset_id)

    def test_shift_window_clamps_and_updates_active_asset(self) -> None:
        assets = [_asset(f"asset-{index:03d}") for index in range(150)]
        state = WorkspaceState(
            assets=assets,
            session=_session(tab_order=[asset.id for asset in assets], pinned_tabs=set()),
            active_asset_id="asset-000",
            window_start=0,
            window_size=100,
        )

        self.assertFalse(self.service.shift_window(state, -1))
        self.assertTrue(self.service.shift_window(state, 1))
        self.assertEqual(100, state.window_start)
        self.assertEqual("asset-100", state.active_asset_id)
        self.assertFalse(self.service.shift_window(state, 1))

    def test_close_active_asset_promotes_next_asset_and_cleans_session(self) -> None:
        assets = [_asset("asset-a"), _asset("asset-b"), _asset("asset-c")]
        session = _session(
            tab_order=["asset-a", "asset-b", "asset-c"],
            pinned_tabs={"asset-a", "asset-c"},
        )
        state = WorkspaceState(
            assets=assets,
            session=session,
            active_asset_id="asset-a",
        )

        changed = self.service.close_asset(state, "asset-a")

        self.assertTrue(changed)
        self.assertEqual(["asset-b", "asset-c"], [asset.id for asset in state.assets])
        self.assertEqual("asset-c", state.active_asset_id)
        self.assertEqual(["asset-b", "asset-c"], session.tab_order)
        self.assertEqual({"asset-c"}, session.pinned_tabs)
        self.assertEqual("asset-c", session.active_tab_asset_id)

    def test_close_non_active_asset_repairs_stale_session_reference(self) -> None:
        assets = [_asset("asset-a"), _asset("asset-b")]
        session = _session(tab_order=["asset-a", "asset-b"], pinned_tabs=set())
        session.active_tab_asset_id = "asset-b"
        state = WorkspaceState(
            assets=assets,
            session=session,
            active_asset_id="asset-a",
        )

        changed = self.service.close_asset(state, "asset-b")

        self.assertTrue(changed)
        self.assertEqual("asset-a", state.active_asset_id)
        self.assertEqual("asset-a", session.active_tab_asset_id)

    def test_render_uses_source_name_for_hash_like_assets(self) -> None:
        asset = AssetRecord(
            id="asset-1",
            original_name=f"{'a' * 32}.png",
            source_uri="https://example.com/assets/sprite_clean.png",
        )
        state = WorkspaceState(
            assets=[asset],
            session=_session(tab_order=[asset.id], pinned_tabs=set()),
            active_asset_id=asset.id,
        )

        render = self.service.sync_workspace_tabs(state)

        self.assertEqual("sprite_clean.png", render.items[0].label)


if __name__ == "__main__":
    unittest.main()
