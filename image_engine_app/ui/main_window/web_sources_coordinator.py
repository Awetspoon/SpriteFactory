"""Web Sources coordinator for main-window UI event handling."""

from __future__ import annotations

import socket
from typing import Any
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener, urlopen

from image_engine_app.app.services.web_sources_service import WebSourcesService
from image_engine_app.app.settings_store import load_web_sources_settings, save_web_sources_settings
from image_engine_app.app.web_sources_models import (
    SmartOptions,
    coerce_import_target,
    coerce_smart_options,
    coerce_web_items,
)
from image_engine_app.engine.ingest.url_ingest import DownloadGuards
from image_engine_app.engine.ingest.webpage_scan import WebpageScanCancelledError
from image_engine_app.engine.models import AssetRecord

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QProgressDialog, QWidget


class _ProgressSession:
    """Cancelable progress dialog wrapper used by web scan/download workflows."""

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
        return bool(self._cancel_requested)

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
        # Prefer hide/deleteLater over close(): some platforms can emit canceled on close.
        try:
            self.dialog.hide()
        finally:
            self.dialog.deleteLater()


class WebSourcesCoordinator:
    """Encapsulates Web Sources panel initialization + scan/download actions."""

    WINDOWS_BLOCKED_ACCESS_TEXT = (
        "Windows blocked network access (WinError 10013). "
        "Check firewall, VPN, proxy, or antivirus web shield settings."
    )

    def __init__(self, window: Any) -> None:
        self._window = window

    @classmethod
    def _normalize_network_error_message(cls, detail: str) -> str:
        lowered = str(detail or "").lower()
        if "winerror 10013" in lowered or "forbidden by its access permissions" in lowered:
            return cls.WINDOWS_BLOCKED_ACCESS_TEXT
        if "http error 403" in lowered:
            return "HTTP 403 (Forbidden): website blocked automated scan requests. Try Network Check or a direct file URL."
        if "http error 429" in lowered:
            return "HTTP 429 (Rate limited): try again in a minute, or reduce repeated scans on this host."
        if "http error 401" in lowered:
            return "HTTP 401 (Unauthorized): this page needs authentication/cookies before scanning."
        return str(detail)

    @classmethod
    def _is_socket_access_denied(cls, exc: Exception) -> bool:
        reason = getattr(exc, "reason", exc)
        win_error = getattr(reason, "winerror", None)
        if win_error == 10013:
            return True
        message = str(reason or exc).lower()
        return "winerror 10013" in message or "forbidden by its access permissions" in message

    @staticmethod
    def _normalize_diagnostics_url(raw_url: str) -> str:
        candidate = str(raw_url or "").strip()
        if not candidate:
            raise ValueError("Missing area URL for diagnostics.")
        if "://" not in candidate:
            candidate = f"https://{candidate}"
        parsed = urlparse(candidate)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Invalid URL. Use http(s)://domain/path.")
        return candidate

    def _diagnostics_summary_for_url(self, area_url: str) -> str:
        normalized = self._normalize_diagnostics_url(area_url)
        parsed = urlparse(normalized)
        host = (parsed.hostname or "").strip()
        if not host:
            raise ValueError("Diagnostics failed: URL host is missing.")

        port = parsed.port
        if port is None:
            port = 443 if parsed.scheme.lower() == "https" else 80

        try:
            socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except Exception as exc:
            detail = self._normalize_network_error_message(str(exc))
            return f"Network diagnostics: DNS lookup failed for {host} ({detail})"

        try:
            with socket.create_connection((host, int(port)), timeout=4.0):
                pass
        except Exception as exc:
            if self._is_socket_access_denied(exc):
                return f"Network diagnostics: {self.WINDOWS_BLOCKED_ACCESS_TEXT}"
            detail = self._normalize_network_error_message(str(exc))
            return f"Network diagnostics: TCP connect failed to {host}:{port} ({detail})"

        request = Request(normalized, headers={"User-Agent": "SpriteFactory/1.0.3 (Network Diagnostics)"})

        try:
            with urlopen(request, timeout=8.0) as response:
                status = getattr(response, "status", None)
                code = int(status) if isinstance(status, int) else 200
                return f"Network diagnostics OK: DNS + TCP + HTTP {code} for {host}:{port}"
        except Exception as first_exc:
            if self._is_socket_access_denied(first_exc):
                return f"Network diagnostics: {self.WINDOWS_BLOCKED_ACCESS_TEXT}"

            try:
                direct_opener = build_opener(ProxyHandler({}))
                with direct_opener.open(request, timeout=8.0) as response:
                    status = getattr(response, "status", None)
                    code = int(status) if isinstance(status, int) else 200
                    return (
                        f"Network diagnostics OK (direct/no-proxy): DNS + TCP + HTTP {code} for {host}:{port}"
                    )
            except Exception as second_exc:
                if self._is_socket_access_denied(second_exc):
                    return f"Network diagnostics: {self.WINDOWS_BLOCKED_ACCESS_TEXT}"
                detail = self._normalize_network_error_message(str(first_exc))
                return (
                    "Network diagnostics partial: DNS + TCP succeeded, "
                    f"HTTP request failed ({detail})"
                )

    def init_panel(self) -> None:
        registry: list[dict] = []
        selected_website_id: str | None = None
        selected_area_id: str | None = None
        smart = SmartOptions()

        if self._window.controller is not None:
            try:
                registry = self._window.controller.load_web_sources_registry()
            except Exception:
                registry = []

            paths = getattr(self._window.controller, "app_paths", None)
            if paths is not None:
                try:
                    web_cfg = load_web_sources_settings(paths)
                    raw_registry = web_cfg.get("registry")
                    if isinstance(raw_registry, list):
                        registry = self._window.controller.load_web_sources_registry(raw_registry)

                    selected = web_cfg.get("last_selected") if isinstance(web_cfg.get("last_selected"), dict) else {}
                    selected_website_id = str(selected.get("website_id")) if selected.get("website_id") else None
                    selected_area_id = str(selected.get("area_id")) if selected.get("area_id") else None

                    smart = coerce_smart_options(web_cfg.get("options"))
                except Exception:
                    pass

        self._window.web_sources_panel.set_sources(
            websites=registry,
            selected_website_id=selected_website_id,
            selected_area_id=selected_area_id,
        )
        self._window.web_sources_panel.set_smart_options(smart)

    def persist_state(
        self,
        *,
        website_id: str | None = None,
        area_id: str | None = None,
        smart: SmartOptions | None = None,
        registry: list[dict] | None = None,
    ) -> None:
        if self._window.controller is None:
            return

        paths = getattr(self._window.controller, "app_paths", None)
        if paths is None:
            return

        panel_website_id, panel_area_id = self._window.web_sources_panel.selected_source_ids()
        active_smart = smart or self._window.web_sources_panel.smart_options()
        active_registry = registry if registry is not None else self._window.web_sources_panel.sources_registry()

        try:
            save_web_sources_settings(
                paths,
                registry=active_registry,
                last_selected={
                    "website_id": website_id if website_id is not None else panel_website_id,
                    "area_id": area_id if area_id is not None else panel_area_id,
                },
                options={
                    "show_likely": active_smart.show_likely,
                    "auto_sort": active_smart.auto_sort,
                    "skip_duplicates": active_smart.skip_duplicates,
                    "allow_zip": active_smart.allow_zip,
                },
            )
        except Exception:
            # Persistence failures should not block the UI workflow.
            pass

    def on_registry_changed(self, payload: object) -> None:
        if self._window.controller is None:
            return

        if not isinstance(payload, list):
            self._window.web_sources_panel.set_status("Invalid website registry payload.")
            return

        registry = self._window.controller.load_web_sources_registry(payload)

        website_id, area_id = self._window.web_sources_panel.selected_source_ids()
        self._window.web_sources_panel.set_sources(
            websites=registry,
            selected_website_id=website_id,
            selected_area_id=area_id,
        )
        persisted_website_id, persisted_area_id = self._window.web_sources_panel.selected_source_ids()
        self.persist_state(
            website_id=persisted_website_id,
            area_id=persisted_area_id,
            registry=registry,
        )

    def on_scan_requested(self, payload: object) -> None:
        if self._window.controller is None:
            self._window.web_sources_panel.set_status("Web Sources scan unavailable: controller not configured")
            return

        if not isinstance(payload, dict):
            self._window.web_sources_panel.set_status("Invalid scan payload.")
            return

        area_url = str(payload.get("area_url", "")).strip()
        if not area_url:
            self._window.web_sources_panel.set_status("Pick a Website + Area first.")
            return

        smart = coerce_smart_options(payload.get("smart"))
        progress = _ProgressSession(
            window=self._window,
            panel=self._window.web_sources_panel,
            label_text="Scanning webpage for assets...",
            title="Web Sources Scan",
            minimum=0,
            maximum=0,
            cancel_label_text="Cancelling scan...",
            cancel_status_text="Cancelling scan...",
        )

        try:
            results = self._window.controller.scan_web_sources_area(
                area_url,
                show_likely=smart.show_likely,
                cancel_requested=progress.is_cancel_requested,
            )
        except WebpageScanCancelledError:
            self._window.web_sources_panel.set_status("Scan cancelled")
            self._window._status("Web Sources scan cancelled")
            return
        except Exception as exc:
            detail = self._normalize_network_error_message(str(exc))
            self._window.web_sources_panel.set_status(f"Scan failed: {detail}")
            return
        finally:
            progress.close()

        self._window.web_sources_panel.set_results(results)
        self._window._status(f"Web Sources scan complete: {len(results.items)} item(s)")
        self.persist_state(
            website_id=(str(payload.get("website_id")) if payload.get("website_id") else None),
            area_id=(str(payload.get("area_id")) if payload.get("area_id") else None),
            smart=smart,
        )

    def on_download_requested(self, payload: object) -> None:
        if self._window.controller is None:
            self._window.web_sources_panel.set_status("Web Sources download unavailable: controller not configured")
            return

        if not isinstance(payload, dict):
            self._window.web_sources_panel.set_status("Invalid download payload.")
            return

        items = coerce_web_items(payload.get("items"))
        if not items:
            self._window.web_sources_panel.set_status("Select at least one item to download.")
            return

        target = coerce_import_target(payload.get("target"))
        smart = coerce_smart_options(payload.get("smart"))

        progress = _ProgressSession(
            window=self._window,
            panel=self._window.web_sources_panel,
            label_text="Preparing downloads...",
            title="Web Sources Download",
            minimum=0,
            maximum=max(1, len(items)),
            cancel_label_text="Cancelling downloads...",
            cancel_status_text="Cancelling downloads...",
        )
        progress.update(
            done_count=0,
            total_count=max(1, len(items)),
            label_text="Preparing downloads...",
            status_text="Preparing downloads...",
        )

        report = None
        try:
            report = self._window.controller.download_web_sources_items(
                items,
                target,
                smart=smart,
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
            detail = self._normalize_network_error_message(str(exc))
            self._window.web_sources_panel.set_status(f"Download failed: {detail}")
            return
        finally:
            should_mark_complete = bool(report is not None and not getattr(report, "cancelled", False))
            progress.close(complete=should_mark_complete)

        if report.assets:
            try:
                workspace_assets = [
                    asset
                    for asset in tuple(getattr(report, "assets", ()) or ())
                    if isinstance(asset, AssetRecord)
                ]
                if workspace_assets:
                    self._window._register_assets(workspace_assets, set_active=True)
            except Exception as exc:
                detail = str(exc).strip() or exc.__class__.__name__
                self._window.web_sources_panel.set_status(
                    f"Download completed but failed to load workspace assets: {detail}"
                )
                self._window._status("Web Sources import completed, but workspace load failed")
                self.persist_state(
                    website_id=(str(payload.get("website_id")) if payload.get("website_id") else None),
                    area_id=(str(payload.get("area_id")) if payload.get("area_id") else None),
                    smart=smart,
                )
                return

        message = self.format_download_status(report)
        self._window.web_sources_panel.set_status(message)
        self._window._status(message)
        self.persist_state(
            website_id=(str(payload.get("website_id")) if payload.get("website_id") else None),
            area_id=(str(payload.get("area_id")) if payload.get("area_id") else None),
            smart=smart,
        )

    def on_network_diagnostics_requested(self, payload: object) -> None:
        if not isinstance(payload, dict):
            self._window.web_sources_panel.set_status("Invalid diagnostics payload.")
            return

        area_url = str(payload.get("area_url", "")).strip()
        if not area_url:
            self._window.web_sources_panel.set_status("Enter a URL or pick an area for diagnostics.")
            return

        try:
            summary = self._diagnostics_summary_for_url(area_url)
        except Exception as exc:
            detail = self._normalize_network_error_message(str(exc))
            summary = f"Network diagnostics failed: {detail}"

        self._window.web_sources_panel.set_status(summary)
        self._window._status(summary)

    @staticmethod
    def format_download_status(report: object) -> str:
        downloaded = len(tuple(getattr(report, "downloaded", ()) or ()))
        skipped = len(tuple(getattr(report, "skipped", ()) or ()))
        failed = len(tuple(getattr(report, "failed", ()) or ()))
        loaded = len(
            [
                asset
                for asset in tuple(getattr(report, "assets", ()) or ())
                if isinstance(asset, AssetRecord)
            ]
        )
        reused = max(0, loaded - downloaded)
        cancelled = bool(getattr(report, "cancelled", False))
        prefix = "Web Sources import cancelled" if cancelled else "Web Sources import"
        message = (
            f"{prefix}: downloaded {downloaded}, reused {reused} cached, "
            f"skipped {skipped}, failed {failed}, workspace loaded {loaded}"
        )
        failure_preview = WebSourcesService.summarize_failures(tuple(getattr(report, "failed", ()) or ()), limit=2)
        if failure_preview:
            return f"{message} | sample failures: {failure_preview}"
        return message





