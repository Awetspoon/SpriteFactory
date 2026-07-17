"""Qt startup smoke tests for the main window shell."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import tempfile
import unittest


try:
    from PySide6.QtWidgets import QApplication, QSplitter, QTextBrowser, QToolButton, QWidget
except Exception:  # pragma: no cover - optional dependency in some environments
    QApplication = None  # type: ignore[assignment]
    QSplitter = None  # type: ignore[assignment]
    QTextBrowser = None  # type: ignore[assignment]
    QToolButton = None  # type: ignore[assignment]
    QWidget = None  # type: ignore[assignment]

from image_engine_app.app.paths import ensure_app_paths  # noqa: E402
from image_engine_app.app.settings_store import save_path_preferences  # noqa: E402
from image_engine_app.app.ui_controller import ImageEngineUIController  # noqa: E402
from image_engine_app.engine.models import AssetFormat, AssetRecord, SessionState  # noqa: E402
from image_engine_app.engine.process.edit_baseline import capture_detected_settings  # noqa: E402
from image_engine_app.ui.common.shell_tokens import SHELL_GEOMETRY  # noqa: E402
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
            toolbar_buttons = window.findChildren(QToolButton, "toolbarMenuButton")
            toolbar_labels = [button.text() for button in toolbar_buttons]
            self.assertEqual(1, toolbar_labels.count("File"))
            self.assertNotIn("Session", toolbar_labels)
            self.assertNotIn("Import", toolbar_labels)
            self.assertNotIn("Presets", toolbar_labels)
            preset_actions = [action.text() for action in window.control_strip._preset_menu.actions()]
            self.assertIn("Manage Presets...", preset_actions)
            file_button = next(button for button in toolbar_buttons if button.text() == "File")
            file_actions = [action.text() for action in file_button.menu().actions() if not action.isSeparator()]
            self.assertEqual(
                [
                    "New Workspace",
                    "Open Workspace...",
                    "Save Workspace...",
                    "Add Files...",
                    "Add Folder...",
                ],
                file_actions,
            )
            self.assertFalse(hasattr(window.asset_tabs, "_import_button"))
            self.assertIsNotNone(window._workspace_splitter)
            self.assertIsInstance(window._workspace_splitter, QSplitter)
            self.assertIsNotNone(window._workspace_editor_splitter)
            self.assertTrue(hasattr(window.export_bar, "_skip_btn"))
            self.assertFalse(window.export_bar._skip_btn.isEnabled())
            self.assertIsNotNone(window._workspace_left_panel)
            self.assertIsNotNone(window._workspace_inspector_panel)
            self.assertGreaterEqual(
                window._workspace_left_panel.width(),
                SHELL_GEOMETRY.workspace_left_min,
            )
            self.assertLessEqual(
                window._workspace_left_panel.width(),
                SHELL_GEOMETRY.workspace_left_max,
            )
            self.assertGreaterEqual(
                window._workspace_inspector_panel.width(),
                SHELL_GEOMETRY.workspace_inspector_min,
            )
            self.assertLessEqual(
                window._workspace_inspector_panel.width(),
                SHELL_GEOMETRY.workspace_inspector_max,
            )
            editor_shell = window.findChild(QWidget, "workspaceEditorShell")
            self.assertIsNotNone(editor_shell)
            self.assertGreaterEqual(editor_shell.width(), SHELL_GEOMETRY.workspace_editor_min)
            self.assertTrue(window._workspace_inspector_panel.isVisible())
            guide = window.findChild(QTextBrowser, "shellGuideBrowser")
            self.assertIsNotNone(guide)
            guide_text = guide.toPlainText()
            self.assertIn("Skip", guide_text)
            self.assertIn("remove black", guide_text.lower())
            self.assertIn("1. Scan Pages", guide_text)
            self.assertIn("2. Saved Library", guide_text)
            self.assertIn("3. Find Linked Pages", guide_text)
            self.assertIn("4. Found Files and Download", guide_text)
            self.assertIn("Only Clear Found Files empties the result basket", guide_text)
            self.assertIn("New Workspace", guide_text)
            self.assertIn("Add Files", guide_text)
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

    def test_new_workspace_updates_status_bar_without_error(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QApplication([])

        controller = ImageEngineUIController()
        window = ImageEngineMainWindow(controller=controller)

        try:
            window._new_workspace()
            self.assertIsNotNone(window.ui_state.session)
            self.assertIsNone(window.ui_state.active_asset)
            self.assertEqual([], window.workspace_assets)
            self.assertEqual(window.statusBar().currentMessage(), "New workspace created")
        finally:
            window.close()
            if owns_app and app is not None:
                app.quit()

    def test_preset_updates_visible_controls_and_reset_restores_detected_baseline(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QApplication([])

        controller = ImageEngineUIController()
        window = ImageEngineMainWindow(controller=controller)
        asset = AssetRecord(id="preset-flow", original_name="hero.png", format=AssetFormat.PNG)
        asset.classification_tags = ["pixel_art"]
        asset.edit_state.settings.detail.sharpen_amount = 0.07
        capture_detected_settings(asset)

        try:
            window.set_active_asset(asset)
            window._on_control_preset_selected("Sprite Crisp 4x")
            app.processEvents()

            self.assertEqual(400.0, asset.edit_state.settings.pixel.resize_percent)
            self.assertEqual(400.0, window.settings_panel._resize_percent.value())
            self.assertEqual("scale_4x", window.settings_panel._output_size.currentData())
            self.assertNotEqual(0.07, asset.edit_state.settings.detail.sharpen_amount)

            window._on_global_reset_requested()
            app.processEvents()

            self.assertEqual(100.0, asset.edit_state.settings.pixel.resize_percent)
            self.assertEqual(100.0, window.settings_panel._resize_percent.value())
            self.assertEqual("original", window.settings_panel._output_size.currentData())
            self.assertEqual(0.07, asset.edit_state.settings.detail.sharpen_amount)
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

