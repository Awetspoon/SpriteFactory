"""Tests for preset stacking, mode clamping, and apply-target behavior."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


from image_engine_app.engine.models import ApplyTarget, EditMode, EditState, PresetModel  # noqa: E402
from image_engine_app.engine.process.bounds import clamp_edit_state_for_mode  # noqa: E402
from image_engine_app.engine.process.presets_apply import (  # noqa: E402
    PresetApplyError,
    ViewEditStates,
    apply_preset_stack,
    apply_preset_to_views,
)


def _make_edit_state(*, mode: EditMode, brightness: float = 0.0, quality: int = 90) -> EditState:
    state = EditState(mode=mode, sync_current_final=False, apply_target=ApplyTarget.CURRENT, auto_apply_light=True)
    state.settings.color.brightness = brightness
    state.settings.export.quality = quality
    return state


class BoundsTests(unittest.TestCase):
    def test_mode_clamping_differs_between_simple_and_expert(self) -> None:
        state = EditState(mode=EditMode.SIMPLE)
        state.settings.color.brightness = 0.8
        state.settings.ai.upscale_factor = 6.0
        state.settings.export.quality = 150
        state.settings.pixel.resize_percent = 2000.0

        simple = clamp_edit_state_for_mode(state, mode=EditMode.SIMPLE)
        expert = clamp_edit_state_for_mode(state, mode=EditMode.EXPERT)

        self.assertEqual(simple.settings.color.brightness, 0.25)
        self.assertEqual(simple.settings.ai.upscale_factor, 2.0)
        self.assertEqual(simple.settings.export.quality, 100)
        self.assertEqual(simple.settings.pixel.resize_percent, 400.0)

        self.assertEqual(expert.settings.color.brightness, 0.8)
        self.assertEqual(expert.settings.ai.upscale_factor, 6.0)
        self.assertEqual(expert.settings.export.quality, 100)
        self.assertEqual(expert.settings.pixel.resize_percent, 1600.0)


class PresetApplyTests(unittest.TestCase):
    def test_apply_preset_to_current_only_without_sync(self) -> None:
        preset = PresetModel(
            name="Brighten",
            description="Raise brightness and quality",
            settings_delta={"color": {"brightness": 0.9}, "export": {"quality": 120}},
            mode_min=EditMode.SIMPLE,
        )
        current = _make_edit_state(mode=EditMode.SIMPLE, brightness=0.0, quality=90)
        current.apply_target = ApplyTarget.CURRENT
        current.sync_current_final = False
        final = _make_edit_state(mode=EditMode.SIMPLE, brightness=-0.1, quality=70)

        report = apply_preset_to_views(preset, states=ViewEditStates(current=current, final=final))

        self.assertEqual(report.effective_target, ApplyTarget.CURRENT)
        self.assertFalse(report.sync_applied)
        self.assertEqual(report.states.current.settings.color.brightness, 0.25)  # clamped in Simple mode
        self.assertEqual(report.states.current.settings.export.quality, 100)
        self.assertEqual(report.states.final.settings.color.brightness, -0.1)  # unchanged
        self.assertEqual(report.states.final.settings.export.quality, 70)

    def test_sync_mirrors_single_target_apply_to_both_views(self) -> None:
        preset = PresetModel(
            name="Cleanup",
            description="Denoise and sharpen",
            settings_delta={"cleanup": {"denoise": 0.9}, "detail": {"sharpen_amount": 2.5}},
            mode_min=EditMode.ADVANCED,
            uses_heavy_tools=False,
            requires_apply=False,
        )
        current = _make_edit_state(mode=EditMode.ADVANCED)
        current.sync_current_final = True
        current.apply_target = ApplyTarget.FINAL
        final = _make_edit_state(mode=EditMode.ADVANCED)

        report = apply_preset_to_views(preset, states=ViewEditStates(current=current, final=final))

        self.assertTrue(report.sync_applied)
        self.assertEqual(report.states.current.settings.cleanup.denoise, 0.8)  # advanced clamp
        self.assertEqual(report.states.final.settings.cleanup.denoise, 0.8)
        self.assertEqual(report.states.current.settings.detail.sharpen_amount, 2.0)
        self.assertEqual(report.states.final.settings.detail.sharpen_amount, 2.0)

    def test_preset_stack_applies_in_order_and_reports_requires_apply(self) -> None:
        base = PresetModel(
            name="BaseTone",
            description="Base color adjustments",
            settings_delta={"color": {"brightness": 0.2, "contrast": 0.1}},
            mode_min=EditMode.SIMPLE,
        )
        override = PresetModel(
            name="HeavyUpscale",
            description="Enable upscale",
            settings_delta={"ai": {"upscale_factor": 6.0}},
            mode_min=EditMode.SIMPLE,
            uses_heavy_tools=True,
            requires_apply=True,
        )
        current = _make_edit_state(mode=EditMode.EXPERT)
        current.apply_target = ApplyTarget.BOTH
        final = _make_edit_state(mode=EditMode.EXPERT)

        report = apply_preset_stack(
            [base, override],
            states=ViewEditStates(current=current, final=final),
        )

        self.assertEqual(report.applied_preset_names, ["BaseTone", "HeavyUpscale"])
        self.assertTrue(report.requires_apply)
        self.assertEqual(report.states.current.settings.color.brightness, 0.2)
        self.assertEqual(report.states.final.settings.color.contrast, 0.1)
        self.assertEqual(report.states.current.settings.ai.upscale_factor, 6.0)
        self.assertEqual(report.states.final.settings.ai.upscale_factor, 6.0)

    def test_mode_min_enforcement_raises(self) -> None:
        preset = PresetModel(
            name="ExpertOnly",
            description="Needs expert mode",
            settings_delta={"ai": {"deblur_strength": 0.8}},
            mode_min=EditMode.EXPERT,
        )
        current = _make_edit_state(mode=EditMode.SIMPLE)
        current.apply_target = ApplyTarget.CURRENT
        final = _make_edit_state(mode=EditMode.SIMPLE)

        with self.assertRaises(PresetApplyError):
            apply_preset_to_views(preset, states=ViewEditStates(current=current, final=final))


if __name__ == "__main__":
    unittest.main()



