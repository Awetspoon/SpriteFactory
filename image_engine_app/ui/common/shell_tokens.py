"""Shared visual and geometry tokens for the desktop shell."""

from __future__ import annotations

from dataclasses import dataclass


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(int(minimum), min(int(maximum), int(value)))


@dataclass(frozen=True)
class ShellGeometry:
    """Measurements shared by the main window and its major panels."""

    window_default_width: int = 1460
    window_default_height: int = 920
    window_min_width: int = 1180
    window_min_height: int = 760

    outer_margin: int = 8
    panel_margin: int = 8
    card_margin: int = 8
    gap: int = 8
    compact_gap: int = 6
    card_radius: int = 12
    control_radius: int = 7
    control_height: int = 26
    toolbar_control_height: int = 30

    page_rail_width: int = 76
    page_button_width: int = 64
    page_button_height: int = 60

    workspace_left_min: int = 210
    workspace_left_max: int = 270
    workspace_left_default: int = 248
    workspace_editor_min: int = 520
    workspace_inspector_min: int = 340
    workspace_inspector_max: int = 390
    workspace_inspector_default: int = 366
    splitter_handle_width: int = 4

    toolbar_brand_width: int = 200
    toolbar_brand_height: int = 40
    toolbar_button_width: int = 68
    toolbar_badge_width: int = 84

    preview_min_height: int = 420
    preview_frame_min_height: int = 360
    preview_scroll_min_height: int = 310
    preview_canvas_min: int = 180
    preview_header_compact_width: int = 700

    settings_tile_width: int = 76
    settings_tile_height: int = 64
    settings_field_min_width: int = 112
    settings_field_max_width: int = 158

    control_menu_width: int = 86
    control_badge_width: int = 86
    export_compact_width: int = 650
    export_profile_width: int = 94
    export_size_width: int = 94

    workspace_section_width: int = 70
    workspace_pager_size: int = 24
    web_short_list_height: int = 88
    web_link_list_height: int = 104

    def workspace_column_sizes(self, window_width: int) -> tuple[int, int, int]:
        """Return left, editor, and inspector sizes that fit the shell."""

        usable = max(
            self.workspace_left_min
            + self.workspace_editor_min
            + self.workspace_inspector_min
            + (2 * self.splitter_handle_width),
            int(window_width)
            - (2 * self.outer_margin)
            - self.page_rail_width
            - self.gap,
        )
        left = _clamp(
            round(usable * 0.18),
            self.workspace_left_min,
            self.workspace_left_max,
        )
        inspector = _clamp(
            round(usable * 0.27),
            self.workspace_inspector_min,
            self.workspace_inspector_max,
        )
        editor = usable - left - inspector - (2 * self.splitter_handle_width)

        if editor < self.workspace_editor_min:
            shortage = self.workspace_editor_min - editor
            left_reduction = min(shortage, left - self.workspace_left_min)
            left -= left_reduction
            shortage -= left_reduction
            inspector -= min(shortage, inspector - self.workspace_inspector_min)
            editor = usable - left - inspector - (2 * self.splitter_handle_width)

        return left, max(self.workspace_editor_min, editor), inspector


@dataclass(frozen=True)
class ShellPalette:
    """Core colors used by the shared stylesheet."""

    canvas: str = "#f5f1ea"
    canvas_cool: str = "#eef0ec"
    toolbar: str = "#f7f4ee"
    surface: str = "#fffdfa"
    surface_soft: str = "#fbfaf7"
    surface_muted: str = "#f8f6f1"
    border: str = "#d3d8d3"
    border_strong: str = "#bdc9c3"
    text: str = "#27353b"
    muted_text: str = "#6f7c81"
    accent: str = "#4a8f93"
    accent_dark: str = "#3c7e82"
    accent_soft: str = "#eaf2ef"


SHELL_GEOMETRY = ShellGeometry()
SHELL_PALETTE = ShellPalette()
