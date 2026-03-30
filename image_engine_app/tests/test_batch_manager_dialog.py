"""Tests for batch manager dialog live-progress behavior."""

from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


try:
    from PySide6.QtWidgets import QApplication, QProgressBar
except Exception:  # pragma: no cover - optional dependency in some environments
    QApplication = None  # type: ignore[assignment]
    QProgressBar = None  # type: ignore[assignment]

from image_engine_app.ui.windows.batch_manager import BatchManagerDialog  # noqa: E402


@unittest.skipIf(QApplication is None, "PySide6 not installed")
class BatchManagerDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app = QApplication.instance()
        cls._owns_app = app is None
        cls._app = app or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        if getattr(cls, "_owns_app", False) and getattr(cls, "_app", None) is not None:
            cls._app.quit()

    def test_current_options_defaults_to_source_name_and_selects_all(self) -> None:
        dialog = BatchManagerDialog()
        dialog.set_queue_assets([
            ("asset-1", "sprite_a.png"),
            ("asset-2", "sprite_b.png"),
        ])
        dialog.set_export_directory("C:/Exports/Dialog")

        options = dialog.current_options()

        self.assertTrue(options.auto_export)
        self.assertEqual(options.export_name_template, "{stem}")
        self.assertEqual(options.export_directory, "C:/Exports/Dialog")
        self.assertEqual(options.selected_asset_ids, ("asset-1", "asset-2"))
        self.assertFalse(options.apply_active_edits)
        self.assertFalse(options.apply_selected_preset)
        self.assertIsNone(options.selected_preset_name)
        self.assertIsNone(options.background_removal_override)

    def test_batch_ui_uses_single_progress_bar(self) -> None:
        dialog = BatchManagerDialog()
        bars = dialog.findChildren(QProgressBar)
        self.assertEqual(1, len(bars))

    def test_run_button_tracks_selection_when_idle(self) -> None:
        dialog = BatchManagerDialog()
        self.assertFalse(dialog._run_btn.isEnabled())

        dialog.set_queue_assets([
            ("asset-1", "sprite_a.png"),
            ("asset-2", "sprite_b.png"),
        ])
        self.assertTrue(dialog._run_btn.isEnabled())

    def test_run_button_requires_preset_choice_when_enabled(self) -> None:
        dialog = BatchManagerDialog()
        dialog.set_queue_assets([
            ("asset-1", "sprite_a.png"),
        ])
        dialog.set_available_presets(["Pixel Clean Upscale", "Photo Recover"])

        self.assertTrue(dialog._run_btn.isEnabled())

        dialog._apply_preset_check.setChecked(True)
        self.assertFalse(dialog._run_btn.isEnabled())

        dialog._batch_preset_combo.setCurrentIndex(1)
        self.assertTrue(dialog._run_btn.isEnabled())

        options = dialog.current_options()
        self.assertTrue(options.apply_selected_preset)
        self.assertEqual(options.selected_preset_name, "Pixel Clean Upscale")
        dialog.clear_selection()
        self.assertFalse(dialog._run_btn.isEnabled())

        dialog.select_all_items()
        self.assertTrue(dialog._run_btn.isEnabled())

    def test_batch_preset_combo_accepts_labeled_entries(self) -> None:
        dialog = BatchManagerDialog()
        dialog.set_queue_assets([
            ("asset-1", "sprite_a.png"),
        ])
        dialog.set_available_presets([
            SimpleNamespace(name="GIF Safe Cleanup", label="GIF Safe Cleanup | Anim | GIF", scope_text="Anim | GIF"),
        ])

        self.assertEqual("GIF Safe Cleanup | Anim | GIF", dialog._batch_preset_combo.itemText(1))
        self.assertEqual("GIF Safe Cleanup", dialog._batch_preset_combo.itemData(1))

    def test_current_options_include_background_override(self) -> None:
        dialog = BatchManagerDialog()
        dialog.set_queue_assets([
            ("asset-1", "sprite_a.png"),
        ])

        dialog._background_combo.setCurrentIndex(2)

        options = dialog.current_options()
        self.assertEqual(options.background_removal_override, "black")

    def test_update_from_event_updates_rows_incrementally_without_duplicates(self) -> None:
        dialog = BatchManagerDialog()
        dialog.set_queue_assets([
            ("asset-1", "sprite_a.png"),
            ("asset-2", "sprite_b.png"),
        ])

        dialog.update_from_event(
            SimpleNamespace(
                event_type="batch_start",
                item_total=2,
                overall_progress=0.0,
            )
        )
        self.assertFalse(dialog._run_btn.isEnabled())
        self.assertTrue(dialog._cancel_btn.isEnabled())

        dialog.update_from_event(
            SimpleNamespace(
                event_type="item_progress",
                item_total=2,
                asset_id="asset-1",
                asset_label="sprite_a.png",
                queue_status="processing",
                stage="exporting",
                queue_progress=0.9,
                overall_progress=0.45,
            )
        )
        self.assertEqual(2, dialog.queue_list.count())
        self.assertEqual("sprite_a.png - processing (exporting 90%)", dialog.queue_list.item(0).text())
        self.assertIn("exporting", dialog._current_stage_label.text().lower())

        dialog.update_from_event(
            SimpleNamespace(
                event_type="item_complete",
                item_total=2,
                asset_id="asset-2",
                asset_label="sprite_b.png",
                queue_status="done",
                queue_progress=1.0,
                overall_progress=1.0,
                processed_count=2,
                failed_count=0,
            )
        )
        self.assertEqual("sprite_b.png - done", dialog.queue_list.item(1).text())

        dialog.update_from_event(
            SimpleNamespace(
                event_type="batch_complete",
                item_total=2,
                overall_progress=1.0,
                processed_count=2,
                failed_count=0,
            )
        )
        self.assertTrue(dialog._run_btn.isEnabled())
        self.assertFalse(dialog._cancel_btn.isEnabled())
        self.assertIn("complete", dialog._current_stage_label.text().lower())

    def test_update_from_event_tolerates_malformed_payload(self) -> None:
        dialog = BatchManagerDialog()
        dialog.set_queue_assets([("asset-1", "sprite_a.png")])

        # Should not raise even if upstream event payload is malformed.
        dialog.update_from_event(
            SimpleNamespace(
                event_type="item_progress",
                item_total=None,
                asset_id="asset-1",
                queue_status="processing",
                stage=123,
                queue_progress="not-a-float",
                overall_progress="bad",
                processed_count="bad",
                failed_count="bad",
            )
        )

        self.assertTrue(dialog._summary_label.text())

    def test_select_failed_items_targets_only_failed_rows_after_run(self) -> None:
        dialog = BatchManagerDialog()
        dialog.set_queue_assets([
            ("asset-1", "sprite_a.png"),
            ("asset-2", "sprite_b.png"),
        ])

        dialog.update_from_event(
            SimpleNamespace(
                event_type="batch_start",
                item_total=2,
                overall_progress=0.0,
            )
        )
        dialog.update_from_event(
            SimpleNamespace(
                event_type="item_complete",
                item_total=2,
                asset_id="asset-1",
                asset_label="sprite_a.png",
                queue_status="done",
                overall_progress=0.5,
                processed_count=1,
                failed_count=0,
            )
        )
        dialog.update_from_event(
            SimpleNamespace(
                event_type="item_complete",
                item_total=2,
                asset_id="asset-2",
                asset_label="sprite_b.png",
                queue_status="failed",
                overall_progress=1.0,
                processed_count=2,
                failed_count=1,
            )
        )
        dialog.update_from_event(
            SimpleNamespace(
                event_type="batch_complete",
                item_total=2,
                overall_progress=1.0,
                processed_count=2,
                failed_count=1,
            )
        )

        self.assertTrue(dialog._select_failed_btn.isEnabled())
        dialog.select_failed_items()
        self.assertEqual(["asset-2"], dialog.selected_asset_ids())
        self.assertIn("failed: 1", dialog._summary_label.text().lower())

    def test_update_from_report_includes_skipped_count_in_summary(self) -> None:
        dialog = BatchManagerDialog()
        dialog.set_queue_assets([
            ("asset-1", "sprite_a.png"),
            ("asset-2", "sprite_b.png"),
        ])

        report = SimpleNamespace(
            items=[
                SimpleNamespace(
                    asset_id="asset-1",
                    queue_item=SimpleNamespace(status=SimpleNamespace(value="done")),
                ),
                SimpleNamespace(
                    asset_id="asset-2",
                    queue_item=SimpleNamespace(status=SimpleNamespace(value="skipped")),
                ),
            ],
            failed_count=0,
            skipped_count=1,
        )

        dialog.update_from_report(report)

        self.assertIn("skipped: 1", dialog._summary_label.text().lower())

    def test_update_from_report_shows_latest_issue_detail(self) -> None:
        dialog = BatchManagerDialog()
        dialog.set_queue_assets([
            ("asset-1", "sprite_a.png"),
        ])

        report = SimpleNamespace(
            items=[
                SimpleNamespace(
                    asset_id="asset-1",
                    queue_item=SimpleNamespace(
                        status=SimpleNamespace(value="failed"),
                        notes="Light processing failed",
                    ),
                    error="Light processing failed",
                ),
            ],
            failed_count=1,
            skipped_count=0,
        )

        dialog.update_from_report(report)

        self.assertIn("sprite_a.png", dialog._details_label.text())
        self.assertIn("light processing failed", dialog._details_label.text().lower())


if __name__ == "__main__":
    unittest.main()




