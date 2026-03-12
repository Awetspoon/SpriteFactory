"""Tests for v3 workspace persistence use-cases."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from image_engine_v3.application import WorkspacePersistenceService  # noqa: E402
from image_engine_v3.infrastructure import LegacySessionStoreWorkspaceRepository  # noqa: E402


class _FakeWorkspaceRepository:
    def __init__(self) -> None:
        self.saved: tuple[dict, list[dict], bool, str | None] | None = None
        self.to_load: dict | None = {"session": {"session_id": "x"}, "assets": []}

    def save_workspace(self, *, session_payload: dict, assets_payload: list[dict], autosave: bool = False, name: str | None = None):
        self.saved = (session_payload, assets_payload, autosave, name)
        return Path("dummy.json")

    def load_workspace(self, path):
        return dict(self.to_load or {})

    def load_latest_autosave_workspace(self):
        return dict(self.to_load or {})


class V3SessionUseCaseTests(unittest.TestCase):
    def test_service_normalizes_assets_and_forwards_save(self) -> None:
        repo = _FakeWorkspaceRepository()
        svc = WorkspacePersistenceService(repo)

        out = svc.save_workspace_bundle(
            session_payload={"session_id": "abc"},
            assets_payload=[{"id": "a1"}, "invalid", {"id": "a2"}],
            autosave=True,
            name="unit",
        )

        self.assertEqual(Path("dummy.json"), out)
        self.assertIsNotNone(repo.saved)
        _, assets, autosave, name = repo.saved
        self.assertEqual([{"id": "a1"}, {"id": "a2"}], assets)
        self.assertTrue(autosave)
        self.assertEqual("unit", name)

    def test_service_rejects_invalid_session_payload(self) -> None:
        repo = _FakeWorkspaceRepository()
        svc = WorkspacePersistenceService(repo)

        with self.assertRaises(ValueError):
            svc.save_workspace_bundle(session_payload="bad", assets_payload=[])

    def test_service_with_legacy_repo_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = LegacySessionStoreWorkspaceRepository(app_data_dir=tmp)
            svc = WorkspacePersistenceService(repo)

            path = svc.save_workspace_bundle(
                session_payload={
                    "session_id": "svc-roundtrip",
                    "opened_at": "2026-03-10T00:00:00+00:00",
                    "active_tab_asset_id": None,
                    "tab_order": [],
                    "pinned_tabs": [],
                    "batch_queue": [],
                    "macros": [],
                    "last_export_dir": None,
                },
                assets_payload=[],
            )

            loaded = svc.load_workspace_bundle(path)
            self.assertEqual("svc-roundtrip", loaded["session"]["session_id"])
            self.assertEqual([], loaded["assets"])


if __name__ == "__main__":
    unittest.main()
