"""Tests for deterministic analysis heuristics and recommendation outputs."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.analyze.gif_scan import GifScanInput, estimate_gif_palette_stress_stub  # noqa: E402
from engine.analyze.quality_scan import QualityScanInput, scan_quality  # noqa: E402
from engine.analyze.recommend import RecommendationInput, build_recommendations  # noqa: E402
from engine.models import AnalysisSummary, AssetFormat  # noqa: E402


class QualityScanTests(unittest.TestCase):
    def test_quality_scan_is_deterministic_and_in_range(self) -> None:
        stats = QualityScanInput(
            width=320,
            height=240,
            file_format=AssetFormat.JPG,
            classification_tags=["photo"],
            edge_density=0.35,
            high_frequency_ratio=0.25,
            noise_variance=0.55,
            blockiness=0.6,
            edge_continuity=0.4,
            banding_likelihood=0.5,
        )
        summary = scan_quality(stats)

        self.assertIsInstance(summary, AnalysisSummary)
        self.assertAlmostEqual(summary.blur_score, 0.715, places=3)
        self.assertAlmostEqual(summary.noise_score, 0.5275, places=4)
        self.assertAlmostEqual(summary.compression_score, 0.57, places=3)
        self.assertAlmostEqual(summary.edge_integrity_score, 0.2075, places=4)
        self.assertAlmostEqual(summary.resolution_need_score, 0.9166666667, places=6)
        self.assertIsNone(summary.gif_palette_stress)
        self.assertTrue(all(0.0 <= value <= 1.0 for value in [
            summary.blur_score,
            summary.noise_score,
            summary.compression_score,
            summary.edge_integrity_score,
            summary.resolution_need_score,
        ]))

    def test_quality_scan_generates_expected_warnings(self) -> None:
        summary = scan_quality(
            QualityScanInput(
                width=128,
                height=128,
                file_format=AssetFormat.JPG,
                classification_tags=["photo"],
                edge_density=0.1,
                high_frequency_ratio=0.1,
                noise_variance=0.95,
                blockiness=0.9,
                edge_continuity=0.1,
                banding_likelihood=0.9,
            )
        )

        self.assertIn("Blur appears high", summary.warnings)
        self.assertIn("Noise appears elevated", summary.warnings)
        self.assertIn("Compression artifacts likely visible", summary.warnings)
        self.assertIn("Resolution may be insufficient for target use", summary.warnings)
        self.assertIn("Edge integrity appears weak", summary.warnings)


class GifScanTests(unittest.TestCase):
    def test_gif_palette_stress_stub_is_deterministic(self) -> None:
        scan = GifScanInput(
            frame_count=20,
            palette_size=256,
            duplicate_frame_ratio=0.2,
            motion_change_ratio=0.8,
        )
        stress = estimate_gif_palette_stress_stub(scan)
        self.assertAlmostEqual(stress, 0.7433333333, places=6)
        self.assertGreaterEqual(stress, 0.0)
        self.assertLessEqual(stress, 1.0)


class RecommendationTests(unittest.TestCase):
    def test_recommendations_for_pixel_art_with_alpha(self) -> None:
        recs = build_recommendations(
            RecommendationInput(
                file_format=AssetFormat.PNG,
                classification_tags=["sprite_sheet", "pixel_art"],
                analysis=AnalysisSummary(
                    blur_score=0.15,
                    noise_score=0.2,
                    compression_score=0.1,
                    edge_integrity_score=0.9,
                    resolution_need_score=0.8,
                    gif_palette_stress=None,
                    warnings=[],
                ),
                has_alpha=True,
                is_animated=False,
            )
        )

        self.assertEqual(recs.suggested_export_profile, "app_asset")
        self.assertEqual(recs.suggested_export_format, "png")
        self.assertGreaterEqual(len(recs.suggested_presets), 1)
        self.assertEqual(recs.suggested_presets[0].preset_name, "Pixel Clean Upscale")
        self.assertAlmostEqual(recs.suggested_presets[0].confidence, 0.9, places=6)

    def test_recommendations_for_photo_with_noise_blur(self) -> None:
        recs = build_recommendations(
            RecommendationInput(
                file_format=AssetFormat.JPG,
                classification_tags=["photo"],
                analysis=AnalysisSummary(
                    blur_score=0.8,
                    noise_score=0.7,
                    compression_score=0.65,
                    edge_integrity_score=0.2,
                    resolution_need_score=0.2,
                    gif_palette_stress=None,
                    warnings=["Blur appears high"],
                ),
                has_alpha=False,
                is_animated=False,
            )
        )

        preset_names = [item.preset_name for item in recs.suggested_presets]
        self.assertEqual(recs.suggested_export_profile, "web")
        self.assertEqual(recs.suggested_export_format, "webp")
        self.assertIn("Artifact Cleanup", preset_names)
        self.assertIn("Photo Recover", preset_names)
        self.assertIn("Edge Repair", preset_names)


if __name__ == "__main__":
    unittest.main()
