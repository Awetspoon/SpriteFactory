"""Tests for control strip state helpers."""

from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


from image_engine_app.engine.models import ApplyTarget  # noqa: E402
from image_engine_app.ui.main_window.control_strip_state import build_control_strip_view_state  # noqa: E402


class ControlStripStateTests(unittest.TestCase):
    def test_missing_asset_defaults_to_disabled_controls(self) -> None:
        state = build_control_strip_view_state(None)

        self.assertFalse(state.has_asset)
        self.assertEqual(ApplyTarget.BOTH.value, state.apply_target)
        self.assertTrue(state.sync_current_final)
        self.assertTrue(state.auto_apply_light)
        self.assertEqual("No asset", state.queue_badge_text)

    def test_asset_state_uses_edit_state_values_and_normalizes_unknown_target(self) -> None:
        asset = SimpleNamespace(
            edit_state=SimpleNamespace(
                apply_target=SimpleNamespace(value="unknown"),
                sync_current_final=False,
                auto_apply_light=False,
            )
        )

        state = build_control_strip_view_state(asset)

        self.assertTrue(state.has_asset)
        self.assertEqual(ApplyTarget.BOTH.value, state.apply_target)
        self.assertFalse(state.sync_current_final)
        self.assertFalse(state.auto_apply_light)
        self.assertEqual("Apply", state.apply_button_text)
        self.assertIn("Views split", state.summary_text)
        self.assertIn("Auto preview off", state.summary_text)

    def test_heavy_queue_state_changes_apply_copy_and_badge(self) -> None:
        asset = SimpleNamespace(
            edit_state=SimpleNamespace(
                apply_target=SimpleNamespace(value=ApplyTarget.CURRENT.value),
                sync_current_final=True,
                auto_apply_light=True,
                queued_heavy_jobs=[object()],
            )
        )
        heavy_state = SimpleNamespace(queued_count=2, running_count=0)

        state = build_control_strip_view_state(asset, heavy_state)

        self.assertEqual("Run 2 Heavy", state.apply_button_text)
        self.assertEqual("Queued: 2", state.queue_badge_text)
        self.assertEqual("queued", state.queue_badge_tone)


if __name__ == "__main__":
    unittest.main()


