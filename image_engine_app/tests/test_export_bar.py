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

from image_engine_app.engine.models import AssetRecord  # noqa: E402
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
            ui_state.export_prediction_changed.emit("Size 42 KB")
            self.assertEqual("Size 42 KB", bar._size_label.text())

            ui_state.set_active_asset(None)
            self.assertEqual("Size --", bar._size_label.text())
        finally:
            bar.close()


if __name__ == "__main__":
    unittest.main()

