"""Tests for the extracted preset library service."""

from __future__ import annotations

import tempfile
import unittest

from image_engine_app.app.paths import ensure_app_paths
from image_engine_app.app.services import PresetLibrary
from image_engine_app.engine.models import AssetFormat, AssetRecord, EditMode, PresetModel


class PresetLibraryTests(unittest.TestCase):
    def test_system_and_user_presets_keep_stable_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            library = PresetLibrary(
                system_presets={
                    "System A": PresetModel(name="System A", description="", mode_min=EditMode.ADVANCED),
                    "System B": PresetModel(name="System B", description="", mode_min=EditMode.ADVANCED),
                },
                app_paths=paths,
            )
            library.upsert_user_preset(
                PresetModel(name="User Z", description="", mode_min=EditMode.ADVANCED)
            )
            library.upsert_user_preset(
                PresetModel(name="User A", description="", mode_min=EditMode.ADVANCED)
            )

            self.assertEqual(
                library.available_names(),
                ["System A", "System B", "User A", "User Z"],
            )

    def test_invalid_user_preset_settings_delta_is_rejected(self) -> None:
        library = PresetLibrary(
            system_presets={
                "System A": PresetModel(name="System A", description="", mode_min=EditMode.ADVANCED),
            }
        )

        with self.assertRaises(ValueError):
            library.upsert_user_preset(
                PresetModel(
                    name="Broken",
                    description="",
                    mode_min=EditMode.ADVANCED,
                    settings_delta={"not_a_real_group": {"value": 1}},
                )
            )

    def test_compatible_only_does_not_fall_back_to_unusable_presets(self) -> None:
        library = PresetLibrary(
            system_presets={
                "Photo": PresetModel(
                    name="Photo",
                    description="",
                    applies_to_formats=["jpg"],
                    applies_to_tags=["photo"],
                    mode_min=EditMode.ADVANCED,
                ),
            }
        )
        asset = AssetRecord(original_name="sprite.png", format=AssetFormat.PNG)
        asset.classification_tags = ["pixel_art"]

        self.assertEqual(library.available_entries(asset, compatible_only=True), [])
