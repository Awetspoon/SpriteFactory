"""Qt coordinator for the application-owned Web Sources workflow."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QProgressDialog, QWidget

from image_engine_app.app.web_sources_models import (
    SmartOptions,
    WebDiagnosticsRequest,
    WebDownloadRequest,
    WebLinkDiscoveryRequest,
    WebRemoveSavedPageRequest,
    WebRemoveSavedWebsiteRequest,
    WebSavePagesRequest,
    WebScanRequest,
    WebSourcesMutation,
    WebSourcesState,
)
from image_engine_app.engine.ingest.url_ingest import DownloadGuards
from image_engine_app.engine.ingest.webpage_scan import WebpageScanCancelledError
from image_engine_app.engine.models import AssetRecord


class _ProgressSession:
    """Cancelable progress dialog shared by scan, discovery, and download work."""

    def __init__(
        self,
        *,
        window: Any,
        panel: Any,
        label_text: str,
        title: str,
        minimum: int,
        maximum: int,
        cancel_label_text: str,
        cancel_status_text: str,
    ) -> None:
        self._panel = panel
        self._cancel_label_text = cancel_label_text
        self._cancel_status_text = cancel_status_text
        self._cancel_requested = False
        self._ignore_cancel_signal = False

        parent = window if isinstance(window, QWidget) else None
        self.dialog = QProgressDialog(label_text, "Cancel", minimum, maximum, parent)
        self.dialog.setWindowTitle(title)
        self.dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.dialog.setMinimumDuration(0)
        self.dialog.setAutoClose(False)
        self.dialog.setAutoReset(False)
        self.dialog.canceled.connect(self._on_cancel_requested)
        self.dialog.show()
        QApplication.processEvents()

    def _on_cancel_requested(self) -> None:
        if self._ignore_cancel_signal or self._cancel_requested:
            return
        self._cancel_requested = True
        self.dialog.setLabelText(self._cancel_label_text)
        self._panel.set_status(self._cancel_status_text)
        QApplication.processEvents()

    def is_cancel_requested(self) -> bool:
        QApplication.processEvents()
        return self._cancel_requested

    def update(
        self,
        *,
        done_count: int,
        total_count: int,
        label_text: str,
        status_text: str,
    ) -> None:
        total = max(1, int(total_count or 1))
        done = max(0, min(int(done_count or 0), total))
        self.dialog.setMaximum(total)
        self.dialog.setValue(done)
        self.dialog.setLabelText(str(label_text))
        self._panel.set_status(str(status_text))
        QApplication.processEvents()

    def close(self, *, complete: bool = False) -> None:
        self._ignore_cancel_signal = True
        try:
            self.dialog.canceled.disconnect(self._on_cancel_requested)
        except Exception:
            pass
        if complete and not self._cancel_requested:
            self.dialog.setValue(self.dialog.maximum())
        try:
            self.dialog.hide()
        finally:
            self.dialog.deleteLater()


class WebSourcesCoordinator:
    """Translate panel requests into application workflow calls."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def init_panel(self) -> None:
        controller = self._window.controller
        state = controller.web_sources_state() if controller is not None else WebSourcesState()
        self._window.web_sources_panel.set_state(state)

    def on_save_pages_requested(self, payload: object) -> None:
        if not isinstance(payload, WebSavePagesRequest):
            self._window.web_sources_panel.set_status("The save-pages request was invalid.")
            return
        self._run_mutation(lambda controller: controller.save_web_sources_pages(payload))

    def on_remove_page_requested(self, payload: object) -> None:
        if not isinstance(payload, WebRemoveSavedPageRequest):
            self._window.web_sources_panel.set_status("The remove-page request was invalid.")
            return
        self._run_mutation(lambda controller: controller.remove_web_sources_page(payload))

    def on_remove_website_requested(self, payload: object) -> None:
        if not isinstance(payload, WebRemoveSavedWebsiteRequest):
            self._window.web_sources_panel.set_status("The remove-website request was invalid.")
            return
        self._run_mutation(lambda controller: controller.remove_web_sources_website(payload))

    def on_clear_links_requested(self) -> None:
        self._run_mutation(lambda controller: controller.clear_web_sources_links())

    def on_clear_found_files_requested(self) -> None:
        self._run_mutation(lambda controller: controller.clear_web_sources_found_files())

    def on_preferences_changed(self, payload: object) -> None:
        controller = self._window.controller
        if controller is None or not isinstance(payload, SmartOptions):
            return
        try:
            state = controller.update_web_sources_preferences(payload)
        except Exception as exc:
            self._window.web_sources_panel.set_status(
                f"Could not update Web Sources options: {controller.friendly_web_sources_error(exc)}"
            )
            return
        self._window.web_sources_panel.set_state(state)

    def on_scan_requested(self, payload: object) -> None:
        controller = self._window.controller
        panel = self._window.web_sources_panel
        if controller is None:
            panel.set_status("Web Sources scanning is unavailable because the controller is not configured.")
            return
        if not isinstance(payload, WebScanRequest):
            panel.set_status("The page scan request was invalid.")
            return

        try:
            plan = controller.plan_web_sources_scan(payload)
        except Exception as exc:
            panel.set_status(controller.friendly_web_sources_error(exc))
            return

        if plan.requires_confirmation and not panel.confirm_large_page_scan(
            plan.requested_count,
            cap=plan.page_limit,
        ):
            panel.set_status("Page scan cancelled before starting.")
            return

        progress = _ProgressSession(
            window=self._window,
            panel=panel,
            label_text=f"Scanning {len(plan.urls)} page(s)...",
            title="Web Sources Scan",
            minimum=0,
            maximum=max(1, len(plan.urls)),
            cancel_label_text="Cancelling page scan...",
            cancel_status_text="Cancelling page scan...",
        )
        outcome = None
        try:
            outcome = controller.run_web_sources_scan(
                plan,
                progress_callback=lambda done, total, message: progress.update(
                    done_count=done,
                    total_count=total,
                    label_text=str(message),
                    status_text=str(message),
                ),
                cancel_requested=progress.is_cancel_requested,
            )
        except WebpageScanCancelledError:
            panel.set_status("Page scan cancelled. Existing Found Files were kept.")
            self._window._status("Web Sources scan cancelled")
            return
        except Exception as exc:
            panel.set_status(f"Page scan failed: {controller.friendly_web_sources_error(exc)}")
            return
        finally:
            progress.close(complete=outcome is not None)

        panel.show_scan_outcome(outcome)
        failed_count = len(outcome.latest.failed_pages)
        status = (
            f"Web Sources scan complete: {outcome.merge.added_count} new, "
            f"{len(outcome.state.found_files)} total"
        )
        if outcome.merge.duplicate_count:
            status += f", {outcome.merge.duplicate_count} duplicate(s) ignored"
        if failed_count:
            status += f", {failed_count} page(s) failed"
        if plan.was_capped:
            status += f", first {plan.page_limit} pages scanned"
        self._window._status(status)

    def on_discover_links_requested(self, payload: object) -> None:
        controller = self._window.controller
        panel = self._window.web_sources_panel
        if controller is None:
            panel.set_status("Linked-page discovery is unavailable because the controller is not configured.")
            return
        if not isinstance(payload, WebLinkDiscoveryRequest):
            panel.set_status("Choose a valid page before finding linked pages.")
            return

        progress = _ProgressSession(
            window=self._window,
            panel=panel,
            label_text="Finding linked pages...",
            title="Find Linked Pages",
            minimum=0,
            maximum=0,
            cancel_label_text="Cancelling page discovery...",
            cancel_status_text="Cancelling page discovery...",
        )
        outcome = None
        try:
            outcome = controller.discover_web_sources_links(
                payload,
                cancel_requested=progress.is_cancel_requested,
            )
        except WebpageScanCancelledError:
            panel.set_status("Linked-page discovery cancelled.")
            self._window._status("Web Sources page discovery cancelled")
            return
        except Exception as exc:
            panel.set_status(f"Could not find linked pages: {controller.friendly_web_sources_error(exc)}")
            return
        finally:
            progress.close(complete=outcome is not None)

        panel.set_state(outcome.state)
        if outcome.links:
            panel.set_status(
                f"Found {len(outcome.links)} linked page(s). Select the pages you want, then scan them."
            )
        else:
            panel.set_status(
                "No linked pages were found. Try scanning this page directly or choose a broader index page."
            )
        self._window._status(f"Web Sources found {len(outcome.links)} linked page(s)")

    def on_download_requested(self, payload: object) -> None:
        controller = self._window.controller
        panel = self._window.web_sources_panel
        if controller is None:
            panel.set_status("Web Sources downloading is unavailable because the controller is not configured.")
            return
        if not isinstance(payload, WebDownloadRequest) or not payload.items:
            panel.set_status("Select at least one found file to download.")
            return

        progress = _ProgressSession(
            window=self._window,
            panel=panel,
            label_text="Preparing downloads...",
            title="Web Sources Download",
            minimum=0,
            maximum=max(1, len(payload.items)),
            cancel_label_text="Cancelling downloads...",
            cancel_status_text="Cancelling downloads...",
        )
        progress.update(
            done_count=0,
            total_count=len(payload.items),
            label_text="Preparing downloads...",
            status_text="Preparing downloads...",
        )

        report = None
        try:
            report = controller.download_web_sources(
                payload,
                guards=DownloadGuards(max_bytes=25 * 1024 * 1024, max_pixels=64_000_000),
                progress_callback=lambda done, total, message: progress.update(
                    done_count=done,
                    total_count=total,
                    label_text=str(message),
                    status_text=str(message),
                ),
                cancel_requested=progress.is_cancel_requested,
            )
        except Exception as exc:
            panel.set_status(f"Download failed: {controller.friendly_web_sources_error(exc)}")
            return
        finally:
            progress.close(complete=bool(report is not None and not getattr(report, "cancelled", False)))

        workspace_assets = [
            asset
            for asset in tuple(getattr(report, "assets", ()) or ())
            if isinstance(asset, AssetRecord)
        ]
        if workspace_assets:
            try:
                self._window._register_assets(workspace_assets, set_active=True)
            except Exception as exc:
                detail = str(exc).strip() or exc.__class__.__name__
                panel.set_status(f"Download completed but workspace loading failed: {detail}")
                self._window._status("Web Sources download completed, but workspace load failed")
                return

        message = controller.format_web_sources_download_status(report)
        panel.set_status(message)
        self._window._status(message)

    def on_diagnostics_requested(self, payload: object) -> None:
        controller = self._window.controller
        panel = self._window.web_sources_panel
        if controller is None:
            panel.set_status("Connection checking is unavailable because the controller is not configured.")
            return
        if not isinstance(payload, WebDiagnosticsRequest):
            panel.set_status("Choose a valid page URL before running a connection check.")
            return
        try:
            summary = controller.diagnose_web_source(payload)
        except Exception as exc:
            summary = f"Connection check failed: {controller.friendly_web_sources_error(exc)}"
        panel.set_status(summary)
        self._window._status(summary)

    def _run_mutation(self, operation) -> None:  # noqa: ANN001
        controller = self._window.controller
        panel = self._window.web_sources_panel
        if controller is None:
            panel.set_status("Web Sources is unavailable because the controller is not configured.")
            return
        try:
            mutation = operation(controller)
        except Exception as exc:
            panel.set_status(f"Web Sources update failed: {controller.friendly_web_sources_error(exc)}")
            return
        if not isinstance(mutation, WebSourcesMutation):
            panel.set_status("Web Sources returned an invalid state update.")
            return
        panel.set_state(mutation.state)
        panel.set_status(mutation.message)
