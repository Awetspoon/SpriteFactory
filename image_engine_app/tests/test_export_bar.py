"""Widget tests for the compact export footer bar."""

from __future__ import annotations

import os
import unittest


try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
except Exception:  # pragma: no cover - optional dependency in some environments
    QApplication = None  # type: ignore[assignment]
    Qt = None  # type: ignore[assignment]

from image_engine_app.engine.models import AssetRecord, ExportFormat, ExportProfile  # noqa: E402
from image_engine_app.ui.common.state_bindings import EngineUIState  # noqa: E402
from image_engine_app.ui.main_window.export_bar import ExportBar  # noqa: E402


@unittest.skipIf(QApplication is None, "PySide6 not installed")
class ExportBarWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication.instance()
        cls._owns_app = app is None
        cls._app = app or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        if getattr(cls, "_owns_app", False) and getattr(cls, "_app", None) is not None:
            cls._app.quit()

    def test_size_badge_uses_dedicated_pill_style(self) -> None:
        bar = ExportBar()
        ui_state = EngineUIState()
        bar.bind_state(ui_state)

        try:
            self.assertEqual("exportSizeBadge", bar._size_label.objectName())
            self.assertGreaterEqual(bar._size_label.minimumHeight(), 24)
            self.assertGreaterEqual(bar._size_label.minimumWidth(), 88)
            self.assertEqual(int(bar._size_label.alignment()), int(Qt.AlignmentFlag.AlignCenter))

            ui_state.set_active_asset(AssetRecord(id="asset-1", original_name="sprite.png"))
            ui_state.export_prediction_changed.emit("Estimate 42 KB")
            self.assertEqual("Estimate 42 KB", bar._size_label.text())

            ui_state.set_active_asset(None)
            self.assertEqual("Estimate --", bar._size_label.text())
        finally:
            bar.close()

    def test_folder_actions_are_grouped_in_menu(self) -> None:
        bar = ExportBar()
        ui_state = EngineUIState()
        bar.bind_state(ui_state)
        ui_state.set_active_asset(AssetRecord(id="asset-2", original_name="sprite.png"))

        browse_calls: list[str] = []
        open_calls: list[str] = []
        bar.browse_export_dir_requested.connect(lambda: browse_calls.append("browse"))
        bar.open_export_dir_requested.connect(lambda: open_calls.append("open"))

        try:
            self.assertEqual("exportBarMenuAction", bar._folder_menu_btn.objectName())
            self.assertEqual("Auto-next", bar._auto_next_toggle.text())
            menu = bar._folder_menu_btn.menu()
            self.assertIsNotNone(menu)
            assert menu is not None
            actions = [action for action in menu.actions() if not action.isSeparator()]
            self.assertEqual(["Choose Folder", "Open Folder"], [action.text() for action in actions])

            actions[0].trigger()
            actions[1].trigger()
            self.assertEqual(["browse"], browse_calls)
            self.assertEqual(["open"], open_calls)
        finally:
            bar.close()

    def test_profile_control_applies_real_export_defaults(self) -> None:
        bar = ExportBar()
        ui_state = EngineUIState()
        bar.bind_state(ui_state)
        asset = AssetRecord(id="asset-3", original_name="print.png")
        ui_state.set_active_asset(asset)

        try:
            print_index = bar._profile_combo.findData(ExportProfile.PRINT.value)
            self.assertGreaterEqual(print_index, 0)
            bar._profile_combo.setCurrentIndex(print_index)

            export = asset.edit_state.settings.export
            self.assertEqual(ExportProfile.PRINT, export.export_profile)
            self.assertEqual(ExportFormat.TIFF, export.format)
            self.assertEqual(100, export.quality)
            self.assertEqual(0, export.compression_level)
            self.assertFalse(export.strip_metadata)
        finally:
            bar.close()


if __name__ == "__main__":
    unittest.main()
