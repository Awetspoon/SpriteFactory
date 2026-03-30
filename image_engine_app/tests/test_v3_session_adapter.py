"""Tests for v3 legacy workspace persistence adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest


from image_engine_app.app.paths import ensure_app_paths  # noqa: E402
from image_engine_app.app.settings_store import SessionStore  # noqa: E402
from image_engine_app.engine.models import AssetRecord, SessionState  # noqa: E402
from image_engine_v3.infrastructure import LegacySessionStoreWorkspaceRepository  # noqa: E402


def _session(session_id: str) -> SessionState:
    return SessionState(
        session_id=session_id,
        opened_at=datetime.now(timezone.utc),
        active_tab_asset_id=None,
        tab_order=[],
        pinned_tabs=set(),
        batch_queue=[],
        macros=[],
        last_export_dir=None,
    )


class V3SessionAdapterTests(unittest.TestCase):
    def test_save_and_load_workspace_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = LegacySessionStoreWorkspaceRepository(app_data_dir=tmp)

            session = _session("v3-session-roundtrip")
            asset = AssetRecord(id="asset-1", original_name="sprite.png")

            path = repo.save_workspace(
                session_payload=session.to_dict(),
                assets_payload=[asset.to_dict()],
                autosave=False,
                name="roundtrip",
            )

            self.assertTrue(path.exists())

            loaded = repo.load_workspace(path)
            self.assertEqual("v3-session-roundtrip", loaded["session"]["session_id"])
            self.assertEqual(1, len(loaded["assets"]))
            self.assertEqual("asset-1", loaded["assets"][0]["id"])
            self.assertFalse(loaded["autosave"])

    def test_load_workspace_tolerates_legacy_session_only_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = ensure_app_paths(base_dir=tmp)
            store = SessionStore(paths)
            session = _session("legacy-only")
            target = paths.sessions / "legacy_session_only.json"
            store.save_session_to_path(target, session, autosave=False)

            repo = LegacySessionStoreWorkspaceRepository(app_paths=paths)
            loaded = repo.load_workspace(target)

            self.assertEqual("legacy-only", loaded["session"]["session_id"])
            self.assertEqual([], loaded["assets"])

    def test_load_latest_autosave_workspace_returns_none_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = LegacySessionStoreWorkspaceRepository(app_data_dir=tmp)
            self.assertIsNone(repo.load_latest_autosave_workspace())


if __name__ == "__main__":
    unittest.main()


