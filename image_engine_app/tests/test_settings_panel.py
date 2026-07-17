"""Settings panel wiring tests for editor controls and export fields."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch


try:
    from PySide6.QtWidgets import QApplication, QToolButton
except Exception:  # pragma: no cover - optional dependency in some environments
    QApplication = None  # type: ignore[assignment]

from PIL import Image  # noqa: E402

from image_engine_app.app.ui_controller import ImageEngineUIController  # noqa: E402
from image_engine_app.engine.analyze.background_scan import BackgroundScanResult  # noqa: E402
from image_engine_app.engine.models import (  # noqa: E402
    AssetFormat,
    AssetRecord,
    EditMode,
    SourceImageMetadata,
)
from image_engine_app.ui.common.shell_tokens import SHELL_GEOMETRY  # noqa: E402
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
        controller = ImageEngineUIController()

        def apply_setting(group_name: str, field_name: str, value: object) -> None:
            asset = ui_state.active_asset
            if asset is None:
                return
            controller.update_asset_setting(asset, group_name, field_name, value)
            ui_state.set_active_asset(asset)

        def apply_output_size(choice_key: str) -> None:
            asset = ui_state.active_asset
            if asset is None:
                return
            controller.apply_asset_output_size(asset, choice_key)
            ui_state.set_active_asset(asset)

        def reset_settings(field_paths: object) -> None:
            asset = ui_state.active_asset
            if asset is None:
                return
            controller.reset_asset_settings(
                asset,
                tuple(field_paths or ()),
                refresh_final=False,
            )
            ui_state.set_active_asset(asset)

        ui_state.edit_setting_requested.connect(apply_setting)
        ui_state.edit_settings_reset_requested.connect(reset_settings)
        ui_state.output_size_requested.connect(apply_output_size)
        return app, owns_app, panel, ui_state

    def test_recent_controls_disable_without_active_asset(self) -> None:
        app, owns_app, panel, _ui_state = self._setup_panel()

        try:
            self.assertIsNotNone(panel._temperature)
            self.assertIsNotNone(panel._export_format)
            self.assertIsNotNone(panel._ico_sizes)

            self.assertFalse(panel._temperature.isEnabled())
            self.assertFalse(panel._export_format.isEnabled())
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
            self.assertTrue(panel._export_format.isEnabled())
            self.assertFalse(panel._ico_sizes.isEnabled())
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_republishing_same_asset_reuses_the_source_background_scan(self) -> None:
        app, owns_app, panel, ui_state = self._setup_panel()

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                source = Path(temp_dir) / "sprite.png"
                Image.new("RGBA", (16, 16), (120, 80, 200, 255)).save(source)
                asset = AssetRecord(
                    id="scan-cache",
                    original_name=source.name,
                    source_uri=str(source),
                    cache_path=str(source),
                    format=AssetFormat.PNG,
                )

                with patch(
                    "image_engine_app.ui.main_window.settings_panel.inspect_background_state",
                    return_value=BackgroundScanResult(),
                ) as inspect:
                    ui_state.set_active_asset(asset)
                    ui_state.set_active_asset(asset)

                self.assertEqual(1, inspect.call_count)
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

    def test_resize_change_does_not_change_metadata_dpi(self) -> None:
        app, owns_app, panel, ui_state = self._setup_panel()

        try:
            asset = AssetRecord(id="asset-3", original_name="scale.png")
            ui_state.set_active_asset(asset)

            panel._resize_percent.setValue(200.0)

            self.assertEqual(72, panel._dpi.value())
            self.assertEqual(200.0, float(asset.edit_state.settings.pixel.resize_percent))
            self.assertEqual(72, int(asset.edit_state.settings.pixel.dpi))
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_output_size_choice_updates_real_pixel_controls(self) -> None:
        app, owns_app, panel, ui_state = self._setup_panel()

        try:
            asset = AssetRecord(id="asset-size", original_name="sprite.png")
            ui_state.set_active_asset(asset)

            index = panel._output_size.findData("height_720")
            panel._output_size.setCurrentIndex(index)

            self.assertEqual(100.0, asset.edit_state.settings.pixel.resize_percent)
            self.assertIsNone(asset.edit_state.settings.pixel.width)
            self.assertEqual(720, asset.edit_state.settings.pixel.height)
            self.assertEqual(720, panel._target_height.value())

            index = panel._output_size.findData("scale_4x")
            panel._output_size.setCurrentIndex(index)

            self.assertEqual(400.0, asset.edit_state.settings.pixel.resize_percent)
            self.assertIsNone(asset.edit_state.settings.pixel.width)
            self.assertIsNone(asset.edit_state.settings.pixel.height)
            self.assertEqual(400.0, panel._resize_percent.value())
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_manual_size_controls_switch_chooser_to_custom(self) -> None:
        app, owns_app, panel, ui_state = self._setup_panel()

        try:
            asset = AssetRecord(id="asset-custom-size", original_name="sprite.png")
            ui_state.set_active_asset(asset)

            panel._target_width.setValue(512)

            self.assertEqual("custom", panel._output_size.currentData())
            self.assertEqual(512, asset.edit_state.settings.pixel.width)
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_dpi_change_does_not_resize_pixels(self) -> None:
        app, owns_app, panel, ui_state = self._setup_panel()

        try:
            asset = AssetRecord(id="asset-4", original_name="print_scale.png")
            ui_state.set_active_asset(asset)

            panel._dpi.setValue(144)

            self.assertEqual(100.0, float(panel._resize_percent.value()))
            self.assertEqual(100.0, float(asset.edit_state.settings.pixel.resize_percent))
            self.assertEqual(144, int(asset.edit_state.settings.pixel.dpi))
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_visual_control_sends_one_edit_request_and_updates_state(self) -> None:
        app, owns_app, panel, ui_state = self._setup_panel()

        try:
            asset = AssetRecord(id="asset-live-final", original_name="sprite.png")
            ui_state.set_active_asset(asset)
            calls: list[tuple[str, str, object]] = []
            ui_state.edit_setting_requested.connect(lambda group, field, value: calls.append((group, field, value)))

            panel._brightness.setValue(0.25)

            self.assertEqual([("color", "brightness", 0.25)], calls)
            self.assertEqual(0.25, asset.edit_state.settings.color.brightness)
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_changed_control_shows_single_reset_and_preserves_other_edits(self) -> None:
        app, owns_app, panel, ui_state = self._setup_panel()

        try:
            asset = AssetRecord(id="asset-reset-one", original_name="sprite.png")
            ui_state.set_active_asset(asset)
            panel._brightness.setValue(0.25)
            panel._contrast.setValue(0.4)

            brightness_reset = next(
                reset
                for reset, paths in panel._reset_bindings
                if paths == (("color", "brightness"),)
            )
            contrast_reset = next(
                reset
                for reset, paths in panel._reset_bindings
                if paths == (("color", "contrast"),)
            )
            self.assertFalse(brightness_reset.isHidden())
            self.assertFalse(contrast_reset.isHidden())

            brightness_reset.click()

            self.assertEqual(0.0, asset.edit_state.settings.color.brightness)
            self.assertEqual(0.4, asset.edit_state.settings.color.contrast)
            self.assertTrue(brightness_reset.isHidden())
            self.assertFalse(contrast_reset.isHidden())
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_source_facts_are_shown_separately_from_editable_controls(self) -> None:
        app, owns_app, panel, ui_state = self._setup_panel()

        try:
            asset = AssetRecord(
                id="asset-source-facts",
                original_name="sprite.gif",
                format=AssetFormat.GIF,
                dimensions_original=(32, 48),
                source_metadata=SourceImageMetadata(
                    color_mode="P",
                    dpi=144,
                    frame_count=12,
                    loop_count=0,
                ),
            )
            asset.capabilities.has_alpha = True
            asset.capabilities.is_animated = True
            ui_state.set_active_asset(asset)

            self.assertIn("GIF | 32 x 48 px | P | alpha | DPI 144", panel._pixel_source_info.text())
            self.assertIn("12 frames", panel._gif_source_info.text())
            self.assertIn("continuous loop", panel._gif_source_info.text())
            self.assertEqual(0, panel._frame_delay.value())
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

    def test_header_updates_with_active_asset(self) -> None:
        app, owns_app, panel, ui_state = self._setup_panel()

        try:
            asset = AssetRecord(id="asset-7", original_name="hero.png")
            asset.edit_state.mode = EditMode.ADVANCED
            ui_state.set_active_asset(asset)
            self.assertEqual("EDIT SETTINGS", panel._header_title.text())
            self.assertIn("hero.png", panel._header_subtitle.text())
            self.assertIn("sections available", panel._header_subtitle.text())
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

    def test_toolbox_section_change_keeps_mock_header_visible(self) -> None:
        app, owns_app, panel, ui_state = self._setup_panel()

        try:
            asset = AssetRecord(id="asset-8c", original_name="workflow.png")
            asset.edit_state.mode = EditMode.EXPERT
            ui_state.set_active_asset(asset)

            panel.resize(320, 260)
            panel.show()
            app.processEvents()

            panel.verticalScrollBar().setValue(0)
            panel._toolbox.setCurrentIndex(panel._group_indices["Export"])
            app.processEvents()

            self.assertEqual(0, panel.verticalScrollBar().value())
            self.assertEqual("Export", panel._toolbox.itemText(panel._toolbox.currentIndex()))
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_settings_group_navigator_uses_tile_picker(self) -> None:
        app, owns_app, panel, ui_state = self._setup_panel()

        try:
            asset = AssetRecord(id="asset-8b", original_name="workflow.png")
            asset.edit_state.mode = EditMode.EXPERT
            ui_state.set_active_asset(asset)

            nav_buttons = panel._toolbox.findChildren(QToolButton, "settingsGroupNavButton")

            self.assertEqual(len(SettingsPanel.GROUP_SPECS), len(nav_buttons))
            self.assertEqual(8, len(nav_buttons))
            self.assertTrue(
                all(
                    button.minimumHeight() == SHELL_GEOMETRY.settings_tile_height
                    for button in nav_buttons
                )
            )
            self.assertTrue(
                all(
                    button.minimumWidth() == SHELL_GEOMETRY.settings_tile_width
                    for button in nav_buttons
                )
            )
            self.assertEqual("Pixel", nav_buttons[0].text())
            export_button = next(button for button in nav_buttons if button.text() == "Export")
            self.assertTrue(bool(export_button.property("linkedExport")))
            self.assertIn("teal Export button", export_button.toolTip())
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


