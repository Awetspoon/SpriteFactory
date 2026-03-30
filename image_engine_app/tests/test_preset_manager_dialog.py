"""Preset manager dialog behavior tests."""

from __future__ import annotations

import os
import unittest

try:
    from PySide6.QtWidgets import QApplication
except Exception:  # pragma: no cover - optional dependency in some environments
    QApplication = None  # type: ignore[assignment]

from image_engine_app.app.ui_controller import ImageEngineUIController  # noqa: E402
from image_engine_app.ui.windows.preset_manager import PresetManagerDialog  # noqa: E402


@unittest.skipIf(QApplication is None, "PySide6 not installed")
class PresetManagerDialogTests(unittest.TestCase):
    def _setup_dialog(self) -> tuple[QApplication, bool, ImageEngineUIController, PresetManagerDialog]:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QApplication([])
        controller = ImageEngineUIController()
        dialog = PresetManagerDialog(controller)
        dialog.show()
        app.processEvents()
        return app, owns_app, controller, dialog

    def test_system_preset_selection_shows_template_guidance(self) -> None:
        app, owns_app, controller, dialog = self._setup_dialog()
        try:
            self.assertGreater(dialog._list.count(), 0)
            selected_name = dialog._selected_preset_name()
            self.assertIsNotNone(selected_name)
            self.assertFalse(controller.is_user_preset(selected_name))
            self.assertIn("System", dialog._preset_kind.text())
            self.assertIn("override", dialog._save_hint.text().lower())
            self.assertFalse(dialog._btn_delete.isEnabled())
        finally:
            dialog.close()
            if owns_app and app is not None:
                app.quit()

    def test_duplicate_selected_creates_editable_user_draft(self) -> None:
        app, owns_app, _controller, dialog = self._setup_dialog()
        try:
            dialog._duplicate_selected()
            self.assertTrue(dialog._name.text().endswith(" Copy"))
            self.assertIn("new user preset", dialog._preset_kind.text().lower())
            self.assertFalse(dialog._btn_delete.isEnabled())
        finally:
            dialog.close()
            if owns_app and app is not None:
                app.quit()

    def test_insert_example_and_format_json_roundtrip(self) -> None:
        app, owns_app, _controller, dialog = self._setup_dialog()
        try:
            dialog._insert_example_delta()
            self.assertIn('"cleanup"', dialog._delta.toPlainText())
            dialog._delta.setPlainText('{"b":1,"a":{"z":2}}')
            dialog._format_delta_json()
            formatted = dialog._delta.toPlainText()
            self.assertIn('"a"', formatted)
            self.assertIn('\n  "a"', formatted)
        finally:
            dialog.close()
            if owns_app and app is not None:
                app.quit()

    def test_save_current_creates_user_preset(self) -> None:
        app, owns_app, controller, dialog = self._setup_dialog()
        try:
            dialog._new_preset()
            dialog._name.setText("My Advanced Preset")
            dialog._desc.setText("Custom tuning")
            dialog._formats.setText("png, webp")
            dialog._tags.setText("sprite_sheet, icon")
            dialog._delta.setPlainText('{"cleanup": {"denoise": 0.25}}')
            dialog._save_current()
            self.assertTrue(controller.is_user_preset("My Advanced Preset"))
            self.assertEqual("My Advanced Preset", dialog._selected_preset_name())
            self.assertIn("User", dialog._preset_kind.text())
        finally:
            dialog.close()
            if owns_app and app is not None:
                app.quit()


if __name__ == "__main__":
    unittest.main()
