"""Tests for batch queue state helpers."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


from image_engine_app.ui.windows.batch_queue_state import (  # noqa: E402
    BatchQueueState,
    build_idle_summary,
    build_run_summary,
    format_event_status,
)


class BatchQueueStateTests(unittest.TestCase):
    def test_set_assets_dedupes_and_defaults_to_queued(self) -> None:
        state = BatchQueueState()

        rows = state.set_assets([
            ("asset-1", "sprite_a.png"),
            ("", "skip-me"),
            ("asset-1", "duplicate.png"),
            ("asset-2", ""),
        ])

        self.assertEqual(["asset-1", "asset-2"], [row.asset_id for row in rows])
        self.assertEqual("sprite_a.png - queued", rows[0].text)
        self.assertEqual("asset-2 - queued", rows[1].text)

    def test_failed_asset_ids_follow_latest_status(self) -> None:
        state = BatchQueueState()
        state.set_assets([
            ("asset-1", "sprite_a.png"),
            ("asset-2", "sprite_b.png"),
            ("asset-3", "sprite_c.png"),
        ])

        state.upsert(asset_id="asset-1", label="sprite_a.png", status="done")
        state.upsert(asset_id="asset-2", label="sprite_b.png", status="failed")
        state.upsert(asset_id="asset-3", label="sprite_c.png", status="error while exporting")

        self.assertEqual(["asset-2", "asset-3"], state.failed_asset_ids())
        self.assertEqual(
            "3 item(s) in batch queue | selected: 1 | failed: 2",
            build_idle_summary(3, 1, failed=2),
        )

    def test_skipped_asset_ids_and_summary_are_reported(self) -> None:
        state = BatchQueueState()
        state.set_assets([
            ("asset-1", "sprite_a.png"),
            ("asset-2", "sprite_b.png"),
        ])

        state.upsert(asset_id="asset-1", label="sprite_a.png", status="skipped")
        state.upsert(asset_id="asset-2", label="sprite_b.png", status="done")

        self.assertEqual(["asset-1"], state.skipped_asset_ids())
        self.assertEqual(
            "2 item(s) in batch queue | selected: 1 | skipped: 1",
            build_idle_summary(2, 1, skipped=1),
        )
        self.assertEqual(
            "Processed: 1/2 | Failed: 0 | Skipped: 1",
            build_run_summary(processed=1, total=2, failed=0, skipped=1),
        )

    def test_format_event_status_includes_stage_percent_and_tolerates_bad_progress(self) -> None:
        self.assertEqual(
            "processing (exporting 75%)",
            format_event_status(
                event_type="item_progress",
                queue_status="processing",
                stage="exporting",
                queue_progress=0.75,
            ),
        )
        self.assertEqual(
            "processing (exporting)",
            format_event_status(
                event_type="item_progress",
                queue_status="processing",
                stage="exporting",
                queue_progress="not-a-number",
            ),
        )


if __name__ == "__main__":
    unittest.main()


