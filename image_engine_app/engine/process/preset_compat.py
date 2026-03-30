"""Preset scope labels and compatibility helpers."""

from __future__ import annotations

from dataclasses import dataclass

from image_engine_app.engine.classify.classifier import classify_asset
from image_engine_app.engine.models import AssetFormat, AssetRecord, PresetModel


FORMAT_LABELS = {
    "*": "Any format",
    "png": "PNG",
    "jpg": "JPG",
    "jpeg": "JPG",
    "webp": "WEBP",
    "gif": "GIF",
    "ico": "ICO",
    "bmp": "BMP",
    "tiff": "TIFF",
    "tif": "TIFF",
    "unknown": "Unknown",
}

TAG_LABELS = {
    "*": "Any asset",
    "pixel_art": "Sprite",
    "sprite_sheet": "Sheet",
    "photo": "Photo",
    "artwork": "Artwork",
    "animation": "Anim",
    "icon": "Icon",
    "ui": "UI",
    "logo": "Logo",
    "texture": "Texture",
    "transparent": "Alpha",
}


@dataclass(frozen=True)
class PresetCatalogEntry:
    name: str
    label: str
    scope_text: str = "Any asset"
    compatible: bool = True
    reason: str = ""


def preset_catalog_entry(preset: PresetModel, *, asset: AssetRecord | None = None) -> PresetCatalogEntry:
    compatible, reason = preset_matches_asset(preset, asset)
    scope_text = describe_preset_scope(preset)
    label = preset.name if scope_text == "Any asset" else f"{preset.name} | {scope_text}"
    return PresetCatalogEntry(
        name=preset.name,
        label=label,
        scope_text=scope_text,
        compatible=compatible,
        reason=reason,
    )


def describe_preset_scope(preset: PresetModel) -> str:
    format_tokens = _normalize_scope_tokens(getattr(preset, "applies_to_formats", None), kind="format")
    tag_tokens = _normalize_scope_tokens(getattr(preset, "applies_to_tags", None), kind="tag")

    if "*" in format_tokens and "*" in tag_tokens:
        return "Any asset"

    parts: list[str] = []
    tag_labels = [_scope_label(token, kind="tag") for token in tag_tokens if token != "*"]
    format_labels = [_scope_label(token, kind="format") for token in format_tokens if token != "*"]

    if tag_labels:
        parts.append(_compact_scope_labels(tag_labels, limit=2))
    if format_labels:
        parts.append(_compact_scope_labels(format_labels, limit=3))

    return " | ".join(parts) if parts else "Any asset"


def describe_asset_scope(asset: AssetRecord | None) -> str:
    if asset is None:
        return "No asset selected"

    format_tokens, tag_tokens = _asset_scope_tokens(asset)
    labels: list[str] = []
    labels.extend(_scope_label(token, kind="tag") for token in _ordered_tag_tokens(tag_tokens))
    labels.extend(_scope_label(token, kind="format") for token in _ordered_format_tokens(format_tokens))

    if not labels:
        return "Unknown asset"
    return _compact_scope_labels(labels, limit=4)


def preset_matches_asset(preset: PresetModel, asset: AssetRecord | None) -> tuple[bool, str]:
    if asset is None:
        return True, ""

    preset_formats = set(_normalize_scope_tokens(getattr(preset, "applies_to_formats", None), kind="format"))
    preset_tags = set(_normalize_scope_tokens(getattr(preset, "applies_to_tags", None), kind="tag"))
    asset_formats, asset_tags = _asset_scope_tokens(asset)

    format_ok = ("*" in preset_formats) or bool(asset_formats & preset_formats)
    tag_ok = ("*" in preset_tags) or bool(asset_tags & preset_tags)

    if "animation" in asset_tags:
        animation_safe = "animation" in preset_tags
        if not animation_safe:
            return (
                False,
                f"Preset '{preset.name}' is not marked animation-safe for animated assets. "
                f"Use an animation preset like 'GIF Safe Cleanup' instead.",
            )

    if format_ok and tag_ok:
        return True, ""

    asset_scope = describe_asset_scope(asset)
    preset_scope = describe_preset_scope(preset)
    if not format_ok and not tag_ok:
        return False, f"Preset '{preset.name}' fits {preset_scope}, but the active asset looks like {asset_scope}."
    if not format_ok:
        return False, f"Preset '{preset.name}' does not target this format. Active asset: {asset_scope}."
    return False, f"Preset '{preset.name}' is tuned for {preset_scope}, not the current asset type ({asset_scope})."


def _asset_scope_tokens(asset: AssetRecord) -> tuple[set[str], set[str]]:
    format_tokens: set[str] = set()
    tags: set[str] = {
        str(tag).strip().lower()
        for tag in (getattr(asset, "classification_tags", None) or [])
        if str(tag).strip()
    }

    if not tags:
        try:
            tags.update(classify_asset(asset).tags)
        except Exception:
            pass

    fmt_value = str(getattr(getattr(asset, "format", None), "value", "") or "").strip().lower()
    if fmt_value:
        if fmt_value == "jpeg":
            fmt_value = "jpg"
        if fmt_value == "tif":
            fmt_value = "tiff"
        format_tokens.add(fmt_value)

    caps = getattr(asset, "capabilities", None)
    if bool(getattr(caps, "has_alpha", False)):
        tags.add("transparent")
    if bool(getattr(caps, "is_animated", False)) or fmt_value == AssetFormat.GIF.value:
        tags.add("animation")
    if bool(getattr(caps, "is_sheet", False)):
        tags.add("sprite_sheet")
    if bool(getattr(caps, "is_ico_bundle", False)) or fmt_value == AssetFormat.ICO.value:
        tags.add("icon")

    return format_tokens, tags


def _normalize_scope_tokens(raw_values: object, *, kind: str) -> list[str]:
    values = raw_values if isinstance(raw_values, list) else ["*"]
    tokens: list[str] = []
    seen: set[str] = set()
    for raw in values:
        token = str(raw or "").strip().lower()
        if not token:
            continue
        if kind == "format" and token == "jpeg":
            token = "jpg"
        if kind == "format" and token == "tif":
            token = "tiff"
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens or ["*"]


def _scope_label(token: str, *, kind: str) -> str:
    mapping = FORMAT_LABELS if kind == "format" else TAG_LABELS
    return mapping.get(token, token.replace("_", " ").title())


def _compact_scope_labels(labels: list[str], *, limit: int) -> str:
    if len(labels) <= limit:
        return " / ".join(labels)
    visible = " / ".join(labels[:limit])
    return f"{visible} +{len(labels) - limit}"


def _ordered_tag_tokens(tags: set[str]) -> list[str]:
    order = ("animation", "pixel_art", "sprite_sheet", "photo", "artwork", "icon", "ui", "logo", "texture", "transparent")
    return [token for token in order if token in tags]


def _ordered_format_tokens(formats: set[str]) -> list[str]:
    order = ("png", "jpg", "webp", "gif", "ico", "bmp", "tiff", "unknown")
    return [token for token in order if token in formats]
