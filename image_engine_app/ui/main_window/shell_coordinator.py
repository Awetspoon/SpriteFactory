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

        tabs = self._window._page_tabs
        helper_index = self._window._helper_tab_index
        if tabs is not None and helper_index is not None and 0 <= helper_index < tabs.count():
            if compact and tabs.currentIndex() == helper_index:
                tabs.setCurrentIndex(0)
            if hasattr(tabs, "setTabVisible"):
                tabs.setTabVisible(helper_index, not compact)
            else:
                tabs.setTabEnabled(helper_index, not compact)

        inspector = self._window._workspace_inspector_panel
        if inspector is not None:
            inspector.setVisible(not compact)
        if self._window._workspace_splitter is not None:
            if compact:
                self._window._workspace_splitter.setSizes(
                    [
                        int(getattr(self._window, "DEFAULT_WORKSPACE_RAIL_WIDTH", 260)),
                        1600,
                        0,
                    ]
                )
            else:
                self._window._workspace_splitter.setSizes(self._window._default_workspace_splitter_sizes())

        self._window._status("Compact UI enabled" if compact else "Compact UI disabled")

    def reset_panels_layout(self) -> None:
        if self._window._compact_ui_enabled:
            self.set_compact_ui(False)
        inspector = self._window._workspace_inspector_panel
        if inspector is not None:
            inspector.show()
        if self._window._workspace_splitter is not None:
            self._window._workspace_splitter.setSizes(self._window._default_workspace_splitter_sizes())
        preview = getattr(self._window, "preview_panel", None)
        if preview is not None and hasattr(preview, "restore_default_view"):
            preview.restore_default_view()
        if hasattr(self._window, "_sync_preview_view_actions"):
            self._window._sync_preview_view_actions()
        self._window._status("Panels reset: Settings restored")
