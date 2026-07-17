"""Classify settings by whether they change the rendered Final preview."""

from __future__ import annotations

from enum import Enum

from image_engine_app.engine.models import SettingsState


class EditImpact(str, Enum):
    """The output surface affected by one settings change."""

    PREVIEW = "preview"
    EXPORT_ONLY = "export_only"


_EXPORT_ONLY_FIELDS = {
    ("pixel", "dpi"),
    ("gif", "frame_optimize"),
}


def setting_impact(group_name: str, field_name: str) -> EditImpact:
    """Return whether a real settings field changes Final or export only."""

    group_key = str(group_name or "").strip()
    field_key = str(field_name or "").strip()
    settings = SettingsState()
    group = getattr(settings, group_key, None)
    if group is None or not hasattr(group, field_key):
        raise ValueError(f"Unknown edit setting: {group_key}.{field_key}")

    if group_key == "export" or (group_key, field_key) in _EXPORT_ONLY_FIELDS:
        return EditImpact.EXPORT_ONLY
    return EditImpact.PREVIEW


def has_visible_settings_changes(
    settings: SettingsState,
    *,
    baseline: SettingsState | None = None,
) -> bool:
    """Return True when settings differ in a way that changes rendered pixels or playback."""

    reference = baseline or SettingsState()
    for group_name in ("pixel", "color", "detail", "cleanup", "edges", "alpha", "ai", "gif"):
        current_group = getattr(settings, group_name)
        reference_group = getattr(reference, group_name)
        for field_name, current_value in current_group.to_dict().items():
            if setting_impact(group_name, field_name) is EditImpact.EXPORT_ONLY:
                continue
            if current_value != reference_group.to_dict().get(field_name):
                return True
    return False
