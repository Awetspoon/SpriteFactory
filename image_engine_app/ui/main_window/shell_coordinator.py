"""Shell layout/visibility coordinator for the main window."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt


class ShellCoordinator:
    """Owns compact UI mode and panel layout reset behavior."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def compact_ui_enabled(self) -> bool:
        return bool(self._window._compact_ui_enabled)

    def set_compact_ui(self, enabled: bool) -> None:
        compact = bool(enabled)
        self._window._compact_ui_enabled = compact

        action = self._window._compact_ui_action
        if action is not None and action.isChecked() != compact:
            action.blockSignals(True)
            action.setChecked(compact)
            action.blockSignals(False)

        tabs = self._window._page_tabs
        helper_index = self._window._helper_tab_index
        if tabs is not None and helper_index is not None and 0 <= helper_index < tabs.count():
            if compact and tabs.currentIndex() == helper_index:
                tabs.setCurrentIndex(0)
            if hasattr(tabs, "setTabVisible"):
                tabs.setTabVisible(helper_index, not compact)
            else:
                tabs.setTabEnabled(helper_index, not compact)

        dock = self._window._settings_dock
        if dock is not None:
            if compact:
                dock.hide()
            else:
                dock.setFloating(False)
                self._window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
                dock.show()
                dock.raise_()
                self._window.resizeDocks([dock], [430], Qt.Orientation.Horizontal)

        self._window.presets_bar.setVisible(not compact)
        if self._window._workspace_helper_panel is not None:
            self._window._workspace_helper_panel.setVisible(not compact)
        if self._window._workspace_splitter is not None:
            self._window._workspace_splitter.setSizes([1400, 0] if compact else [1180, 220])

        self._window._status("Compact UI enabled" if compact else "Compact UI disabled")

    def reset_panels_layout(self) -> None:
        dock = self._window._settings_dock
        if self._window._compact_ui_enabled:
            self.set_compact_ui(False)
        if dock is None:
            return

        dock.setFloating(False)
        self._window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        dock.show()
        dock.raise_()
        self._window.resizeDocks([dock], [430], Qt.Orientation.Horizontal)
        self._window._status("Panels reset: Settings restored")
