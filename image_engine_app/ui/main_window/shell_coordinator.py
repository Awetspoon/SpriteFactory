"""Shell layout/visibility coordinator for the integrated studio shell."""

from __future__ import annotations

from typing import Any


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

        pages = self._window._page_tabs
        helper_index = self._window._helper_tab_index
        if pages is not None and helper_index is not None and 0 <= helper_index < pages.count():
            if compact and pages.currentIndex() == helper_index:
                if hasattr(self._window, "_set_page_index"):
                    self._window._set_page_index(0)
                else:
                    pages.setCurrentIndex(0)
            helper_button = getattr(self._window, "_page_nav_buttons", {}).get(helper_index)
            if helper_button is not None:
                helper_button.setVisible(not compact)

        inspector = self._window._workspace_inspector_panel
        if inspector is not None:
            inspector.setVisible(not compact)

        self._window._status("Compact UI enabled" if compact else "Compact UI disabled")

    def reset_panels_layout(self) -> None:
        if self._window._compact_ui_enabled:
            self.set_compact_ui(False)
        inspector = self._window._workspace_inspector_panel
        if inspector is not None:
            inspector.show()
        preview = getattr(self._window, "preview_panel", None)
        if preview is not None and hasattr(preview, "restore_default_view"):
            preview.restore_default_view()
        if hasattr(self._window, "_sync_preview_view_actions"):
            self._window._sync_preview_view_actions()
        self._window._status("Panels reset: Settings restored")
