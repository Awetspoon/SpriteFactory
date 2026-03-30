"""Tests for user preset persistence."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


from image_engine_app.app.paths import ensure_app_paths  # noqa: E402
from image_engine_app.app.preset_store import PresetStore  # noqa: E402
from image_engine_app.engine.models import EditMode, PresetModel  # noqa: E402


class PresetStoreTests(unittest.TestCase):
    def test_roundtrip_user_presets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            store = PresetStore(paths)

            presets = [
                PresetModel(
                    name="My Preset",
                    description="demo",
                    settings_delta={"cleanup": {"denoise": 0.2}},
                    uses_heavy_tools=False,
                    requires_apply=False,
                    mode_min=EditMode.SIMPLE,
                ),
                PresetModel(
                    name="Another",
                    description="x",
                    settings_delta={"export": {"format": "png"}},
                    uses_heavy_tools=True,
                    requires_apply=True,
                    mode_min=EditMode.ADVANCED,
                ),
            ]
            path = store.save_user_presets(presets)
            self.assertTrue(path.exists())

            loaded = store.load_user_presets().presets
            self.assertEqual([p.name for p in loaded], ["My Preset", "Another"])
            self.assertEqual(loaded[0].settings_delta["cleanup"]["denoise"], 0.2)
            self.assertTrue(loaded[1].uses_heavy_tools)
            self.assertEqual(loaded[1].mode_min, EditMode.ADVANCED)


