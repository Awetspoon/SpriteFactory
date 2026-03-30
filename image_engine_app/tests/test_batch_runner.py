"""Tests for sequential batch runner orchestration."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


from image_engine_app.engine.batch.batch_runner import BatchRunner, BatchRunnerConfig, BatchWorkItem  # noqa: E402
from image_engine_app.engine.models import (  # noqa: E402
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
from image_engine_app.engine.process.performance_backend import (  # noqa: E402
    PerformanceAvailability,
    PerformanceBackend,
    PerformanceModeResolution,
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


def _write_source_fixture(path: Path, *, fmt: AssetFormat, animated: bool = False, with_alpha: bool = False) -> None:
    from PIL import Image

    if fmt is AssetFormat.GIF and animated:
        frame_a = Image.new("RGBA", (24, 24), (255, 0, 0, 255))
        frame_b = Image.new("RGBA", (24, 24), (0, 255, 0, 255))
        frame_a.save(
            path,
            format="GIF",
            save_all=True,
            append_images=[frame_b],
            duration=[70, 90],
            loop=0,
        )
        return

    if fmt in {AssetFormat.PNG, AssetFormat.WEBP, AssetFormat.TIFF, AssetFormat.ICO} and with_alpha:
        image = Image.new("RGBA", (32, 28), (80, 140, 220, 255))
    else:
        image = Image.new("RGB", (32, 28), (80, 140, 220))

    if fmt is AssetFormat.PNG:
        image.save(path, format="PNG")
    elif fmt is AssetFormat.JPG:
        image.convert("RGB").save(path, format="JPEG")
    elif fmt is AssetFormat.WEBP:
        image.save(path, format="WEBP")
    elif fmt is AssetFormat.BMP:
        image.convert("RGB").save(path, format="BMP")
    elif fmt is AssetFormat.TIFF:
        image.save(path, format="TIFF")
    elif fmt is AssetFormat.ICO:
        image.convert("RGBA").save(path, format="ICO", sizes=[(16, 16), (32, 32)])
    else:
        raise AssertionError(f"Unsupported fixture format: {fmt}")


class _RecordingPerformanceBackend(PerformanceBackend):
    def __init__(self, *, availability: PerformanceAvailability) -> None:
        super().__init__(availability=availability)
        self.calls: list[tuple[str, str]] = []

    def run_heavy_job(self, job: HeavyJobSpec, *, requested_mode: str) -> PerformanceModeResolution:
        self.calls.append((job.id, requested_mode))
        return super().run_heavy_job(job, requested_mode=requested_mode)


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

    def test_batch_runner_uses_configured_performance_mode_for_heavy_jobs(self) -> None:
        asset = _make_asset(
            asset_id="asset-heavy-1",
            name="heavy-source.png",
            fmt=AssetFormat.PNG,
            dims=(128, 128),
            has_alpha=True,
        )
        asset.edit_state.queued_heavy_jobs = [
            HeavyJobSpec(id="job-heavy-1", tool=HeavyTool.AI_UPSCALE, params={"factor": 2})
        ]
        backend = _RecordingPerformanceBackend(
            availability=PerformanceAvailability(
                cpu_available=True,
                gpu_available=True,
                gpu_backend_label="Fake GPU",
                gpu_disabled_reason=None,
            )
        )
        runner = BatchRunner(
            BatchRunnerConfig(
                preview_skip_mode=True,
                auto_export=False,
                performance_mode="gpu",
            ),
            performance_backend=backend,
        )

        report = runner.run([BatchWorkItem(asset=asset, queue_item=_make_queue(asset, 20))])

        self.assertEqual(report.processed_count, 1)
        self.assertEqual(backend.calls, [("job-heavy-1", "gpu")])
        self.assertEqual(asset.edit_state.queued_heavy_jobs[0].status, HeavyJobStatus.DONE)

    @unittest.skipUnless(_pillow_available(), "Pillow required for batch heavy render test.")
    def test_batch_runner_heavy_jobs_render_into_batch_cache(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            src = Path(temp_dir) / "batch-heavy.png"
            Image.new("RGBA", (12, 10), (200, 80, 60, 255)).save(src, format="PNG")

            asset = _make_asset(
                asset_id="asset-heavy-cache",
                name="batch-heavy.png",
                fmt=AssetFormat.PNG,
                dims=(12, 10),
                has_alpha=True,
            )
            asset.source_uri = str(src)
            asset.cache_path = str(src)
            asset.edit_state.settings.ai.upscale_factor = 2.0
            asset.edit_state.queued_heavy_jobs = [
                HeavyJobSpec(id="job-batch-heavy", tool=HeavyTool.AI_UPSCALE, params={"factor": 2.0})
            ]

            cache_dir = Path(temp_dir) / "cache-root"
            runner = BatchRunner(
                BatchRunnerConfig(
                    preview_skip_mode=True,
                    auto_export=False,
                    derived_cache_dir=cache_dir,
                )
            )

            report = runner.run([BatchWorkItem(asset=asset, queue_item=_make_queue(asset, 30))])

            self.assertEqual(report.processed_count, 1)
            self.assertTrue(isinstance(asset.derived_final_path, str) and Path(asset.derived_final_path).exists())
            self.assertIn("cache-root", asset.derived_final_path)
            self.assertGreaterEqual(asset.dimensions_final[0], 24)
            self.assertEqual(asset.edit_state.queued_heavy_jobs[0].status, HeavyJobStatus.DONE)

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

    def test_batch_runner_skips_incompatible_auto_presets_for_animated_gif(self) -> None:
        asset = _make_asset(
            asset_id="asset-gif-preset",
            name="loop.gif",
            fmt=AssetFormat.GIF,
            dims=(24, 24),
            has_alpha=True,
            is_animated=True,
        )
        asset.classification_tags = ["animation", "pixel_art"]
        incompatible = PresetModel(
            name="Photo Batch Recover",
            description="Photo-only cleanup",
            applies_to_formats=["jpg"],
            applies_to_tags=["photo"],
            settings_delta={"cleanup": {"denoise": 0.45}},
            mode_min=EditMode.SIMPLE,
        )
        gif_safe = PresetModel(
            name="GIF Safe Batch",
            description="GIF-safe cleanup",
            applies_to_formats=["gif"],
            applies_to_tags=["animation", "pixel_art"],
            settings_delta={
                "cleanup": {"artifact_removal": 0.14},
                "export": {"format": ExportFormat.GIF.value, "palette_limit": 256},
            },
            mode_min=EditMode.SIMPLE,
        )

        runner = BatchRunner(
            BatchRunnerConfig(
                preview_skip_mode=True,
                auto_export=False,
                per_source_preset_rules={"gif": [incompatible, gif_safe]},
            )
        )
        report = runner.run([BatchWorkItem(asset=asset, queue_item=_make_queue(asset, 31))])

        self.assertEqual(report.processed_count, 1)
        self.assertEqual(report.items[0].applied_preset_names, ["GIF Safe Batch"])
        self.assertAlmostEqual(asset.edit_state.settings.cleanup.denoise, 0.0, places=6)
        self.assertAlmostEqual(asset.edit_state.settings.cleanup.artifact_removal, 0.14, places=6)
        self.assertEqual(asset.edit_state.settings.export.format, ExportFormat.GIF)

    @unittest.skipUnless(_pillow_available(), "Pillow required for static batch export test.")
    def test_batch_runner_auto_export_applies_background_removal_when_no_derived_preview_exists(self) -> None:
        from PIL import Image  # type: ignore

        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            src = tmp_path / "sprite_bg.png"
            export_dir = tmp_path / "exports"

            image = Image.new("RGBA", (12, 12), (255, 255, 255, 255))
            for y in range(3, 9):
                for x in range(3, 9):
                    image.putpixel((x, y), (220, 40, 40, 255))
            image.save(src, format="PNG")

            asset = _make_asset(
                asset_id="asset-static-cutout",
                name="sprite_bg.png",
                fmt=AssetFormat.PNG,
                dims=(12, 12),
                has_alpha=True,
            )
            asset.source_uri = str(src)
            asset.cache_path = str(src)
            asset.derived_current_path = None
            asset.derived_final_path = None
            asset.edit_state.settings.export.format = ExportFormat.PNG
            asset.edit_state.settings.alpha.background_removal_mode = "white"

            runner = BatchRunner(
                BatchRunnerConfig(
                    preview_skip_mode=True,
                    auto_export=True,
                    export_dir=export_dir,
                    derived_cache_dir=None,
                    heavy_progress_steps=1,
                    heavy_step_delay_seconds=0.0,
                )
            )
            report = runner.run([BatchWorkItem(asset=asset, queue_item=_make_queue(asset, 20))])

            self.assertEqual(report.processed_count, 1)
            self.assertEqual(report.failed_count, 0)
            self.assertTrue(report.items[0].export_result is not None)
            self.assertFalse(report.items[0].export_result.is_stub)

            out_path = Path(report.items[0].export_result.output_path)
            with Image.open(out_path) as im:
                rgba = im.convert("RGBA")
                self.assertEqual(0, rgba.getpixel((0, 0))[3])
                self.assertGreater(rgba.getpixel((5, 5))[3], 0)


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

    @unittest.skipUnless(_pillow_available(), "Pillow required for animated GIF batch export test.")
    def test_batch_runner_auto_export_applies_background_removal_to_animated_gif(self) -> None:
        from PIL import Image, ImageSequence  # type: ignore

        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            src = tmp_path / "anim_bg.gif"
            export_dir = tmp_path / "exports"
            cache_dir = tmp_path / "cache"

            frame_a = Image.new("RGB", (12, 12), (255, 255, 255))
            frame_b = Image.new("RGB", (12, 12), (255, 255, 255))
            for y in range(3, 9):
                for x in range(3, 9):
                    frame_a.putpixel((x, y), (255, 0, 0))
                    frame_b.putpixel((x, y), (0, 255, 0))
            frame_a.save(
                src,
                format="GIF",
                save_all=True,
                append_images=[frame_b],
                duration=[80, 120],
                loop=0,
            )

            asset = _make_asset(
                asset_id="asset-gif-cutout",
                name="anim_bg.gif",
                fmt=AssetFormat.GIF,
                dims=(12, 12),
                has_alpha=True,
                is_animated=True,
            )
            asset.source_uri = str(src)
            asset.cache_path = str(src)
            asset.edit_state.settings.export.format = ExportFormat.GIF
            asset.edit_state.settings.alpha.background_removal_mode = "white"

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
            report = runner.run([BatchWorkItem(asset=asset, queue_item=_make_queue(asset, 22))])

            self.assertEqual(report.processed_count, 1)
            self.assertEqual(report.failed_count, 0)
            self.assertTrue(report.items[0].export_result is not None)

            out_path = Path(report.items[0].export_result.output_path)
            with Image.open(out_path) as im:
                self.assertTrue(bool(getattr(im, "is_animated", False)))
                for frame in ImageSequence.Iterator(im):
                    rgba = frame.convert("RGBA")
                    self.assertEqual(0, rgba.getpixel((0, 0))[3])
                    self.assertGreater(rgba.getpixel((5, 5))[3], 0)

    @unittest.skipUnless(_pillow_available(), "Pillow required for supported-format batch export test.")
    def test_batch_runner_mixed_supported_sources_export_without_failure(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            export_dir = tmp_path / "exports"
            cache_dir = tmp_path / "cache"

            cases = [
                ("asset-png", "sprite.png", AssetFormat.PNG, ExportFormat.PNG, True, False, False, HeavyTool.AI_UPSCALE),
                ("asset-jpg", "photo.jpg", AssetFormat.JPG, ExportFormat.JPG, False, False, False, HeavyTool.AI_DEBLUR),
                ("asset-webp", "web_art.webp", AssetFormat.WEBP, ExportFormat.WEBP, True, False, False, None),
                ("asset-bmp", "sprite.bmp", AssetFormat.BMP, ExportFormat.BMP, False, False, False, None),
                ("asset-tiff", "print.tiff", AssetFormat.TIFF, ExportFormat.TIFF, True, False, False, None),
                ("asset-ico", "icon.ico", AssetFormat.ICO, ExportFormat.ICO, True, False, False, None),
                ("asset-sheet", "sheet.png", AssetFormat.PNG, ExportFormat.PNG, True, False, True, None),
            ]

            work_items: list[BatchWorkItem] = []
            by_id: dict[str, AssetRecord] = {}
            for idx, (asset_id, file_name, fmt, export_fmt, has_alpha, is_animated, is_sheet, heavy_tool) in enumerate(cases, start=40):
                src = tmp_path / file_name
                _write_source_fixture(src, fmt=fmt, animated=is_animated, with_alpha=has_alpha)
                asset = _make_asset(
                    asset_id=asset_id,
                    name=file_name,
                    fmt=fmt,
                    dims=(32, 28),
                    has_alpha=has_alpha,
                    is_animated=is_animated,
                    is_sheet=is_sheet,
                )
                asset.source_uri = str(src)
                asset.cache_path = str(src)
                asset.edit_state.settings.export.format = export_fmt
                if heavy_tool is HeavyTool.AI_UPSCALE:
                    asset.edit_state.settings.ai.upscale_factor = 2.0
                    asset.edit_state.queued_heavy_jobs = [
                        HeavyJobSpec(id=f"job-{asset_id}", tool=heavy_tool, params={"factor": 2.0})
                    ]
                elif heavy_tool is HeavyTool.AI_DEBLUR:
                    asset.edit_state.settings.ai.deblur_strength = 0.6
                    asset.edit_state.queued_heavy_jobs = [
                        HeavyJobSpec(id=f"job-{asset_id}", tool=heavy_tool, params={"strength": 0.6})
                    ]
                work_items.append(BatchWorkItem(asset=asset, queue_item=_make_queue(asset, idx)))
                by_id[asset_id] = asset

            runner = BatchRunner(
                BatchRunnerConfig(
                    preview_skip_mode=True,
                    auto_export=True,
                    export_dir=export_dir,
                    derived_cache_dir=cache_dir,
                    group_outputs=False,
                    heavy_progress_steps=1,
                    heavy_step_delay_seconds=0.0,
                )
            )
            report = runner.run(work_items)

            self.assertEqual(report.processed_count, len(cases))
            self.assertEqual(report.failed_count, 0)
            self.assertEqual(report.skipped_count, 0)
            for item in report.items:
                with self.subTest(asset_id=item.asset_id):
                    self.assertIsNotNone(item.export_result)
                    self.assertTrue(item.export_result.success)
                    self.assertFalse(item.export_result.is_stub)
                    out_path = Path(item.export_result.output_path)
                    self.assertTrue(out_path.exists())
                    with Image.open(out_path) as exported:
                        self.assertGreaterEqual(exported.size[0], 1)
                        self.assertGreaterEqual(exported.size[1], 1)

            self.assertEqual(by_id["asset-png"].edit_state.queued_heavy_jobs[0].status, HeavyJobStatus.DONE)
            self.assertEqual(by_id["asset-jpg"].edit_state.queued_heavy_jobs[0].status, HeavyJobStatus.DONE)
            self.assertTrue(Path(str(by_id["asset-png"].derived_final_path)).exists())
            self.assertTrue(Path(str(by_id["asset-jpg"].derived_final_path)).exists())


if __name__ == "__main__":
    unittest.main()


