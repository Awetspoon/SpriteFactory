"""Main-window coordinator for controls, presets, Final, Apply, and Reset."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject

from image_engine_app.engine.process.edit_baseline import ensure_detected_settings
from image_engine_app.engine.process.edit_impact import EditImpact, has_visible_settings_changes
from image_engine_app.engine.process.presets_apply import PresetApplyError
from image_engine_app.ui.main_window.final_preview_scheduler import FinalPreviewScheduler


class EditCoordinator:
    """Route every interactive edit through the controller's one edit workflow."""

    def __init__(self, window: Any) -> None:
        self._window = window
        parent = window if isinstance(window, QObject) else None
        self._preview_scheduler = FinalPreviewScheduler(
            renderer=self._render_preview_snapshot,
            active_asset_provider=self._active_asset,
            parent=parent,
        )
        self._preview_scheduler.preview_ready.connect(self._on_preview_ready)
        self._preview_scheduler.preview_failed.connect(self._on_preview_failed)

    def on_active_asset_changed(self, asset: object | None) -> None:
        self._preview_scheduler.note_active_asset(asset)

    def on_setting_change_requested(self, group_name: str, field_name: str, value: object) -> None:
        asset = self._active_asset()
        controller = self._controller()
        if asset is None or controller is None:
            return
        try:
            result = controller.update_asset_setting(
                asset,
                group_name,
                field_name,
                value,
                refresh_final=False,
            )
        except Exception as exc:
            self._window._status(f"Control update failed: {exc}")
            return
        if not bool(getattr(result, "changed", False)):
            return

        self._refresh_after_model_change(asset)
        if getattr(result, "impact", None) is EditImpact.PREVIEW:
            self._preview_scheduler.request(asset, reason="edit")

    def on_output_size_requested(self, choice_key: str) -> None:
        asset = self._active_asset()
        controller = self._controller()
        if asset is None or controller is None:
            return
        try:
            result = controller.apply_asset_output_size(
                asset,
                choice_key,
                refresh_final=False,
            )
        except Exception as exc:
            self._window._status(f"Output size failed: {exc}")
            return
        if not bool(getattr(result, "changed", False)):
            return

        self._refresh_after_model_change(asset, sync_values=True)
        self._preview_scheduler.request(asset, reason="edit")

    def on_settings_reset_requested(self, field_paths: object) -> None:
        asset = self._active_asset()
        controller = self._controller()
        if asset is None or controller is None:
            return
        try:
            normalized = tuple(
                (str(group_name), str(field_name))
                for group_name, field_name in tuple(field_paths or ())
            )
            result = controller.reset_asset_settings(
                asset,
                normalized,
                refresh_final=False,
            )
        except Exception as exc:
            self._window._status(f"Control reset failed: {exc}")
            return
        if not bool(getattr(result, "changed", False)):
            return

        self._refresh_after_model_change(asset, sync_values=True)
        if getattr(result, "impact", None) is EditImpact.PREVIEW:
            self._preview_scheduler.request(asset, reason="reset-control")
        self._window._status("Reset selected control to its source value")

    def on_export_profile_requested(self, profile_value: str) -> None:
        asset = self._active_asset()
        controller = self._controller()
        if asset is None or controller is None:
            return
        try:
            controller.set_asset_export_profile(asset, profile_value)
        except Exception as exc:
            self._window._status(f"Export profile failed: {exc}")
            return
        self._publish(asset)
        self._window._status(f"Export profile set to {profile_value.replace('_', ' ').title()}")

    def on_final_preview_requested(self) -> None:
        asset = self._active_asset()
        if asset is None or self._controller() is None:
            return
        self._preview_scheduler.request(asset, immediate=True, reason="manual")
        self._window._status("Refreshing Final preview...")

    def on_apply_requested(self) -> None:
        asset = self._active_asset()
        if asset is None:
            return
        controller = self._controller()
        if controller is None:
            self._window._status("Apply unavailable: controller not configured")
            return

        queued = sum(
            1
            for job in asset.edit_state.queued_heavy_jobs
            if str(getattr(getattr(job, "status", None), "value", "")) == "queued"
        )
        if queued == 0:
            self.on_final_preview_requested()
            return

        self._preview_scheduler.cancel_pending()
        self._window.ui_state.set_heavy_queue_counts(queued_count=queued, running_count=1)
        try:
            finished = controller.apply_heavy_queue(asset)
        except Exception as exc:
            self._publish(asset)
            self._window._status(f"Apply failed: {exc}")
            return

        self._publish(asset)
        if finished:
            self._window._status(f"Apply complete: {len(finished)} heavy step(s) finished")
        else:
            self._window._status("Apply complete: no heavy jobs ran")

    def on_preset_requested(self, preset_name: str) -> None:
        asset = self._active_asset()
        if asset is None:
            self._window._status("Preset skipped: no active asset")
            return
        controller = self._controller()
        if controller is None:
            self._window._status("Preset skipped: controller unavailable")
            return

        try:
            summary = controller.apply_named_preset(
                asset,
                preset_name,
                refresh_final=False,
            )
        except PresetApplyError as exc:
            self._window._status(f"Preset skipped: {exc}")
            return
        except Exception as exc:
            self._window._status(f"Preset failed: {exc}")
            return

        self._refresh_after_model_change(asset, sync_values=True)
        self._refresh_heavy_queue_state(asset)
        self._preview_scheduler.request(asset, immediate=True, reason="preset")
        preset_label = str(getattr(summary, "preset_name", preset_name) or preset_name)
        if bool(getattr(summary, "requires_apply", False)):
            self._window._status(f"Preset applied: {preset_label}. Run the queued heavy step to finish.")
        else:
            self._window._status(f"Preset applied: {preset_label}")

    def on_global_reset_requested(self) -> None:
        asset = self._active_asset()
        if asset is None:
            self._window._status("Reset skipped: no active asset")
            return
        controller = self._controller()
        if controller is None:
            self._window._status("Reset skipped: controller unavailable")
            return

        try:
            result = controller.restore_asset_detected_settings(
                asset,
                refresh_final=False,
            )
        except Exception as exc:
            self._window._status(f"Reset failed: {exc}")
            return

        self._refresh_after_model_change(asset, sync_values=True)
        self._refresh_heavy_queue_state(asset)
        self._preview_scheduler.request(asset, immediate=True, reason="reset")
        self._window._status("Reset active asset to its detected controls")

    def shutdown(self, *, wait: bool = False) -> None:
        self._preview_scheduler.shutdown(wait=wait)

    @property
    def preview_refresh_busy(self) -> bool:
        return self._preview_scheduler.is_busy

    def _render_preview_snapshot(self, asset: object, generation: int) -> object:
        controller = self._controller()
        if controller is None:
            raise RuntimeError("Final preview controller is unavailable")
        return controller.refresh_asset_final(
            asset,
            output_stem=f"preview-{int(generation)}",
        )

    def _on_preview_ready(self, reason: str, snapshot: object, result: object) -> None:
        asset = self._active_asset()
        if asset is None or getattr(asset, "id", None) != getattr(snapshot, "id", None):
            self._discard_temporary_output(snapshot)
            return
        live_settings = getattr(getattr(asset, "edit_state", None), "settings", None)
        snapshot_settings = getattr(getattr(snapshot, "edit_state", None), "settings", None)
        if (
            live_settings is None
            or snapshot_settings is None
            or has_visible_settings_changes(live_settings, baseline=snapshot_settings)
        ):
            self._discard_temporary_output(snapshot)
            self._preview_scheduler.request(asset, reason="edit")
            return

        preview_error = getattr(result, "preview_error", None)
        if preview_error:
            self._discard_temporary_output(snapshot)
            self._publish(asset)
            self._window._status(f"Final preview failed: {preview_error}")
            return

        if bool(getattr(result, "preview_rendered", False)):
            try:
                asset.derived_final_path = self._promote_temporary_output(snapshot)
            except OSError as exc:
                self._discard_temporary_output(snapshot)
                self._window._status(f"Final preview failed: {exc}")
                return
            asset.dimensions_final = tuple(getattr(snapshot, "dimensions_final", asset.dimensions_final))
        else:
            self._discard_temporary_output(snapshot)
            asset.derived_final_path = None

        self._publish(asset)
        if reason == "manual":
            if bool(getattr(result, "preview_rendered", False)):
                self._window._status("Final preview refreshed")
            elif not has_visible_settings_changes(
                asset.edit_state.settings,
                baseline=ensure_detected_settings(asset),
            ):
                self._window._status("Final already matches Current; no edits to render")
            else:
                self._window._status("Final preview unavailable: no readable local source")

    def _on_preview_failed(self, _reason: str, error: str) -> None:
        self._window._status(f"Final preview failed: {error}")

    def _refresh_after_model_change(self, asset: object, *, sync_values: bool = False) -> None:
        settings_panel = getattr(self._window, "settings_panel", None)
        refresh = getattr(settings_panel, "refresh_after_edit", None)
        if callable(refresh):
            refresh(asset, sync_values=sync_values)
        self._window._refresh_export_prediction()

    def _refresh_heavy_queue_state(self, asset: object) -> None:
        jobs = list(getattr(getattr(asset, "edit_state", None), "queued_heavy_jobs", ()) or ())
        queued = sum(
            1
            for job in jobs
            if str(getattr(getattr(job, "status", None), "value", "")) == "queued"
        )
        running = sum(
            1
            for job in jobs
            if str(getattr(getattr(job, "status", None), "value", "")) == "running"
        )
        self._window.ui_state.set_heavy_queue_counts(
            queued_count=queued,
            running_count=running,
        )

    def _publish(self, asset: object) -> None:
        self._window.ui_state.set_active_asset(asset)
        self._window._refresh_export_prediction()

    def _active_asset(self):
        return self._window.ui_state.active_asset

    def _controller(self):
        return self._window.controller

    @staticmethod
    def _promote_temporary_output(snapshot: object) -> str:
        raw_path = getattr(snapshot, "derived_final_path", None)
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise OSError("render completed without a Final preview file")
        temporary = Path(raw_path)
        if not temporary.exists() or not temporary.is_file():
            raise OSError("rendered Final preview file is missing")
        canonical = temporary.with_name(f"final{temporary.suffix.lower()}")
        if temporary != canonical:
            temporary.replace(canonical)
        return str(canonical)

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
