"""Tests for the heavy job queue engine replace/cancel behavior."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.models import HeavyJobSpec, HeavyJobStatus, HeavyTool  # noqa: E402
from engine.process.heavy_queue import HeavyQueueEngine  # noqa: E402


class HeavyQueueTests(unittest.TestCase):
    def test_enqueue_or_replace_queued_job_last_setting_wins(self) -> None:
        engine = HeavyQueueEngine(sleep_func=lambda _: None)

        first = engine.enqueue_or_replace(
            HeavyJobSpec(id="job-1", tool=HeavyTool.AI_UPSCALE, params={"factor": 2})
        )
        second = engine.enqueue_or_replace(
            HeavyJobSpec(id="job-2", tool=HeavyTool.AI_UPSCALE, params={"factor": 4})
        )
        other = engine.enqueue_or_replace(
            HeavyJobSpec(id="job-3", tool=HeavyTool.BG_REMOVE, params={"strength": 0.5})
        )

        self.assertEqual(first.id, "job-1")
        self.assertEqual(second.id, "job-2")
        self.assertEqual(other.id, "job-3")

        jobs = engine.list_jobs()
        self.assertEqual(len(jobs), 2)
        upscale = next(job for job in jobs if job.tool is HeavyTool.AI_UPSCALE)
        self.assertEqual(upscale.id, "job-2")
        self.assertEqual(upscale.params["factor"], 4)
        self.assertEqual(upscale.status, HeavyJobStatus.QUEUED)

    def test_cancel_queued_job_prevents_execution(self) -> None:
        engine = HeavyQueueEngine(sleep_func=lambda _: None)
        engine.enqueue_or_replace(HeavyJobSpec(id="job-1", tool=HeavyTool.AI_UPSCALE, params={"factor": 4}))
        engine.enqueue_or_replace(HeavyJobSpec(id="job-2", tool=HeavyTool.AI_DEBLUR, params={"strength": 0.6}))

        self.assertTrue(engine.cancel_job("job-1"))
        completed = engine.run_all(progress_steps=3, step_delay_seconds=0.0)

        job1 = engine.get_job("job-1")
        job2 = engine.get_job("job-2")
        self.assertIsNotNone(job1)
        self.assertIsNotNone(job2)
        self.assertEqual(job1.status, HeavyJobStatus.CANCELLED)
        self.assertEqual(job2.status, HeavyJobStatus.DONE)
        self.assertEqual([job.id for job in completed], ["job-2"])

    def test_cancel_running_job_via_progress_callback(self) -> None:
        engine = HeavyQueueEngine(sleep_func=lambda _: None)
        engine.enqueue_or_replace(HeavyJobSpec(id="job-1", tool=HeavyTool.AI_UPSCALE, params={"factor": 4}))

        progress_events: list[tuple[str, str, float]] = []

        def on_progress(job):  # noqa: ANN001
            progress_events.append((job.id, job.status.value, job.progress))
            if job.id == "job-1" and job.status is HeavyJobStatus.RUNNING and job.progress >= 0.5:
                engine.cancel_job(job.id)

        engine.run_all(progress_steps=4, step_delay_seconds=0.0, progress_callback=on_progress)

        job = engine.get_job("job-1")
        self.assertIsNotNone(job)
        self.assertEqual(job.status, HeavyJobStatus.CANCELLED)
        self.assertTrue(any(status == "running" for _, status, _ in progress_events))
        self.assertTrue(any(status == "cancelled" for _, status, _ in progress_events))

    def test_progress_callback_receives_done_status_and_monotonic_progress(self) -> None:
        engine = HeavyQueueEngine(sleep_func=lambda _: None)
        engine.enqueue_or_replace(HeavyJobSpec(id="job-1", tool=HeavyTool.BG_REMOVE, params={"strength": 0.4}))

        seen_progress: list[float] = []

        def on_progress(job):  # noqa: ANN001
            if job.id == "job-1":
                seen_progress.append(job.progress)

        engine.run_all(progress_steps=5, step_delay_seconds=0.0, progress_callback=on_progress)
        job = engine.get_job("job-1")

        self.assertIsNotNone(job)
        self.assertEqual(job.status, HeavyJobStatus.DONE)
        self.assertGreaterEqual(len(seen_progress), 2)
        self.assertEqual(seen_progress[-1], 1.0)
        self.assertEqual(seen_progress, sorted(seen_progress))


if __name__ == "__main__":
    unittest.main()

