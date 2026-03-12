"""Qt startup smoke tests for the main window shell."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from PySide6.QtWidgets import QApplication
except Exception:  # pragma: no cover - optional dependency in some environments
    QApplication = None  # type: ignore[assignment]

from app.paths import ensure_app_paths  # noqa: E402
from app.settings_store import save_path_preferences  # noqa: E402
from app.ui_controller import ImageEngineUIController  # noqa: E402
from engine.models import SessionState  # noqa: E402
from ui.main_window.main_window import ImageEngineMainWindow  # noqa: E402


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
            self.assertTrue(hasattr(window.preview_panel, "_clear_pane"))
            self.assertTrue(hasattr(window.preview_panel, "_resolve_preview_path_for_view"))
            self.assertTrue(hasattr(window, "web_sources_panel"))
            self.assertTrue(hasattr(window.web_sources_panel, "set_sources"))
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
            window._new_session()
            self.assertIsNotNone(window.ui_state.session)
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