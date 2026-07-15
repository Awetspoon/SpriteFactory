"""Shared output-size choices backed by the existing pixel controls."""

from __future__ import annotations

from dataclasses import dataclass

from image_engine_app.engine.models import PixelSettings


@dataclass(frozen=True)
class OutputSizeChoice:
    key: str
    label: str
    resize_percent: float = 100.0
    target_height: int | None = None


ORIGINAL_SIZE = "original"
CUSTOM_SIZE = "custom"

OUTPUT_SIZE_CHOICES: tuple[OutputSizeChoice, ...] = (
    OutputSizeChoice(ORIGINAL_SIZE, "Original dimensions"),
    OutputSizeChoice("scale_2x", "Scale 2x", resize_percent=200.0),
    OutputSizeChoice("scale_3x", "Scale 3x", resize_percent=300.0),
    OutputSizeChoice("scale_4x", "Scale 4x", resize_percent=400.0),
    OutputSizeChoice("scale_8x", "Scale 8x", resize_percent=800.0),
    OutputSizeChoice("height_240", "Height 240p", target_height=240),
    OutputSizeChoice("height_360", "Height 360p", target_height=360),
    OutputSizeChoice("height_480", "Height 480p", target_height=480),
    OutputSizeChoice("height_720", "Height 720p (HD)", target_height=720),
    OutputSizeChoice("height_1080", "Height 1080p (Full HD)", target_height=1080),
    OutputSizeChoice("height_1440", "Height 1440p (QHD)", target_height=1440),
    OutputSizeChoice("height_2160", "Height 2160p (4K)", target_height=2160),
)

_CHOICES_BY_KEY = {choice.key: choice for choice in OUTPUT_SIZE_CHOICES}


def apply_output_size_choice(pixel: PixelSettings, key: str) -> bool:
    """Apply one convenience choice to the real resize/width/height settings."""

    choice = _CHOICES_BY_KEY.get(str(key or ""))
    if choice is None:
        return False

    before = (float(pixel.resize_percent), pixel.width, pixel.height)
    pixel.resize_percent = float(choice.resize_percent)
    pixel.width = None
    pixel.height = choice.target_height
    return before != (float(pixel.resize_percent), pixel.width, pixel.height)


def output_size_choice_for(pixel: PixelSettings) -> str:
    """Return the matching chooser key, or custom for manually entered dimensions."""

    resize_percent = float(pixel.resize_percent or 100.0)
    width = pixel.width
    height = pixel.height

    for choice in OUTPUT_SIZE_CHOICES:
        if choice.target_height is None:
            if width is None and height is None and abs(resize_percent - choice.resize_percent) < 0.001:
                return choice.key
            continue

        if (
            width is None
            and height == choice.target_height
            and abs(resize_percent - choice.resize_percent) < 0.001
        ):
            return choice.key

    return CUSTOM_SIZE
