"""Tests for heavy CPU/GPU backend selection."""

from __future__ import annotations

import unittest

from image_engine_app.engine.models import HeavyJobSpec, HeavyTool
from image_engine_app.engine.process.performance_backend import (
    PerformanceAvailability,
    PerformanceBackend,
)


class PerformanceBackendTests(unittest.TestCase):
    def test_gpu_request_falls_back_when_backend_is_unavailable(self) -> None:
        backend = PerformanceBackend(
            availability=PerformanceAvailability(
                cpu_available=True,
                gpu_available=False,
                gpu_backend_label=None,
                gpu_disabled_reason="GPU backend not installed",
            )
        )

        resolution = backend.resolve_mode("gpu")

        self.assertEqual(resolution.requested_mode, "gpu")
        self.assertEqual(resolution.effective_mode, "cpu")
        self.assertTrue(resolution.fell_back)
        self.assertIn("using CPU", resolution.status_message)

    def test_gpu_request_stays_on_gpu_when_backend_is_available(self) -> None:
        backend = PerformanceBackend(
            availability=PerformanceAvailability(
                cpu_available=True,
                gpu_available=True,
                gpu_backend_label="Fake GPU",
                gpu_disabled_reason=None,
            )
        )

        resolution = backend.resolve_mode("gpu", tool=HeavyTool.AI_UPSCALE)

        self.assertEqual(resolution.requested_mode, "gpu")
        self.assertEqual(resolution.effective_mode, "gpu")
        self.assertFalse(resolution.fell_back)
        self.assertIn("Fake GPU", resolution.status_message)

    def test_run_heavy_job_uses_same_resolution_rules(self) -> None:
        backend = PerformanceBackend(
            availability=PerformanceAvailability(
                cpu_available=True,
                gpu_available=False,
                gpu_backend_label=None,
                gpu_disabled_reason="GPU backend not installed",
            )
        )
        job = HeavyJobSpec(id="job-1", tool=HeavyTool.BG_REMOVE, params={"strength": 0.5})

        resolution = backend.run_heavy_job(job, requested_mode="gpu")

        self.assertEqual(resolution.effective_mode, "cpu")


if __name__ == "__main__":
    unittest.main()
