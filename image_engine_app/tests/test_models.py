"""Serialization round-trip tests for engine data models."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest


from image_engine_app.engine.models import (  # noqa: E402
    AISettings,
    AlphaSettings,
    AnalysisSummary,
    ApplyTarget,
    AssetFormat,
    AssetRecord,
    Capabilities,
    ChromaSubsampling,
    CleanupSettings,
    ColorSettings,
    DetailSettings,
    EditMode,
    EditState,
    EdgeSettings,
    ExportComparisonEntry,
    ExportFormat,
    ExportPrediction,
    ExportProfile,
    ExportProfileModel,
    ExportSettings,
    GifSettings,
    HeavyJobSpec,
    HeavyJobStatus,
    HeavyTool,
    HistoryAffectsView,
    HistoryState,
    HistoryStep,
    PixelSettings,
    PresetModel,
    PresetSuggestion,
    JobState,
    ProgressEvent,
    QueueItem,
    QueueItemStatus,
    RecommendationsSummary,
    ScaleMethod,
    SessionState,
    SettingsState,
    SourceType,
    TabState,
)


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 2, 23, hour, minute, tzinfo=timezone.utc)


class ModelSerializationTests(unittest.TestCase):
    def test_asset_record_round_trip(self) -> None:
        asset = AssetRecord(
            id="asset-001",
            source_type=SourceType.URL,
            source_uri="https://example.com/sprite.png",
            cache_path="cache/asset-001.png",
            original_name="sprite.png",
            created_at=_dt(20, 15),
            format=AssetFormat.PNG,
            capabilities=Capabilities(
                has_alpha=True,
                is_animated=False,
                is_sheet=True,
                is_ico_bundle=False,
            ),
            dimensions_original=(64, 64),
            dimensions_current=(128, 128),
            dimensions_final=(256, 256),
            classification_tags=["sprite_sheet", "pixel_art"],
            analysis=AnalysisSummary(
                blur_score=0.12,
                noise_score=0.08,
                compression_score=0.03,
                edge_integrity_score=0.94,
                resolution_need_score=0.77,
                gif_palette_stress=None,
                warnings=["low resolution source"],
            ),
            recommendations=RecommendationsSummary(
                suggested_presets=[
                    PresetSuggestion(
                        preset_name="Pixel Clean Upscale",
                        confidence=0.91,
                        reason="Pixel-art tags + low source resolution",
                    )
                ],
                suggested_export_profile="app_asset",
                suggested_export_format="png",
            ),
            edit_state=EditState(
                mode=EditMode.ADVANCED,
                sync_current_final=False,
                apply_target=ApplyTarget.FINAL,
                auto_apply_light=False,
                queued_heavy_jobs=[
                    HeavyJobSpec(
                        id="job-001",
                        tool=HeavyTool.AI_UPSCALE,
                        params={"factor": 4, "model": "pixel"},
                        status=HeavyJobStatus.QUEUED,
                        progress=0.0,
                    )
                ],
                settings=SettingsState(
                    pixel=PixelSettings(
                        resize_percent=400.0,
                        width=256,
                        height=256,
                        dpi=72,
                        scale_method=ScaleMethod.NEAREST,
                        pixel_snap=True,
                    ),
                    color=ColorSettings(
                        brightness=0.05,
                        contrast=0.12,
                        saturation=0.0,
                        temperature=-0.03,
                        gamma=1.05,
                        curves={"rgb": [[0, 0], [128, 140], [255, 255]]},
                    ),
                    detail=DetailSettings(
                        sharpen_amount=0.2,
                        sharpen_radius=0.5,
                        sharpen_threshold=0.1,
                        clarity=0.15,
                        texture=0.1,
                    ),
                    cleanup=CleanupSettings(
                        denoise=0.25,
                        artifact_removal=0.4,
                        halo_cleanup=0.1,
                        banding_removal=0.0,
                    ),
                    edges=EdgeSettings(
                        antialias=0.0,
                        edge_refine=0.2,
                        grow_shrink_px=0.0,
                        feather_px=0.0,
                    ),
                    alpha=AlphaSettings(
                        remove_white_bg=True,
                        alpha_smooth=0.05,
                        matte_fix=0.0,
                        alpha_threshold=1,
                    ),
                    ai=AISettings(
                        upscale_factor=4.0,
                        deblur_strength=0.0,
                        detail_reconstruct=0.2,
                        bg_remove_strength=0.0,
                    ),
                    gif=GifSettings(
                        frame_delay_ms=90,
                        loop=True,
                        palette_size=256,
                        dither_strength=0.0,
                        frame_optimize=True,
                    ),
                    export=ExportSettings(
                        export_profile=ExportProfile.APP_ASSET,
                        format=ExportFormat.PNG,
                        quality=100,
                        compression_level=3,
                        chroma_subsampling=ChromaSubsampling.AUTO,
                        palette_limit=None,
                        ico_sizes=[16, 32, 64, 128, 256],
                        strip_metadata=True,
                    ),
                ),
            ),
            history=HistoryState(
                steps=[
                    HistoryStep(
                        id="hist-001",
                        timestamp=_dt(20, 16),
                        label="Apply pixel upscale",
                        state_snapshot={
                            "mode": "advanced",
                            "settings": {"pixel": {"resize_percent": 400.0}},
                        },
                        affects_view=HistoryAffectsView.FINAL,
                    )
                ],
                pointer=0,
            ),
        )

        payload = asset.to_dict()
        json.dumps(payload)  # JSON-safe check

        restored = AssetRecord.from_dict(payload)
        self.assertEqual(asset, restored)
        self.assertIsInstance(restored.dimensions_original, tuple)
        self.assertIsInstance(restored.created_at, datetime)
        self.assertIsInstance(restored.edit_state.queued_heavy_jobs[0].tool, HeavyTool)

    def test_session_state_round_trip(self) -> None:
        session = SessionState(
            session_id="session-001",
            opened_at=_dt(19, 50),
            active_tab_asset_id="asset-001",
            tab_order=["asset-001", "asset-002"],
            pinned_tabs={"asset-002"},
            batch_queue=[
                QueueItem(
                    id="queue-001",
                    asset_id="asset-001",
                    status=QueueItemStatus.PENDING,
                    progress=0.0,
                    notes=None,
                ),
                QueueItem(
                    id="queue-002",
                    asset_id="asset-002",
                    status=QueueItemStatus.DONE,
                    progress=1.0,
                    notes="exported",
                ),
            ],
            macros=["macro-clean", "macro-export-webp"],
            last_export_dir="C:/Exports",
        )

        payload = session.to_dict()
        json.dumps(payload)
        self.assertIsInstance(payload["pinned_tabs"], list)

        restored = SessionState.from_dict(payload)
        self.assertEqual(session, restored)
        self.assertIsInstance(restored.pinned_tabs, set)
        self.assertEqual(restored.batch_queue[1].status, QueueItemStatus.DONE)

    def test_preset_and_export_prediction_round_trip(self) -> None:
        preset = PresetModel(
            name="Web Clean",
            description="Light cleanup + web export defaults",
            applies_to_formats=["jpg", "png", "webp"],
            applies_to_tags=["photo", "artwork"],
            settings_delta={
                "cleanup": {"denoise": 0.15},
                "export": {"export_profile": "web", "format": "webp", "quality": 85},
            },
            uses_heavy_tools=False,
            requires_apply=False,
            mode_min=EditMode.SIMPLE,
        )
        prediction = ExportPrediction(
            predicted_bytes=123456,
            predicted_format="webp",
            confidence=0.82,
            comparison=[
                ExportComparisonEntry(format="jpg", predicted_bytes=156000),
                ExportComparisonEntry(format="webp", predicted_bytes=123456),
                ExportComparisonEntry(format="png", predicted_bytes=412345),
            ],
        )

        preset_payload = preset.to_dict()
        prediction_payload = prediction.to_dict()
        json.dumps(preset_payload)
        json.dumps(prediction_payload)

        self.assertEqual(preset, PresetModel.from_dict(preset_payload))
        self.assertEqual(prediction, ExportPrediction.from_dict(prediction_payload))


    def test_extended_models_round_trip(self) -> None:
        export_profile_model = ExportProfileModel(
            id="profile-001",
            name="Web Fast",
            description="Fast web export defaults",
            export_profile=ExportProfile.WEB,
            format=ExportFormat.WEBP,
            quality=82,
            compression_level=5,
            chroma_subsampling=ChromaSubsampling.CS_420,
            palette_limit=128,
            ico_sizes=[16, 32, 64],
            strip_metadata=True,
        )
        job_state = JobState(
            total=12,
            queued=3,
            running=1,
            done=7,
            failed=1,
            cancelled=False,
            message="Processing",
            updated_at=_dt(21, 5),
        )
        progress_event = ProgressEvent(
            event_type="item_progress",
            item_index=3,
            item_total=12,
            asset_id="asset-003",
            asset_label="sprite_003.png",
            queue_status="processing",
            queue_progress=0.4,
            overall_progress=0.25,
            stage="light_preview",
            processed_count=2,
            failed_count=0,
            message="Applying light pipeline",
            timestamp=_dt(21, 6),
        )
        tab_state = TabState(
            asset_id="asset-003",
            label="sprite_003.png",
            pinned=True,
            active=False,
            window_index=2,
            hidden=False,
        )

        self.assertEqual(export_profile_model, ExportProfileModel.from_dict(export_profile_model.to_dict()))
        self.assertEqual(job_state, JobState.from_dict(job_state.to_dict()))
        self.assertEqual(progress_event, ProgressEvent.from_dict(progress_event.to_dict()))
        self.assertEqual(tab_state, TabState.from_dict(tab_state.to_dict()))

if __name__ == "__main__":
    unittest.main()




