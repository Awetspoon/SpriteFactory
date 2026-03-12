"""Workspace tab-bar visibility tests for section navigation controls."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from PySide6.QtWidgets import QApplication
except Exception:  # pragma: no cover - optional dependency in some environments
    QApplication = None  # type: ignore[assignment]

from ui.main_window.asset_tabs import AssetTabItem, WorkspaceAssetTabs  # noqa: E402


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
    def _items(count: int) -> list[AssetTabItem]:
        return [AssetTabItem(asset_id=f"asset-{idx:03d}", label=f"asset-{idx:03d}", tooltip="") for idx in range(count)]

    def test_window_controls_hidden_when_not_sectioned(self) -> None:
        app, owns_app, tabs = self._setup_tabs()

        try:
            tabs.set_tabs(self._items(3), active_asset_id="asset-000", total_count=3, window_start=0, window_size=100)
            self.assertTrue(tabs._window_prev_button.isHidden())
            self.assertTrue(tabs._window_next_button.isHidden())
            self.assertTrue(tabs._window_section_combo.isHidden())
            self.assertFalse(tabs._pin_button.isHidden())
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

            tabs.set_tabs(self._items(40), active_asset_id="asset-120", total_count=140, window_start=100, window_size=100)
            self.assertFalse(tabs._window_prev_button.isHidden())
            self.assertTrue(tabs._window_next_button.isHidden())
            self.assertFalse(tabs._window_section_combo.isHidden())
        finally:
            tabs.close()
            if owns_app and app is not None:
                app.quit()


if __name__ == "__main__":
    unittest.main()

