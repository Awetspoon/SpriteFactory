"""Batch workflow coordinator for the main window."""

from __future__ import annotations

from copy import deepcopy
import logging
from typing import Any

from app.ui_controller import ImageEngineUIController
from engine.models import AssetRecord

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot


LOGGER = logging.getLogger("image_engine_app.batch.coordinator")


class _BatchRunWorker(QObject):
    """Run a batch operation off the UI thread and forward progress events."""

    progress_event = Signal(object)
    finished_report = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        *,
        controller: ImageEngineUIController,
        assets: list[AssetRecord],
        preview_skip_mode: bool,
        auto_export: bool,
        auto_preset: bool,
        export_name_template: str,
        avoid_overwrite: bool,
        export_dir: str | None,
    ) -> None:
        super().__init__()
        self._controller = controller
        self._assets = list(assets)
        self._preview_skip_mode = preview_skip_mode
        self._auto_export = auto_export
        self._auto_preset = auto_preset
        self._export_name_template = export_name_template
        self._avoid_overwrite = avoid_overwrite
        self._export_dir = export_dir
        self._cancel_requested = False

    def request_cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        LOGGER.info(
            "Batch worker started: items=%s auto_export=%s auto_preset=%s preview_skip=%s export_dir=%s",
            len(self._assets),
            self._auto_export,
            self._auto_preset,
            self._preview_skip_mode,
            self._export_dir,
        )
        try:
            report = self._controller.run_batch(
                self._assets,
                preview_skip_mode=self._preview_skip_mode,
                auto_export=self._auto_export,
                auto_preset=self._auto_preset,
                export_name_template=self._export_name_template,
                avoid_overwrite=self._avoid_overwrite,
                export_dir=self._export_dir,
                event_callback=self.progress_event.emit,
                cancel_requested=lambda: bool(self._cancel_requested),
            )
        except Exception as exc:
            LOGGER.exception("Batch worker crashed: %s", exc)
            self.failed.emit(str(exc))
            return

        LOGGER.info(
            "Batch worker finished: processed=%s failed=%s cancelled=%s",
            int(getattr(report, "processed_count", 0)),
            int(getattr(report, "failed_count", 0)),
            bool(getattr(report, "cancelled", False)),
        )
        self.finished_report.emit(report)


class _BatchUiBridge(QObject):
    """Marshal worker-thread signals onto the UI thread safely."""

    progress_on_ui = Signal(object)
    finished_on_ui = Signal(object)
    failed_on_ui = Signal(str)

    @Slot(object)
    def recv_progress(self, event: object) -> None:
        self.progress_on_ui.emit(event)

    @Slot(object)
    def recv_finished(self, report: object) -> None:
        self.finished_on_ui.emit(report)

    @Slot(str)
    def recv_failed(self, message: str) -> None:
        self.failed_on_ui.emit(message)


