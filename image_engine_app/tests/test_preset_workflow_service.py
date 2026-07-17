"""Tests for the application preset workflow."""

from __future__ import annotations

import unittest

from image_engine_app.app.services import (
    AssetEditService,
    PresetLibrary,
    PresetWorkflowService,
)
from image_engine_app.engine.models import (
    AssetFormat,
    AssetRecord,
    EditMode,
    PresetModel,
    PresetSuggestion,
    RecommendationsSummary,
)
from image_engine_app.engine.process.edit_baseline import capture_detected_settings


def _asset() -> AssetRecord:
    asset = AssetRecord(
        id="workflow-asset",
        original_name="sprite.png",
        format=AssetFormat.PNG,
        dimensions_original=(16, 16),
        dimensions_current=(16, 16),
        dimensions_final=(16, 16),
    )
    asset.classification_tags = ["pixel_art"]
    asset.edit_state.settings.cleanup.denoise = 0.1
    capture_detected_settings(asset)
    return asset


class PresetWorkflowServiceTests(unittest.TestCase):
    def _workflow(self, presets: dict[str, PresetModel]) -> tuple[PresetLibrary, PresetWorkflowService]:
        library = PresetLibrary(system_presets=presets)
        workflow = PresetWorkflowService(
            library=library,
            asset_edits=AssetEditService(derived_cache_dir=None),
        )
        return library, workflow

    def test_named_application_can_skip_final_render_for_batch_preparation(self) -> None:
        preset = PresetModel(
            name="Clean",
            description="",
            applies_to_formats=["png"],
            applies_to_tags=["pixel_art"],
            settings_delta={"cleanup": {"artifact_removal": 0.25}},
            mode_min=EditMode.ADVANCED,
        )
        _library, workflow = self._workflow({"Clean": preset})
        asset = _asset()
        asset.edit_state.settings.cleanup.denoise = 0.8
        asset.derived_final_path = "C:/stale/final.png"

        result = workflow.apply_named(asset, "Clean", refresh_final=False)

        self.assertTrue(result.edit_result.changed)
        self.assertFalse(result.edit_result.preview_attempted)
        self.assertAlmostEqual(0.1, asset.edit_state.settings.cleanup.denoise)
        self.assertAlmostEqual(0.25, asset.edit_state.settings.cleanup.artifact_removal)
        self.assertIsNone(asset.derived_final_path)

    def test_recommended_application_skips_incompatible_candidate(self) -> None:
        photo = PresetModel(
            name="Photo",
            description="",
            applies_to_formats=["jpg"],
            applies_to_tags=["photo"],
            settings_delta={"color": {"contrast": 0.2}},
            mode_min=EditMode.ADVANCED,
        )
        pixel = PresetModel(
            name="Pixel",
            description="",
            applies_to_formats=["png"],
            applies_to_tags=["pixel_art"],
            settings_delta={"detail": {"clarity": 0.18}},
            mode_min=EditMode.ADVANCED,
        )
        _library, workflow = self._workflow({"Photo": photo, "Pixel": pixel})
        asset = _asset()
        asset.recommendations = RecommendationsSummary(
            suggested_presets=[
                PresetSuggestion("Photo", 0.95, "wrong format"),
                PresetSuggestion("Pixel", 0.9, "correct scope"),
            ]
        )

        result = workflow.apply_recommended(asset, minimum_confidence=0.6)

        self.assertIsNotNone(result)
        self.assertEqual("Pixel", result.preset_name)
        self.assertAlmostEqual(0.18, asset.edit_state.settings.detail.clarity)
        self.assertEqual([], asset.edit_state.queued_heavy_jobs)

    def test_library_normalizes_unmarked_heavy_user_presets(self) -> None:
        library, workflow = self._workflow({})
        preset = PresetModel(
            name="Custom Upscale",
            description="",
            applies_to_formats=["png"],
            applies_to_tags=["pixel_art"],
            settings_delta={"ai": {"upscale_factor": 2.0}},
            uses_heavy_tools=False,
            requires_apply=False,
            mode_min=EditMode.ADVANCED,
        )

        library.upsert_user_preset(preset)
        saved = library.get("Custom Upscale")
        result = workflow.apply_named(_asset(), "Custom Upscale", refresh_final=False)

        self.assertTrue(saved.uses_heavy_tools)
        self.assertTrue(saved.requires_apply)
        self.assertTrue(result.requires_apply)
        self.assertEqual(1, result.queued_heavy_jobs)


if __name__ == "__main__":
    unittest.main()
