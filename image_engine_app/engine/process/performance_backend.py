"""Runtime selection for heavy CPU/GPU processing backends."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from typing import Callable

from image_engine_app.engine.models import HeavyJobSpec, HeavyTool


CPU_MODE = "cpu"
GPU_MODE = "gpu"
_GPU_PROVIDERS = {
    "CUDAExecutionProvider": "ONNX Runtime CUDA",
    "DmlExecutionProvider": "ONNX Runtime DirectML",
    "ROCMExecutionProvider": "ONNX Runtime ROCm",
}
_GPU_MANAGED_TOOLS = frozenset(
    {
        HeavyTool.AI_UPSCALE,
        HeavyTool.AI_DEBLUR,
        HeavyTool.BG_REMOVE,
        HeavyTool.AI_EXTEND,
    }
)


@dataclass(frozen=True)
class PerformanceAvailability:
    """Detected heavy-processing backend availability for the current machine."""

    cpu_available: bool = True
    gpu_available: bool = False
    gpu_backend_label: str | None = None
    gpu_disabled_reason: str | None = "GPU backend not installed"


@dataclass(frozen=True)
class PerformanceModeResolution:
    """Resolved backend choice after applying availability and tool support."""

    requested_mode: str
    effective_mode: str
    gpu_available: bool
    gpu_backend_label: str | None = None
    fallback_reason: str | None = None

    @property
    def fell_back(self) -> bool:
        return self.requested_mode != self.effective_mode

    @property
    def status_message(self) -> str:
        if self.effective_mode == GPU_MODE and self.gpu_backend_label:
            return f"Performance mode set to GPU ({self.gpu_backend_label})"
        if self.effective_mode == GPU_MODE:
            return "Performance mode set to GPU"
        if self.fell_back and self.fallback_reason:
            return f"{self.fallback_reason}; using CPU"
        return "Performance mode set to CPU"


def detect_performance_availability() -> PerformanceAvailability:
    """Best-effort backend detection for the current Python environment."""

    onnxruntime_spec = importlib.util.find_spec("onnxruntime")
    if onnxruntime_spec is not None:
        try:
            import onnxruntime as ort  # type: ignore

            providers = {str(name) for name in ort.get_available_providers()}
            for provider_name, label in _GPU_PROVIDERS.items():
                if provider_name in providers:
                    return PerformanceAvailability(
                        cpu_available=True,
                        gpu_available=True,
                        gpu_backend_label=label,
                        gpu_disabled_reason=None,
                    )
        except Exception:
            pass

    torch_spec = importlib.util.find_spec("torch")
    if torch_spec is not None:
        try:
            import torch  # type: ignore

            if bool(torch.cuda.is_available()):
                return PerformanceAvailability(
                    cpu_available=True,
                    gpu_available=True,
                    gpu_backend_label="PyTorch CUDA",
                    gpu_disabled_reason=None,
                )
        except Exception:
            pass

    return PerformanceAvailability()


class PerformanceBackend:
    """Shared heavy-processing backend selector used by single-item and batch flows."""

    def __init__(
        self,
        *,
        availability: PerformanceAvailability | None = None,
        availability_loader: Callable[[], PerformanceAvailability] | None = None,
    ) -> None:
        self._availability = availability or (availability_loader or detect_performance_availability)()

    @property
    def availability(self) -> PerformanceAvailability:
        return self._availability

    def resolve_mode(self, requested_mode: str, *, tool: HeavyTool | None = None) -> PerformanceModeResolution:
        requested = GPU_MODE if str(requested_mode).strip().lower() == GPU_MODE else CPU_MODE

        if requested == GPU_MODE and not self._availability.gpu_available:
            fallback_reason = self._availability.gpu_disabled_reason or "GPU backend unavailable"
            return PerformanceModeResolution(
                requested_mode=requested,
                effective_mode=CPU_MODE,
                gpu_available=False,
                gpu_backend_label=self._availability.gpu_backend_label,
                fallback_reason=fallback_reason,
            )

        if requested == GPU_MODE and tool is not None and tool not in _GPU_MANAGED_TOOLS:
            return PerformanceModeResolution(
                requested_mode=requested,
                effective_mode=CPU_MODE,
                gpu_available=self._availability.gpu_available,
                gpu_backend_label=self._availability.gpu_backend_label,
                fallback_reason=f"{tool.value} does not support GPU execution",
            )

        return PerformanceModeResolution(
            requested_mode=requested,
            effective_mode=requested,
            gpu_available=self._availability.gpu_available,
            gpu_backend_label=self._availability.gpu_backend_label,
            fallback_reason=None,
        )

    def run_heavy_job(self, job: HeavyJobSpec, *, requested_mode: str) -> PerformanceModeResolution:
        """Resolve the backend for a heavy job.

        The heavy queue still owns progress/status behavior; this layer makes the CPU/GPU
        choice explicit so future backend implementations can plug in here cleanly.
        """

        return self.resolve_mode(requested_mode, tool=job.tool)
