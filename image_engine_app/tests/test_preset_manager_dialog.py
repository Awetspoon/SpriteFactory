"""Preset manager dialog behavior tests."""

from __future__ import annotations

import json
import os
import unittest

try:
    from PySide6.QtWidgets import QApplication
except Exception:  # pragma: no cover - optional dependency in some environments
    QApplication = None  # type: ignore[assignment]

from image_engine_app.app.ui_controller import ImageEngineUIController  # noqa: E402
from image_engine_app.engine.models import AssetFormat, AssetRecord  # noqa: E402
from image_engine_app.engine.process.edit_baseline import capture_detected_settings  # noqa: E402
from image_engine_app.ui.windows.preset_manager import PresetManagerDialog  # noqa: E402


@unittest.skipIf(QApplication is None, "PySide6 not installed")
class PresetManagerDialogTests(unittest.TestCase):
    def _setup_dialog(
        self,
    ) -> tuple[QApplication, bool, ImageEngineUIController, AssetRecord, PresetManagerDialog]:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QApplication([])

        controller = ImageEngineUIController()
        asset = AssetRecord(id="active", original_name="hero.png", format=AssetFormat.PNG)
        asset.classification_tags = ["pixel_art", "transparent"]
        asset.edit_state.settings.cleanup.denoise = 0.12
        capture_detected_settings(asset)
        asset.edit_state.settings.cleanup.denoise = 0.28

        dialog = PresetManagerDialog(controller, active_asset_provider=lambda: asset)
        dialog.show()
        app.processEvents()
        return app, owns_app, controller, asset, dialog

    def test_system_preset_selection_shows_template_guidance(self) -> None:
        app, owns_app, controller, _asset, dialog = self._setup_dialog()
        try:
            selected_name = dialog._selected_preset_name()
            self.assertIsNotNone(selected_name)
            self.assertFalse(controller.is_user_preset(selected_name))
            self.assertIn("System", dialog._preset_kind.text())
            self.assertIn("duplicate", dialog._save_hint.text().lower())
            self.assertFalse(dialog._btn_delete.isEnabled())
        finally:
            dialog.close()
            if owns_app:
                app.quit()

    def test_new_from_active_captures_sparse_controls_and_scope(self) -> None:
        app, owns_app, _controller, _asset, dialog = self._setup_dialog()
        try:
            dialog._new_preset()
            delta = json.loads(dialog._delta.toPlainText())

            self.assertEqual(delta, {"cleanup": {"denoise": 0.28}})
            self.assertEqual(dialog._formats.text(), "png")
            self.assertIn("pixel_art", dialog._tags.text())
            self.assertIn("Cleanup", dialog._capture_status.text())
            self.assertTrue(dialog._name.text().endswith("Polish"))
        finally:
            dialog.close()
            if owns_app:
                app.quit()

    def test_advanced_editor_is_hidden_by_default_and_formats_json(self) -> None:
        app, owns_app, _controller, _asset, dialog = self._setup_dialog()
        try:
            self.assertFalse(dialog._advanced_panel.isVisible())
            dialog._advanced_toggle.setChecked(True)
            app.processEvents()
            self.assertTrue(dialog._advanced_panel.isVisible())

            dialog._delta.setPlainText('{"b":1,"a":{"z":2}}')
            dialog._format_delta_json()
            self.assertIn('\n  "a"', dialog._delta.toPlainText())
        finally:
            dialog.close()
            if owns_app:
                app.quit()

    def test_save_captured_controls_creates_user_preset(self) -> None:
        app, owns_app, controller, _asset, dialog = self._setup_dialog()
        try:
            changes: list[str] = []
            dialog.presets_changed.connect(lambda: changes.append("changed"))
            dialog._new_preset()
            dialog._name.setText("My Sprite Polish")
            dialog._save_current()

            self.assertTrue(controller.is_user_preset("My Sprite Polish"))
            self.assertEqual("My Sprite Polish", dialog._selected_preset_name())
            self.assertEqual(changes, ["changed"])
        finally:
            dialog.close()
            if owns_app:
                app.quit()


if __name__ == "__main__":
    unittest.main()
