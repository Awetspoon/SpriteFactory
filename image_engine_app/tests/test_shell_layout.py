"""Responsive geometry tests for the main desktop shell."""

from __future__ import annotations

import os
from pathlib import Path
import unittest

try:
    from PySide6.QtWidgets import QApplication, QDoubleSpinBox, QStyle, QStyleOptionSpinBox, QWidget
except Exception:  # pragma: no cover - optional dependency in some environments
    QApplication = None  # type: ignore[assignment]
    QWidget = None  # type: ignore[assignment]

from image_engine_app.app.ui_controller import ImageEngineUIController
from image_engine_app.ui.common.shell_theme import build_app_stylesheet
from image_engine_app.ui.common.shell_tokens import SHELL_GEOMETRY
from image_engine_app.ui.main_window.main_window import ImageEngineMainWindow


class ShellGeometryTests(unittest.TestCase):
    def test_workspace_columns_fit_supported_window_widths(self) -> None:
        for window_width in (
            SHELL_GEOMETRY.window_min_width,
            SHELL_GEOMETRY.window_default_width,
            1600,
        ):
            left, editor, inspector = SHELL_GEOMETRY.workspace_column_sizes(window_width)
            usable = (
                window_width
                - (2 * SHELL_GEOMETRY.outer_margin)
                - SHELL_GEOMETRY.page_rail_width
                - SHELL_GEOMETRY.gap
            )
            occupied = (
                left
                + editor
                + inspector
                + (2 * SHELL_GEOMETRY.splitter_handle_width)
            )

            self.assertLessEqual(occupied, usable)
            self.assertGreaterEqual(left, SHELL_GEOMETRY.workspace_left_min)
            self.assertGreaterEqual(editor, SHELL_GEOMETRY.workspace_editor_min)
            self.assertGreaterEqual(inspector, SHELL_GEOMETRY.workspace_inspector_min)

    def test_stylesheet_resolves_all_shell_placeholders(self) -> None:
        stylesheet = build_app_stylesheet()

        self.assertNotIn("__", stylesheet)
        self.assertIn("QSplitter#workspaceMainSplitter::handle", stylesheet)
        self.assertIn("QDoubleSpinBox::up-button", stylesheet)
        self.assertIn("QDoubleSpinBox::down-button", stylesheet)
        self.assertIn("chevron_up.svg", stylesheet)
        self.assertIn("chevron_down.svg", stylesheet)

    def test_main_window_source_has_no_legacy_mock_widths(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "ui"
            / "main_window"
            / "main_window.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("MOCK_", source)
        self.assertNotIn("left_shell.setFixedWidth", source)
        self.assertNotIn("inspector_shell.setFixedWidth", source)


@unittest.skipIf(QApplication is None, "PySide6 not installed")
class ShellResponsiveWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication.instance()
        cls._owns_app = app is None
        cls._app = app or QApplication([])
        cls._app.setStyleSheet(build_app_stylesheet())

    @classmethod
    def tearDownClass(cls) -> None:
        if getattr(cls, "_owns_app", False) and getattr(cls, "_app", None) is not None:
            cls._app.quit()

    def test_minimum_and_wide_shell_layouts_do_not_crush_the_editor(self) -> None:
        window = ImageEngineMainWindow(controller=ImageEngineUIController())
        try:
            window.show()
            window.resize(
                SHELL_GEOMETRY.window_min_width,
                SHELL_GEOMETRY.window_min_height,
            )
            self._app.processEvents()

            editor = window.findChild(QWidget, "workspaceEditorShell")
            self.assertIsNotNone(editor)
            self.assertGreaterEqual(editor.width(), SHELL_GEOMETRY.workspace_editor_min)
            self.assertTrue(window.preview_panel._header_compact)
            self.assertTrue(window.export_bar._compact_layout)

            window.resize(1600, 900)
            window._restore_workspace_columns()
            self._app.processEvents()

            self.assertGreater(editor.width(), SHELL_GEOMETRY.workspace_editor_min)
            self.assertFalse(window.preview_panel._header_compact)
            self.assertFalse(window.export_bar._compact_layout)
        finally:
            window.close()

    def test_spin_box_arrow_buttons_have_separate_hit_areas(self) -> None:
        spin = QDoubleSpinBox()
        try:
            spin.resize(
                SHELL_GEOMETRY.settings_field_max_width,
                SHELL_GEOMETRY.control_height,
            )
            spin.show()
            self._app.processEvents()

            option = QStyleOptionSpinBox()
            spin.initStyleOption(option)
            up_rect = spin.style().subControlRect(
                QStyle.ComplexControl.CC_SpinBox,
                option,
                QStyle.SubControl.SC_SpinBoxUp,
                spin,
            )
            down_rect = spin.style().subControlRect(
                QStyle.ComplexControl.CC_SpinBox,
                option,
                QStyle.SubControl.SC_SpinBoxDown,
                spin,
            )

            self.assertGreater(up_rect.width(), 0)
            self.assertGreater(up_rect.height(), 0)
            self.assertGreater(down_rect.width(), 0)
            self.assertGreater(down_rect.height(), 0)
            self.assertTrue(up_rect.intersected(down_rect).isEmpty())
        finally:
            spin.close()


if __name__ == "__main__":
    unittest.main()
