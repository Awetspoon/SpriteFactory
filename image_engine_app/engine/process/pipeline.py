"""Processing pipeline ordering and plan builder (Prompt 9)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PipelinePhase(str, Enum):
    """Canonical processing phase ordering from the spec."""

    DENOISE = "denoise"
    SHARPEN = "sharpen"
    UPSCALE = "upscale"
    COLOR = "color"
    EXPORT = "export"


PHASE_ORDER = {
    PipelinePhase.DENOISE: 0,
    PipelinePhase.SHARPEN: 1,
    PipelinePhase.UPSCALE: 2,
    PipelinePhase.COLOR: 3,
    PipelinePhase.EXPORT: 4,
}


@dataclass(frozen=True)
class ProcessingStep:
    """Single processing operation in a plan."""

    key: str
    phase: PipelinePhase
    params: dict[str, Any] = field(default_factory=dict)
    is_heavy: bool = False
    enabled: bool = True

    @property
    def requires_queue(self) -> bool:
        return self.is_heavy


@dataclass
class ProcessingPlan:
    """Ordered processing plan split into live (light) and queued (heavy) steps."""

    steps: list[ProcessingStep] = field(default_factory=list)

    @property
    def ordered_steps(self) -> list[ProcessingStep]:
        return list(_sort_steps(self.steps))

    @property
    def live_steps(self) -> list[ProcessingStep]:
        return [step for step in self.ordered_steps if not step.is_heavy]

    @property
    def queued_heavy_steps(self) -> list[ProcessingStep]:
        return [step for step in self.ordered_steps if step.is_heavy]

    def to_apply_sequence(self) -> list[ProcessingStep]:
        """Sequence used when Apply is pressed (includes both live and heavy in order)."""

        return self.ordered_steps


def build_processing_plan(steps: list[ProcessingStep]) -> ProcessingPlan:
    """Build a normalized plan from requested steps."""

    normalized = [step for step in steps if step.enabled]
    return ProcessingPlan(steps=_sort_steps(normalized))


def merge_processing_plans(*plans: ProcessingPlan) -> ProcessingPlan:
    """
    Merge plans by step key with last-plan-wins semantics, then reapply canonical ordering.

    This supports "light preview plan + heavy queued changes + export override" composition.
    """

    merged_by_key: dict[str, ProcessingStep] = {}
    for plan in plans:
        for step in plan.steps:
            if not step.enabled:
                continue
            merged_by_key[step.key] = step
    return ProcessingPlan(steps=_sort_steps(list(merged_by_key.values())))


def _sort_steps(steps: list[ProcessingStep]) -> list[ProcessingStep]:
    return sorted(
        steps,
        key=lambda step: (
            PHASE_ORDER[step.phase],
            1 if step.is_heavy else 0,  # light before heavy within the same phase
            step.key,
        ),
    )

