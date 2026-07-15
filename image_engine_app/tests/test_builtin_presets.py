"""Bundled preset catalog tests."""

from __future__ import annotations

import unittest

from image_engine_app.engine.models import EditState
from image_engine_app.engine.presets import build_builtin_presets
from image_engine_app.engine.process.presets_apply import apply_preset_to_edit_state


class BuiltinPresetTests(unittest.TestCase):
    def test_catalog_is_unique_and_every_delta_is_valid(self) -> None:
        presets = build_builtin_presets()

        self.assertEqual(16, len(presets))
        self.assertEqual(len(presets), len(set(presets)))
        for name, preset in presets.items():
            self.assertEqual(name, preset.name)
            apply_preset_to_edit_state(preset, EditState(mode=preset.mode_min))

    def test_catalog_removes_overlapping_starter_variants(self) -> None:
        presets = build_builtin_presets()

        self.assertNotIn("Starter Cleanup Smooth", presets)
        self.assertNotIn("Starter Edges Clean", presets)
        self.assertNotIn("Starter AI Recover", presets)
        self.assertNotIn("Logo Alpha Clean", presets)

    def test_sprite_and_gif_size_presets_use_real_pixel_controls(self) -> None:
        presets = build_builtin_presets()

        self.assertEqual(200.0, presets["Sprite Crisp 2x"].settings_delta["pixel"]["resize_percent"])
        self.assertEqual(400.0, presets["Sprite Crisp 4x"].settings_delta["pixel"]["resize_percent"])
        self.assertEqual(200.0, presets["GIF Crisp 2x"].settings_delta["pixel"]["resize_percent"])


if __name__ == "__main__":
    unittest.main()
