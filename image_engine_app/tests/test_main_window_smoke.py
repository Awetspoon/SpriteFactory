"""Qt startup smoke tests for the main window shell."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import tempfile
import unittest


try:
    from PySide6.QtWidgets import QApplication, QTextBrowser, QToolButton
except Exception:  # pragma: no cover - optional dependency in some environments
    QApplication = None  # type: ignore[assignment]
    QTextBrowser = None  # type: ignore[assignment]
    QToolButton = None  # type: ignore[assignment]

from image_engine_app.app.paths import ensure_app_paths  # noqa: E402
from image_engine_app.app.settings_store import save_path_preferences  # noqa: E402
from image_engine_app.app.ui_controller import ImageEngineUIController  # noqa: E402
from image_engine_app.engine.models import AssetRecord, EditMode, SessionState  # noqa: E402
from image_engine_app.ui.main_window.main_window import ImageEngineMainWindow  # noqa: E402


def _session(*, session_id: str, last_export_dir: str | None) -> SessionState:
    return SessionState(
        session_id=session_id,
        opened_at=datetime.now(timezone.utc),
        active_tab_asset_id=None,
        tab_order=[],
        pinned_tabs=set(),
        batch_queue=[],
        macros=[],
        last_export_dir=last_export_dir,
    )


@unittest.skipIf(QApplication is None, "PySide6 not installed")
class MainWindowSmokeTests(unittest.TestCase):
    def test_main_window_construction_and_show_offscreen(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QApplication([])

        controller = ImageEngineUIController()
        window = ImageEngineMainWindow(controller=controller)

        try:
            window.show()
            app.processEvents()
            self.assertTrue(hasattr(window.preview_panel, "_clear_pane"))
            self.assertTrue(hasattr(window.preview_panel, "_resolve_preview_path_for_view"))
            self.assertEqual(tuple(window.preview_panel._panes.keys()), ("current", "final"))
            self.assertTrue(hasattr(window, "web_sources_panel"))
            self.assertTrue(hasattr(window.web_sources_panel, "set_sources"))
            self.assertEqual(3, len(window._page_nav_buttons))
            self.assertTrue(window.findChildren(QToolButton, "shellPageRailButton"))
            self.assertFalse(hasattr(window.asset_tabs, "_import_button"))
            self.assertIsNotNone(window._workspace_splitter)
            self.assertIsNotNone(window._workspace_editor_splitter)
            self.assertTrue(hasattr(window.export_bar, "_skip_btn"))
            self.assertFalse(window.export_bar._skip_btn.isEnabled())
            self.assertIsNotNone(window._workspace_left_panel)
            self.assertIsNotNone(window._workspace_inspector_panel)
            self.assertEqual(window.MOCK_WORKSPACE_PANEL_WIDTH, window._workspace_left_panel.width())
            self.assertEqual(window.MOCK_INSPECTOR_PANEL_WIDTH, window._workspace_inspector_panel.width())
            self.assertTrue(window._workspace_inspector_panel.isVisible())
            guide = window.findChild(QTextBrowser, "shellGuideBrowser")
            self.assertIsNotNone(guide)
            self.assertIn("Skip", guide.toPlainText())
            self.assertIn("remove black", guide.toPlainText().lower())
            window._set_preview_view_mode(window.preview_panel.VIEW_FINAL)
            self.assertEqual(window.preview_panel.preview_view_mode(), window.preview_panel.VIEW_FINAL)
            self.assertFalse(window.preview_panel._pane_containers["current"].isVisible())
            self.assertTrue(window.preview_panel._pane_containers["final"].isVisible())
            window._reset_panels_layout()
            self.assertEqual(window.preview_panel.preview_view_mode(), window.preview_panel.VIEW_COMPARE)
            self.assertTrue(window.preview_panel._pane_containers["current"].isVisible())
            self.assertTrue(window.preview_panel._pane_containers["final"].isVisible())
        finally:
            window.close()
            if owns_app and app is not None:
                app.quit()

    def test_new_session_updates_status_bar_without_error(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QApplication([])

        controller = ImageEngineUIController()
        window = ImageEngineMainWindow(controller=controller)

        try:
            asset = AssetRecord(id="asset-reset-1", original_name="sprite.png")
            window.set_active_asset(asset)
            window.ui_state.set_mode(EditMode.EXPERT)
            window._new_session()
            self.assertIsNotNone(window.ui_state.session)
            self.assertIsNone(window.ui_state.active_asset)
            self.assertEqual([], window.workspace_assets)
            self.assertEqual(window.statusBar().currentMessage(), "New session created")
        finally:
            window.close()
            if owns_app and app is not None:
                app.quit()

    def test_export_directory_restores_default_then_remembered_then_session_specific(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QApplication([])

        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            controller = ImageEngineUIController(app_paths=paths)
            window = ImageEngineMainWindow(controller=controller)

            try:
                window.set_session(_session(session_id="session-default", last_export_dir=None))
                self.assertEqual(window.export_bar.export_directory(), str(paths.exports))

                remembered_dir = Path(temp_dir) / "remembered-exports"
                save_path_preferences(paths, last_export_dir=str(remembered_dir))
                window.set_session(_session(session_id="session-remembered", last_export_dir=None))
                self.assertEqual(window.export_bar.export_directory(), str(remembered_dir))

                custom_dir = Path(temp_dir) / "custom-exports"
                window.set_session(_session(session_id="session-custom", last_export_dir=str(custom_dir)))
                self.assertEqual(window.export_bar.export_directory(), str(custom_dir))
            finally:
                window.close()

        if owns_app and app is not None:
            app.quit()

if __name__ == "__main__":
    unittest.main()

