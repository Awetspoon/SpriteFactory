"""Header and navigation state helpers for the settings panel."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SettingsPanelHeaderState:
    """Presentation-ready summary for the top of the settings panel."""

    title_text: str = "EDIT SETTINGS"
    subtitle_text: str = "Select an asset to unlock editing groups and export controls."


def build_settings_panel_header_state(
    *,
    asset: object | None,
    visible_group_count: int,
    total_group_count: int,
    active_group_title: str | None,
    has_alpha: bool,
    is_gif: bool,
) -> SettingsPanelHeaderState:
    visible_count = max(0, int(visible_group_count))
    total_count = max(0, int(total_group_count))

    if asset is None:
        return SettingsPanelHeaderState(
            subtitle_text=f"Select an asset to unlock editing groups and export controls. {visible_count}/{total_count} sections available.",
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
            f"{visible_count}/{total_count} sections available. "
            f"Jump to {active_group_label} below."
        ).strip(),
    )
