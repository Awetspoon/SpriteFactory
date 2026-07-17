"""Tests for the shared preset application plan."""

from __future__ import annotations

import unittest

from image_engine_app.engine.models import (
    AssetFormat,
    AssetRecord,
    EditMode,
    HeavyTool,
    PresetModel,
)
from image_engine_app.engine.process.edit_baseline import capture_detected_settings
from image_engine_app.engine.process.preset_application import (
    commit_preset_application,
    plan_preset_application,
    select_first_compatible_preset,
)
from image_engine_app.engine.process.presets_apply import PresetApplyError


def _pixel_asset() -> AssetRecord:
    asset = AssetRecord(
        id="preset-plan",
        original_name="hero.png",
        format=AssetFormat.PNG,
        dimensions_original=(24, 18),
        dimensions_current=(24, 18),
        dimensions_final=(24, 18),
    )
    asset.classification_tags = ["pixel_art"]
    asset.edit_state.settings.cleanup.denoise = 0.12
    capture_detected_settings(asset)
    return asset


class PresetApplicationTests(unittest.TestCase):
    def test_plan_replaces_stale_edits_and_promotes_required_mode(self) -> None:
        asset = _pixel_asset()
        asset.edit_state.settings.cleanup.denoise = 0.48
        asset.edit_state.settings.color.brightness = 0.3
        preset = PresetModel(
            name="Expert Pixel",
            description="",
            applies_to_formats=["png"],
            applies_to_tags=["pixel_art"],
            settings_delta={"cleanup": {"artifact_removal": 0.24}},
            mode_min=EditMode.EXPERT,
        )

        plan = plan_preset_application(asset, preset)

        self.assertEqual(EditMode.EXPERT, plan.edit_state.mode)
        self.assertAlmostEqual(0.12, plan.edit_state.settings.cleanup.denoise)
        self.assertAlmostEqual(0.24, plan.edit_state.settings.cleanup.artifact_removal)
        self.assertAlmostEqual(0.0, plan.edit_state.settings.color.brightness)

    def test_plan_can_suppress_heavy_queue_for_import_detection(self) -> None:
        asset = _pixel_asset()
        preset = PresetModel(
            name="Detected Upscale",
            description="",
            applies_to_formats=["png"],
            applies_to_tags=["pixel_art"],
            settings_delta={"ai": {"upscale_factor": 3.0}},
            mode_min=EditMode.ADVANCED,
        )

        explicit = plan_preset_application(asset, preset)
        detected = plan_preset_application(asset, preset, queue_heavy_jobs=False)

        self.assertEqual(1, len(explicit.queued_heavy_jobs))
        self.assertEqual(HeavyTool.AI_UPSCALE, explicit.queued_heavy_jobs[0].tool)
        self.assertTrue(explicit.requires_apply)
        self.assertEqual(0, len(detected.queued_heavy_jobs))
        self.assertEqual([], detected.edit_state.queued_heavy_jobs)

    def test_plan_rejects_incompatible_assets(self) -> None:
        asset = _pixel_asset()
        photo = PresetModel(
            name="Photo Only",
            description="",
            applies_to_formats=["jpg"],
            applies_to_tags=["photo"],
            settings_delta={"cleanup": {"denoise": 0.2}},
            mode_min=EditMode.ADVANCED,
        )

        with self.assertRaises(PresetApplyError):
            plan_preset_application(asset, photo)

    def test_selection_and_commit_share_compatibility_and_output_reset(self) -> None:
        asset = _pixel_asset()
        asset.derived_final_path = "C:/stale/final.png"
        incompatible = PresetModel(
            name="Photo",
            description="",
            applies_to_formats=["jpg"],
            applies_to_tags=["photo"],
            mode_min=EditMode.ADVANCED,
        )
        compatible = PresetModel(
            name="Pixel",
            description="",
            applies_to_formats=["png"],
            applies_to_tags=["pixel_art"],
            settings_delta={"detail": {"clarity": 0.2}},
            mode_min=EditMode.ADVANCED,
        )

        selected = select_first_compatible_preset(asset, [incompatible, compatible])
        self.assertIs(selected, compatible)

        changed = commit_preset_application(asset, plan_preset_application(asset, compatible))
        self.assertTrue(changed)
        self.assertIsNone(asset.derived_final_path)
        self.assertAlmostEqual(0.2, asset.edit_state.settings.detail.clarity)


if __name__ == "__main__":
    unittest.main()
