"""Export workflow coordinator for the main window."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from image_engine_app.app.settings_store import load_path_preferences, save_path_preferences
from image_engine_app.engine.models import SessionState

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog


class ExportCoordinator:
    """Owns export run + export-directory state helpers for the main window."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def on_export_requested(self) -> None:
        asset = self._window.ui_state.active_asset
        if asset is None:
            return

        self._window._refresh_export_prediction()
        if self._window.controller is None:
            self._window._status("Export requested: controller not configured")
            return

        try:
            export_dir = self._window.export_bar.export_directory()
            if export_dir:
                self.remember_export_directory(export_dir)
            result = self._window.controller.export_active_asset(asset, export_dir=export_dir)
        except Exception as exc:
            self._window._status(f"Export failed: {exc}")
            return

        fallback_kind = getattr(result, "fallback_kind", None)
        if fallback_kind == "metadata":
            kind = "fallback metadata"
        elif fallback_kind == "placeholder":
            kind = "placeholder image"
        else:
            kind = "real file"
        msg = getattr(result, "message", "Export complete")

        moved_next = False
        if self._window.export_bar.auto_next_after_export():
            moved_next = self.activate_next_asset() is not None

        status = (
            f"Exported ({kind}): {result.output_path.name} ({result.bytes_written} bytes) - {msg}"
            f" | folder: {result.output_path.parent}"
        )
        if moved_next:
            status += " | moved to next asset"
        self._window._status(status)

    def on_skip_requested(self) -> None:
        asset = self._window.ui_state.active_asset
        if asset is None:
            return

        target = self.activate_next_asset()
        if target is None:
            self._window._status("Skip unavailable: already at the last asset")
            return

        label = target.original_name or target.id
        self._window._status(f"Skipped to next asset: {label}")

    def default_export_directory(self) -> Path | None:
        app_paths = self._app_paths()
        if app_paths is None:
            return None
        return app_paths.exports

    def sync_export_directory_from_session(self, session: SessionState | None) -> None:
        path_value: str | None = None
        if session is not None and session.last_export_dir:
            path_value = str(session.last_export_dir).strip()
        if not path_value:
            path_value = self._remembered_export_directory()
        if not path_value:
            default_dir = self.default_export_directory()
            path_value = str(default_dir) if default_dir is not None else None
        self._window.export_bar.set_export_directory(path_value)

    def remember_export_directory(self, path: str | Path | None) -> None:
        normalized = str(path).strip() if path is not None else ""
        if normalized:
            self._window.export_bar.set_export_directory(normalized)
        session = self._window.ui_state.session
        if session is not None:
            session.last_export_dir = normalized or None

        app_paths = self._app_paths()
        if app_paths is None:
            return
        try:
            save_path_preferences(app_paths, last_export_dir=normalized or None)
        except Exception:
            return

    def on_export_directory_browse_requested(self) -> None:
        start_dir = self._window.export_bar.export_directory()
        if not start_dir:
            default_dir = self.default_export_directory()
            start_dir = str(default_dir) if default_dir is not None else ""

        selected = QFileDialog.getExistingDirectory(
            self._window,
            "Select Export Folder",
            start_dir,
        )
        if not selected:
            return

        self.remember_export_directory(selected)
        self._window._status(f"Export folder set: {selected}")

    def on_export_directory_open_requested(self) -> None:
        target_dir = self._window.export_bar.export_directory()
        if not target_dir:
            default_dir = self.default_export_directory()
            target_dir = str(default_dir) if default_dir is not None else ""
        if not target_dir:
            self._window._status("Open export folder unavailable: no export folder configured")
            return

        folder = Path(target_dir)
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            self._window._status(f"Open export folder failed: {exc}")
            return

        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            self._window._status(f"Open export folder failed: {folder}")
            return
        self._window._status(f"Opened export folder: {folder}")

    def activate_next_asset(self):
        active = self._window.ui_state.active_asset
        if active is None:
            return None

        ordered = self._window._ordered_workspace_assets()
        if len(ordered) < 2:
            return None

        current_idx = next((idx for idx, item in enumerate(ordered) if item.id == active.id), -1)
        if current_idx < 0:
            return None

        next_idx = current_idx + 1
        if next_idx >= len(ordered):
            return None

        target = ordered[next_idx]
        self._window.ui_state.set_active_asset(target)
        self._window._sync_session_active_asset(target)
        return target

    def _app_paths(self):
        controller = self._window.controller
        return getattr(controller, 'app_paths', None) if controller is not None else None

    def _remembered_export_directory(self) -> str | None:
        app_paths = self._app_paths()
        if app_paths is None:
            return None
        try:
            prefs = load_path_preferences(app_paths)
        except Exception:
            return None
        value = prefs.get("last_export_dir") if isinstance(prefs, dict) else None
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None
