"""Session coordinator tests for clear/save workflows."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


try:
    from PySide6.QtWidgets import QMessageBox
except Exception:  # pragma: no cover - optional dependency in some environments
    QMessageBox = None  # type: ignore[assignment]

from image_engine_app.app.paths import ensure_app_paths  # noqa: E402
from image_engine_app.app.settings_store import SessionStore  # noqa: E402
from image_engine_app.engine.models import AssetRecord, SessionState, SourceType  # noqa: E402
from image_engine_app.ui.main_window.session_coordinator import SessionCoordinator  # noqa: E402


class _FakeUIState:
    def __init__(self, session: SessionState | None) -> None:
        self.session = session


class _FakeWindow:
    def __init__(self, *, session_store: SessionStore, session: SessionState | None, assets: list[AssetRecord]) -> None:
        self.session_store = session_store
        self.ui_state = _FakeUIState(session)
        self._workspace_assets = list(assets)
        self.status_messages: list[str] = []
        self.loaded_states: list[tuple[SessionState, list[AssetRecord]]] = []
        self.error_messages: list[tuple[str, str]] = []

    @property
    def workspace_assets(self) -> list[AssetRecord]:
        return list(self._workspace_assets)

    def load_workspace_state(self, session: SessionState, assets: list[AssetRecord]) -> None:
        self.loaded_states.append((session, list(assets)))
        self.ui_state.session = session
        self._workspace_assets = list(assets)

    def _status(self, text: str) -> None:
        self.status_messages.append(text)

    def _show_error(self, title: str, message: str) -> None:
        self.error_messages.append((title, message))


def _session(session_id: str = "session-test") -> SessionState:
    return SessionState(
        session_id=session_id,
        opened_at=datetime.now(timezone.utc),
        active_tab_asset_id="asset-a",
        tab_order=["asset-a"],
        pinned_tabs=set(),
        batch_queue=[],
        macros=[],
        last_export_dir=None,
    )


def _asset(asset_id: str = "asset-a") -> AssetRecord:
    return AssetRecord(
        id=asset_id,
        source_type=SourceType.FILE,
        source_uri=f"C:/images/{asset_id}.png",
        cache_path=f"C:/images/{asset_id}.png",
        original_name=f"{asset_id}.png",
    )


@unittest.skipIf(QMessageBox is None, "PySide6 not installed")
class SessionCoordinatorTests(unittest.TestCase):
    def test_clear_session_discard_clears_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            store = SessionStore(paths)
            window = _FakeWindow(session_store=store, session=_session(), assets=[_asset()])
            coordinator = SessionCoordinator(window)

            with patch(
                "image_engine_app.ui.main_window.session_coordinator.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Discard,
            ):
                coordinator.clear_session()

            self.assertEqual(1, len(window.loaded_states))
            loaded_session, loaded_assets = window.loaded_states[0]
            self.assertTrue(loaded_session.session_id.startswith("session-"))
            self.assertEqual([], loaded_assets)
            self.assertEqual("Session cleared", window.status_messages[-1])

    def test_clear_session_save_then_cancel_save_dialog_does_not_clear(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            store = SessionStore(paths)
            window = _FakeWindow(session_store=store, session=_session(), assets=[_asset()])
            coordinator = SessionCoordinator(window)

            with patch(
                "image_engine_app.ui.main_window.session_coordinator.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Save,
            ):
                with patch("image_engine_app.ui.main_window.session_coordinator.QFileDialog.getSaveFileName", return_value=("", "")):
                    coordinator.clear_session()

            self.assertEqual([], window.loaded_states)
            self.assertEqual("Clear session canceled", window.status_messages[-1])

    def test_clear_session_without_content_skips_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            store = SessionStore(paths)
            empty_session = SessionState(
                session_id="session-empty",
                opened_at=datetime.now(timezone.utc),
                active_tab_asset_id=None,
                tab_order=[],
                pinned_tabs=set(),
                batch_queue=[],
                macros=[],
                last_export_dir=None,
            )
            window = _FakeWindow(session_store=store, session=empty_session, assets=[])
            coordinator = SessionCoordinator(window)

            with patch("image_engine_app.ui.main_window.session_coordinator.QMessageBox.question") as mocked_prompt:
                coordinator.clear_session()

            mocked_prompt.assert_not_called()
            self.assertEqual(1, len(window.loaded_states))
            self.assertEqual("Session cleared", window.status_messages[-1])


if __name__ == "__main__":
    unittest.main()



