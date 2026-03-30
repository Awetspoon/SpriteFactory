"""Workspace rail visibility tests for section navigation controls."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest


try:
    from PySide6.QtWidgets import QApplication
except Exception:  # pragma: no cover - optional dependency in some environments
    QApplication = None  # type: ignore[assignment]

from image_engine_app.ui.main_window.asset_tabs import AssetTabItem, WorkspaceAssetTabs  # noqa: E402


@unittest.skipIf(QApplication is None, "PySide6 not installed")
class WorkspaceAssetTabsTests(unittest.TestCase):
    def _setup_tabs(self) -> tuple[QApplication, bool, WorkspaceAssetTabs]:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QApplication([])

        tabs = WorkspaceAssetTabs()
        return app, owns_app, tabs

    @staticmethod
    def _items(count: int, *, start: int = 0) -> list[AssetTabItem]:
        return [
            AssetTabItem(
                asset_id=f"asset-{idx:03d}",
                label=f"asset-{idx:03d}",
                tooltip="",
            )
            for idx in range(start, start + count)
        ]

    def test_window_controls_hidden_when_not_sectioned(self) -> None:
        app, owns_app, tabs = self._setup_tabs()

        try:
            tabs.set_tabs(self._items(3), active_asset_id="asset-000", total_count=3, window_start=0, window_size=100)
            self.assertTrue(tabs._window_prev_button.isHidden())
            self.assertTrue(tabs._window_next_button.isHidden())
            self.assertTrue(tabs._window_section_combo.isHidden())
            self.assertTrue(tabs._pin_button.isHidden())
            self.assertFalse(tabs._remove_button.isHidden())
            self.assertEqual(3, tabs._asset_list.count())
        finally:
            tabs.close()
            if owns_app and app is not None:
                app.quit()

    def test_empty_workspace_hides_asset_list_and_shows_compact_summary(self) -> None:
        app, owns_app, tabs = self._setup_tabs()

        try:
            tabs.set_tabs([], active_asset_id=None, total_count=0, window_start=0, window_size=100)
            self.assertTrue(tabs._asset_list.isHidden())
            self.assertIn("Import a file", tabs._summary_label.text())
        finally:
            tabs.close()
            if owns_app and app is not None:
                app.quit()

    def test_window_controls_show_only_available_direction(self) -> None:
        app, owns_app, tabs = self._setup_tabs()

        try:
            tabs.set_tabs(self._items(100), active_asset_id="asset-000", total_count=140, window_start=0, window_size=100)
            self.assertTrue(tabs._window_prev_button.isHidden())
            self.assertFalse(tabs._window_next_button.isHidden())
            self.assertFalse(tabs._window_section_combo.isHidden())
            self.assertEqual(100, tabs._asset_list.count())

            tabs.set_tabs(self._items(40, start=100), active_asset_id="asset-120", total_count=140, window_start=100, window_size=100)
            self.assertFalse(tabs._window_prev_button.isHidden())
            self.assertTrue(tabs._window_next_button.isHidden())
            self.assertFalse(tabs._window_section_combo.isHidden())
            self.assertEqual(40, tabs._asset_list.count())
            self.assertEqual("asset-120", tabs.active_asset_id())
        finally:
            tabs.close()
            if owns_app and app is not None:
                app.quit()

    def test_set_active_asset_selects_matching_list_row(self) -> None:
        app, owns_app, tabs = self._setup_tabs()

        try:
            tabs.set_tabs(self._items(5), active_asset_id="asset-001", total_count=5, window_start=0, window_size=100)
            tabs.set_active_asset("asset-004")
            self.assertEqual("asset-004", tabs.active_asset_id())
        finally:
            tabs.close()
            if owns_app and app is not None:
                app.quit()


if __name__ == "__main__":
    unittest.main()



