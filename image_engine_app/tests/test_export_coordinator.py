"""Tests for export-bar skip navigation and export coordinator helpers."""

from __future__ import annotations

from datetime import datetime
import unittest

from image_engine_app.engine.models import AssetRecord
from image_engine_app.ui.main_window.export_coordinator import ExportCoordinator


def _asset(asset_id: str, *, name: str | None = None) -> AssetRecord:
    return AssetRecord(
        id=asset_id,
        original_name=name or f"{asset_id}.png",
        source_uri=f"file:///{asset_id}.png",
        created_at=datetime(2026, 1, 1),
    )


class _FakeUIState:
    def __init__(self, active_asset: AssetRecord | None) -> None:
        self.active_asset = active_asset

    def set_active_asset(self, asset: AssetRecord | None) -> None:
        self.active_asset = asset


class _FakeExportBar:
    def auto_next_after_export(self) -> bool:
        return False


class _FakeWindow:
    def __init__(self, assets: list[AssetRecord], active_asset: AssetRecord | None) -> None:
        self._assets = list(assets)
        self.ui_state = _FakeUIState(active_asset)
        self.export_bar = _FakeExportBar()
        self.synced_asset_ids: list[str | None] = []
        self.status_messages: list[str] = []

    def _ordered_workspace_assets(self) -> list[AssetRecord]:
        return list(self._assets)

    def _sync_session_active_asset(self, asset: AssetRecord | None) -> None:
        self.synced_asset_ids.append(asset.id if asset is not None else None)

    def _status(self, text: str) -> None:
        self.status_messages.append(text)


class ExportCoordinatorTests(unittest.TestCase):
    def test_activate_next_asset_advances_selection_and_syncs_session(self) -> None:
        assets = [_asset("asset-a"), _asset("asset-b"), _asset("asset-c")]
        window = _FakeWindow(assets=assets, active_asset=assets[0])

        coordinator = ExportCoordinator(window)
        target = coordinator.activate_next_asset()

        self.assertIsNotNone(target)
        self.assertEqual("asset-b", target.id)
        self.assertEqual("asset-b", window.ui_state.active_asset.id)
        self.assertEqual(["asset-b"], window.synced_asset_ids)

    def test_on_skip_requested_moves_to_next_asset_and_reports_name(self) -> None:
        assets = [_asset("asset-a"), _asset("asset-b", name="Second Sprite.png")]
        window = _FakeWindow(assets=assets, active_asset=assets[0])

        coordinator = ExportCoordinator(window)
        coordinator.on_skip_requested()

        self.assertEqual("asset-b", window.ui_state.active_asset.id)
        self.assertEqual(["asset-b"], window.synced_asset_ids)
        self.assertEqual(["Skipped to next asset: Second Sprite.png"], window.status_messages)

    def test_on_skip_requested_reports_when_already_at_last_asset(self) -> None:
        assets = [_asset("asset-a"), _asset("asset-b")]
        window = _FakeWindow(assets=assets, active_asset=assets[-1])

        coordinator = ExportCoordinator(window)
        coordinator.on_skip_requested()

        self.assertEqual("asset-b", window.ui_state.active_asset.id)
        self.assertEqual([], window.synced_asset_ids)
        self.assertEqual(["Skip unavailable: already at the last asset"], window.status_messages)


if __name__ == "__main__":
    unittest.main()
