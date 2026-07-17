"""Tests for application-owned Batch preparation and execution isolation."""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from image_engine_app.app.services.batch_workflow import BatchWorkflowService
from image_engine_app.engine.models import (
    AssetFormat,
    AssetRecord,
    BatchEditSource,
    EditMode,
    HeavyJobSpec,
    HeavyTool,
)
from image_engine_app.engine.process.heavy_queue import HeavyQueueEngine


class _FakePresetWorkflow:
    def __init__(self) -> None:
        self.refresh_final_values: list[bool] = []

    def apply_named(self, asset, preset_name: str, *, refresh_final: bool = True):  # noqa: ANN001
        self.refresh_final_values.append(bool(refresh_final))
        asset.edit_state.settings.cleanup.denoise = 0.42
        return SimpleNamespace(preset_name=preset_name)


def _service(preset_workflow: object | None = None) -> BatchWorkflowService:
    return BatchWorkflowService(
        app_paths=None,
        preset_library=object(),  # type: ignore[arg-type]
        preset_workflow=(preset_workflow or _FakePresetWorkflow()),  # type: ignore[arg-type]
        heavy_queue_factory=lambda: HeavyQueueEngine(),
    )


def _asset(asset_id: str) -> AssetRecord:
    asset = AssetRecord(
        id=asset_id,
        original_name=f"{asset_id}.png",
        source_uri=f"C:/assets/{asset_id}.png",
        cache_path=f"C:/cache/{asset_id}.png",
        format=AssetFormat.PNG,
        dimensions_original=(32, 24),
        dimensions_current=(32, 24),
        dimensions_final=(96, 72),
    )
    asset.edit_state.mode = EditMode.ADVANCED
    asset.derived_final_path = f"C:/derived/{asset_id}/final.png"
    return asset


class BatchWorkflowServiceTests(unittest.TestCase):
    def test_prepare_copies_active_controls_and_clears_generated_state(self) -> None:
        active = _asset("active")
        target = _asset("target")
        active.edit_state.settings.cleanup.denoise = 0.37
        active.edit_state.queued_heavy_jobs = [
            HeavyJobSpec(id="job-1", tool=HeavyTool.AI_UPSCALE, params={"factor": 2}),
        ]

        result = _service().prepare_assets(
            selected_assets=[target],
            active_asset=active,
            edit_source=BatchEditSource.COPY_ACTIVE,
            selected_preset_name="",
            background_override=None,
        )

        prepared = result.assets[0]
        self.assertIsNot(prepared, target)
        self.assertAlmostEqual(prepared.edit_state.settings.cleanup.denoise, 0.37, places=3)
        self.assertEqual(len(prepared.edit_state.queued_heavy_jobs), 1)
        self.assertEqual(prepared.edit_state.queued_heavy_jobs[0].tool, HeavyTool.AI_UPSCALE)
        self.assertIsNone(prepared.derived_final_path)
        self.assertEqual((32, 24), prepared.dimensions_final)
        self.assertIsNotNone(target.derived_final_path)
        self.assertEqual((96, 72), target.dimensions_final)

    def test_prepare_applies_chosen_preset_without_rendering_final(self) -> None:
        preset_workflow = _FakePresetWorkflow()

        result = _service(preset_workflow).prepare_assets(
            selected_assets=[_asset("target")],
            active_asset=None,
            edit_source=BatchEditSource.CHOSEN_PRESET,
            selected_preset_name="Clean",
            background_override=None,
        )

        self.assertEqual([False], preset_workflow.refresh_final_values)
        self.assertAlmostEqual(0.42, result.assets[0].edit_state.settings.cleanup.denoise)
        self.assertEqual(1, result.applied_preset_count)

    def test_run_never_mutates_the_assets_received_from_workspace(self) -> None:
        asset = _asset("workspace")
        asset.classification_tags = []
        asset.edit_state.settings.cleanup.denoise = 0.0
        original_derived = asset.derived_final_path

        report = _service().run(
            [asset],
            preview_skip_mode=True,
            auto_export=False,
            auto_preset=False,
        )

        self.assertEqual(1, report.processed_count)
        self.assertEqual([], asset.classification_tags)
        self.assertEqual(0.0, asset.edit_state.settings.cleanup.denoise)
        self.assertEqual(original_derived, asset.derived_final_path)


if __name__ == "__main__":
    unittest.main()
