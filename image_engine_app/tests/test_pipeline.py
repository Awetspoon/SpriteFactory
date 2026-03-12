"""Tests for processing plan ordering and merge behavior."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.process.pipeline import (  # noqa: E402
    PipelinePhase,
    ProcessingPlan,
    ProcessingStep,
    build_processing_plan,
    merge_processing_plans,
)


class PipelineTests(unittest.TestCase):
    def test_build_processing_plan_enforces_canonical_order(self) -> None:
        requested = [
            ProcessingStep(key="color.balance", phase=PipelinePhase.COLOR, params={"contrast": 0.1}),
            ProcessingStep(key="denoise.base", phase=PipelinePhase.DENOISE, params={"denoise": 0.2}),
            ProcessingStep(key="upscale.ai", phase=PipelinePhase.UPSCALE, params={"factor": 2}, is_heavy=True),
            ProcessingStep(key="sharpen.edge", phase=PipelinePhase.SHARPEN, params={"amount": 0.3}),
            ProcessingStep(key="export.webp", phase=PipelinePhase.EXPORT, params={"format": "webp"}),
        ]
        plan = build_processing_plan(requested)

        ordered_keys = [step.key for step in plan.ordered_steps]
        self.assertEqual(
            ordered_keys,
            [
                "denoise.base",
                "sharpen.edge",
                "upscale.ai",
                "color.balance",
                "export.webp",
            ],
        )
        self.assertEqual([step.key for step in plan.live_steps], [
            "denoise.base",
            "sharpen.edge",
            "color.balance",
            "export.webp",
        ])
        self.assertEqual([step.key for step in plan.queued_heavy_steps], ["upscale.ai"])

    def test_merge_processing_plans_uses_last_wins_by_key_and_reorders(self) -> None:
        preview_plan = build_processing_plan(
            [
                ProcessingStep(key="denoise.base", phase=PipelinePhase.DENOISE, params={"denoise": 0.1}),
                ProcessingStep(key="color.balance", phase=PipelinePhase.COLOR, params={"brightness": 0.05}),
                ProcessingStep(key="upscale.ai", phase=PipelinePhase.UPSCALE, params={"factor": 2}, is_heavy=True),
            ]
        )
        override_plan = build_processing_plan(
            [
                ProcessingStep(key="upscale.ai", phase=PipelinePhase.UPSCALE, params={"factor": 4}, is_heavy=True),
                ProcessingStep(key="export.png", phase=PipelinePhase.EXPORT, params={"format": "png"}),
                ProcessingStep(key="color.balance", phase=PipelinePhase.COLOR, params={"brightness": 0.15}),
            ]
        )

        merged = merge_processing_plans(preview_plan, override_plan)
        merged_keys = [step.key for step in merged.ordered_steps]
        self.assertEqual(
            merged_keys,
            ["denoise.base", "upscale.ai", "color.balance", "export.png"],
        )

        upscale_step = next(step for step in merged.steps if step.key == "upscale.ai")
        self.assertEqual(upscale_step.params["factor"], 4)
        color_step = next(step for step in merged.steps if step.key == "color.balance")
        self.assertEqual(color_step.params["brightness"], 0.15)

    def test_disabled_steps_are_ignored(self) -> None:
        plan = build_processing_plan(
            [
                ProcessingStep(key="denoise.base", phase=PipelinePhase.DENOISE, enabled=False),
                ProcessingStep(key="export.jpg", phase=PipelinePhase.EXPORT, params={"format": "jpg"}),
            ]
        )
        self.assertEqual([step.key for step in plan.ordered_steps], ["export.jpg"])
        self.assertIsInstance(plan, ProcessingPlan)


if __name__ == "__main__":
    unittest.main()

