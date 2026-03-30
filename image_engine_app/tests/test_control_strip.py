"""Widget tests for the redesigned control strip."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest


try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
except Exception:  # pragma: no cover - optional dependency in some environments
    QApplication = None  # type: ignore[assignment]
    Qt = None  # type: ignore[assignment]

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

    def test_apply_button_text_tracks_heavy_queue_state(self) -> None:
        ui_state = EngineUIState()
        strip = ControlStrip()
        strip.bind_state(ui_state)

        try:
            self.assertFalse(strip._apply_button.isEnabled())
            self.assertIn("Select an asset", strip._header_summary.text())

            asset = AssetRecord(id="asset-1", original_name="sprite.png")
            ui_state.set_active_asset(asset)
            self.assertTrue(strip._apply_button.isEnabled())
            self.assertEqual("Apply", strip._apply_button.text())
            self.assertEqual("Ready", strip._queue_badge.text())

            ui_state.set_heavy_queue_counts(queued_count=2, running_count=0)
            self.assertEqual("Run 2 Heavy", strip._apply_button.text())
            self.assertIn("queued", strip._queue_badge.text().lower())
        finally:
            strip.close()

    def test_preview_button_emits_light_preview_request(self) -> None:
        ui_state = EngineUIState()
        strip = ControlStrip()
        strip.bind_state(ui_state)
        asset = AssetRecord(id="asset-2", original_name="sprite2.png")
        ui_state.set_active_asset(asset)

        calls: list[str] = []
        ui_state.light_preview_requested.connect(lambda: calls.append("preview"))

        try:
            strip._preview_button.click()
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
            self.assertEqual("controlStripMenuAction", strip._background_button.objectName())
            self.assertEqual("controlStripMenuAction", strip._options_button.objectName())
            self.assertGreaterEqual(strip._background_button.minimumWidth(), 84)
            self.assertGreaterEqual(strip._options_button.minimumWidth(), 72)
        finally:
            strip.close()

    def test_target_badge_uses_centered_header_badge_layout(self) -> None:
        ui_state = EngineUIState()
        strip = ControlStrip()
        strip.bind_state(ui_state)
        asset = AssetRecord(id="asset-4b", original_name="sprite4b.png")
        ui_state.set_active_asset(asset)

        try:
            self.assertGreaterEqual(strip._target_badge.minimumHeight(), 24)
            self.assertEqual(int(strip._target_badge.alignment()), int(Qt.AlignmentFlag.AlignCenter))
            self.assertIn("Target:", strip._target_badge.text())
        finally:
            strip.close()

    def test_background_mode_change_requests_preview_even_when_auto_preview_is_off(self) -> None:
        ui_state = EngineUIState()
        strip = ControlStrip()
        strip.bind_state(ui_state)
        asset = AssetRecord(id="asset-5", original_name="sprite5.png")
        asset.edit_state.auto_apply_light = False
        ui_state.set_active_asset(asset)

        calls: list[str] = []
        ui_state.light_preview_requested.connect(lambda: calls.append("preview"))

        try:
            strip._emit_background_mode(BackgroundRemovalMode.WHITE.value)
            self.assertEqual(["preview"], calls)
            self.assertEqual(BackgroundRemovalMode.WHITE.value, asset.edit_state.settings.alpha.background_removal_mode)
        finally:
            strip.close()


if __name__ == "__main__":
    unittest.main()


