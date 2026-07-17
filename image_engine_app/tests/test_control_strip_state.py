"""Tests for control strip state helpers."""

from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


from image_engine_app.ui.main_window.control_strip_state import build_control_strip_view_state  # noqa: E402


class ControlStripStateTests(unittest.TestCase):
    def test_missing_asset_defaults_to_disabled_controls(self) -> None:
        state = build_control_strip_view_state(None)

        self.assertFalse(state.has_asset)
        self.assertEqual("No asset", state.queue_badge_text)

    def test_asset_state_reports_source_final_workflow(self) -> None:
        asset = SimpleNamespace(
            edit_state=SimpleNamespace()
        )

        state = build_control_strip_view_state(asset)

        self.assertTrue(state.has_asset)
        self.assertEqual("Refresh Final", state.run_button_text)
        self.assertFalse(state.run_heavy)
        self.assertIn("Current is the source", state.summary_text)
        self.assertIn("Final updates automatically", state.summary_text)

    def test_heavy_queue_state_changes_run_copy_and_badge(self) -> None:
        asset = SimpleNamespace(
            edit_state=SimpleNamespace(
                queued_heavy_jobs=[object()],
            )
        )
        heavy_state = SimpleNamespace(queued_count=2, running_count=0)

        state = build_control_strip_view_state(asset, heavy_state)

        self.assertEqual("Run 2 Heavy", state.run_button_text)
        self.assertTrue(state.run_heavy)
        self.assertEqual("Queued: 2", state.queue_badge_text)
        self.assertEqual("queued", state.queue_badge_tone)


if __name__ == "__main__":
    unittest.main()


