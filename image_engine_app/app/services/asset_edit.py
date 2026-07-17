"""Single application workflow for asset controls and Final-preview output."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from image_engine_app.engine.export.profiles import get_profile_rule
from image_engine_app.engine.models import (
    AssetRecord,
    EditState,
    ExportProfile,
    normalize_background_removal_mode,
)
from image_engine_app.engine.process.asset_preview import render_asset_preview
from image_engine_app.engine.process.edit_baseline import (
    clear_generated_outputs,
    ensure_detected_settings,
    restore_detected_settings,
)
from image_engine_app.engine.process.edit_impact import (
    EditImpact,
    has_visible_settings_changes,
    setting_impact,
)
from image_engine_app.engine.process.errors import ProcessingError
from image_engine_app.engine.process.output_size import apply_output_size_choice


@dataclass(frozen=True)
class AssetEditResult:
    """Outcome of one control, preset, refresh, or reset operation."""

    changed: bool
    impact: EditImpact
    preview_attempted: bool = False
    preview_rendered: bool = False
    preview_error: str | None = None


class AssetEditService:
    """Own the active EditState mutation and derived Final lifecycle."""

    def __init__(self, *, derived_cache_dir: str | Path | None) -> None:
        self._derived_cache_dir = Path(derived_cache_dir) if derived_cache_dir is not None else None

    def update_setting(
        self,
        asset: AssetRecord,
        group_name: str,
        field_name: str,
        value: Any,
        *,
        refresh_final: bool = True,
    ) -> AssetEditResult:
        """Update one real settings field and refresh Final only when required."""

        impact = setting_impact(group_name, field_name)
        group = getattr(asset.edit_state.settings, group_name)
        current = getattr(group, field_name)
        resolved = self._coerce_setting_value(current, value)

        if group_name == "alpha" and field_name == "background_removal_mode":
            resolved = normalize_background_removal_mode(resolved).value
            changed = current != resolved or bool(group.remove_white_bg) != (resolved == "white")
            if not changed:
                return AssetEditResult(changed=False, impact=impact)
            group.background_removal_mode = resolved
            group.remove_white_bg = resolved == "white"
        elif group_name == "alpha" and field_name == "remove_white_bg":
            resolved = bool(resolved)
            mode_value = "white" if resolved else "off"
            changed = bool(current) != resolved or group.background_removal_mode != mode_value
            if not changed:
                return AssetEditResult(changed=False, impact=impact)
            group.remove_white_bg = resolved
            group.background_removal_mode = mode_value
        else:
            if current == resolved:
                return AssetEditResult(changed=False, impact=impact)
            setattr(group, field_name, resolved)

        return self._finish_change(asset, impact=impact, refresh_final=refresh_final)

    def apply_output_size(
        self,
        asset: AssetRecord,
        choice_key: str,
        *,
        refresh_final: bool = True,
    ) -> AssetEditResult:
        """Apply a convenience size choice to the same pixel controls used by manual edits."""

        changed = apply_output_size_choice(asset.edit_state.settings.pixel, choice_key)
        if not changed:
            return AssetEditResult(changed=False, impact=EditImpact.PREVIEW)
        return self._finish_change(
            asset,
            impact=EditImpact.PREVIEW,
            refresh_final=refresh_final,
        )

    def reset_settings_to_detected(
        self,
        asset: AssetRecord,
        field_paths: Iterable[tuple[str, str]],
        *,
        refresh_final: bool = True,
    ) -> AssetEditResult:
        """Restore selected fields from the source baseline without touching other edits."""

        baseline = ensure_detected_settings(asset)
        changed = False
        combined_impact = EditImpact.EXPORT_ONLY
        seen: set[tuple[str, str]] = set()

        for raw_group_name, raw_field_name in field_paths:
            group_name = str(raw_group_name)
            field_name = str(raw_field_name)
            field_path = (group_name, field_name)
            if field_path in seen:
                continue
            seen.add(field_path)

            baseline_group = getattr(baseline, group_name)
            baseline_value = deepcopy(getattr(baseline_group, field_name))
            result = self.update_setting(
                asset,
                group_name,
                field_name,
                baseline_value,
                refresh_final=False,
            )
            if not result.changed:
                continue
            changed = True
            if result.impact is EditImpact.PREVIEW:
                combined_impact = EditImpact.PREVIEW

        if not changed:
            return AssetEditResult(changed=False, impact=combined_impact)
        if refresh_final and combined_impact is EditImpact.PREVIEW:
            return self._render_result(asset, changed=True)
        return AssetEditResult(changed=True, impact=combined_impact)

    def set_export_profile(self, asset: AssetRecord, profile: ExportProfile | str) -> AssetEditResult:
        """Apply encoding defaults without rebuilding Final."""

        profile_enum = profile if isinstance(profile, ExportProfile) else ExportProfile(str(profile))
        rule = get_profile_rule(profile_enum)
        export = asset.edit_state.settings.export
        before = deepcopy(export)
        export.export_profile = profile_enum
        export.format = rule.default_format
        export.quality = rule.default_quality
        export.compression_level = rule.default_compression_level
        export.strip_metadata = rule.strip_metadata
        return AssetEditResult(changed=(before != export), impact=EditImpact.EXPORT_ONLY)

    def replace_edit_state(
        self,
        asset: AssetRecord,
        edit_state: EditState,
        *,
        refresh_final: bool = True,
    ) -> AssetEditResult:
        """Replace controls atomically and optionally rebuild Final."""

        changed = asset.edit_state != edit_state
        asset.edit_state = deepcopy(edit_state)
        clear_generated_outputs(asset)
        if not refresh_final:
            return AssetEditResult(changed=changed, impact=EditImpact.PREVIEW)
        return self._render_result(asset, changed=changed)

    def reset_to_detected(
        self,
        asset: AssetRecord,
        *,
        refresh_final: bool = True,
    ) -> AssetEditResult:
        """Restore the detected baseline and rebuild Final from that one state."""

        before = deepcopy(asset.edit_state)
        restore_detected_settings(asset)
        if not refresh_final:
            return AssetEditResult(
                changed=(before != asset.edit_state),
                impact=EditImpact.PREVIEW,
            )
        return self._render_result(asset, changed=(before != asset.edit_state))

    def refresh_final(
        self,
        asset: AssetRecord,
        *,
        output_stem: str = "final",
    ) -> AssetEditResult:
        """Explicitly rebuild Final from the current EditState."""

        clear_generated_outputs(asset)
        return self._render_result(asset, changed=False, output_stem=output_stem)

    def ensure_final(self, asset: AssetRecord) -> AssetEditResult:
        """Reuse the exact source until the user makes a visible edit."""

        if not self._has_visible_edits(asset):
            clear_generated_outputs(asset)
            return AssetEditResult(changed=False, impact=EditImpact.PREVIEW)

        raw_path = asset.derived_final_path
        if isinstance(raw_path, str) and raw_path.strip():
            try:
                path = Path(raw_path)
                if path.exists() and path.is_file():
                    return AssetEditResult(changed=False, impact=EditImpact.PREVIEW)
            except OSError:
                pass
        clear_generated_outputs(asset)
        return self._render_result(asset, changed=False)

    def _finish_change(
        self,
        asset: AssetRecord,
        *,
        impact: EditImpact,
        refresh_final: bool,
    ) -> AssetEditResult:
        if impact is EditImpact.EXPORT_ONLY:
            return AssetEditResult(changed=True, impact=impact)
        clear_generated_outputs(asset)
        if not refresh_final:
            return AssetEditResult(changed=True, impact=impact)
        return self._render_result(asset, changed=True)

    def _render_result(
        self,
        asset: AssetRecord,
        *,
        changed: bool,
        output_stem: str = "final",
    ) -> AssetEditResult:
        if not self._has_visible_edits(asset):
            clear_generated_outputs(asset)
            return AssetEditResult(
                changed=changed,
                impact=EditImpact.PREVIEW,
                preview_attempted=False,
            )
        if self._derived_cache_dir is None:
            return AssetEditResult(
                changed=changed,
                impact=EditImpact.PREVIEW,
                preview_attempted=False,
            )
        try:
            rendered = render_asset_preview(
                asset,
                derived_cache_dir=self._derived_cache_dir,
                output_stem=output_stem,
            )
            return AssetEditResult(
                changed=changed,
                impact=EditImpact.PREVIEW,
                preview_attempted=True,
                preview_rendered=rendered,
            )
        except ProcessingError as exc:
            return AssetEditResult(
                changed=changed,
                impact=EditImpact.PREVIEW,
                preview_attempted=True,
                preview_error=str(exc),
            )

    @staticmethod
    def _has_visible_edits(asset: AssetRecord) -> bool:
        return has_visible_settings_changes(
            asset.edit_state.settings,
            baseline=ensure_detected_settings(asset),
        )

    @staticmethod
    def _coerce_setting_value(current: Any, value: Any) -> Any:
        if isinstance(current, Enum) and not isinstance(value, current.__class__):
            return current.__class__(value)
        return value
