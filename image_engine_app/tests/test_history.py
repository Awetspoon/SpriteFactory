"""Tests for undo/redo history, debounced slider grouping, snapshots, and branches."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest


from image_engine_app.engine.models import HistoryAffectsView  # noqa: E402
from image_engine_app.engine.process.history import HistoryEngine  # noqa: E402


def _dt(hour: int, minute: int, second: int = 0, ms: int = 0) -> datetime:
    return datetime(2026, 2, 23, hour, minute, second, ms * 1000, tzinfo=timezone.utc)


class HistoryEngineTests(unittest.TestCase):
    def test_record_apply_and_undo_redo(self) -> None:
        engine = HistoryEngine()

        engine.record_apply(
            label="Apply cleanup",
            state_snapshot={"cleanup": {"denoise": 0.2}},
            affects_view=HistoryAffectsView.CURRENT,
            timestamp=_dt(20, 0),
        )
        engine.record_apply(
            label="Apply sharpen",
            state_snapshot={"detail": {"sharpen_amount": 0.5}},
            affects_view=HistoryAffectsView.FINAL,
            timestamp=_dt(20, 1),
        )

        self.assertEqual(engine.history_state.pointer, 1)
        self.assertEqual(engine.current_step().label, "Apply sharpen")

        undone = engine.undo()
        self.assertEqual(undone, {"cleanup": {"denoise": 0.2}})
        self.assertEqual(engine.history_state.pointer, 0)

        undone_to_start = engine.undo()
        self.assertIsNone(undone_to_start)
        self.assertEqual(engine.history_state.pointer, -1)

        redone = engine.redo()
        self.assertEqual(redone, {"cleanup": {"denoise": 0.2}})
        self.assertEqual(engine.history_state.pointer, 0)

        redone_again = engine.redo()
        self.assertEqual(redone_again, {"detail": {"sharpen_amount": 0.5}})
        self.assertEqual(engine.history_state.pointer, 1)

    def test_slider_updates_debounce_grouping(self) -> None:
        engine = HistoryEngine(debounce_window_ms=250)

        first = engine.record_slider_update(
            control_key="brightness",
            state_snapshot={"color": {"brightness": 0.1}},
            affects_view=HistoryAffectsView.CURRENT,
            timestamp=_dt(20, 10, 0, 0),
        )
        second = engine.record_slider_update(
            control_key="brightness",
            state_snapshot={"color": {"brightness": 0.2}},
            affects_view=HistoryAffectsView.CURRENT,
            timestamp=_dt(20, 10, 0, 100),
        )
        third = engine.record_slider_update(
            control_key="brightness",
            state_snapshot={"color": {"brightness": 0.3}},
            affects_view=HistoryAffectsView.CURRENT,
            timestamp=_dt(20, 10, 0, 400),
        )

        self.assertEqual(len(engine.history_state.steps), 2)
        self.assertEqual(engine.history_state.steps[0].label, "Adjust brightness")
        self.assertEqual(engine.history_state.steps[0].state_snapshot, {"color": {"brightness": 0.2}})
        self.assertEqual(engine.history_state.steps[1].state_snapshot, {"color": {"brightness": 0.3}})
        self.assertEqual(first.label, "Adjust brightness")
        self.assertEqual(second.label, "Adjust brightness")
        self.assertEqual(third.label, "Adjust brightness")

    def test_branch_capture_when_recording_after_undo(self) -> None:
        engine = HistoryEngine()
        engine.record_apply(
            label="Step 1",
            state_snapshot={"s": 1},
            affects_view=HistoryAffectsView.BOTH,
            timestamp=_dt(21, 0, 0),
        )
        engine.record_apply(
            label="Step 2",
            state_snapshot={"s": 2},
            affects_view=HistoryAffectsView.BOTH,
            timestamp=_dt(21, 0, 1),
        )
        engine.record_apply(
            label="Step 3",
            state_snapshot={"s": 3},
            affects_view=HistoryAffectsView.BOTH,
            timestamp=_dt(21, 0, 2),
        )

        engine.undo()  # pointer -> step 2
        engine.record_apply(
            label="Step 2b",
            state_snapshot={"s": 22},
            affects_view=HistoryAffectsView.BOTH,
            timestamp=_dt(21, 0, 3),
        )

        self.assertEqual([step.label for step in engine.history_state.steps], ["Step 1", "Step 2", "Step 2b"])
        self.assertEqual(engine.history_state.pointer, 2)

        branches = engine.list_named_branches()
        self.assertEqual(len(branches), 1)
        self.assertEqual(branches[0].name, "branch_001")
        self.assertEqual([step.label for step in branches[0].abandoned_steps], ["Step 3"])
        self.assertEqual(branches[0].base_pointer, 1)

    def test_named_snapshots_save_and_restore(self) -> None:
        engine = HistoryEngine()

        snap1 = engine.save_named_snapshot("before_cleanup", {"cleanup": {"denoise": 0.0}}, timestamp=_dt(22, 0))
        snap2 = engine.save_named_snapshot("after_cleanup", {"cleanup": {"denoise": 0.3}}, timestamp=_dt(22, 1))

        self.assertEqual(snap1.name, "before_cleanup")
        self.assertEqual(engine.get_named_snapshot("after_cleanup").state_snapshot, {"cleanup": {"denoise": 0.3}})
        listed = engine.list_named_snapshots()
        self.assertEqual([snap.name for snap in listed], ["before_cleanup", "after_cleanup"])


if __name__ == "__main__":
    unittest.main()



