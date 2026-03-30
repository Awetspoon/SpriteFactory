"""Tests for isolated batch asset preparation."""

from __future__ import annotations

import unittest

from image_engine_app.engine.models import AssetFormat, AssetRecord, EditMode, HeavyJobSpec, HeavyTool
from image_engine_app.ui.main_window.batch_run_prep import prepare_batch_assets


class _FakeController:
    def apply_named_preset(self, asset, preset_name: str):  # noqa: ANN001
        asset.edit_state.settings.cleanup.denoise = 0.42
        return object()


def _asset(asset_id: str) -> AssetRecord:
    asset = AssetRecord(
        id=asset_id,
        original_name=f"{asset_id}.png",
        source_uri=f"C:/assets/{asset_id}.png",
        cache_path=f"C:/cache/{asset_id}.png",
        format=AssetFormat.PNG,
    )
    asset.edit_state.mode = EditMode.ADVANCED
    asset.derived_current_path = f"C:/derived/{asset_id}/current.png"
    asset.derived_final_path = f"C:/derived/{asset_id}/final.png"
    return asset


class BatchRunPrepTests(unittest.TestCase):
    def test_prepare_batch_assets_copies_active_heavy_jobs_and_clears_derived_outputs(self) -> None:
        active = _asset("active")
        target = _asset("target")
        active.edit_state.settings.cleanup.denoise = 0.37
        active.edit_state.queued_heavy_jobs = [
            HeavyJobSpec(id="job-1", tool=HeavyTool.AI_UPSCALE, params={"factor": 2}),
        ]

        result = prepare_batch_assets(
            selected_assets=[target],
            active_asset=active,
            controller=_FakeController(),
            auto_export=False,
            apply_active_edits=True,
            apply_selected_preset=False,
            selected_preset_name="",
            background_override=None,
        )

        self.assertEqual(len(result.assets), 1)
        prepared = result.assets[0]
        self.assertIsNot(prepared, target)
        self.assertAlmostEqual(prepared.edit_state.settings.cleanup.denoise, 0.37, places=3)
        self.assertEqual(len(prepared.edit_state.queued_heavy_jobs), 1)
        self.assertEqual(prepared.edit_state.queued_heavy_jobs[0].tool, HeavyTool.AI_UPSCALE)
        self.assertIsNone(prepared.derived_current_path)
        self.assertIsNone(prepared.derived_final_path)
        self.assertIsNotNone(target.derived_current_path)
        self.assertIsNotNone(target.derived_final_path)


if __name__ == "__main__":
    unittest.main()
