"""Rules-first content classification (Prompt 7)."""

from __future__ import annotations

from dataclasses import dataclass, field

from engine.common.math_utils import clamp01
from pathlib import Path

from engine.models import AssetFormat, AssetRecord


@dataclass(frozen=True)
class ClassificationRuleMatch:
    """A single matched rule used to explain classification output."""

    tag: str
    confidence: float
    reason: str


@dataclass
class ClassificationResult:
    """Rules-first classification output with ordered tags and rule explanations."""

    tags: list[str] = field(default_factory=list)
    matches: list[ClassificationRuleMatch] = field(default_factory=list)

    def add(self, tag: str, confidence: float, reason: str) -> None:
        if tag in self.tags:
            return
        self.tags.append(tag)
        self.matches.append(
            ClassificationRuleMatch(
                tag=tag,
                confidence=clamp01(confidence),
                reason=reason,
            )
        )


@dataclass
class ClassificationInput:
    """Input features for rules-first classification."""

    file_name: str = ""
    file_format: AssetFormat = AssetFormat.UNKNOWN
    dimensions: tuple[int, int] | None = None
    has_alpha: bool = False
    is_animated: bool = False
    is_sheet: bool = False
    is_ico_bundle: bool = False
    color_count_estimate: int | None = None
    frame_count: int | None = None


def classify_content(features: ClassificationInput) -> ClassificationResult:
    """Classify image content using deterministic rules and metadata heuristics."""

    result = ClassificationResult()
    name = features.file_name.lower()
    width, height = features.dimensions or (0, 0)
    max_dim = max(width, height)
    min_dim = min(width, height) if width and height else 0
    area = width * height if width and height else 0
    colors = features.color_count_estimate

    if features.is_animated or (features.frame_count is not None and features.frame_count > 1):
        result.add("animation", 0.96, "Animated flag or multiple frames detected.")

    if features.is_ico_bundle or features.file_format is AssetFormat.ICO:
        conf = 0.98 if features.is_ico_bundle else 0.88
        result.add("icon", conf, "ICO format or icon bundle signature detected.")

    if _contains_any(name, ("favicon", "appicon", "icon_", "_icon")) and "icon" not in result.tags:
        result.add("icon", 0.82, "Filename pattern suggests an icon asset.")

    if features.is_sheet:
        result.add("sprite_sheet", 0.95, "Sheet heuristic flagged atlas/grid-like content.")
    elif _contains_any(name, ("spritesheet", "sprite_sheet", "sheet", "atlas")):
        result.add("sprite_sheet", 0.83, "Filename pattern suggests sprite sheet/atlas.")

    if _contains_any(name, ("logo", "brand", "wordmark")):
        result.add("logo", 0.9, "Filename pattern suggests logo/branding asset.")

    if _contains_any(name, ("ui", "hud", "button", "panel", "menu")):
        result.add("ui", 0.82, "Filename pattern suggests interface asset.")

    if _looks_like_pixel_art(features, max_dim=max_dim, min_dim=min_dim, area=area, colors=colors, name=name):
        reason = (
            "Low color-count + sprite/pixel indicators."
            if colors is not None and colors <= 64
            else "Pixel-art indicators from format/dimensions/name."
        )
        result.add("pixel_art", 0.89, reason)

    if _looks_like_texture(features, width=width, height=height, name=name):
        result.add("texture", 0.72, "Power-of-two or texture filename heuristic matched.")

    if _looks_like_photo(features, max_dim=max_dim, area=area, colors=colors):
        reason = "Large raster image with lossy/photo-like metadata."
        if colors is not None and colors >= 4096:
            reason = "High estimated color count suggests photo content."
        result.add("photo", 0.84, reason)

    if "photo" not in result.tags and "pixel_art" not in result.tags:
        result.add("artwork", 0.55, "Default fallback for non-photo/non-pixel content.")
    elif "photo" in result.tags and "artwork" not in result.tags and _contains_any(name, ("art", "illustration")):
        result.add("artwork", 0.61, "Filename suggests illustrative artwork.")

    # Optional ML classifier hook can refine/override confidences in a future extension.
    return result


def classify_asset(
    asset: AssetRecord,
    *,
    color_count_estimate: int | None = None,
    frame_count: int | None = None,
) -> ClassificationResult:
    """Classify an AssetRecord using current metadata and optional lightweight estimates."""

    file_name = asset.original_name or Path(asset.source_uri).name
    return classify_content(
        ClassificationInput(
            file_name=file_name,
            file_format=asset.format,
            dimensions=asset.dimensions_current or asset.dimensions_original,
            has_alpha=asset.capabilities.has_alpha,
            is_animated=asset.capabilities.is_animated,
            is_sheet=asset.capabilities.is_sheet,
            is_ico_bundle=asset.capabilities.is_ico_bundle,
            color_count_estimate=color_count_estimate,
            frame_count=frame_count,
        )
    )


def _looks_like_pixel_art(
    features: ClassificationInput,
    *,
    max_dim: int,
    min_dim: int,
    area: int,
    colors: int | None,
    name: str,
) -> bool:
    if _contains_any(name, ("pixel", "sprite", "tileset")) and max_dim <= 2048:
        return True

    if colors is None:
        return False

    low_color = colors <= 64
    modest_canvas = max_dim <= 1024 and area <= 1024 * 1024
    raster_sprite_formats = features.file_format in {AssetFormat.PNG, AssetFormat.GIF, AssetFormat.WEBP}
    squareish = min_dim > 0 and (max_dim / max(min_dim, 1)) <= 8.0
    return low_color and modest_canvas and raster_sprite_formats and squareish


def _looks_like_texture(
    features: ClassificationInput,
    *,
    width: int,
    height: int,
    name: str,
) -> bool:
    if _contains_any(name, ("texture", "albedo", "normal", "roughness")):
        return True
    if width < 128 or height < 128:
        return False
    if width != height:
        return False
    return _is_power_of_two(width)


def _looks_like_photo(
    features: ClassificationInput,
    *,
    max_dim: int,
    area: int,
    colors: int | None,
) -> bool:
    if features.file_format is AssetFormat.JPG and max_dim >= 512 and not features.has_alpha:
        return True
    if colors is not None and colors >= 4096 and area >= 256 * 256 and not features.is_animated:
        return True
    return False


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def _is_power_of_two(value: int) -> bool:
    return value > 0 and (value & (value - 1)) == 0





