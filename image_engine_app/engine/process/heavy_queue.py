"""Heavy tool queue engine with replace/cancel behavior (Prompt 10)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
import threading
import time

from engine.models import HeavyJobSpec, HeavyJobStatus, HeavyTool


ProgressCallback = Callable[[HeavyJobSpec], None]


class HeavyQueueEngine:
    """Sequential heavy job queue with last-setting-wins replacement for queued jobs."""

    def __init__(
        self,
        *,
        sleep_func: Callable[[float], None] | None = None,
        now_func: Callable[[], datetime] | None = None,
    ) -> None:
        self._sleep = sleep_func or time.sleep
        self._now = now_func or datetime.now
        self._lock = threading.RLock()
        self._jobs: list[HeavyJobSpec] = []
        self._cancelled_ids: set[str] = set()

    def list_jobs(self) -> list[HeavyJobSpec]:
        with self._lock:
            return [replace(job) for job in self._jobs]

    def get_job(self, job_id: str) -> HeavyJobSpec | None:
        with self._lock:
            for job in self._jobs:
                if job.id == job_id:
                    return replace(job)
        return None

    def enqueue_or_replace(self, job: HeavyJobSpec) -> HeavyJobSpec:
        """
        Enqueue a heavy job and replace any queued job for the same tool.

        Running jobs are not replaced; only queued jobs honor last-setting-wins.
        """

        with self._lock:
            replaced_index = None
            for idx, existing in enumerate(self._jobs):
                if existing.tool is job.tool and existing.status is HeavyJobStatus.QUEUED:
                    replaced_index = idx
                    break

            queued_job = replace(
                job,
                status=HeavyJobStatus.QUEUED,
                progress=0.0,
                started_at=None,
                ended_at=None,
                error_message=None,
            )

            if replaced_index is not None:
                self._jobs[replaced_index] = queued_job
            else:
                self._jobs.append(queued_job)

            return replace(queued_job)

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a queued or running job by id."""

        with self._lock:
            self._cancelled_ids.add(job_id)
            for job in self._jobs:
                if job.id != job_id:
                    continue

                if job.status is HeavyJobStatus.DONE:
                    return False

                if job.status in {HeavyJobStatus.QUEUED, HeavyJobStatus.RUNNING}:
                    job.status = HeavyJobStatus.CANCELLED
                    job.error_message = None
                    if job.started_at is None:
                        job.started_at = None
                    job.ended_at = self._now()
                    return True

                if job.status is HeavyJobStatus.CANCELLED:
                    return True

                return False
            return False

    def run_all(
        self,
        *,
        progress_steps: int = 5,
        step_delay_seconds: float = 0.01,
        progress_callback: ProgressCallback | None = None,
        task_runner: Callable[[HeavyJobSpec], None] | None = None,
    ) -> list[HeavyJobSpec]:
        """Run all queued jobs sequentially with simulated progress."""

        if progress_steps <= 0:
            raise ValueError("progress_steps must be >= 1")

        completed_ids: list[str] = []
        while True:
            job_id = self._next_queued_job_id()
            if job_id is None:
                break
            self._run_single_job(
                job_id,
                progress_steps=progress_steps,
                step_delay_seconds=step_delay_seconds,
                progress_callback=progress_callback,
                task_runner=task_runner,
            )
            completed_ids.append(job_id)

        return [job for job in (self.get_job(job_id) for job_id in completed_ids) if job is not None]

    def _next_queued_job_id(self) -> str | None:
        with self._lock:
            for job in self._jobs:
                if job.status is HeavyJobStatus.QUEUED:
                    return job.id
        return None

    def _run_single_job(
        self,
        job_id: str,
        *,
        progress_steps: int,
        step_delay_seconds: float,
        progress_callback: ProgressCallback | None,
        task_runner: Callable[[HeavyJobSpec], None] | None,
    ) -> None:
        with self._lock:
            job = self._job_ref(job_id)
            if job is None:
                return
            if job.id in self._cancelled_ids or job.status is HeavyJobStatus.CANCELLED:
                job.status = HeavyJobStatus.CANCELLED
                if job.ended_at is None:
                    job.ended_at = self._now()
                self._emit(job, progress_callback)
                return

            job.status = HeavyJobStatus.RUNNING
            job.started_at = self._now()
            job.ended_at = None
            job.progress = 0.0
            self._emit(job, progress_callback)

        for step in range(1, progress_steps + 1):
            self._sleep(step_delay_seconds)

            with self._lock:
                job = self._job_ref(job_id)
                if job is None:
                    return
                if job.id in self._cancelled_ids or job.status is HeavyJobStatus.CANCELLED:
                    job.status = HeavyJobStatus.CANCELLED
                    job.ended_at = self._now()
                    self._emit(job, progress_callback)
                    return

                job.progress = step / progress_steps
                self._emit(job, progress_callback)

        try:
            if task_runner is not None:
                snapshot = self.get_job(job_id)
                if snapshot is not None:
                    task_runner(snapshot)
            with self._lock:
                job = self._job_ref(job_id)
                if job is None:
                    return
                if job.id in self._cancelled_ids or job.status is HeavyJobStatus.CANCELLED:
                    job.status = HeavyJobStatus.CANCELLED
                else:
                    job.status = HeavyJobStatus.DONE
                    job.progress = 1.0
                job.ended_at = self._now()
                self._emit(job, progress_callback)
        except Exception as exc:  # pragma: no cover - kept for engine behavior completeness
            with self._lock:
                job = self._job_ref(job_id)
                if job is None:
                    return
                job.status = HeavyJobStatus.ERROR
                job.error_message = str(exc)
                job.ended_at = self._now()
                self._emit(job, progress_callback)

    def _job_ref(self, job_id: str) -> HeavyJobSpec | None:
        for job in self._jobs:
            if job.id == job_id:
                return job
        return None

    @staticmethod
    def _emit(job: HeavyJobSpec, callback: ProgressCallback | None) -> None:
        if callback is not None:
            callback(replace(job))


def queue_job_for_tool(
    engine: HeavyQueueEngine,
    *,
    tool: HeavyTool,
    params: dict,
    job_id: str | None = None,
) -> HeavyJobSpec:
    """Convenience helper to enqueue a HeavyJobSpec for a tool."""

    job = HeavyJobSpec(id=job_id or HeavyJobSpec().id, tool=tool, params=dict(params))
    return engine.enqueue_or_replace(job)

