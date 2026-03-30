"""Shared state helpers for the preview control strip."""

from __future__ import annotations

from dataclasses import dataclass

from image_engine_app.engine.models import ApplyTarget, BackgroundRemovalMode, normalize_background_removal_mode


@dataclass(frozen=True)
class ControlStripViewState:
    """Normalized control-strip state derived from the active asset."""

    has_asset: bool
    apply_target: str = ApplyTarget.BOTH.value
    sync_current_final: bool = True
    auto_apply_light: bool = True
    queued_heavy_jobs: int = 0
    running_heavy_jobs: int = 0
    summary_text: str = "Select an asset to start editing."
    queue_badge_text: str = "No asset"
    queue_badge_tone: str = "disabled"
    target_badge_text: str = "Target: --"
    background_mode: str = BackgroundRemovalMode.OFF.value
    background_button_text: str = "BG Off"
    background_button_tooltip: str = "Keep the current background settings for the active asset."
    apply_button_text: str = "Apply"
    apply_button_tooltip: str = "Select an asset before applying changes."
    preview_button_text: str = "Preview"
    preview_button_tooltip: str = "Render a light-only preview for the active asset."


def build_control_strip_view_state(asset: object | None, heavy_queue_state: object | None = None) -> ControlStripViewState:
    edit_state = getattr(asset, "edit_state", None)
    if edit_state is None:
        return ControlStripViewState(has_asset=False)

    apply_target = getattr(getattr(edit_state, "apply_target", None), "value", ApplyTarget.BOTH.value)
    if apply_target not in {
        ApplyTarget.CURRENT.value,
        ApplyTarget.FINAL.value,
        ApplyTarget.BOTH.value,
    }:
        apply_target = ApplyTarget.BOTH.value

    queued_heavy_jobs = _int_attr(
        heavy_queue_state,
        "queued_count",
        default=len(getattr(edit_state, "queued_heavy_jobs", ()) or ()),
    )
    running_heavy_jobs = _int_attr(heavy_queue_state, "running_count", default=0)
    alpha_settings = getattr(getattr(edit_state, "settings", None), "alpha", None)

    target_label = _TARGET_LABELS.get(apply_target, "Both")
    sync_text = "Views linked" if bool(getattr(edit_state, "sync_current_final", True)) else "Views split"
    preview_text = "Auto preview on" if bool(getattr(edit_state, "auto_apply_light", True)) else "Auto preview off"

    queue_badge_text = "Ready"
    queue_badge_tone = "ready"
    apply_button_text = "Apply"
    apply_button_tooltip = "Commit the light pipeline for the active asset."
    background_mode = normalize_background_removal_mode(
        getattr(alpha_settings, "background_removal_mode", None),
        remove_white_bg=bool(getattr(alpha_settings, "remove_white_bg", False)),
    ).value

    if running_heavy_jobs > 0:
        queue_badge_text = f"Running: {running_heavy_jobs}"
        queue_badge_tone = "running"
        apply_button_text = "Run Heavy"
        apply_button_tooltip = "Run the queued heavy steps for the active asset."
    elif queued_heavy_jobs > 0:
        queue_badge_text = f"Queued: {queued_heavy_jobs}"
        queue_badge_tone = "queued"
        apply_button_text = f"Run {queued_heavy_jobs} Heavy"
        apply_button_tooltip = "Run the queued heavy steps for the active asset."

    return ControlStripViewState(
        has_asset=True,
        apply_target=apply_target,
        sync_current_final=bool(getattr(edit_state, "sync_current_final", True)),
        auto_apply_light=bool(getattr(edit_state, "auto_apply_light", True)),
        queued_heavy_jobs=max(0, queued_heavy_jobs),
        running_heavy_jobs=max(0, running_heavy_jobs),
        summary_text=f"{sync_text} | {preview_text}",
        queue_badge_text=queue_badge_text,
        queue_badge_tone=queue_badge_tone,
        target_badge_text=f"Target: {target_label}",
        background_mode=background_mode,
        background_button_text=_BACKGROUND_BUTTON_TEXT[background_mode],
        background_button_tooltip=_BACKGROUND_BUTTON_TOOLTIPS[background_mode],
        apply_button_text=apply_button_text,
        apply_button_tooltip=apply_button_tooltip,
    )


_TARGET_LABELS: dict[str, str] = {
    ApplyTarget.CURRENT.value: "Current",
    ApplyTarget.FINAL.value: "Final",
    ApplyTarget.BOTH.value: "Both",
}

_BACKGROUND_BUTTON_TEXT: dict[str, str] = {
    BackgroundRemovalMode.OFF.value: "BG Off",
    BackgroundRemovalMode.WHITE.value: "BG White",
    BackgroundRemovalMode.BLACK.value: "BG Black",
}

_BACKGROUND_BUTTON_TOOLTIPS: dict[str, str] = {
    BackgroundRemovalMode.OFF.value: "Keep the current image background.",
    BackgroundRemovalMode.WHITE.value: "Remove edge-connected white backgrounds.",
    BackgroundRemovalMode.BLACK.value: "Remove edge-connected black backgrounds.",
}


def _int_attr(source: object | None, name: str, *, default: int) -> int:
    try:
        if source is None:
            return max(0, int(default))
        return max(0, int(getattr(source, name, default)))
    except Exception:
        return max(0, int(default))

