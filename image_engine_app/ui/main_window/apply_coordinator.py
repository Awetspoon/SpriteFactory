"""Apply/preset/reset workflow coordinator for the main window."""

from __future__ import annotations

from typing import Any

from image_engine_app.engine.process.presets_apply import PresetApplyError


class ApplyCoordinator:
    """Owns light/heavy apply, preset apply, and global reset actions."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def on_light_preview_requested(self) -> None:
        """Render light pipeline preview without consuming heavy job queues."""
        asset = self._window.ui_state.active_asset
        if asset is None or self._window.controller is None:
            return

        try:
            wrote = self._window.controller.apply_light_pipeline(asset)
        except Exception:
            # Keep UI responsive while user edits settings; status noise is avoided here.
            return

        if wrote:
            self._window.ui_state.set_active_asset(asset)
            self._window._refresh_export_prediction()

    def on_apply_requested(self) -> None:
        asset = self._window.ui_state.active_asset
        if asset is None:
            return

        if self._window.controller is None:
            self._window._status("Apply pressed: controller not configured")
            return

        queued = len(asset.edit_state.queued_heavy_jobs)

        # If no heavy jobs are queued, treat Apply as a light-pipeline commit.
        if queued == 0:
            try:
                wrote = self._window.controller.apply_light_pipeline(asset)
            except Exception as exc:
                self._window._status(f"Apply failed: {exc}")
                return
            if wrote:
                # Re-emit active asset so preview panes reload derived outputs.
                self._window.ui_state.set_active_asset(asset)
                self._window._status("Apply complete: light pipeline rendered")
            else:
                self._window._status("Apply pressed: light pipeline unavailable for this asset")
            self._window._refresh_export_prediction()
            return

        # Heavy queue run
        self._window.ui_state.set_heavy_queue_counts(queued_count=queued, running_count=1)

        finished = self._window.controller.apply_heavy_queue(asset)
        remaining_queued = sum(1 for job in asset.edit_state.queued_heavy_jobs if job.status.value == "queued")
        running = sum(1 for job in asset.edit_state.queued_heavy_jobs if job.status.value == "running")
        self._window.ui_state.set_heavy_queue_counts(queued_count=remaining_queued, running_count=running)
        if finished:
            self._window._status(f"Apply complete: {len(finished)} heavy step(s) finished")
        else:
            self._window._status("Apply complete: no heavy jobs ran")
        self._window._refresh_export_prediction()

    def on_preset_requested(self, preset_name: str) -> None:
        """Apply one named preset to the active asset through the shared preset engine."""

        asset = self._window.ui_state.active_asset
        if asset is None:
            self._window._status("Preset skipped: no active asset")
            return

        if self._window.controller is None:
            self._window._status("Preset skipped: controller unavailable")
            return

        try:
            self._window.controller.reset_asset_settings_to_defaults(asset)
            summary = self._window.controller.apply_named_preset(asset, preset_name)
        except PresetApplyError as exc:
            self._window._status(f"Preset skipped: {exc}")
            return
        except Exception as exc:
            self._window._status(f"Preset failed: {exc}")
            return

        preview_error: Exception | None = None
        try:
            self._window.controller.apply_light_pipeline(asset)
        except Exception as exc:
            preview_error = exc

        self._window.ui_state.set_active_asset(asset)
        self._window.ui_state.set_heavy_queue_counts(
            queued_count=int(getattr(summary, "queued_heavy_jobs", 0) or 0),
            running_count=0,
        )
        self._window._refresh_export_prediction()

        preset_label = str(getattr(summary, "preset_name", preset_name) or preset_name)
        if preview_error is not None:
            self._window._status(f"Preset applied, but preview refresh failed: {preview_error}")
        elif bool(getattr(summary, "requires_apply", False)):
            self._window._status(f"Preset applied: {preset_label}. Press Apply to finish heavy steps.")
        else:
            self._window._status(f"Preset applied: {preset_label}")

    def on_global_reset_requested(self) -> None:
        asset = self._window.ui_state.active_asset
        if asset is None:
            self._window._status("Reset skipped: no active asset")
            return

        if self._window.controller is None:
            self._window._status("Reset skipped: controller unavailable")
            return

        try:
            self._window.controller.reset_asset_settings_to_defaults(asset)
            self._window.controller.apply_light_pipeline(asset)
            self._window.ui_state.set_active_asset(asset)
            self._window.ui_state.set_heavy_queue_counts(
                queued_count=len(asset.edit_state.queued_heavy_jobs),
                running_count=0,
            )
            self._window._refresh_export_prediction()
            self._window._status("Reset active asset edits to defaults")
        except Exception as exc:
            self._window._status(f"Reset failed: {exc}")

