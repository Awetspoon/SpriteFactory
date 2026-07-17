"""Transparency cleanup and edge-connected background removal."""

from __future__ import annotations

from collections import deque

from image_engine_app.engine.models import BackgroundRemovalMode, SettingsState, normalize_background_removal_mode
from image_engine_app.engine.process.pillow_runtime import require_pillow


def _background_strength(pixel: tuple[int, int, int], mode: BackgroundRemovalMode) -> int:
    """Return 0..255 confidence that a pixel belongs to a removable background."""

    red, green, blue = (int(pixel[0]), int(pixel[1]), int(pixel[2]))
    minimum = min(red, green, blue)
    maximum = max(red, green, blue)
    spread = maximum - minimum

    if mode is BackgroundRemovalMode.WHITE:
        if minimum < 205 or spread > 46:
            return 0
        if minimum >= 248 and spread <= 18:
            return 255
        brightness = max(0.0, min(1.0, (minimum - 205) / 43.0))
        neutrality = max(0.0, min(1.0, 1.0 - (spread / 46.0)))
        return int(round(255.0 * brightness * neutrality))

    if mode is BackgroundRemovalMode.BLACK:
        if maximum > 72 or spread > 46:
            return 0
        if maximum <= 14 and spread <= 18:
            return 255
        darkness = max(0.0, min(1.0, (72 - maximum) / 58.0))
        neutrality = max(0.0, min(1.0, 1.0 - (spread / 46.0)))
        return int(round(255.0 * darkness * neutrality))

    return 0


def build_background_cutout_keep_mask(rgb_image, mode: BackgroundRemovalMode):
    """Flood-fill removable white/black pixels from the image edges."""

    Image, _, _, _ = require_pillow()
    if rgb_image.mode != "RGB":
        rgb_image = rgb_image.convert("RGB")

    width, height = rgb_image.size
    if width <= 0 or height <= 0:
        return Image.new("L", (max(1, width), max(1, height)), 255)

    keep_mask = Image.new("L", (width, height), 255)
    keep_pixels = keep_mask.load()
    rgb_pixels = rgb_image.load()
    visited = bytearray(width * height)
    pending: deque[tuple[int, int]] = deque()

    def try_seed(x: int, y: int) -> None:
        index = y * width + x
        if visited[index]:
            return
        strength = _background_strength(rgb_pixels[x, y], mode)
        if strength <= 0:
            return
        visited[index] = 1
        keep_pixels[x, y] = 255 - strength
        pending.append((x, y))

    for x in range(width):
        try_seed(x, 0)
        if height > 1:
            try_seed(x, height - 1)
    for y in range(1, max(1, height - 1)):
        try_seed(0, y)
        if width > 1:
            try_seed(width - 1, y)

    neighbors = (
        (-1, -1),
        (0, -1),
        (1, -1),
        (-1, 0),
        (1, 0),
        (-1, 1),
        (0, 1),
        (1, 1),
    )
    while pending:
        x, y = pending.popleft()
        for delta_x, delta_y in neighbors:
            neighbor_x = x + delta_x
            neighbor_y = y + delta_y
            if neighbor_x < 0 or neighbor_y < 0 or neighbor_x >= width or neighbor_y >= height:
                continue
            index = neighbor_y * width + neighbor_x
            if visited[index]:
                continue
            strength = _background_strength(rgb_pixels[neighbor_x, neighbor_y], mode)
            if strength <= 0:
                continue
            visited[index] = 1
            keep_pixels[neighbor_x, neighbor_y] = min(
                keep_pixels[neighbor_x, neighbor_y],
                255 - strength,
            )
            pending.append((neighbor_x, neighbor_y))

    return keep_mask


def apply_transparency(image, settings: SettingsState):
    """Apply background removal and alpha cleanup to one in-memory frame."""

    Image, _, ImageFilter, _ = require_pillow()
    from PIL import ImageChops  # type: ignore

    alpha_settings = settings.alpha
    background_mode = normalize_background_removal_mode(
        getattr(alpha_settings, "background_removal_mode", None),
        remove_white_bg=bool(getattr(alpha_settings, "remove_white_bg", False)),
    )

    if image.mode != "RGBA":
        if background_mode is BackgroundRemovalMode.OFF:
            return image
        image = image.convert("RGBA")

    red, green, blue, alpha = image.split()
    if background_mode is not BackgroundRemovalMode.OFF:
        keep_mask = build_background_cutout_keep_mask(
            Image.merge("RGB", (red, green, blue)),
            background_mode,
        )
        alpha = ImageChops.multiply(alpha, keep_mask)

    smooth = max(0.0, float(getattr(alpha_settings, "alpha_smooth", 0.0) or 0.0))
    if smooth > 1e-6:
        alpha = alpha.filter(ImageFilter.GaussianBlur(radius=min(2.5, smooth * 2.5)))

    matte = max(0.0, float(getattr(alpha_settings, "matte_fix", 0.0) or 0.0))
    if matte > 1e-6:
        alpha = alpha.filter(ImageFilter.MedianFilter(size=3))
        if matte > 0.2:
            alpha = alpha.filter(ImageFilter.GaussianBlur(radius=min(1.5, matte * 1.5)))

    threshold = int(getattr(alpha_settings, "alpha_threshold", 0) or 0)
    if threshold > 0:
        alpha = alpha.point(lambda value: 255 if value >= threshold else 0)

    return Image.merge("RGBA", (red, green, blue, alpha))
