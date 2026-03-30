"""Header and navigation state helpers for the settings panel."""

from __future__ import annotations

from dataclasses import dataclass

from image_engine_app.engine.models import EditMode


@dataclass(frozen=True)
class SettingsPanelHeaderState:
    """Presentation-ready summary for the top of the settings panel."""

    title_text: str = "Settings"
    subtitle_text: str = "Select an asset to unlock editing groups and export controls."


def build_settings_panel_header_state(
    *,
    asset: object | None,
    mode_value: str,
    visible_group_count: int,
    total_group_count: int,
    active_group_title: str | None,
    has_alpha: bool,
    is_gif: bool,
) -> SettingsPanelHeaderState:
    mode_label = _format_mode_label(mode_value)
    visible_count = max(0, int(visible_group_count))
    total_count = max(0, int(total_group_count))

    if asset is None:
        return SettingsPanelHeaderState(
            subtitle_text=f"Select an asset to unlock editing groups and export controls. {visible_count}/{total_count} sections available in {mode_label} mode.",
        )

    asset_name = str(getattr(asset, "original_name", "") or getattr(asset, "id", "Untitled asset")).strip() or "Untitled asset"
    traits: list[str] = []
    if is_gif:
        traits.append("animated")
    elif has_alpha:
        traits.append("alpha-aware")
    active_group_label = str(active_group_title or "a section").strip()
    trait_text = ""
    if traits:
        trait_text = f" {traits[0].capitalize()} asset."
    return SettingsPanelHeaderState(
        subtitle_text=(
            f"Editing {asset_name}.{trait_text} "
            f"{visible_count}/{total_count} sections available in {mode_label} mode. "
            f"Jump to {active_group_label} below."
        ).strip(),
    )


def _format_mode_label(mode_value: str) -> str:
    normalized = str(mode_value or EditMode.SIMPLE.value).strip().lower()
    try:
        return EditMode(normalized).value.title()
    except Exception:
        return normalized.title() or EditMode.SIMPLE.value.title()
