"""Application workflow for applying catalog presets to assets."""

from __future__ import annotations

from dataclasses import dataclass

from image_engine_app.app.services.asset_edit import AssetEditResult, AssetEditService
from image_engine_app.app.services.preset_library import PresetLibrary
from image_engine_app.engine.models import AssetRecord, PresetModel
from image_engine_app.engine.process.preset_application import (
    plan_preset_application,
    select_first_compatible_preset,
)


@dataclass(frozen=True)
class PresetWorkflowResult:
    """Application-level outcome shared by Workspace, imports, and Batch prep."""

    preset_name: str
    requires_apply: bool
    queued_heavy_jobs: int
    edit_result: AssetEditResult


class PresetWorkflowService:
    """Apply presets from the single library through the single edit service."""

    def __init__(
        self,
        *,
        library: PresetLibrary,
        asset_edits: AssetEditService,
    ) -> None:
        self._library = library
        self._asset_edits = asset_edits

    def apply_named(
        self,
        asset: AssetRecord,
        preset_name: str,
        *,
        refresh_final: bool = True,
        queue_heavy_jobs: bool = True,
    ) -> PresetWorkflowResult:
        """Apply one named preset from the detected baseline."""

        preset = self._library.get(preset_name)
        return self._apply_preset(
            asset,
            preset,
            refresh_final=refresh_final,
            queue_heavy_jobs=queue_heavy_jobs,
        )

    def apply_recommended(
        self,
        asset: AssetRecord,
        *,
        minimum_confidence: float,
        refresh_final: bool = False,
        queue_heavy_jobs: bool = False,
    ) -> PresetWorkflowResult | None:
        """Apply the first confident, compatible recommendation from the catalog."""

        recommendations = getattr(asset, "recommendations", None)
        suggestions = list(getattr(recommendations, "suggested_presets", []) or [])
        candidates: list[PresetModel] = []
        for suggestion in suggestions:
            name = str(getattr(suggestion, "preset_name", "") or "").strip()
            confidence = float(getattr(suggestion, "confidence", 0.0) or 0.0)
            if not name or confidence < minimum_confidence or not self._library.has_preset(name):
                continue
            candidates.append(self._library.get(name))

        selected = select_first_compatible_preset(asset, candidates)
        if selected is None:
            return None
        return self._apply_preset(
            asset,
            selected,
            refresh_final=refresh_final,
            queue_heavy_jobs=queue_heavy_jobs,
        )

    def _apply_preset(
        self,
        asset: AssetRecord,
        preset: PresetModel,
        *,
        refresh_final: bool,
        queue_heavy_jobs: bool,
    ) -> PresetWorkflowResult:
        plan = plan_preset_application(
            asset,
            preset,
            queue_heavy_jobs=queue_heavy_jobs,
        )
        edit_result = self._asset_edits.replace_edit_state(
            asset,
            plan.edit_state,
            refresh_final=refresh_final,
        )
        return PresetWorkflowResult(
            preset_name=plan.preset_name,
            requires_apply=plan.requires_apply,
            queued_heavy_jobs=len(plan.queued_heavy_jobs),
            edit_result=edit_result,
        )
