"""Imported-asset hydration and analysis helpers."""

from __future__ import annotations

from pathlib import Path

from image_engine_app.engine.analyze.gif_scan import GifScanInput, estimate_gif_palette_stress_for_source
from image_engine_app.engine.analyze.quality_scan import QualityScanInput, scan_quality
from image_engine_app.engine.analyze.recommend import RecommendationInput, build_recommendations
from image_engine_app.engine.classify.classifier import classify_asset
from image_engine_app.engine.models import AssetFormat, AssetRecord, ExportFormat, ExportProfile, ScaleMethod, SourceType
from image_engine_app.engine.process.bounds import clamp_edit_state_for_mode


class AssetProfileService:
    """Prepares imported assets with metadata, analysis, and default controls."""

    def hydrate_imported_asset(self, asset: AssetRecord, *, apply_baseline_preset) -> None:
        self.probe_image_metadata(asset)
        self.reset_new_asset_to_default_size(asset)
        self.analyze_asset_profile(asset)
        apply_baseline_preset(asset)
        self.apply_analysis_inferred_control_defaults(asset)
        self.apply_recommended_export_defaults(asset)

    def hydrate_local_assets(self, assets: list[AssetRecord], *, hydrate_asset) -> None:
        for asset in assets:
            if asset.cache_path is None and asset.source_type in {SourceType.FILE, SourceType.FOLDER_ITEM}:
                asset.cache_path = asset.source_uri
            hydrate_asset(asset)

    @staticmethod
    def reset_new_asset_to_default_size(asset: AssetRecord) -> None:
        settings = getattr(getattr(asset, "edit_state", None), "settings", None)
        pixel = getattr(settings, "pixel", None)
        if pixel is not None:
            pixel.resize_percent = 100.0
            pixel.width = None
            pixel.height = None

        asset.derived_current_path = None
        asset.derived_final_path = None

        original = getattr(asset, "dimensions_original", (0, 0))
        if isinstance(original, tuple) and len(original) == 2:
            ow = int(original[0] or 0)
            oh = int(original[1] or 0)
            if ow > 0 and oh > 0:
                asset.dimensions_current = (ow, oh)
                asset.dimensions_final = (ow, oh)

    def analyze_asset_profile(self, asset: AssetRecord) -> None:
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
    def clamp01(value: object, *, default: float = 0.0) -> float:
        try:
            parsed = float(value)
        except Exception:
            parsed = default
        return max(0.0, min(1.0, parsed))

    def apply_analysis_inferred_control_defaults(self, asset: AssetRecord) -> None:
        analysis = getattr(asset, "analysis", None)
        settings = getattr(getattr(asset, "edit_state", None), "settings", None)
        if analysis is None or settings is None:
            return

        tags = {str(tag).strip().lower() for tag in (asset.classification_tags or []) if str(tag).strip()}
        pixel_like = ("pixel_art" in tags) or ("sprite_sheet" in tags)
        photo_like = "photo" in tags

        noise = self.clamp01(getattr(analysis, "noise_score", 0.0))
        compression = self.clamp01(getattr(analysis, "compression_score", 0.0))
        blur = self.clamp01(getattr(analysis, "blur_score", 0.0))
        edge_weakness = self.clamp01(1.0 - self.clamp01(getattr(analysis, "edge_integrity_score", 1.0)))
        resolution_need = self.clamp01(getattr(analysis, "resolution_need_score", 0.0))

        noise_strength = self.clamp01((noise - 0.08) / 0.92)
        compression_strength = self.clamp01((compression - 0.03) / 0.97)
        blur_strength = self.clamp01((blur - 0.12) / 0.88)

        settings.cleanup.denoise = max(settings.cleanup.denoise, round(0.04 + (0.46 * noise_strength), 2))
        settings.cleanup.artifact_removal = max(
            settings.cleanup.artifact_removal,
            round(0.04 + (0.62 * compression_strength), 2),
        )
        settings.cleanup.banding_removal = max(
            settings.cleanup.banding_removal,
            round(0.02 + (0.42 * compression_strength), 2),
        )
        settings.cleanup.halo_cleanup = max(
            settings.cleanup.halo_cleanup,
            round(0.02 + (0.28 * ((compression_strength + edge_weakness) / 2.0)), 2),
        )

        settings.detail.sharpen_amount = max(settings.detail.sharpen_amount, round(0.05 + (0.50 * blur_strength), 2))
        settings.detail.clarity = max(settings.detail.clarity, round(0.03 + (0.38 * blur_strength), 2))
        settings.detail.sharpen_threshold = max(
            settings.detail.sharpen_threshold,
            round(0.03 + (0.24 * noise_strength), 2),
        )

        if pixel_like:
            settings.pixel.scale_method = ScaleMethod.NEAREST
            settings.pixel.pixel_snap = True
            settings.detail.texture = max(settings.detail.texture, 0.12)
            settings.ai.deblur_strength = max(settings.ai.deblur_strength, round(0.04 + (0.24 * blur_strength), 2))
        elif photo_like:
            settings.pixel.scale_method = ScaleMethod.LANCZOS
            settings.pixel.pixel_snap = False
            settings.detail.texture = max(settings.detail.texture, round(0.06 + (0.30 * blur_strength), 2))
            settings.ai.deblur_strength = max(settings.ai.deblur_strength, round(0.16 + (0.64 * blur_strength), 2))
            settings.ai.detail_reconstruct = max(
                settings.ai.detail_reconstruct,
                round(0.08 + (0.48 * blur_strength), 2),
            )
        else:
            settings.ai.deblur_strength = max(settings.ai.deblur_strength, round(0.08 + (0.42 * blur_strength), 2))

        if (not pixel_like) and edge_weakness > 0.2:
            settings.edges.edge_refine = max(settings.edges.edge_refine, round(0.12 + (0.60 * edge_weakness), 2))
            settings.edges.antialias = max(settings.edges.antialias, round(0.08 + (0.42 * edge_weakness), 2))

        if resolution_need >= 0.72:
            inferred_upscale = min(4.0, round(1.0 + (1.5 * resolution_need), 2))
            settings.ai.upscale_factor = max(settings.ai.upscale_factor, inferred_upscale)

        if asset.format is AssetFormat.GIF and asset.capabilities.is_animated:
            stress = self.clamp01(getattr(analysis, "gif_palette_stress", 0.0))
            settings.gif.dither_strength = max(settings.gif.dither_strength, round(0.05 + (0.5 * stress), 2))
            if stress >= 0.6:
                settings.gif.palette_size = min(int(settings.gif.palette_size), 128)

        asset.edit_state = clamp_edit_state_for_mode(asset.edit_state, mode=asset.edit_state.mode)

    @staticmethod
    def apply_recommended_export_defaults(asset: AssetRecord) -> None:
        recs = getattr(asset, "recommendations", None)
        if recs is None:
            return

        profile_value = getattr(recs, "suggested_export_profile", None)
        if isinstance(profile_value, str) and profile_value:
            try:
                asset.edit_state.settings.export.export_profile = ExportProfile(profile_value)
            except Exception:
                pass

        format_value = getattr(recs, "suggested_export_format", None)
        if isinstance(format_value, str) and format_value:
            try:
                asset.edit_state.settings.export.format = ExportFormat(format_value)
            except Exception:
                pass

    @staticmethod
    def probe_image_metadata(asset: AssetRecord) -> None:
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
            with Image.open(file_path) as im:
                im.load()
                w, h = im.size

                previous_original = tuple(getattr(asset, "dimensions_original", (0, 0)) or (0, 0))
                if w > 0 and h > 0:
                    measured = (int(w), int(h))
                    asset.dimensions_original = measured

                    current_dims = tuple(getattr(asset, "dimensions_current", (0, 0)) or (0, 0))
                    if current_dims == (0, 0) or current_dims == previous_original:
                        asset.dimensions_current = measured

                    final_dims = tuple(getattr(asset, "dimensions_final", (0, 0)) or (0, 0))
                    if final_dims == (0, 0) or final_dims == previous_original:
                        asset.dimensions_final = measured
                bands = set(getattr(im, "getbands", lambda: ())())
                mode = str(getattr(im, "mode", ""))
                has_alpha = ("A" in bands) or (mode in {"RGBA", "LA", "PA"})
                asset.capabilities.has_alpha = bool(has_alpha)

                n_frames = int(getattr(im, "n_frames", 1) or 1)
                is_animated = bool(getattr(im, "is_animated", False)) or n_frames > 1
                asset.capabilities.is_animated = bool(is_animated)
        except Exception:
            return

    @staticmethod
    def extension_for_format(fmt_value: str) -> str:
        mapping = {
            "jpg": ".jpg",
            "png": ".png",
            "webp": ".webp",
            "gif": ".gif",
            "ico": ".ico",
            "tiff": ".tiff",
            "bmp": ".bmp",
        }
        return mapping.get(fmt_value, ".bin")

    @staticmethod
    def asset_format_from_extension(ext: str) -> AssetFormat:
        cleaned = str(ext or "").strip().lower().lstrip(".")
        return AssetProfileService.asset_format_from_detected(cleaned)

    @staticmethod
    def asset_format_from_detected(detected_format: str) -> AssetFormat:
        mapping = {
            "jpeg": AssetFormat.JPG,
            "jpg": AssetFormat.JPG,
            "png": AssetFormat.PNG,
            "webp": AssetFormat.WEBP,
            "gif": AssetFormat.GIF,
            "bmp": AssetFormat.BMP,
            "ico": AssetFormat.ICO,
            "tiff": AssetFormat.TIFF,
        }
        return mapping.get(str(detected_format).lower(), AssetFormat.UNKNOWN)
