"""Tests for settings panel header state helpers."""

from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


from image_engine_app.engine.models import EditMode  # noqa: E402
from image_engine_app.ui.main_window.settings_panel_state import build_settings_panel_header_state  # noqa: E402


class SettingsPanelStateTests(unittest.TestCase):
    def test_header_state_defaults_without_asset(self) -> None:
        state = build_settings_panel_header_state(
            asset=None,
            mode_value=EditMode.SIMPLE.value,
            visible_group_count=0,
            total_group_count=10,
            active_group_title=None,
            has_alpha=False,
            is_gif=False,
        )

        self.assertEqual("Settings", state.title_text)
        self.assertIn("Select an asset", state.subtitle_text)
        self.assertIn("0/10", state.subtitle_text)

    def test_header_state_describes_active_asset(self) -> None:
        asset = SimpleNamespace(
            original_name="hero_sprite.png",
            id="asset-1",
            format=SimpleNamespace(value="png"),
        )
        state = build_settings_panel_header_state(
            asset=asset,
            mode_value=EditMode.EXPERT.value,
            visible_group_count=7,
            total_group_count=10,
            active_group_title="Export",
            has_alpha=True,
            is_gif=False,
        )

        self.assertEqual("Settings", state.title_text)
        self.assertIn("Editing hero_sprite.png", state.subtitle_text)
        self.assertIn("7/10", state.subtitle_text)
        self.assertIn("Expert mode", state.subtitle_text)
        self.assertIn("Export", state.subtitle_text)


if __name__ == "__main__":
    unittest.main()

