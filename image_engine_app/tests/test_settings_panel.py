"""Settings panel wiring tests for editor controls and export fields."""

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

from engine.models import AssetRecord, EditMode  # noqa: E402
from ui.common.state_bindings import EngineUIState  # noqa: E402
from ui.main_window.settings_panel import SettingsPanel  # noqa: E402


@unittest.skipIf(QApplication is None, "PySide6 not installed")
class SettingsPanelTests(unittest.TestCase):
    def _setup_panel(self) -> tuple[QApplication, bool, SettingsPanel, EngineUIState]:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QApplication([])

        panel = SettingsPanel()
        ui_state = EngineUIState()
        panel.bind_state(ui_state)
        return app, owns_app, panel, ui_state

    def test_recent_controls_disable_without_active_asset(self) -> None:
        app, owns_app, panel, _ui_state = self._setup_panel()

        try:
            self.assertIsNotNone(panel._temperature)
            self.assertIsNotNone(panel._ai_bg_remove)
            self.assertIsNotNone(panel._export_format)
            self.assertIsNotNone(panel._export_profile)
            self.assertIsNotNone(panel._ico_sizes)

            self.assertFalse(panel._temperature.isEnabled())
            self.assertFalse(panel._ai_bg_remove.isEnabled())
            self.assertFalse(panel._export_format.isEnabled())
            self.assertFalse(panel._export_profile.isEnabled())
            self.assertFalse(panel._ico_sizes.isEnabled())
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_recent_controls_enable_with_active_asset(self) -> None:
        app, owns_app, panel, ui_state = self._setup_panel()

        try:
            asset = AssetRecord(id="asset-1", original_name="sprite.png")
            asset.edit_state.mode = EditMode.EXPERT
            ui_state.set_active_asset(asset)

            self.assertTrue(panel._temperature.isEnabled())
            self.assertTrue(panel._ai_bg_remove.isEnabled())
            self.assertTrue(panel._export_format.isEnabled())
            self.assertTrue(panel._export_profile.isEnabled())
            self.assertTrue(panel._ico_sizes.isEnabled())
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_ico_sizes_editor_normalizes_and_updates_export_state(self) -> None:
        app, owns_app, panel, ui_state = self._setup_panel()

        try:
            asset = AssetRecord(id="asset-2", original_name="icon_source.png")
            ui_state.set_active_asset(asset)

            panel._ico_sizes.setText("64, 32, bad, 0, 256, 64, 4096")
            panel._on_ico_sizes_changed()

            self.assertEqual([32, 64, 256, 2048], asset.edit_state.settings.export.ico_sizes)
            self.assertEqual("32, 64, 256, 2048", panel._ico_sizes.text())
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_resize_change_scales_dpi(self) -> None:
        app, owns_app, panel, ui_state = self._setup_panel()

        try:
            asset = AssetRecord(id="asset-3", original_name="scale.png")
            ui_state.set_active_asset(asset)

            panel._resize_percent.setValue(200.0)

            self.assertEqual(144, panel._dpi.value())
            self.assertEqual(200.0, float(asset.edit_state.settings.pixel.resize_percent))
            self.assertEqual(144, int(asset.edit_state.settings.pixel.dpi))
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_dpi_change_scales_resize_percent(self) -> None:
        app, owns_app, panel, ui_state = self._setup_panel()

        try:
            asset = AssetRecord(id="asset-4", original_name="print_scale.png")
            ui_state.set_active_asset(asset)

            panel._dpi.setValue(144)

            self.assertEqual(200.0, float(panel._resize_percent.value()))
            self.assertEqual(200.0, float(asset.edit_state.settings.pixel.resize_percent))
            self.assertEqual(144, int(asset.edit_state.settings.pixel.dpi))
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_white_background_mode_updates_alpha_settings(self) -> None:
        app, owns_app, panel, ui_state = self._setup_panel()

        try:
            asset = AssetRecord(id="asset-5", original_name="alpha.png")
            asset.edit_state.mode = EditMode.ADVANCED
            ui_state.set_active_asset(asset)

            self.assertIsNotNone(panel._white_bg_mode)

            panel._white_bg_mode.setCurrentIndex(1)
            self.assertTrue(asset.edit_state.settings.alpha.remove_white_bg)

            panel._white_bg_mode.setCurrentIndex(0)
            self.assertFalse(asset.edit_state.settings.alpha.remove_white_bg)
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_open_encoding_button_emits_signal(self) -> None:
        app, owns_app, panel, ui_state = self._setup_panel()

        try:
            asset = AssetRecord(id="asset-6", original_name="expert.png")
            asset.edit_state.mode = EditMode.EXPERT
            ui_state.set_active_asset(asset)

            self.assertIsNotNone(panel._open_encoding_window_btn)
            fired: list[str] = []
            panel.open_encoding_window_requested.connect(lambda: fired.append("open"))

            panel._open_encoding_window_btn.click()

            self.assertEqual(["open"], fired)
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()


if __name__ == "__main__":
    unittest.main()
