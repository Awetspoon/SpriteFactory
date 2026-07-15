"""Shared state helpers for the preview control strip."""

from __future__ import annotations

from dataclasses import dataclass

from image_engine_app.engine.models import BackgroundRemovalMode, normalize_background_removal_mode


@dataclass(frozen=True)
class ControlStripViewState:
    """Normalized control-strip state derived from the active asset."""

    has_asset: bool
    queued_heavy_jobs: int = 0
    running_heavy_jobs: int = 0
    summary_text: str = "Select an asset to start editing."
    queue_badge_text: str = "No asset"
    queue_badge_tone: str = "disabled"
    background_mode: str = BackgroundRemovalMode.OFF.value
    background_button_text: str = "Keep BG"
    background_button_tooltip: str = "Keep the current background settings for the active asset."
    run_button_text: str = "Refresh Final"
    run_button_tooltip: str = "Select an asset before refreshing Final."
    run_heavy: bool = False


def build_control_strip_view_state(asset: object | None, heavy_queue_state: object | None = None) -> ControlStripViewState:
    edit_state = getattr(asset, "edit_state", None)
    if edit_state is None:
        return ControlStripViewState(has_asset=False)

    queued_heavy_jobs = _int_attr(
        heavy_queue_state,
        "queued_count",
        default=len(getattr(edit_state, "queued_heavy_jobs", ()) or ()),
    )
    running_heavy_jobs = _int_attr(heavy_queue_state, "running_count", default=0)
    alpha_settings = getattr(getattr(edit_state, "settings", None), "alpha", None)

    queue_badge_text = "Ready"
    queue_badge_tone = "ready"
    run_button_text = "Refresh Final"
    run_button_tooltip = "Rebuild the Final pane using the current edit settings."
    run_heavy = False
    background_mode = normalize_background_removal_mode(
        getattr(alpha_settings, "background_removal_mode", None),
        remove_white_bg=bool(getattr(alpha_settings, "remove_white_bg", False)),
    ).value

    if running_heavy_jobs > 0:
        queue_badge_text = f"Running: {running_heavy_jobs}"
        queue_badge_tone = "running"
        run_button_text = "Heavy Steps Running"
        run_button_tooltip = "Heavy processing is currently running."
        run_heavy = True
    elif queued_heavy_jobs > 0:
        queue_badge_text = f"Queued: {queued_heavy_jobs}"
        queue_badge_tone = "queued"
        run_button_text = f"Run {queued_heavy_jobs} Heavy"
        run_button_tooltip = "Run the queued heavy steps and refresh the Final pane."
        run_heavy = True

    return ControlStripViewState(
        has_asset=True,
        queued_heavy_jobs=max(0, queued_heavy_jobs),
        running_heavy_jobs=max(0, running_heavy_jobs),
        summary_text="Current is the source | Final updates automatically",
        queue_badge_text=queue_badge_text,
        queue_badge_tone=queue_badge_tone,
        background_mode=background_mode,
        background_button_text=_BACKGROUND_BUTTON_TEXT[background_mode],
        background_button_tooltip=_BACKGROUND_BUTTON_TOOLTIPS[background_mode],
        run_button_text=run_button_text,
        run_button_tooltip=run_button_tooltip,
        run_heavy=run_heavy,
    )

_BACKGROUND_BUTTON_TEXT: dict[str, str] = {
    BackgroundRemovalMode.OFF.value: "Keep BG",
    BackgroundRemovalMode.WHITE.value: "Remove White",
    BackgroundRemovalMode.BLACK.value: "Remove Black",
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

