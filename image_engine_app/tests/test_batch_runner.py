"""Tests for sequential batch runner orchestration."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.batch.batch_runner import BatchRunner, BatchRunnerConfig, BatchWorkItem  # noqa: E402
from engine.models import (  # noqa: E402
    ApplyTarget,
    AssetFormat,
    AssetRecord,
    Capabilities,
    EditMode,
    ExportFormat,
    ExportProfile,
    HeavyJobSpec,
    HeavyJobStatus,
    HeavyTool,
    PresetModel,
    QueueItem,
    QueueItemStatus,
    SourceType,
)


def _pillow_available() -> bool:
    try:
        from PIL import Image  # noqa: F401
        return True
    except Exception:
        return False


def _make_asset(
    *,
    asset_id: str,
    name: str,
    fmt: AssetFormat,
    dims: tuple[int, int],
    has_alpha: bool = False,
    is_animated: bool = False,
    is_sheet: bool = False,
) -> AssetRecord:
    asset = AssetRecord(
        id=asset_id,
        source_type=SourceType.FILE,
        source_uri=f"C:/assets/{name}",
        original_name=name,
        format=fmt,
        capabilities=Capabilities(
            has_alpha=has_alpha,
            is_animated=is_animated,
            is_sheet=is_sheet,
            is_ico_bundle=(fmt is AssetFormat.ICO),
        ),
        dimensions_original=dims,
        dimensions_current=dims,
        dimensions_final=dims,
    )
    asset.edit_state.mode = EditMode.SIMPLE
    asset.edit_state.apply_target = ApplyTarget.CURRENT
    asset.edit_state.sync_current_final = False
    asset.edit_state.settings.export.export_profile = ExportProfile.APP_ASSET if has_alpha else ExportProfile.WEB
    asset.edit_state.settings.export.format = ExportFormat.AUTO
    return asset


def _make_queue(asset: AssetRecord, idx: int) -> QueueItem:
    return QueueItem(
        id=f"queue-{idx}",
        asset_id=asset.id,
        status=QueueItemStatus.PENDING,
        progress=0.0,
    )


class BatchRunnerTests(unittest.TestCase):
    def test_batch_runner_sequential_auto_preset_heavy_and_export(self) -> None:
        pixel_asset = _make_asset(
            asset_id="asset-1",
            name="enemy_sprite.png",
            fmt=AssetFormat.PNG,
            dims=(64, 64),
            has_alpha=True,
        )
        pixel_asset.edit_state.queued_heavy_jobs = [
            HeavyJobSpec(id="job-upscale-1", tool=HeavyTool.AI_UPSCALE, params={"factor": 4})
        ]

        photo_asset = _make_asset(
            asset_id="asset-2",
            name="portrait.jpg",
            fmt=AssetFormat.JPG,
            dims=(1600, 1200),
            has_alpha=False,
        )

        # Simple mode clamp should cap brightness at 0.25.
        pixel_preset = PresetModel(
            name="Pixel Batch Boost",
            description="Boost pixel assets in batch",
            settings_delta={"color": {"brightness": 0.9}, "cleanup": {"denoise": 0.3}},
            mode_min=EditMode.SIMPLE,
        )

        config = BatchRunnerConfig(
            preview_skip_mode=True,
            auto_export=True,
            auto_preset_rules={"pixel_art": [pixel_preset]},
            heavy_progress_steps=2,
            heavy_step_delay_seconds=0.0,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            config.export_dir = temp_dir
            runner = BatchRunner(config)
            report = runner.run(
                [
                    BatchWorkItem(asset=pixel_asset, queue_item=_make_queue(pixel_asset, 1)),
                    BatchWorkItem(asset=photo_asset, queue_item=_make_queue(photo_asset, 2)),
                ]
            )

            self.assertEqual(report.processed_count, 2)
            self.assertEqual(report.failed_count, 0)
            self.assertEqual([item.asset_id for item in report.items], ["asset-1", "asset-2"])
            self.assertTrue(all(item.preview_skipped for item in report.items))
            self.assertTrue(all(item.processing_plan is None for item in report.items))

            # Classification + auto preset applied to the sprite item.
            self.assertIn("pixel_art", pixel_asset.classification_tags)
            self.assertEqual(pixel_asset.edit_state.settings.color.brightness, 0.25)
            self.assertEqual(pixel_asset.edit_state.settings.cleanup.denoise, 0.3)
            self.assertEqual(report.items[0].applied_preset_names, ["Pixel Batch Boost"])
            self.assertEqual(report.items[1].applied_preset_names, [])

            # Heavy queue executed and statuses persisted back to the asset.
            self.assertEqual(len(pixel_asset.edit_state.queued_heavy_jobs), 1)
            self.assertEqual(pixel_asset.edit_state.queued_heavy_jobs[0].status, HeavyJobStatus.DONE)
            self.assertEqual(report.items[0].heavy_jobs[0].status, HeavyJobStatus.DONE)

            # Auto export wrote placeholder files for both items.
            exports = sorted(Path(temp_dir).iterdir())
            self.assertEqual(len(exports), 2)
            self.assertTrue(report.items[0].export_result is not None)
            self.assertTrue(report.items[1].export_result is not None)
            self.assertTrue(report.items[0].export_result.is_stub)
            self.assertTrue(report.items[1].export_result.is_stub)
            self.assertEqual(report.items[0].queue_item.status, QueueItemStatus.DONE)
            self.assertEqual(report.items[1].queue_item.status, QueueItemStatus.DONE)
            self.assertEqual(report.items[0].queue_item.progress, 1.0)
            self.assertEqual(report.items[1].queue_item.progress, 1.0)

    def test_batch_runner_generates_processing_plan_when_preview_not_skipped(self) -> None:
        asset = _make_asset(
            asset_id="asset-3",
            name="icon.png",
            fmt=AssetFormat.PNG,
            dims=(256, 256),
            has_alpha=True,
        )
        asset.edit_state.settings.cleanup.denoise = 0.2
        asset.edit_state.settings.detail.sharpen_amount = 0.4
        asset.edit_state.settings.color.brightness = 0.1
        asset.edit_state.settings.ai.upscale_factor = 2.0

        queue = _make_queue(asset, 3)
        runner = BatchRunner(BatchRunnerConfig(preview_skip_mode=False, auto_export=False))
        report = runner.run([BatchWorkItem(asset=asset, queue_item=queue)])

        self.assertEqual(report.processed_count, 1)
        item = report.items[0]
        self.assertFalse(item.preview_skipped)
        self.assertIsNotNone(item.processing_plan)
        ordered_keys = [step.key for step in item.processing_plan.ordered_steps]
        self.assertEqual(ordered_keys, ["cleanup.denoise", "detail.sharpen", "ai.upscale", "color.adjust"])
        self.assertEqual(item.queue_item.status, QueueItemStatus.DONE)

    def test_batch_runner_emits_live_progress_events(self) -> None:
        asset = _make_asset(
            asset_id="asset-4",
            name="batch_event_asset.png",
            fmt=AssetFormat.PNG,
            dims=(128, 128),
            has_alpha=True,
        )
        queue = _make_queue(asset, 4)
        runner = BatchRunner(BatchRunnerConfig(preview_skip_mode=True, auto_export=False))

        events: list[object] = []
        report = runner.run([BatchWorkItem(asset=asset, queue_item=queue)], event_callback=events.append)

        self.assertEqual(report.processed_count, 1)
        event_types = [getattr(event, "event_type", "") for event in events]
        self.assertGreaterEqual(len(events), 4)
        self.assertEqual(event_types[0], "batch_start")
        self.assertIn("item_start", event_types)
        self.assertIn("item_progress", event_types)
        self.assertIn("item_complete", event_types)
        self.assertEqual(event_types[-1], "batch_complete")

        progress_events = [event for event in events if getattr(event, "event_type", "") == "item_progress"]
        self.assertTrue(all(getattr(event, "asset_id", None) == "asset-4" for event in progress_events))
        overall_values = [
            float(getattr(event, "overall_progress", 0.0))
            for event in events
            if getattr(event, "overall_progress", None) is not None
        ]
        self.assertEqual(overall_values, sorted(overall_values))
        self.assertAlmostEqual(overall_values[-1], 1.0, places=6)

    def test_batch_runner_supports_cancellation(self) -> None:
        a1 = _make_asset(
            asset_id="asset-c1",
            name="first.png",
            fmt=AssetFormat.PNG,
            dims=(64, 64),
            has_alpha=True,
        )
        a2 = _make_asset(
            asset_id="asset-c2",
            name="second.png",
            fmt=AssetFormat.PNG,
            dims=(64, 64),
            has_alpha=True,
        )
        runner = BatchRunner(BatchRunnerConfig(preview_skip_mode=True, auto_export=False))

        events: list[object] = []
        cancel_flag = {"value": False}

        def on_event(event: object) -> None:
            events.append(event)
            if getattr(event, "event_type", "") == "item_progress" and getattr(event, "stage", "") == "classify":
                cancel_flag["value"] = True

        report = runner.run(
            [
                BatchWorkItem(asset=a1, queue_item=_make_queue(a1, 11)),
                BatchWorkItem(asset=a2, queue_item=_make_queue(a2, 12)),
            ],
            event_callback=on_event,
            cancel_requested=lambda: bool(cancel_flag["value"]),
        )

        self.assertTrue(report.cancelled)
        self.assertEqual(len(report.items), 1)
        self.assertEqual(report.processed_count, 0)
        self.assertEqual(report.failed_count, 0)
        self.assertEqual(report.items[0].queue_item.status, QueueItemStatus.SKIPPED)
        event_types = [getattr(event, "event_type", "") for event in events]
        self.assertIn("item_cancelled", event_types)
        self.assertIn("batch_cancelled", event_types)
        self.assertNotIn("batch_complete", event_types)


    def test_auto_export_collision_appends_suffix(self) -> None:
        asset = _make_asset(
            asset_id="asset-collide",
            name="enemy_sprite.png",
            fmt=AssetFormat.PNG,
            dims=(64, 64),
            has_alpha=True,
        )
        config = BatchRunnerConfig(
            preview_skip_mode=True,
            auto_export=True,
            group_outputs=False,
            heavy_progress_steps=1,
            heavy_step_delay_seconds=0.0,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            config.export_dir = temp_dir
            # Pre-create a file at the expected first output path to force a collision.
            existing = Path(temp_dir) / "001_enemy_sprite.png"
            existing.write_text("existing", encoding="utf-8")

            runner = BatchRunner(config)
            report = runner.run([BatchWorkItem(asset=asset, queue_item=_make_queue(asset, 1))])

            self.assertEqual(report.processed_count, 1)
            self.assertEqual(report.failed_count, 0)
            self.assertTrue(report.items[0].export_result is not None)

            out_path = Path(report.items[0].export_result.output_path)
            # Should not overwrite the existing file.
            self.assertNotEqual(out_path.name, existing.name)
            self.assertTrue(out_path.name.startswith("001_enemy_sprite__"))
            self.assertTrue(out_path.exists())

            files = sorted(Path(temp_dir).glob("*.png"))
            self.assertEqual(len(files), 2)


    @unittest.skipUnless(_pillow_available(), "Pillow required for animated GIF batch export test.")
    def test_batch_runner_auto_export_preserves_animated_gif_when_format_is_auto(self) -> None:
        from PIL import Image  # type: ignore

        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            src = tmp_path / "anim.gif"
            export_dir = tmp_path / "exports"
            cache_dir = tmp_path / "cache"

            frame_a = Image.new("RGBA", (12, 12), (255, 0, 0, 255))
            frame_b = Image.new("RGBA", (12, 12), (0, 255, 0, 255))
            frame_a.save(
                src,
                format="GIF",
                save_all=True,
                append_images=[frame_b],
                duration=[80, 120],
                loop=0,
            )

            asset = _make_asset(
                asset_id="asset-gif-auto",
                name="anim.gif",
                fmt=AssetFormat.GIF,
                dims=(12, 12),
                has_alpha=True,
                is_animated=True,
            )
            asset.source_uri = str(src)
            asset.cache_path = str(src)
            asset.edit_state.settings.export.format = ExportFormat.AUTO

            runner = BatchRunner(
                BatchRunnerConfig(
                    preview_skip_mode=True,
                    auto_export=True,
                    export_dir=export_dir,
                    derived_cache_dir=cache_dir,
                    heavy_progress_steps=1,
                    heavy_step_delay_seconds=0.0,
                )
            )
            report = runner.run([BatchWorkItem(asset=asset, queue_item=_make_queue(asset, 21))])

            self.assertEqual(report.processed_count, 1)
            self.assertEqual(report.failed_count, 0)
            self.assertTrue(report.items[0].export_result is not None)

            out_path = Path(report.items[0].export_result.output_path)
            with Image.open(out_path) as im:
                self.assertTrue(bool(getattr(im, "is_animated", False)))
                self.assertGreaterEqual(int(getattr(im, "n_frames", 1)), 2)


if __name__ == "__main__":
    unittest.main()
