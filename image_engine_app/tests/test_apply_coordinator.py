"""Apply coordinator behavior tests for preset sync and preview refresh wiring."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ui_controller import PresetApplySummary  # noqa: E402
from engine.models import AssetRecord, EditMode  # noqa: E402
from ui.main_window.apply_coordinator import ApplyCoordinator  # noqa: E402


class _FakeUIState:
    def __init__(self, asset: AssetRecord | None) -> None:
        self.active_asset = asset
        self.heavy_counts: list[tuple[int, int]] = []
        self.set_active_asset_calls = 0

    def set_heavy_queue_counts(self, *, queued_count: int, running_count: int) -> None:
        self.heavy_counts.append((queued_count, running_count))

    def set_active_asset(self, asset: AssetRecord | None) -> None:
        self.active_asset = asset
        self.set_active_asset_calls += 1


class _FakeController:
    def __init__(self, *, light_result: bool = False) -> None:
        self.light_result = light_result
        self.apply_light_calls = 0

    def apply_named_preset(self, asset: AssetRecord, preset_name: str) -> PresetApplySummary:
        asset.edit_state.mode = EditMode.ADVANCED
        return PresetApplySummary(
            preset_name=preset_name,
            requires_apply=False,
            queued_heavy_jobs=len(asset.edit_state.queued_heavy_jobs),
        )

    def apply_light_pipeline(self, asset: AssetRecord) -> bool:
        self.apply_light_calls += 1
        return bool(self.light_result)


class _FakeWindow:
    def __init__(self, *, controller: _FakeController, asset: AssetRecord) -> None:
        self.controller = controller
        self.ui_state = _FakeUIState(asset)
        self.status_messages: list[str] = []
        self.refresh_calls = 0

    def _status(self, text: str) -> None:
        self.status_messages.append(text)

    def _refresh_export_prediction(self) -> None:
        self.refresh_calls += 1


class ApplyCoordinatorTests(unittest.TestCase):
    def test_preset_resyncs_active_asset_when_auto_apply_disabled(self) -> None:
        asset = AssetRecord(id="asset-1", original_name="sprite.png")
        asset.edit_state.auto_apply_light = False
        window = _FakeWindow(controller=_FakeController(light_result=False), asset=asset)

        coordinator = ApplyCoordinator(window)
        coordinator.on_preset_requested("Photo Recover")

        self.assertEqual(EditMode.ADVANCED, asset.edit_state.mode)
        self.assertEqual(0, window.controller.apply_light_calls)
        self.assertEqual(1, window.ui_state.set_active_asset_calls)
        self.assertEqual(1, window.refresh_calls)
        self.assertTrue(window.status_messages)

    def test_preset_auto_apply_runs_and_still_resyncs_once(self) -> None:
        asset = AssetRecord(id="asset-2", original_name="sprite2.png")
        asset.edit_state.auto_apply_light = True
        window = _FakeWindow(controller=_FakeController(light_result=True), asset=asset)

        coordinator = ApplyCoordinator(window)
        coordinator.on_preset_requested("Photo Recover")

        self.assertEqual(1, window.controller.apply_light_calls)
        self.assertEqual(1, window.ui_state.set_active_asset_calls)
        self.assertEqual(1, window.refresh_calls)


if __name__ == "__main__":
    unittest.main()

