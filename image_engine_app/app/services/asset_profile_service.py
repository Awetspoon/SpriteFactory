"""Imported-asset metadata, analysis, and recommendation helpers."""

from __future__ import annotations

from pathlib import Path

from image_engine_app.engine.analyze.gif_scan import (
    GifScanInput,
    estimate_gif_palette_stress_for_source,
)
from image_engine_app.engine.analyze.quality_scan import QualityScanInput, scan_quality
from image_engine_app.engine.analyze.recommend import RecommendationInput, build_recommendations
from image_engine_app.engine.classify.classifier import classify_asset
from image_engine_app.engine.models import AssetFormat, AssetRecord, SettingsState, SourceImageMetadata


class AssetProfileService:
    """Prepare imported assets without silently applying suggested edits."""

    def hydrate_imported_asset(self, asset: AssetRecord) -> None:
        """Create a source-faithful baseline, then calculate optional advice."""

        self.reset_new_asset_to_source_controls(asset)
        self.probe_image_metadata(asset)
        self.analyze_asset_profile(asset)

    @staticmethod
    def reset_new_asset_to_source_controls(asset: AssetRecord) -> None:
        """Start every new import from neutral, source-preserving controls."""

        asset.edit_state.settings = SettingsState()
        asset.edit_state.queued_heavy_jobs.clear()
        asset.detected_settings = None
        asset.derived_final_path = None

        original = getattr(asset, "dimensions_original", (0, 0))
        if isinstance(original, tuple) and len(original) == 2:
            width = int(original[0] or 0)
            height = int(original[1] or 0)
            if width > 0 and height > 0:
                asset.dimensions_current = (width, height)
                asset.dimensions_final = (width, height)

    def analyze_asset_profile(self, asset: AssetRecord) -> None:
        """Classify the source and build advice without mutating its controls."""

        classification = classify_asset(asset)
        merged_tags: list[str] = []
        for tag in [*classification.tags, *asset.classification_tags]:
            normalized = str(tag).strip()
            if normalized and normalized not in merged_tags:
                merged_tags.append(normalized)
        asset.classification_tags = merged_tags

        quality_input = self.build_quality_input_for_asset(asset)
        analysis = scan_quality(quality_input)
        if asset.format is AssetFormat.GIF and asset.capabilities.is_animated:
            analysis.gif_palette_stress = estimate_gif_palette_stress_for_source(
                source_path=asset.cache_path or asset.source_uri or asset.derived_final_path,
                fallback_scan=GifScanInput(
                    frame_count=8,
                    palette_size=asset.edit_state.settings.gif.palette_size,
                    duplicate_frame_ratio=0.1,
                    motion_change_ratio=0.5,
                ),
            )
        asset.analysis = analysis
        asset.recommendations = build_recommendations(
            RecommendationInput(
                file_format=asset.format,
                classification_tags=asset.classification_tags,
                analysis=asset.analysis,
                has_alpha=asset.capabilities.has_alpha,
                is_animated=asset.capabilities.is_animated,
            )
        )

    @staticmethod
    def build_quality_input_for_asset(asset: AssetRecord) -> QualityScanInput:
        width, height = asset.dimensions_current or asset.dimensions_original or (0, 0)
        tags = set(asset.classification_tags)
        edge_density = 0.55
        high_freq = 0.55
        noise_variance = 0.2
        blockiness = 0.1 if asset.format in {AssetFormat.JPG, AssetFormat.WEBP} else 0.03
        continuity = 0.75
        banding = 0.05

        if "pixel_art" in tags or "sprite_sheet" in tags:
            edge_density = 0.8
            high_freq = 0.7
            noise_variance = 0.08
            blockiness = 0.02
            continuity = 0.9
        elif "photo" in tags:
            edge_density = 0.45
            high_freq = 0.4
            noise_variance = 0.35 if asset.format is AssetFormat.JPG else 0.25
            blockiness = 0.3 if asset.format is AssetFormat.JPG else blockiness
            continuity = 0.6

        return QualityScanInput(
            width=max(1, width),
            height=max(1, height),
            file_format=asset.format,
            classification_tags=list(asset.classification_tags),
            edge_density=edge_density,
            high_frequency_ratio=high_freq,
            noise_variance=noise_variance,
            blockiness=blockiness,
            edge_continuity=continuity,
            banding_likelihood=banding,
        )

    @staticmethod
    def probe_image_metadata(asset: AssetRecord) -> None:
        """Copy measurable source facts into capabilities and neutral controls."""

        raw_path = asset.cache_path or asset.source_uri
        if not raw_path:
            return

        try:
            file_path = Path(raw_path)
        except Exception:
            return

        if not file_path.exists() or not file_path.is_file():
            return

        try:
            from PIL import Image  # type: ignore
        except Exception:
            return

        try:
            with Image.open(file_path) as image:
                source_info = dict(getattr(image, "info", {}) or {})
                frame_count = max(1, int(getattr(image, "n_frames", 1) or 1))
                is_animated = bool(getattr(image, "is_animated", False)) or frame_count > 1
                image.seek(0)
                image.load()
                width, height = image.size

                previous_original = tuple(
                    getattr(asset, "dimensions_original", (0, 0)) or (0, 0)
                )
                if width > 0 and height > 0:
                    measured = (int(width), int(height))
                    asset.dimensions_original = measured

                    current_dims = tuple(
                        getattr(asset, "dimensions_current", (0, 0)) or (0, 0)
                    )
                    if current_dims == (0, 0) or current_dims == previous_original:
                        asset.dimensions_current = measured

                    final_dims = tuple(
                        getattr(asset, "dimensions_final", (0, 0)) or (0, 0)
                    )
                    if final_dims == (0, 0) or final_dims == previous_original:
                        asset.dimensions_final = measured

                bands = set(getattr(image, "getbands", lambda: ())())
                mode = str(getattr(image, "mode", ""))
                asset.capabilities.has_alpha = bool(
                    ("A" in bands)
                    or (mode in {"RGBA", "LA", "PA"})
                    or ("transparency" in source_info)
                )
                asset.capabilities.is_animated = bool(is_animated)

                source_dpi = AssetProfileService._normalize_source_dpi(
                    source_info.get("dpi")
                )
                source_loop_count: int | None = None
                if asset.format is AssetFormat.GIF and "loop" in source_info:
                    source_loop_count = AssetProfileService._normalize_source_loop_count(
                        source_info.get("loop")
                    )
                asset.source_metadata = SourceImageMetadata(
                    color_mode=mode,
                    dpi=source_dpi,
                    frame_count=frame_count,
                    loop_count=source_loop_count,
                )
                if source_dpi is not None:
                    asset.edit_state.settings.pixel.dpi = source_dpi

                if asset.format is AssetFormat.GIF:
                    loop_present = "loop" in source_info
                    gif = asset.edit_state.settings.gif
                    gif.frame_delay_ms = 0
                    gif.loop = loop_present
                    gif.loop_count = source_loop_count if loop_present else None
        except Exception:
            return

    @staticmethod
    def _normalize_source_dpi(raw_value: object) -> int | None:
        if isinstance(raw_value, (tuple, list)):
            raw_value = raw_value[0] if raw_value else None
        try:
            dpi = int(round(float(raw_value)))
        except (TypeError, ValueError, OverflowError):
            return None
        return dpi if 1 <= dpi <= 2400 else None

    @staticmethod
    def _normalize_source_loop_count(raw_value: object) -> int:
        try:
            return max(0, int(raw_value))
        except (TypeError, ValueError, OverflowError):
            return 0