class BatchCoordinator:
    """Owns batch-run orchestration and worker lifecycle for the main window."""

    def __init__(self, window: Any) -> None:
        self._window = window
        bridge_parent = window if isinstance(window, QObject) else None
        self._ui_bridge = _BatchUiBridge(bridge_parent)
        self._ui_bridge.progress_on_ui.connect(self.on_progress_event)
        self._ui_bridge.finished_on_ui.connect(self.on_run_finished)
        self._ui_bridge.failed_on_ui.connect(self.on_run_failed)

    def show_manager(self) -> None:
        self._window._sync_batch_dialog_items()
        self._window.batch_manager_dialog.show()
        self._window.batch_manager_dialog.raise_()
        self._window.batch_manager_dialog.activateWindow()

    def on_run_requested(self, options_obj: object) -> None:
        if self._window.controller is None:
            self._window._status("Batch run unavailable: controller not configured")
            return
        if not self._window._workspace_assets:
            self._window._status("Batch run skipped: no assets in workspace")
            return
        if self._window._batch_thread is not None:
            self._window._status("Batch run already in progress")
            return

        auto_preset = bool(getattr(options_obj, "auto_preset", True))
        auto_export = bool(getattr(options_obj, "auto_export", True))
        preview_skip = bool(getattr(options_obj, "preview_skip_mode", True))
        export_name_template = str(getattr(options_obj, "export_name_template", "{stem}"))
        avoid_overwrite = bool(getattr(options_obj, "avoid_overwrite", True))
        apply_active_edits = bool(getattr(options_obj, "apply_active_edits", False))
        apply_selected_preset = bool(getattr(options_obj, "apply_selected_preset", False))
        selected_preset_name = str(getattr(options_obj, "selected_preset_name", "") or "").strip()

        selected_ids = [str(item) for item in getattr(options_obj, "selected_asset_ids", ()) if str(item)]
        if not selected_ids:
            self._window._status("Batch run skipped: select at least one queued asset")
            return
        by_id = {asset.id: asset for asset in self._window._workspace_assets}
        selected_assets = [by_id[asset_id] for asset_id in selected_ids if asset_id in by_id]
        if not selected_assets:
            self._window._status("Batch run skipped: selected assets are no longer in workspace")
            return

        export_dir = self._resolve_export_directory(getattr(options_obj, "export_directory", None)) if auto_export else None
        if auto_export and export_dir and hasattr(self._window, "_export_coordinator"):
            self._window._export_coordinator.remember_export_directory(export_dir)

        if auto_export:
            self._apply_active_export_settings_to_selection(selected_assets)

        if apply_active_edits:
            self._apply_active_edit_settings_to_selection(selected_assets)

        if apply_selected_preset:
            if not selected_preset_name:
                self._window._status("Batch run skipped: choose a preset or disable preset apply")
                return
            try:
                self._apply_named_preset_to_selection(selected_assets, selected_preset_name)
            except Exception as exc:
                self._window._status(f"Batch run skipped: preset apply failed ({exc})")
                return

        LOGGER.info(
            "Batch run requested: selected=%s auto_export=%s auto_preset=%s preview_skip=%s export_dir=%s template=%s apply_active_edits=%s apply_selected_preset=%s preset=%s",
            len(selected_assets),
            auto_export,
            auto_preset,
            preview_skip,
            export_dir,
            export_name_template,
            apply_active_edits,
            apply_selected_preset,
            selected_preset_name,
        )

        self._window.batch_manager_dialog.set_running(True)
        self.start_worker(
            assets=selected_assets,
            preview_skip_mode=preview_skip,
            auto_export=auto_export,
            auto_preset=auto_preset,
            export_name_template=export_name_template,
            avoid_overwrite=avoid_overwrite,
            export_dir=export_dir,
        )
        self._window._status(f"Batch run started ({len(selected_assets)} item(s))")

    def on_progress_event(self, event: object) -> None:
        try:
            LOGGER.debug(
                "event=%s asset=%s stage=%s q_progress=%s overall=%s processed=%s failed=%s",
                getattr(event, "event_type", ""),
                getattr(event, "asset_id", None),
                getattr(event, "stage", None),
                getattr(event, "queue_progress", None),
                getattr(event, "overall_progress", None),
                getattr(event, "processed_count", None),
                getattr(event, "failed_count", None),
            )
            self._window.batch_manager_dialog.update_from_event(event)
        except Exception as exc:
            LOGGER.exception("Batch progress UI update failed: %s", exc)
            self._window._status(f"Batch progress UI warning: {exc}")

    def on_cancel_requested(self) -> None:
        worker = self._window._batch_worker
        if worker is None:
            self._window._status("No batch run is currently active")
            return
        worker.request_cancel()
        LOGGER.info("Batch cancellation requested")
        self._window.batch_manager_dialog.set_running(True)
        self._window._status("Batch cancellation requested")

    def on_run_finished(self, report: object) -> None:
        try:
            self._window.batch_manager_dialog.update_from_report(report)
        except Exception as exc:
            LOGGER.exception("Batch report UI update failed: %s", exc)
            self._window._status(f"Batch report UI warning: {exc}")
        self._window.batch_manager_dialog.set_running(False)

        cancelled = bool(getattr(report, "cancelled", False))
        processed = int(getattr(report, "processed_count", 0))
        failed = int(getattr(report, "failed_count", 0))
        LOGGER.info("Batch run finished: processed=%s failed=%s cancelled=%s", processed, failed, cancelled)
        if cancelled:
            self._window._status(f"Batch cancelled: processed {processed}, failed {failed}")
        else:
            self._window._status(f"Batch complete: processed {processed}, failed {failed}")

        self._window._refresh_export_prediction()

    def on_run_failed(self, message: str) -> None:
        LOGGER.error("Batch run failed: %s", message)
        self._window.batch_manager_dialog.set_running(False)
        self._window._show_error("Batch Run Failed", message)

    def start_worker(
        self,
        *,
        assets: list[AssetRecord],
        preview_skip_mode: bool,
        auto_export: bool,
        auto_preset: bool,
        export_name_template: str,
        avoid_overwrite: bool,
        export_dir: str | None,
    ) -> None:
        if self._window.controller is None:
            raise RuntimeError("Batch worker requires controller")
        if self._window._batch_thread is not None:
            raise RuntimeError("Batch worker already running")

        thread_parent = self._window if isinstance(self._window, QObject) else None
        thread = QThread(thread_parent)
        worker = _BatchRunWorker(
            controller=self._window.controller,
            assets=list(assets),
            preview_skip_mode=preview_skip_mode,
            auto_export=auto_export,
            auto_preset=auto_preset,
            export_name_template=export_name_template,
            avoid_overwrite=avoid_overwrite,
            export_dir=export_dir,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress_event.connect(self._ui_bridge.recv_progress, Qt.ConnectionType.QueuedConnection)
        worker.finished_report.connect(self._ui_bridge.recv_finished, Qt.ConnectionType.QueuedConnection)
        worker.failed.connect(self._ui_bridge.recv_failed, Qt.ConnectionType.QueuedConnection)
        worker.finished_report.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished_report.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self.on_thread_finished)

        self._window._batch_thread = thread
        self._window._batch_worker = worker
        thread.start()

    def on_thread_finished(self) -> None:
        LOGGER.debug("Batch worker thread finished")
        self._window._batch_thread = None
        self._window._batch_worker = None
        self._window.batch_manager_dialog.set_running(False)

    def _resolve_export_directory(self, candidate: object) -> str | None:
        if isinstance(candidate, str):
            value = candidate.strip()
            if value:
                return value
        fallback = self._window.export_bar.export_directory() if hasattr(self._window, "export_bar") else None
        if isinstance(fallback, str) and fallback.strip():
            return fallback.strip()
        return None

    def _apply_active_export_settings_to_selection(self, assets: list[AssetRecord]) -> None:
        active = self._window.ui_state.active_asset
        if active is None:
            return

        template = deepcopy(active.edit_state.settings.export)
        for asset in assets:
            asset.edit_state.settings.export = deepcopy(template)

    def _apply_active_edit_settings_to_selection(self, assets: list[AssetRecord]) -> None:
        active = self._window.ui_state.active_asset
        if active is None:
            return

        template_mode = deepcopy(active.edit_state.mode)
        template_apply_target = deepcopy(active.edit_state.apply_target)
        template_sync = bool(active.edit_state.sync_current_final)
        template_settings = deepcopy(active.edit_state.settings)

        for asset in assets:
            asset.edit_state.mode = deepcopy(template_mode)
            asset.edit_state.apply_target = deepcopy(template_apply_target)
            asset.edit_state.sync_current_final = template_sync
            asset.edit_state.settings = deepcopy(template_settings)

    def _apply_named_preset_to_selection(self, assets: list[AssetRecord], preset_name: str) -> None:
        controller = getattr(self._window, "controller", None)
        if controller is None:
            raise RuntimeError("controller not configured")

        for asset in assets:
            controller.apply_named_preset(asset, preset_name)



