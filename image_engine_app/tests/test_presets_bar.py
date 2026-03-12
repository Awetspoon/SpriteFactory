"""Tests for preset dropdown bar behavior."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from PySide6.QtWidgets import QApplication, QComboBox
except Exception:  # pragma: no cover - optional dependency in some environments
    QApplication = None  # type: ignore[assignment]
    QComboBox = None  # type: ignore[assignment]

from ui.main_window.presets_bar import PresetsBar  # noqa: E402


@unittest.skipIf(QApplication is None, "PySide6 not installed")
class PresetsBarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app = QApplication.instance()
        cls._owns_app = app is None
        cls._app = app or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        if getattr(cls, "_owns_app", False) and getattr(cls, "_app", None) is not None:
            cls._app.quit()

    def test_dropdown_contains_all_presets(self) -> None:
        bar = PresetsBar()
        bar.set_presets(["Preset A", "Preset B", "Preset C"])

        combo = bar.findChild(QComboBox)
        self.assertIsNotNone(combo)
        assert combo is not None

        self.assertEqual(4, combo.count())
        self.assertEqual(None, combo.itemData(0))
        self.assertEqual("Preset A", combo.itemData(1))
        self.assertEqual("Preset B", combo.itemData(2))
        self.assertEqual("Preset C", combo.itemData(3))

    def test_selecting_preset_emits_and_resets(self) -> None:
        bar = PresetsBar()
        bar.set_presets(["Preset A", "Preset B"])
        emitted: list[str] = []
        bar.preset_clicked.connect(emitted.append)

        combo = bar.findChild(QComboBox)
        self.assertIsNotNone(combo)
        assert combo is not None

        combo.setCurrentIndex(2)

        self.assertEqual(["Preset B"], emitted)
        self.assertEqual(0, combo.currentIndex())


if __name__ == "__main__":
    unittest.main()
