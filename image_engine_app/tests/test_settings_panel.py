"""Settings panel wiring tests for editor controls and export fields."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import sys
import unittest


try:
    from PySide6.QtWidgets import QApplication, QPushButton
except Exception:  # pragma: no cover - optional dependency in some environments
    QApplication = None  # type: ignore[assignment]

from PIL import Image  # noqa: E402

from image_engine_app.engine.models import AssetFormat, AssetRecord, EditMode  # noqa: E402
from image_engine_app.ui.common.state_bindings import EngineUIState  # noqa: E402
from image_engine_app.ui.main_window.settings_panel import SettingsPanel  # noqa: E402


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
            self.assertEqual("white", asset.edit_state.settings.alpha.background_removal_mode)

            panel._white_bg_mode.setCurrentIndex(0)
            self.assertFalse(asset.edit_state.settings.alpha.remove_white_bg)
            self.assertEqual("off", asset.edit_state.settings.alpha.background_removal_mode)

            panel._white_bg_mode.setCurrentIndex(2)
            self.assertFalse(asset.edit_state.settings.alpha.remove_white_bg)
            self.assertEqual("black", asset.edit_state.settings.alpha.background_removal_mode)
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

    def test_header_updates_with_active_asset_and_mode(self) -> None:
        app, owns_app, panel, ui_state = self._setup_panel()

        try:
            asset = AssetRecord(id="asset-7", original_name="hero.png")
            asset.edit_state.mode = EditMode.ADVANCED
            ui_state.set_active_asset(asset)
            ui_state.set_mode(EditMode.ADVANCED)

            self.assertEqual("Settings", panel._header_title.text())
            self.assertIn("hero.png", panel._header_subtitle.text())
            self.assertIn("Advanced mode", panel._header_subtitle.text())
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_toolbox_section_change_updates_header_summary(self) -> None:
        app, owns_app, panel, ui_state = self._setup_panel()

        try:
            asset = AssetRecord(id="asset-8", original_name="workflow.png")
            asset.edit_state.mode = EditMode.EXPERT
            ui_state.set_active_asset(asset)

            export_index = panel._group_indices["Export"]
            self.assertNotEqual(export_index, panel._toolbox.currentIndex())

            panel._toolbox.setCurrentIndex(export_index)

            self.assertEqual(export_index, panel._toolbox.currentIndex())
            self.assertIn("Export", panel._header_subtitle.text())
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_toolbox_section_change_scrolls_active_group_into_view(self) -> None:
        app, owns_app, panel, ui_state = self._setup_panel()

        try:
            asset = AssetRecord(id="asset-8c", original_name="workflow.png")
            asset.edit_state.mode = EditMode.EXPERT
            ui_state.set_active_asset(asset)

            panel.resize(320, 260)
            panel.show()
            app.processEvents()

            scroll_bar = panel.verticalScrollBar()
            self.assertGreater(scroll_bar.maximum(), 0)

            scroll_bar.setValue(scroll_bar.maximum())
            app.processEvents()

            panel._toolbox.setCurrentIndex(panel._group_indices["Export"])
            app.processEvents()

            self.assertLess(scroll_bar.value(), scroll_bar.maximum())
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_settings_group_navigator_uses_stable_button_rail(self) -> None:
        app, owns_app, panel, ui_state = self._setup_panel()

        try:
            asset = AssetRecord(id="asset-8b", original_name="workflow.png")
            asset.edit_state.mode = EditMode.EXPERT
            ui_state.set_active_asset(asset)

            nav_buttons = panel._toolbox.findChildren(QPushButton, "settingsGroupNavButton")

            self.assertEqual(len(SettingsPanel.GROUP_SPECS), len(nav_buttons))
            self.assertTrue(all(button.minimumHeight() >= 34 for button in nav_buttons))
            self.assertEqual("Pixel and Resolution", nav_buttons[0].text())
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_background_status_reports_existing_transparency(self) -> None:
        app, owns_app, panel, ui_state = self._setup_panel()

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                image_path = Path(temp_dir) / "transparent.png"
                image = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
                image.putpixel((5, 5), (40, 180, 220, 255))
                image.save(image_path, format="PNG")

                asset = AssetRecord(id="asset-9", original_name="transparent.png")
                asset.edit_state.mode = EditMode.ADVANCED
                asset.cache_path = str(image_path)
                ui_state.set_active_asset(asset)

                self.assertIsNotNone(panel._background_status)
                self.assertIn("Transparency already exists", panel._background_status.text())
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_background_status_warns_when_gif_cutout_is_likely_wrong(self) -> None:
        app, owns_app, panel, ui_state = self._setup_panel()

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                gif_path = Path(temp_dir) / "sprite.gif"
                frames = [
                    Image.new("RGB", (12, 12), (255, 255, 255)),
                    Image.new("RGB", (12, 12), (255, 255, 255)),
                ]
                for frame in frames:
                    for top in range(2, 10):
                        for left in range(2, 10):
                            frame.putpixel((left, top), (25, 90, 210))
                frames[0].save(
                    gif_path,
                    format="GIF",
                    save_all=True,
                    append_images=frames[1:],
                    duration=[80, 80],
                    loop=0,
                )

                asset = AssetRecord(id="asset-10", original_name="sprite.gif")
                asset.edit_state.mode = EditMode.ADVANCED
                asset.format = AssetFormat.GIF
                asset.cache_path = str(gif_path)
                ui_state.set_active_asset(asset)

                panel._white_bg_mode.setCurrentIndex(2)

                self.assertIn("GIF cutout runs on every frame", panel._background_status.text())
                self.assertIn("does not match the scan", panel._background_status.text())
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()


if __name__ == "__main__":
    unittest.main()


