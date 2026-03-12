"""Mode-aware numeric bounds and clamping helpers (Prompt 11)."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from engine.models import EditMode, EditState, SettingsState


MODE_ORDER = {
    EditMode.SIMPLE: 0,
    EditMode.ADVANCED: 1,
    EditMode.EXPERT: 2,
}


@dataclass(frozen=True)
class NumericBounds:
    """
    Numeric bounds definition for a setting.

    NOTE: The spec does not define exact numeric limits per control. These values are a safe,
    conservative starter set so Prompt 11 clamping behavior can be implemented and tested.
    """

    minimum: float
    safe_min: float
    default: float
    safe_max: float
    maximum: float
    integer: bool = False
    mode_limits: dict[EditMode, tuple[float, float]] = field(default_factory=dict)

    def clamp(self, value: Any, *, mode: EditMode) -> Any:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return value

        low, high = self.mode_limits.get(mode, (self.minimum, self.maximum))
        clamped = min(max(float(value), low), high)
        if self.integer:
            return int(round(clamped))
        return clamped


DEFAULT_SETTING_BOUNDS: dict[str, NumericBounds] = {
    "pixel.resize_percent": NumericBounds(
        minimum=1.0,
        safe_min=25.0,
        default=100.0,
        safe_max=400.0,
        maximum=1600.0,
        mode_limits={
            EditMode.SIMPLE: (50.0, 400.0),
            EditMode.ADVANCED: (10.0, 800.0),
            EditMode.EXPERT: (1.0, 1600.0),
        },
    ),
    "pixel.width": NumericBounds(
        minimum=1,
        safe_min=16,
        default=256,
        safe_max=4096,
        maximum=16384,
        integer=True,
        mode_limits={
            EditMode.SIMPLE: (1, 4096),
            EditMode.ADVANCED: (1, 8192),
            EditMode.EXPERT: (1, 16384),
        },
    ),
    "pixel.height": NumericBounds(
        minimum=1,
        safe_min=16,
        default=256,
        safe_max=4096,
        maximum=16384,
        integer=True,
        mode_limits={
            EditMode.SIMPLE: (1, 4096),
            EditMode.ADVANCED: (1, 8192),
            EditMode.EXPERT: (1, 16384),
        },
    ),
    "pixel.dpi": NumericBounds(
        minimum=1,
        safe_min=72,
        default=72,
        safe_max=300,
        maximum=1200,
        integer=True,
        mode_limits={
            EditMode.SIMPLE: (72, 300),
            EditMode.ADVANCED: (36, 600),
            EditMode.EXPERT: (1, 1200),
        },
    ),
    "color.brightness": NumericBounds(
        minimum=-1.0,
        safe_min=-0.25,
        default=0.0,
        safe_max=0.25,
        maximum=1.0,
        mode_limits={
            EditMode.SIMPLE: (-0.25, 0.25),
            EditMode.ADVANCED: (-0.5, 0.5),
            EditMode.EXPERT: (-1.0, 1.0),
        },
    ),
    "color.contrast": NumericBounds(
        minimum=-1.0,
        safe_min=-0.3,
        default=0.0,
        safe_max=0.3,
        maximum=1.0,
        mode_limits={
            EditMode.SIMPLE: (-0.3, 0.3),
            EditMode.ADVANCED: (-0.6, 0.6),
            EditMode.EXPERT: (-1.0, 1.0),
        },
    ),
    "color.saturation": NumericBounds(
        minimum=-1.0,
        safe_min=-0.4,
        default=0.0,
        safe_max=0.4,
        maximum=1.0,
        mode_limits={
            EditMode.SIMPLE: (-0.4, 0.4),
            EditMode.ADVANCED: (-0.75, 0.75),
            EditMode.EXPERT: (-1.0, 1.0),
        },
    ),
    "color.temperature": NumericBounds(
        minimum=-1.0,
        safe_min=-0.4,
        default=0.0,
        safe_max=0.4,
        maximum=1.0,
        mode_limits={
            EditMode.SIMPLE: (-0.25, 0.25),
            EditMode.ADVANCED: (-0.5, 0.5),
            EditMode.EXPERT: (-1.0, 1.0),
        },
    ),
    "color.gamma": NumericBounds(
        minimum=0.1,
        safe_min=0.5,
        default=1.0,
        safe_max=2.0,
        maximum=5.0,
        mode_limits={
            EditMode.SIMPLE: (0.5, 2.0),
            EditMode.ADVANCED: (0.25, 3.0),
            EditMode.EXPERT: (0.1, 5.0),
        },
    ),
    "detail.sharpen_amount": NumericBounds(
        minimum=0.0,
        safe_min=0.0,
        default=0.0,
        safe_max=1.0,
        maximum=3.0,
        mode_limits={
            EditMode.SIMPLE: (0.0, 1.0),
            EditMode.ADVANCED: (0.0, 2.0),
            EditMode.EXPERT: (0.0, 3.0),
        },
    ),
    "cleanup.denoise": NumericBounds(
        minimum=0.0,
        safe_min=0.0,
        default=0.0,
        safe_max=0.5,
        maximum=1.0,
        mode_limits={
            EditMode.SIMPLE: (0.0, 0.5),
            EditMode.ADVANCED: (0.0, 0.8),
            EditMode.EXPERT: (0.0, 1.0),
        },
    ),
    "edges.antialias": NumericBounds(
        minimum=0.0,
        safe_min=0.0,
        default=0.0,
        safe_max=0.6,
        maximum=1.0,
        mode_limits={
            EditMode.SIMPLE: (0.0, 0.4),
            EditMode.ADVANCED: (0.0, 0.8),
            EditMode.EXPERT: (0.0, 1.0),
        },
    ),
    "alpha.alpha_threshold": NumericBounds(
        minimum=0,
        safe_min=0,
        default=0,
        safe_max=255,
        maximum=255,
        integer=True,
        mode_limits={
            EditMode.SIMPLE: (0, 255),
            EditMode.ADVANCED: (0, 255),
            EditMode.EXPERT: (0, 255),
        },
    ),
    "ai.upscale_factor": NumericBounds(
        minimum=1.0,
        safe_min=1.0,
        default=1.0,
        safe_max=2.0,
        maximum=8.0,
        mode_limits={
            EditMode.SIMPLE: (1.0, 2.0),
            EditMode.ADVANCED: (1.0, 4.0),
            EditMode.EXPERT: (1.0, 8.0),
        },
    ),
    "ai.deblur_strength": NumericBounds(
        minimum=0.0,
        safe_min=0.0,
        default=0.0,
        safe_max=0.5,
        maximum=1.0,
        mode_limits={
            EditMode.SIMPLE: (0.0, 0.3),
            EditMode.ADVANCED: (0.0, 0.7),
            EditMode.EXPERT: (0.0, 1.0),
        },
    ),
    "gif.frame_delay_ms": NumericBounds(
        minimum=1,
        safe_min=16,
        default=100,
        safe_max=500,
        maximum=5000,
        integer=True,
        mode_limits={
            EditMode.SIMPLE: (10, 500),
            EditMode.ADVANCED: (1, 2000),
            EditMode.EXPERT: (1, 5000),
        },
    ),
    "gif.palette_size": NumericBounds(
        minimum=2,
        safe_min=16,
        default=256,
        safe_max=256,
        maximum=256,
        integer=True,
        mode_limits={
            EditMode.SIMPLE: (16, 256),
            EditMode.ADVANCED: (2, 256),
            EditMode.EXPERT: (2, 256),
        },
    ),
    "export.quality": NumericBounds(
        minimum=1,
        safe_min=60,
        default=90,
        safe_max=100,
        maximum=100,
        integer=True,
        mode_limits={
            EditMode.SIMPLE: (50, 100),
            EditMode.ADVANCED: (1, 100),
            EditMode.EXPERT: (1, 100),
        },
    ),
    "export.compression_level": NumericBounds(
        minimum=0,
        safe_min=0,
        default=6,
        safe_max=9,
        maximum=9,
        integer=True,
        mode_limits={
            EditMode.SIMPLE: (0, 9),
            EditMode.ADVANCED: (0, 9),
            EditMode.EXPERT: (0, 9),
        },
    ),
}


def clamp_settings_for_mode(
    settings: SettingsState,
    *,
    mode: EditMode,
    bounds_map: dict[str, NumericBounds] | None = None,
) -> SettingsState:
    """Return a clamped copy of SettingsState for the selected mode."""

    clamped = deepcopy(settings)
    for path, bounds in (bounds_map or DEFAULT_SETTING_BOUNDS).items():
        current_value = _get_path(clamped, path)
        if current_value is None and path.rsplit(".", 1)[-1] in {"width", "height", "palette_limit"}:
            # Optional dimensions/palette limits may legitimately be None.
            continue
        _set_path(clamped, path, bounds.clamp(current_value, mode=mode))
    return clamped


def clamp_edit_state_for_mode(
    edit_state: EditState,
    *,
    mode: EditMode | None = None,
    bounds_map: dict[str, NumericBounds] | None = None,
) -> EditState:
    """Return a copy of EditState with settings clamped to the mode."""

    clamped = deepcopy(edit_state)
    effective_mode = mode or clamped.mode
    clamped.settings = clamp_settings_for_mode(
        clamped.settings,
        mode=effective_mode,
        bounds_map=bounds_map,
    )
    return clamped


def mode_meets_minimum(active_mode: EditMode, required_mode: EditMode) -> bool:
    """Check whether a mode satisfies a preset's minimum mode requirement."""

    return MODE_ORDER[active_mode] >= MODE_ORDER[required_mode]


def _get_path(root: SettingsState, dotted_path: str) -> Any:
    current: Any = root
    for part in dotted_path.split("."):
        current = getattr(current, part)
    return current


def _set_path(root: SettingsState, dotted_path: str, value: Any) -> None:
    current: Any = root
    parts = dotted_path.split(".")
    for part in parts[:-1]:
        current = getattr(current, part)
    setattr(current, parts[-1], value)

