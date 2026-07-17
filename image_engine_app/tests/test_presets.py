"""Tests for single-state preset application and mode clamping."""

from __future__ import annotations

from copy import deepcopy
import unittest

from image_engine_app.engine.models import EditMode, EditState, PresetModel
from image_engine_app.engine.process.bounds import clamp_edit_state_for_mode
from image_engine_app.engine.process.presets_apply import PresetApplyError, apply_preset_to_edit_state


class BoundsTests(unittest.TestCase):
    def test_mode_clamping_differs_between_advanced_and_expert(self) -> None:
        state = EditState(mode=EditMode.ADVANCED)
        state.settings.color.brightness = 0.8
        state.settings.ai.upscale_factor = 6.0
        state.settings.export.quality = 150
        state.settings.pixel.resize_percent = 2000.0

        advanced = clamp_edit_state_for_mode(state, mode=EditMode.ADVANCED)
        expert = clamp_edit_state_for_mode(state, mode=EditMode.EXPERT)

        self.assertEqual(advanced.settings.color.brightness, 0.5)
        self.assertEqual(advanced.settings.ai.upscale_factor, 4.0)
        self.assertEqual(advanced.settings.export.quality, 100)
        self.assertEqual(advanced.settings.pixel.resize_percent, 800.0)
        self.assertEqual(expert.settings.color.brightness, 0.8)
        self.assertEqual(expert.settings.ai.upscale_factor, 6.0)
        self.assertEqual(expert.settings.pixel.resize_percent, 1600.0)


class PresetApplyTests(unittest.TestCase):
    def test_preset_updates_the_one_edit_state_and_clamps_values(self) -> None:
        preset = PresetModel(
            name="Brighten",
            description="Raise brightness and quality",
            settings_delta={"color": {"brightness": 0.9}, "export": {"quality": 120}},
            mode_min=EditMode.ADVANCED,
        )
        state = EditState(mode=EditMode.ADVANCED)

        updated = apply_preset_to_edit_state(preset, state)

        self.assertEqual(updated.settings.color.brightness, 0.5)
        self.assertEqual(updated.settings.export.quality, 100)
        self.assertEqual(state.settings.color.brightness, 0.0)
        self.assertEqual(state.settings.export.quality, 90)

    def test_presets_can_be_composed_explicitly_on_one_state(self) -> None:
        base = PresetModel(
            name="Base Tone",
            description="Base color",
            settings_delta={"color": {"brightness": 0.2, "contrast": 0.1}},
            mode_min=EditMode.ADVANCED,
        )
        override = PresetModel(
            name="Upscale",
            description="Upscale",
            settings_delta={"ai": {"upscale_factor": 6.0}},
            mode_min=EditMode.ADVANCED,
            uses_heavy_tools=True,
            requires_apply=True,
        )
        state = EditState(mode=EditMode.EXPERT)

        updated = apply_preset_to_edit_state(base, deepcopy(state))
        updated = apply_preset_to_edit_state(override, updated)

        self.assertEqual(updated.settings.color.brightness, 0.2)
        self.assertEqual(updated.settings.color.contrast, 0.1)
        self.assertEqual(updated.settings.ai.upscale_factor, 6.0)

    def test_mode_min_enforcement_raises(self) -> None:
        preset = PresetModel(
            name="Expert Only",
            description="Needs expert mode",
            settings_delta={"ai": {"deblur_strength": 0.8}},
            mode_min=EditMode.EXPERT,
        )

        with self.assertRaises(PresetApplyError):
            apply_preset_to_edit_state(preset, EditState(mode=EditMode.ADVANCED))

    def test_legacy_palette_limit_maps_to_gif_palette(self) -> None:
        preset = PresetModel(
            name="Legacy GIF",
            description="Old payload",
            settings_delta={"export": {"palette_limit": 64}},
            mode_min=EditMode.ADVANCED,
        )

        updated = apply_preset_to_edit_state(preset, EditState())

        self.assertEqual(64, updated.settings.gif.palette_size)


if __name__ == "__main__":
    unittest.main()
