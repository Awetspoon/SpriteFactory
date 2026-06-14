"""Tests for extracted imported-asset profile helpers."""

from __future__ import annotations

import unittest

from image_engine_app.app.services import AssetProfileService
from image_engine_app.engine.models import (
    AnalysisSummary,
    ApplyTarget,
    AssetFormat,
    AssetRecord,
    Capabilities,
    EditMode,
    ExportProfile,
    ScaleMethod,
    SourceType,
)


def _asset(*, mode: EditMode = EditMode.ADVANCED) -> AssetRecord:
    asset = AssetRecord(
        id="asset-profile-001",
        source_type=SourceType.FILE,
        source_uri="C:/demo/sprite.png",
        original_name="sprite.png",
        format=AssetFormat.PNG,
        capabilities=Capabilities(has_alpha=True, is_animated=False, is_sheet=False, is_ico_bundle=False),
        dimensions_original=(64, 64),
        dimensions_current=(128, 128),
        dimensions_final=(256, 256),
    )
    asset.edit_state.mode = mode
    asset.edit_state.apply_target = ApplyTarget.BOTH
    asset.edit_state.sync_current_final = True
    asset.edit_state.settings.export.export_profile = ExportProfile.APP_ASSET
    return asset


class AssetProfileServiceTests(unittest.TestCase):
    def test_asset_format_helpers_cover_known_formats(self) -> None:
        service = AssetProfileService()
        self.assertEqual(service.asset_format_from_extension(".png"), AssetFormat.PNG)
        self.assertEqual(service.asset_format_from_detected("jpeg"), AssetFormat.JPG)
        self.assertEqual(service.extension_for_format("gif"), ".gif")

    def test_analysis_inference_prefills_pixel_art_defaults(self) -> None:
        service = AssetProfileService()
        asset = _asset(mode=EditMode.ADVANCED)
        asset.classification_tags = ["pixel_art"]
        asset.analysis = AnalysisSummary(
            blur_score=0.76,
            noise_score=0.62,
            compression_score=0.58,
            edge_integrity_score=0.48,
            resolution_need_score=0.95,
            gif_palette_stress=None,
            warnings=[],
        )

        service.apply_analysis_inferred_control_defaults(asset)

        self.assertEqual(asset.edit_state.settings.pixel.scale_method, ScaleMethod.NEAREST)
        self.assertTrue(asset.edit_state.settings.pixel.pixel_snap)
        self.assertGreater(asset.edit_state.settings.cleanup.denoise, 0.0)
        self.assertLessEqual(asset.edit_state.settings.ai.upscale_factor, 4.0)
