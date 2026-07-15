"""Session workflow coordinator for the main window."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from image_engine_app.app.settings_store import load_path_preferences, save_path_preferences
from image_engine_app.engine.models import SessionState

from PySide6.QtWidgets import QFileDialog, QMessageBox


class SessionCoordinator:
    """Owns safe new/open/save workspace workflows for the main window."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def new_workspace(self) -> bool:
        """Start an empty workspace without silently discarding current work."""

        if not self._confirm_workspace_replacement(
            title="New Workspace",
            prompt="Save your current workspace before starting a new one?",
        ):
            self._window._status("New workspace canceled")
            return False

        self._window.load_workspace_state(self._create_empty_session(), [])
        self._window._status("New workspace created")
        return True

    def save_workspace_file(self) -> bool:
        """Save the current workspace session + assets to a chosen JSON file."""

        if self._window.session_store is None:
            self._window._status("Save workspace unavailable: workspace store not configured")
            return False
        session = self._window.ui_state.session
        if session is None:
            self._window._status("Save workspace skipped: no active workspace")
            return False

        default_dir = self._default_workspace_directory()
        default_base = Path(default_dir) if default_dir else Path.home()
        default_name = f"workspace_{session.session_id}.json"
        path_str, _selected = QFileDialog.getSaveFileName(
            self._window,
            "Save Workspace",
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
            self._remember_workspace_directory(result.path.parent)
            self._window._status(f"Workspace saved: {result.path.name} | folder: {result.path.parent}")
            return True
        except Exception as exc:
            self._window._show_error("Save Workspace Failed", str(exc))
            return False

    def open_workspace_file(self) -> None:
        """Open a saved session/workspace JSON file."""

        if self._window.session_store is None:
            self._window._status("Open workspace unavailable: workspace store not configured")
            return

        start_dir = self._default_workspace_directory()
        path_str, _selected = QFileDialog.getOpenFileName(
            self._window,
            "Open Workspace",
            start_dir,
            "JSON Files (*.json);;All Files (*)",
        )
        if not path_str:
            return

        target = Path(path_str)
        if not self._confirm_workspace_replacement(
            title="Open Workspace",
            prompt="Save your current workspace before opening another one?",
        ):
            self._window._status("Open workspace canceled")
            return
        if self.load_workspace_from_file(target, source_label="Workspace"):
            self._remember_workspace_directory(target.parent)

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

    def _confirm_workspace_replacement(self, *, title: str, prompt: str) -> bool:
        if not self._has_workspace_content():
            return True

        answer = QMessageBox.question(
            self._window,
            title,
            prompt,
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            return self.save_workspace_file()
        return True

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

    def _default_workspace_directory(self) -> str:
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

    def _remember_workspace_directory(self, path: Path) -> None:
        if self._window.session_store is None:
            return
        try:
            save_path_preferences(self._window.session_store.paths, last_session_dir=str(path))
        except Exception:
            return

