"""Tests for v3 workspace state use-cases."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


from image_engine_v3.application.workspace_use_cases import WorkspaceStateService  # noqa: E402
from image_engine_v3.domain.models import WorkspaceAsset, WorkspaceSession, WorkspaceState  # noqa: E402


def _asset(asset_id: str, *, source_uri: str = "") -> WorkspaceAsset:
    return WorkspaceAsset(id=asset_id, original_name=f"{asset_id}.png", source_uri=source_uri)


def _session(*, tab_order: list[str], pinned_tabs: set[str]) -> WorkspaceSession:
    return WorkspaceSession(
        active_tab_asset_id=(tab_order[0] if tab_order else None),
        tab_order=list(tab_order),
        pinned_tabs=set(pinned_tabs),
    )


class V3WorkspaceUseCaseTests(unittest.TestCase):
    def test_ordered_assets_applies_pin_priority_without_tab_order(self) -> None:
        assets = [_asset("asset-a"), _asset("asset-b"), _asset("asset-c")]
        state = WorkspaceState(
            assets=assets,
            session=_session(tab_order=[], pinned_tabs={"asset-c"}),
            active_asset_id="asset-a",
        )

        service = WorkspaceStateService()
        ordered = service.ordered_assets(state)

        self.assertEqual(["asset-c", "asset-a", "asset-b"], [asset.id for asset in ordered])

    def test_visible_assets_returns_all_when_under_window_limit(self) -> None:
        assets = [_asset(f"asset-{idx:03d}") for idx in range(80)]
        state = WorkspaceState(
            assets=assets,
            session=_session(tab_order=[asset.id for asset in assets], pinned_tabs=set()),
            active_asset_id="asset-000",
            window_start=200,
            window_size=100,
        )

        service = WorkspaceStateService()
        start, visible = service.visible_assets(state)

        self.assertEqual(0, start)
        self.assertEqual(0, state.window_start)
        self.assertEqual(80, len(visible))

    def test_toggle_pin_moves_target_into_visible_window_section(self) -> None:
        assets = [_asset(f"asset-{idx:03d}") for idx in range(150)]
        state = WorkspaceState(
            assets=assets,
            session=_session(tab_order=[asset.id for asset in assets], pinned_tabs=set()),
            active_asset_id="asset-000",
            window_start=100,
            window_size=100,
        )

        service = WorkspaceStateService()
        status = service.toggle_pin(state, "asset-120")

        self.assertEqual("Pinned tab: asset-120", status)
        self.assertEqual("asset-120", state.active_asset_id)
        self.assertIsNotNone(state.session)
        self.assertIn("asset-120", state.session.pinned_tabs)
        self.assertEqual(0, state.window_start)

        render = service.sync_workspace_tabs(state)
        self.assertEqual(0, render.window_start)
        self.assertEqual(150, render.total_count)
        self.assertEqual(100, len(render.items))
        self.assertEqual("asset-120", render.items[0].asset_id)

    def test_request_window_section_selects_section_start_asset(self) -> None:
        assets = [_asset(f"asset-{idx:03d}") for idx in range(150)]
        state = WorkspaceState(
            assets=assets,
            session=_session(tab_order=[asset.id for asset in assets], pinned_tabs=set()),
            active_asset_id="asset-005",
            window_start=0,
            window_size=100,
        )

        service = WorkspaceStateService()
        changed = service.request_window_section(state, 120)

        self.assertTrue(changed)
        self.assertEqual(100, state.window_start)
        self.assertEqual("asset-100", state.active_asset_id)
        self.assertIsNotNone(state.session)
        self.assertEqual("asset-100", state.session.active_tab_asset_id)

    def test_shift_window_clamps_and_updates_active_asset(self) -> None:
        assets = [_asset(f"asset-{idx:03d}") for idx in range(150)]
        state = WorkspaceState(
            assets=assets,
            session=_session(tab_order=[asset.id for asset in assets], pinned_tabs=set()),
            active_asset_id="asset-000",
            window_start=0,
            window_size=100,
        )

        service = WorkspaceStateService()
        self.assertFalse(service.shift_window(state, -1))
        self.assertEqual(0, state.window_start)

        self.assertTrue(service.shift_window(state, 1))
        self.assertEqual(100, state.window_start)
        self.assertEqual("asset-100", state.active_asset_id)

        self.assertFalse(service.shift_window(state, 1))
        self.assertEqual(100, state.window_start)

    def test_close_active_asset_promotes_next_asset_and_cleans_session(self) -> None:
        assets = [_asset("asset-a"), _asset("asset-b"), _asset("asset-c")]
        state = WorkspaceState(
            assets=assets,
            session=WorkspaceSession(
                active_tab_asset_id="asset-a",
                tab_order=["asset-a", "asset-b", "asset-c"],
                pinned_tabs={"asset-a", "asset-c"},
            ),
            active_asset_id="asset-a",
            window_start=0,
            window_size=100,
        )

        service = WorkspaceStateService()
        changed = service.close_asset(state, "asset-a")

        self.assertTrue(changed)
        self.assertEqual(["asset-b", "asset-c"], [asset.id for asset in state.assets])
        self.assertEqual("asset-c", state.active_asset_id)
        self.assertIsNotNone(state.session)
        self.assertEqual(["asset-b", "asset-c"], state.session.tab_order)
        self.assertEqual({"asset-c"}, state.session.pinned_tabs)
        self.assertEqual("asset-c", state.session.active_tab_asset_id)

    def test_close_non_active_asset_repairs_stale_session_active_reference(self) -> None:
        assets = [_asset("asset-a"), _asset("asset-b")]
        state = WorkspaceState(
            assets=assets,
            session=WorkspaceSession(
                active_tab_asset_id="asset-b",
                tab_order=["asset-a", "asset-b"],
                pinned_tabs=set(),
            ),
            active_asset_id="asset-a",
            window_start=0,
            window_size=100,
        )

        service = WorkspaceStateService()
        changed = service.close_asset(state, "asset-b")

        self.assertTrue(changed)
        self.assertEqual("asset-a", state.active_asset_id)
        self.assertIsNotNone(state.session)
        self.assertEqual("asset-a", state.session.active_tab_asset_id)

    def test_sync_workspace_tabs_uses_source_name_for_hash_like_assets(self) -> None:
        hash_name = "a" * 32 + ".png"
        assets = [
            WorkspaceAsset(
                id="asset-1",
                original_name=hash_name,
                source_uri="https://example.com/assets/sprite_clean.png",
            ),
        ]
        state = WorkspaceState(
            assets=assets,
            session=_session(tab_order=["asset-1"], pinned_tabs=set()),
            active_asset_id="asset-1",
        )

        service = WorkspaceStateService()
        render = service.sync_workspace_tabs(state)

        self.assertEqual(1, len(render.items))
        self.assertEqual("sprite_clean.png", render.items[0].label)


if __name__ == "__main__":
    unittest.main()



