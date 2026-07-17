"""Widget tests for the redesigned control strip."""

from __future__ import annotations

import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


try:
    from PySide6.QtWidgets import QApplication, QLabel
except Exception:  # pragma: no cover - optional dependency in some environments
    QApplication = None  # type: ignore[assignment]
    QLabel = None  # type: ignore[assignment]

from image_engine_app.engine.models import AssetRecord, BackgroundRemovalMode  # noqa: E402
from image_engine_app.ui.common.state_bindings import EngineUIState  # noqa: E402
from image_engine_app.ui.main_window.control_strip import ControlStrip  # noqa: E402


@unittest.skipIf(QApplication is None, "PySide6 not installed")
class ControlStripWidgetTests(unittest.TestCase):
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

    def test_run_button_tracks_heavy_queue_state(self) -> None:
        ui_state = EngineUIState()
        strip = ControlStrip()
        strip.bind_state(ui_state)

        try:
            self.assertFalse(strip._run_button.isEnabled())
            self.assertIn("Select an asset", strip._header_summary.text())

            asset = AssetRecord(id="asset-1", original_name="sprite.png")
            ui_state.set_active_asset(asset)
            self.assertTrue(strip._run_button.isEnabled())
            self.assertEqual("Refresh Final", strip._run_button.text())
            self.assertEqual("Ready", strip._queue_badge.text())

            ui_state.set_heavy_queue_counts(queued_count=2, running_count=0)
            self.assertEqual("Run 2 Heavy", strip._run_button.text())
            self.assertIn("queued", strip._queue_badge.text().lower())
        finally:
            strip.close()

    def test_run_button_requests_final_preview_without_heavy_queue(self) -> None:
        ui_state = EngineUIState()
        strip = ControlStrip()
        strip.bind_state(ui_state)
        asset = AssetRecord(id="asset-2", original_name="sprite2.png")
        ui_state.set_active_asset(asset)

        calls: list[str] = []
        ui_state.final_preview_requested.connect(lambda: calls.append("preview"))

        try:
            strip._run_button.click()
            self.assertEqual(["preview"], calls)
        finally:
            strip.close()

    def test_options_menu_actions_emit_reset_requests(self) -> None:
        ui_state = EngineUIState()
        strip = ControlStrip()
        strip.bind_state(ui_state)
        asset = AssetRecord(id="asset-3", original_name="sprite3.png")
        ui_state.set_active_asset(asset)

        calls: list[str] = []
        ui_state.global_reset_requested.connect(lambda: calls.append("settings"))
        ui_state.reset_view_requested.connect(lambda: calls.append("view"))

        try:
            strip._reset_settings_action.trigger()
            strip._reset_view_action.trigger()
            self.assertTrue(strip._actions_group.isEnabled())
            self.assertEqual(["settings", "view"], calls)
        finally:
            strip.close()

    def test_menu_buttons_use_dedicated_menu_style_width(self) -> None:
        ui_state = EngineUIState()
        strip = ControlStrip()
        strip.bind_state(ui_state)
        asset = AssetRecord(id="asset-4", original_name="sprite4.png")
        ui_state.set_active_asset(asset)

        try:
            self.assertEqual("controlStripHeaderMenuAction", strip._preset_button.objectName())
            self.assertEqual("controlStripHeaderMenuAction", strip._background_button.objectName())
            self.assertEqual("controlStripMenuAction", strip._options_button.objectName())
            self.assertEqual("FINAL", strip._actions_group.findChild(QLabel, "controlStripSectionLabel").text())
            self.assertGreaterEqual(strip._background_button.minimumWidth(), 84)
            self.assertGreaterEqual(strip._options_button.minimumWidth(), 72)
        finally:
            strip.close()

    def test_preset_menu_emits_selected_preset_name(self) -> None:
        strip = ControlStrip()
        calls: list[str] = []
        strip.preset_selected.connect(calls.append)

        try:
            strip.set_preset_entries(
                [
                    SimpleNamespace(
                        name="GIF Safe Cleanup",
                        label="GIF Safe Cleanup | GIF",
                        scope_text="Animation-safe preset",
                    )
                ],
                has_asset=True,
            )
            action = strip._preset_menu.actions()[0]
            self.assertEqual("GIF Safe Cleanup | GIF", action.text())
            self.assertEqual("GIF Safe Cleanup", action.data())
            action.trigger()
            self.assertEqual(["GIF Safe Cleanup"], calls)
        finally:
            strip.close()

    def test_preset_menu_keeps_manager_available_without_asset(self) -> None:
        strip = ControlStrip()
        calls: list[str] = []
        strip.preset_manager_requested.connect(lambda: calls.append("manager"))

        try:
            strip.set_preset_entries([], has_asset=False)
            actions = strip._preset_menu.actions()
            self.assertIn("Select an asset first", actions[0].text())
            actions[-1].trigger()
            self.assertEqual(["manager"], calls)
        finally:
            strip.close()

    def test_header_uses_preset_background_and_queue_controls(self) -> None:
        ui_state = EngineUIState()
        strip = ControlStrip()
        strip.bind_state(ui_state)
        asset = AssetRecord(id="asset-4b", original_name="sprite4b.png")
        ui_state.set_active_asset(asset)

        try:
            self.assertEqual(strip._preset_button.size(), strip._background_button.size())
            self.assertEqual(strip._background_button.height(), strip._queue_badge.height())
            self.assertIn("Current is the source", strip._header_summary.text())
        finally:
            strip.close()

    def test_background_mode_sends_one_edit_request(self) -> None:
        ui_state = EngineUIState()
        strip = ControlStrip()
        strip.bind_state(ui_state)
        asset = AssetRecord(id="asset-5", original_name="sprite5.png")
        ui_state.set_active_asset(asset)

        calls: list[tuple[str, str, object]] = []
        ui_state.edit_setting_requested.connect(lambda group, field, value: calls.append((group, field, value)))

        try:
            strip._emit_background_mode(BackgroundRemovalMode.WHITE.value)
            self.assertEqual([("alpha", "background_removal_mode", BackgroundRemovalMode.WHITE.value)], calls)
            self.assertEqual(BackgroundRemovalMode.OFF.value, asset.edit_state.settings.alpha.background_removal_mode)
        finally:
            strip.close()


if __name__ == "__main__":
    unittest.main()


