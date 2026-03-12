"""Tests for app-data path helpers and session persistence/crash recovery."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.paths import build_app_paths, ensure_app_paths  # noqa: E402
from app.settings_store import (  # noqa: E402
    SessionStore,
    load_path_preferences,
    load_user_settings,
    load_web_sources_settings,
    save_path_preferences,
    save_user_settings,
    save_web_sources_settings,
)
from engine.models import AssetFormat, AssetRecord, QueueItem, QueueItemStatus, SessionState, SourceType  # noqa: E402


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 2, 23, hour, minute, tzinfo=timezone.utc)


def _session(session_id: str, active_asset: str) -> SessionState:
    return SessionState(
        session_id=session_id,
        opened_at=_dt(18, 0),
        active_tab_asset_id=active_asset,
        tab_order=[active_asset, "asset-b"],
        pinned_tabs={"asset-b"},
        batch_queue=[
            QueueItem(
                id=f"queue-{session_id}",
                asset_id=active_asset,
                status=QueueItemStatus.PENDING,
                progress=0.0,
            )
        ],
        macros=["macro-a"],
        last_export_dir="C:/Exports",
    )


def _asset(asset_id: str, name: str) -> AssetRecord:
    asset = AssetRecord(
        id=asset_id,
        source_type=SourceType.FILE,
        source_uri=f"C:/images/{name}",
        cache_path=f"C:/images/{name}",
        original_name=name,
        format=AssetFormat.PNG,
        dimensions_original=(64, 64),
        dimensions_current=(64, 64),
        dimensions_final=(64, 64),
    )
    asset.edit_state.settings.pixel.resize_percent = 200.0
    asset.edit_state.settings.cleanup.denoise = 0.25
    return asset


class AppPathsTests(unittest.TestCase):
    def test_build_and_ensure_app_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = build_app_paths(base_dir=temp_dir)
            self.assertEqual(paths.root, Path(temp_dir))
            self.assertEqual(paths.cache, Path(temp_dir) / "cache")
            self.assertEqual(paths.sessions, Path(temp_dir) / "sessions")
            self.assertEqual(paths.settings_file, Path(temp_dir) / "settings.json")

            ensured = ensure_app_paths(base_dir=temp_dir)
            self.assertTrue(ensured.root.exists())
            self.assertTrue(ensured.cache.exists())
            self.assertTrue(ensured.sessions.exists())
            self.assertTrue(ensured.exports.exists())
            self.assertTrue(ensured.logs.exists())


class UserSettingsStoreTests(unittest.TestCase):
    def test_save_and_load_user_settings_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            settings = {
                "ui": {"mode": "advanced", "last_profile": "web"},
                "window": {"width": 1400, "height": 900},
            }
            save_user_settings(paths, settings)
            restored = load_user_settings(paths)
            self.assertEqual(settings, restored)

    def test_path_preferences_defaults_and_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)

            defaults = load_path_preferences(paths)
            self.assertEqual(defaults["last_session_dir"], None)
            self.assertEqual(defaults["last_export_dir"], None)

            save_path_preferences(
                paths,
                last_session_dir=str(Path(temp_dir) / "sessions-picked"),
                last_export_dir=str(Path(temp_dir) / "exports-picked"),
            )
            restored = load_path_preferences(paths)
            self.assertEqual(restored["last_session_dir"], str(Path(temp_dir) / "sessions-picked"))
            self.assertEqual(restored["last_export_dir"], str(Path(temp_dir) / "exports-picked"))

    def test_web_sources_settings_defaults_and_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)

            defaults = load_web_sources_settings(paths)
            self.assertIn("registry", defaults)
            self.assertIn("options", defaults)
            self.assertEqual(defaults["options"]["skip_duplicates"], True)
            self.assertEqual([], defaults["registry"])

            save_web_sources_settings(
                paths,
                last_selected={"website_id": "example_com", "area_id": "root"},
                options={"show_likely": True, "auto_sort": True, "allow_zip": False},
            )
            restored = load_web_sources_settings(paths)

            self.assertEqual(restored["last_selected"]["website_id"], "example_com")
            self.assertEqual(restored["last_selected"]["area_id"], "root")
            self.assertTrue(restored["options"]["show_likely"])
            self.assertTrue(restored["options"]["auto_sort"])
            self.assertFalse(restored["options"]["allow_zip"])

    def test_web_sources_settings_preserves_saved_registry_without_injecting_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)

            save_web_sources_settings(
                paths,
                registry=[
                    {
                        "id": "example_com",
                        "name": "example.com",
                        "areas": [
                            {
                                "id": "root",
                                "label": "Root",
                                "url": "https://example.com/",
                            }
                        ],
                    }
                ],
            )

            restored = load_web_sources_settings(paths)
            website_ids = {str(entry.get("id")) for entry in restored["registry"] if isinstance(entry, dict)}
            self.assertIn("example_com", website_ids)
            self.assertNotIn("pokemon_db", website_ids)


class SessionStoreTests(unittest.TestCase):
    def test_save_and_load_session_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            store = SessionStore(paths)
            session = _session("session-001", "asset-a")

            save_result = store.save_session(session, name="My Session", saved_at=_dt(19, 10))
            self.assertFalse(save_result.autosave)
            self.assertTrue(save_result.path.exists())
            self.assertIn("session_my_session_", save_result.path.name)

            restored = store.load_session(save_result.path)
            self.assertEqual(session, restored)

            non_autosaves = store.list_session_files(include_autosaves=False)
            self.assertEqual([p.name for p in non_autosaves], [save_result.path.name])

    def test_save_and_load_workspace_bundle_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            store = SessionStore(paths)
            session = _session("session-workspace", "asset-a")
            assets = [_asset("asset-a", "a.png"), _asset("asset-b", "b.png")]

            save_result = store.save_workspace(session, assets, name="Workspace", saved_at=_dt(21, 0))
            self.assertTrue(save_result.path.exists())

            loaded = store.load_workspace(save_result.path)
            self.assertEqual(session, loaded.session)
            self.assertEqual(2, len(loaded.assets))
            self.assertEqual([a.id for a in assets], [a.id for a in loaded.assets])
            self.assertEqual(200.0, loaded.assets[0].edit_state.settings.pixel.resize_percent)
            self.assertAlmostEqual(0.25, loaded.assets[1].edit_state.settings.cleanup.denoise)

    def test_save_workspace_to_explicit_path_does_not_create_hidden_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            store = SessionStore(paths)
            session = _session("session-picked", "asset-a")
            assets = [_asset("asset-a", "a.png")]
            chosen_path = Path(temp_dir) / "picked" / "manual-session.json"

            save_result = store.save_workspace_to_path(chosen_path, session, assets, saved_at=_dt(21, 30))
            self.assertEqual(save_result.path, chosen_path)
            self.assertTrue(chosen_path.exists())

            loaded = store.load_workspace(chosen_path)
            self.assertEqual(loaded.session, session)
            self.assertEqual([asset.id for asset in loaded.assets], ["asset-a"])
            self.assertEqual(store.list_session_files(include_autosaves=True), [])

    def test_autosave_crash_recovery_keeps_latest_workspace_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            store = SessionStore(paths)

            older_session = _session("session-older", "asset-old")
            newer_session = _session("session-newer", "asset-new")

            older = store.autosave_workspace(older_session, [_asset("asset-old", "old.png")], saved_at=_dt(20, 0))
            newer = store.autosave_workspace(newer_session, [_asset("asset-new", "new.png")], saved_at=_dt(20, 5))

            self.assertFalse(older.path.exists())
            self.assertTrue(newer.path.exists())

            restored = store.load_latest_autosave_workspace()
            self.assertIsNotNone(restored)
            self.assertEqual(restored.session.session_id, "session-newer")
            self.assertEqual(restored.session.active_tab_asset_id, "asset-new")

            all_files = store.list_session_files(include_autosaves=True)
            self.assertEqual([p.name for p in all_files], [newer.path.name])
            self.assertTrue(all(path.name.startswith("autosave_") for path in all_files))

            removed = store.clear_autosaves()
            self.assertEqual(removed, 1)
            self.assertEqual(store.list_session_files(include_autosaves=True), [])
            self.assertIsNone(store.load_latest_autosave_workspace())


if __name__ == "__main__":
    unittest.main()



