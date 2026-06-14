"""Tests for extracted batch preset-rule helpers."""

from __future__ import annotations

import unittest

from image_engine_app.app.services import (
    PresetLibrary,
    build_batch_auto_preset_rules,
    build_batch_per_source_preset_rules,
)
from image_engine_app.engine.models import EditMode, PresetModel


class BatchPresetRulesServiceTests(unittest.TestCase):
    def test_auto_rules_pick_known_system_presets(self) -> None:
        library = PresetLibrary(
            system_presets={
                "Pixel Clean Upscale": PresetModel(name="Pixel Clean Upscale", description="", mode_min=EditMode.ADVANCED),
                "Photo Recover": PresetModel(name="Photo Recover", description="", mode_min=EditMode.ADVANCED),
                "GIF Safe Cleanup": PresetModel(name="GIF Safe Cleanup", description="", mode_min=EditMode.ADVANCED),
                "Artifact Cleanup": PresetModel(name="Artifact Cleanup", description="", mode_min=EditMode.ADVANCED),
            }
        )

        rules = build_batch_auto_preset_rules(library, enabled=True)

        self.assertIn("pixel_art", rules)
        self.assertEqual(rules["pixel_art"][0].name, "Pixel Clean Upscale")
        self.assertEqual(rules["photo"][0].name, "Photo Recover")
        self.assertEqual(rules["animation"][0].name, "GIF Safe Cleanup")

    def test_per_source_rules_can_be_disabled(self) -> None:
        self.assertEqual(build_batch_per_source_preset_rules(enabled=False), {})
