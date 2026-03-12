"""Session workflow coordinator for the main window."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.settings_store import load_path_preferences, save_path_preferences
from engine.models import SessionState

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QMessageBox


class SessionCoordinator:
    """Owns new/open/save/clear session workflows for the main window."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def new_session(self) -> None:
        """Start a fresh empty session and clear the workspace."""

        self._window.load_workspace_state(self._create_empty_session(), [])
        self._window._status("New session created")

    def save_session_file(self) -> bool:
        """Save the current workspace session + assets to a chosen JSON file."""

        if self._window.session_store is None:
            self._window._status("Save session unavailable: session store not configured")
            return False
        session = self._window.ui_state.session
        if session is None:
            self._window._status("Save session skipped: no active session")
            return False

        default_dir = self._default_session_directory()
        default_base = Path(default_dir) if default_dir else Path.home()
        default_name = f"session_{session.session_id}.json"
        path_str, _selected = QFileDialog.getSaveFileName(
            self._window,
            "Save Session",
            str(default_base / default_name),
            "JSON Files (*.json);;All Files (*)",
        )
        if not path_str:
            return False

        saved_path = Path(path_str)
        if not saved_path.suffix:
            saved_path = saved_path.with_suffix(".json")

        try:
            result = self._window.session_store.save_workspace_to_path(
                saved_path,
                session,
                self._window.workspace_assets,
            )
            self._remember_session_directory(result.path.parent)
            self._window._status(f"Session saved: {result.path.name} | folder: {result.path.parent}")
            return True
        except Exception as exc:
            self._window._show_error("Save Session Failed", str(exc))
            return False

    def open_session_file(self) -> None:
        """Open a saved session/workspace JSON file."""

        if self._window.session_store is None:
            self._window._status("Open session unavailable: session store not configured")
            return

        start_dir = self._default_session_directory()
        path_str, _selected = QFileDialog.getOpenFileName(
            self._window,
            "Open Session",
            start_dir,
            "JSON Files (*.json);;All Files (*)",
        )
        if not path_str:
            return

        target = Path(path_str)
        if self.load_workspace_from_file(target, source_label="Session"):
            self._remember_session_directory(target.parent)

    def clear_session(self) -> None:
        """Clear the active workspace, prompting to save before discarding work."""

        if self._has_workspace_content():
            answer = QMessageBox.question(
                self._window,
                "Clear Session",
                "Save your current work before clearing the session?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if answer == QMessageBox.StandardButton.Cancel:
                self._window._status("Clear session canceled")
                return
            if answer == QMessageBox.StandardButton.Save and not self.save_session_file():
                self._window._status("Clear session canceled")
                return

        self._window.load_workspace_state(self._create_empty_session(), [])
        self._window._status("Session cleared")

    def load_workspace_from_file(self, path: Path, *, source_label: str) -> bool:
        """Load a workspace/session JSON file and replace current workspace state."""

        if self._window.session_store is None:
            self._window._status(f"{source_label} load unavailable: session store not configured")
            return False

        try:
            loaded = self._window.session_store.load_workspace(path)
        except Exception as exc:
            self._window._show_error(f"{source_label} Load Failed", str(exc))
            return False

        self._window.load_workspace_state(loaded.session, loaded.assets)
        self._window._status(f"{source_label} loaded: {loaded.path.name} ({len(loaded.assets)} asset(s))")
        return True

    def open_sessions_folder(self) -> None:
        """Open the sessions storage directory in the system file manager."""

        if self._window.session_store is None:
            self._window._status("Open sessions folder unavailable: session store not configured")
            return

        default_dir = self._default_session_directory()
        folder = Path(default_dir) if default_dir else self._window.session_store.paths.sessions
        folder.mkdir(parents=True, exist_ok=True)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            self._window._status(f"Open sessions folder failed: {folder}")
            return
        self._window._status(f"Opened sessions folder: {folder}")

    @staticmethod
    def _create_empty_session() -> SessionState:
        return SessionState(
            session_id=f"session-{uuid4().hex[:8]}",
            opened_at=datetime.now(timezone.utc),
            active_tab_asset_id=None,
            tab_order=[],
            pinned_tabs=set(),
            batch_queue=[],
            macros=[],
            last_export_dir=None,
        )

    def _has_workspace_content(self) -> bool:
        session = self._window.ui_state.session
        if self._window.workspace_assets:
            return True
        if session is None:
            return False
        return bool(
            session.active_tab_asset_id
            or session.tab_order
            or session.pinned_tabs
            or session.batch_queue
            or session.macros
        )

    def _default_session_directory(self) -> str:
        if self._window.session_store is None:
            return ""
        try:
            prefs = load_path_preferences(self._window.session_store.paths)
        except Exception:
            prefs = {}
        preferred = prefs.get("last_session_dir") if isinstance(prefs, dict) else None
        if isinstance(preferred, str) and preferred.strip():
            return preferred.strip()
        return str(self._window.session_store.paths.sessions)

    def _remember_session_directory(self, path: Path) -> None:
        if self._window.session_store is None:
            return
        try:
            save_path_preferences(self._window.session_store.paths, last_session_dir=str(path))
        except Exception:
            return
