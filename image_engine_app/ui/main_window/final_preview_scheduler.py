"""Debounced background rendering for the interactive Final preview."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal, Slot


class _PreviewRenderSignals(QObject):
    finished = Signal(int, str, object, object, str)


class _PreviewRenderJob(QRunnable):
    """Render one immutable asset snapshot away from the Qt UI thread."""

    def __init__(
        self,
        *,
        renderer: Callable[[object, int], object],
        generation: int,
        reason: str,
        asset_snapshot: object,
    ) -> None:
        super().__init__()
        self.signals = _PreviewRenderSignals()
        self._renderer = renderer
        self._generation = int(generation)
        self._reason = str(reason)
        self._asset_snapshot = asset_snapshot

    @Slot()
    def run(self) -> None:
        try:
            result = self._renderer(self._asset_snapshot, self._generation)
            error = ""
        except Exception as exc:
            result = None
            error = str(exc)
        self.signals.finished.emit(
            self._generation,
            self._reason,
            self._asset_snapshot,
            result,
            error,
        )


class FinalPreviewScheduler(QObject):
    """Coalesce control changes and publish only the newest completed render."""

    preview_ready = Signal(str, object, object)
    preview_failed = Signal(str, str)

    STATIC_DEBOUNCE_MS = 140
    ANIMATED_DEBOUNCE_MS = 260

    def __init__(
        self,
        *,
        renderer: Callable[[object, int], object],
        active_asset_provider: Callable[[], object | None],
        parent: QObject | None = None,
        thread_pool: QThreadPool | None = None,
    ) -> None:
        super().__init__(parent)
        self._renderer = renderer
        self._active_asset_provider = active_asset_provider
        self._owns_thread_pool = thread_pool is None
        self._thread_pool = thread_pool or QThreadPool(self)
        if self._owns_thread_pool:
            self._thread_pool.setMaxThreadCount(1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._start_pending_render)

        self._generation = 0
        self._observed_asset_id = self._asset_id(self._active_asset_provider())
        self._pending_generation: int | None = None
        self._pending_asset_id: str | None = None
        self._pending_reason = "edit"
        self._render_running = False
        self._active_job: _PreviewRenderJob | None = None

    def note_active_asset(self, asset: object | None) -> None:
        """Invalidate work when the workspace selection changes."""

        asset_id = self._asset_id(asset)
        if asset_id == self._observed_asset_id:
            return
        self._observed_asset_id = asset_id
        self.cancel_pending()

    def request(self, asset: object, *, immediate: bool = False, reason: str = "edit") -> None:
        """Queue the latest asset state, replacing any older pending request."""

        asset_id = self._asset_id(asset)
        if asset_id is None:
            return
        if asset_id != self._observed_asset_id:
            self.note_active_asset(asset)

        self._generation += 1
        self._pending_generation = self._generation
        self._pending_asset_id = asset_id
        self._pending_reason = str(reason or "edit")

        capabilities = getattr(asset, "capabilities", None)
        is_animated = bool(getattr(capabilities, "is_animated", False))
        delay = 0 if immediate else (
            self.ANIMATED_DEBOUNCE_MS if is_animated else self.STATIC_DEBOUNCE_MS
        )
        self._timer.start(delay)

    def cancel_pending(self) -> None:
        """Invalidate queued and running results without blocking the UI."""

        self._generation += 1
        self._pending_generation = None
        self._pending_asset_id = None
        self._timer.stop()

    def shutdown(self, *, wait: bool = False) -> None:
        """Stop accepting pending work and optionally wait for the active render."""

        self.cancel_pending()
        if self._owns_thread_pool:
            self._thread_pool.clear()
            if wait:
                self._thread_pool.waitForDone()

    @property
    def is_busy(self) -> bool:
        return self._render_running or self._pending_generation is not None

    @Slot()
    def _start_pending_render(self) -> None:
        if self._render_running or self._pending_generation is None:
            return

        active_asset = self._active_asset_provider()
        if self._asset_id(active_asset) != self._pending_asset_id:
            self._pending_generation = None
            self._pending_asset_id = None
            return

        generation = self._pending_generation
        reason = self._pending_reason
        snapshot = deepcopy(active_asset)
        self._pending_generation = None
        self._pending_asset_id = None
        self._render_running = True

        job = _PreviewRenderJob(
            renderer=self._renderer,
            generation=generation,
            reason=reason,
            asset_snapshot=snapshot,
        )
        job.signals.finished.connect(
            self._on_render_finished,
            Qt.ConnectionType.QueuedConnection,
        )
        self._active_job = job
        self._thread_pool.start(job)

    @Slot(int, str, object, object, str)
    def _on_render_finished(
        self,
        generation: int,
        reason: str,
        snapshot: object,
        result: object,
        error: str,
    ) -> None:
        self._render_running = False
        self._active_job = None

        active_asset = self._active_asset_provider()
        is_current = (
            int(generation) == self._generation
            and self._asset_id(active_asset) == self._asset_id(snapshot)
        )
        if not is_current:
            self._discard_temporary_output(snapshot)
        elif error:
            self._discard_temporary_output(snapshot)
            self.preview_failed.emit(reason, error)
        else:
            self.preview_ready.emit(reason, snapshot, result)

        if self._pending_generation is not None:
            self._timer.start(0)

    @staticmethod
    def _asset_id(asset: object | None) -> str | None:
        raw_value = getattr(asset, "id", None)
        if not isinstance(raw_value, str):
            return None
        value = raw_value.strip()
        return value or None

    @staticmethod
    def _discard_temporary_output(snapshot: object) -> None:
        raw_path = getattr(snapshot, "derived_final_path", None)
        if not isinstance(raw_path, str) or not raw_path.strip():
            return
        path = Path(raw_path)
        if not path.name.startswith("preview-"):
            return
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
