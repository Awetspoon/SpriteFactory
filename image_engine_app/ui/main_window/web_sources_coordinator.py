"""Coordinator for the Web Sources workspace."""

from __future__ import annotations

import re
import socket
from typing import Any
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener, urlopen

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QProgressDialog, QWidget

from image_engine_app.app.services.web_sources_service import WebSourcesService
from image_engine_app.app.settings_store import load_web_sources_settings, save_web_sources_settings
from image_engine_app.app.web_sources_models import (
    ScanResults,
    SmartOptions,
    WebDiagnosticsRequest,
    WebDownloadRequest,
    WebLinkDiscoveryRequest,
    WebScanRequest,
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
    """Own Web Sources calls while keeping the panel free of network and file I/O."""

    WINDOWS_BLOCKED_ACCESS_TEXT = (
        "Windows blocked network access (WinError 10013). "
        "Check firewall, VPN, proxy, or antivirus web shield settings."
    )

    def __init__(self, window: Any) -> None:
        self._window = window

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
                    config = load_web_sources_settings(paths)
                    raw_registry = config.get("registry")
                    if isinstance(raw_registry, list):
                        registry = self._window.controller.load_web_sources_registry(raw_registry)
                    selected = config.get("last_selected") if isinstance(config.get("last_selected"), dict) else {}
                    selected_website_id = str(selected.get("website_id")) if selected.get("website_id") else None
                    selected_area_id = str(selected.get("area_id")) if selected.get("area_id") else None
                    options = config.get("options") if isinstance(config.get("options"), dict) else {}
                    smart = SmartOptions(
                        show_likely=bool(options.get("show_likely", False)),
                        auto_sort=True,
                        skip_duplicates=bool(options.get("skip_duplicates", True)),
                        allow_zip=bool(options.get("allow_zip", True)),
                    )
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
        controller = self._window.controller
        if controller is None:
            return
        paths = getattr(controller, "app_paths", None)
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
                    "auto_sort": True,
                    "skip_duplicates": active_smart.skip_duplicates,
                    "allow_zip": active_smart.allow_zip,
                },
            )
        except Exception:
            # Settings persistence must never block scanning or downloading.
            return

    def on_registry_changed(self, payload: object) -> None:
        controller = self._window.controller
        if controller is None:
            return
        if not isinstance(payload, list):
            self._window.web_sources_panel.set_status("Saved-page update was invalid.")
            return

        registry = controller.load_web_sources_registry(payload)
        website_id, area_id = self._window.web_sources_panel.selected_source_ids()
        self._window.web_sources_panel.set_sources(
            websites=registry,
            selected_website_id=website_id,
            selected_area_id=area_id,
        )
        self.persist_state(website_id=website_id, area_id=area_id, registry=registry)

    def on_preferences_changed(self, payload: object) -> None:
        if not isinstance(payload, SmartOptions):
            return
        self.persist_state(smart=payload)

    def on_scan_requested(self, payload: object) -> None:
        controller = self._window.controller
        panel = self._window.web_sources_panel
        if controller is None:
            panel.set_status("Web Sources scanning is unavailable because the controller is not configured.")
            return
        if not isinstance(payload, WebScanRequest):
            panel.set_status("The page scan request was invalid.")
            return

        urls = self._unique_urls(payload.urls)
        if not urls:
            panel.set_status("Choose at least one valid page URL to scan.")
            return

        cap = int(getattr(panel, "PAGE_SCAN_CAP", 100))
        if len(urls) > cap:
            if not panel.confirm_large_page_scan(len(urls), cap=cap):
                panel.set_status("Page scan cancelled before starting.")
                return
            urls = urls[:cap]

        progress = _ProgressSession(
            window=self._window,
            panel=panel,
            label_text=f"Scanning {len(urls)} page(s)...",
            title="Web Sources Scan",
            minimum=0,
            maximum=0,
            cancel_label_text="Cancelling page scan...",
            cancel_status_text="Cancelling page scan...",
        )
        results: ScanResults | None = None
        try:
            results = controller.scan_web_source_pages(
                urls,
                show_likely=payload.smart.show_likely,
                cancel_requested=progress.is_cancel_requested,
            )
        except WebpageScanCancelledError:
            panel.set_status("Page scan cancelled. Existing Found Files were kept.")
            self._window._status("Web Sources scan cancelled")
            return
        except Exception as exc:
            panel.set_status(f"Page scan failed: {self._normalize_network_error_message(str(exc))}")
            return
        finally:
            progress.close(complete=results is not None)

        friendly_results = self._friendly_scan_results(results)
        outcome = panel.add_results(friendly_results)
        failed_count = len(friendly_results.failed_pages)
        status = (
            f"Web Sources scan complete: {outcome.added_count} new, "
            f"{len(outcome.results.items)} total"
        )
        if failed_count:
            status += f", {failed_count} page(s) failed"
        self._window._status(status)
        self.persist_state(
            website_id=payload.website_id,
            area_id=payload.area_id,
            smart=payload.smart,
        )

    def on_discover_links_requested(self, payload: object) -> None:
        controller = self._window.controller
        panel = self._window.web_sources_panel
        if controller is None:
            panel.set_status("Linked-page discovery is unavailable because the controller is not configured.")
            return
        if not isinstance(payload, WebLinkDiscoveryRequest) or not payload.url.strip():
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
        links = None
        try:
            links = controller.discover_web_source_index_links(
                payload.url,
                cancel_requested=progress.is_cancel_requested,
            )
        except WebpageScanCancelledError:
            panel.set_status("Linked-page discovery cancelled.")
            self._window._status("Web Sources page discovery cancelled")
            return
        except Exception as exc:
            panel.set_status(f"Could not find linked pages: {self._normalize_network_error_message(str(exc))}")
            return
        finally:
            progress.close(complete=links is not None)

        panel.set_index_links(tuple(links))
        self._window._status(f"Web Sources found {len(links)} linked page(s)")
        self.persist_state(website_id=payload.website_id, area_id=payload.area_id)

    def on_download_requested(self, payload: object) -> None:
        controller = self._window.controller
        panel = self._window.web_sources_panel
        if controller is None:
            panel.set_status("Web Sources downloading is unavailable because the controller is not configured.")
            return
        if not isinstance(payload, WebDownloadRequest) or not payload.items:
            panel.set_status("Select at least one found file to download.")
            return

        items = list(payload.items)
        progress = _ProgressSession(
            window=self._window,
            panel=panel,
            label_text="Preparing downloads...",
            title="Web Sources Download",
            minimum=0,
            maximum=max(1, len(items)),
            cancel_label_text="Cancelling downloads...",
            cancel_status_text="Cancelling downloads...",
        )
        progress.update(
            done_count=0,
            total_count=len(items),
            label_text="Preparing downloads...",
            status_text="Preparing downloads...",
        )

        report = None
        try:
            report = controller.download_web_sources_items(
                items,
                payload.target,
                smart=payload.smart,
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
            panel.set_status(f"Download failed: {self._normalize_network_error_message(str(exc))}")
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
                self.persist_state(
                    website_id=payload.website_id,
                    area_id=payload.area_id,
                    smart=payload.smart,
                )
                return

        message = self.format_download_status(report)
        panel.set_status(message)
        self._window._status(message)
        self.persist_state(
            website_id=payload.website_id,
            area_id=payload.area_id,
            smart=payload.smart,
        )

    def on_diagnostics_requested(self, payload: object) -> None:
        panel = self._window.web_sources_panel
        if not isinstance(payload, WebDiagnosticsRequest) or not payload.url.strip():
            panel.set_status("Choose a valid page URL before running a connection check.")
            return
        try:
            summary = self._diagnostics_summary_for_url(payload.url)
        except Exception as exc:
            summary = f"Connection check failed: {self._normalize_network_error_message(str(exc))}"
        panel.set_status(summary)
        self._window._status(summary)

    @staticmethod
    def _unique_urls(values: tuple[str, ...]) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()
        for value in values:
            url = str(value or "").strip()
            if not url or url.casefold() in seen:
                continue
            seen.add(url.casefold())
            urls.append(url)
        return urls

    @classmethod
    def _friendly_scan_results(cls, results: ScanResults) -> ScanResults:
        failures: list[str] = []
        for entry in tuple(results.failed_pages or ()):
            text = " ".join(str(entry).split())
            scheme_at = text.find("://")
            separator = text.find(": ", scheme_at + 3 if scheme_at >= 0 else 0)
            if separator < 0:
                failures.append(cls._normalize_network_error_message(text))
                continue
            page = text[:separator]
            detail = text[separator + 2 :]
            failures.append(f"{page}: {cls._normalize_network_error_message(detail)}")
        return ScanResults(
            items=tuple(results.items),
            filtered_count=int(results.filtered_count or 0),
            failed_pages=tuple(failures),
        )

    @classmethod
    def _normalize_network_error_message(cls, detail: str) -> str:
        raw = str(detail or "").strip()
        lowered = raw.lower()
        if "winerror 10013" in lowered or "forbidden by its access permissions" in lowered:
            return cls.WINDOWS_BLOCKED_ACCESS_TEXT
        if "timed out" in lowered or "timeout" in lowered or "winerror 10060" in lowered:
            return "Network timeout: the website did not respond in time. Try again or scan fewer pages."
        http_match = re.search(r"http error\s+(\d{3})(?::\s*([^>]+))?", raw, flags=re.IGNORECASE)
        if http_match:
            return cls._friendly_http_error(
                int(http_match.group(1)),
                reason=" ".join(str(http_match.group(2) or "").split()),
            )
        return raw or "Unknown network error"

    @staticmethod
    def _friendly_http_error(code: int, *, reason: str = "") -> str:
        reason_text = f" ({reason})" if reason else ""
        if code == 401:
            return "HTTP 401 (Unauthorized): this page needs authentication or cookies before scanning."
        if code == 403:
            return "HTTP 403 (Forbidden): the website blocked automated scanning. Try a connection check or a direct file URL."
        if code == 404:
            return "HTTP 404 (Not Found): the page or file URL no longer exists."
        if code == 429:
            return "HTTP 429 (Rate limited): wait briefly, then scan fewer pages on this website."
        if code in {500, 502, 503, 504}:
            return (
                f"HTTP {code}{reason_text}: the website or server failed before Sprite Factory could scan it. "
                "Try again later, scan fewer pages, or use a direct file URL."
            )
        if 400 <= code < 500:
            return f"HTTP {code}{reason_text}: the website rejected this request."
        if 500 <= code < 600:
            return f"HTTP {code}{reason_text}: the website or server failed. Try again later."
        return f"HTTP {code}{reason_text}"

    @classmethod
    def _is_socket_access_denied(cls, exc: Exception) -> bool:
        reason = getattr(exc, "reason", exc)
        if getattr(reason, "winerror", None) == 10013:
            return True
        message = str(reason or exc).lower()
        return "winerror 10013" in message or "forbidden by its access permissions" in message

    @staticmethod
    def _normalize_diagnostics_url(raw_url: str) -> str:
        candidate = str(raw_url or "").strip()
        if not candidate:
            raise ValueError("Missing page URL for the connection check.")
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
            raise ValueError("Connection check failed because the URL host is missing.")
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)

        try:
            socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except Exception as exc:
            return f"Connection check: DNS lookup failed for {host} ({self._normalize_network_error_message(str(exc))})"
        try:
            with socket.create_connection((host, int(port)), timeout=4.0):
                pass
        except Exception as exc:
            if self._is_socket_access_denied(exc):
                return f"Connection check: {self.WINDOWS_BLOCKED_ACCESS_TEXT}"
            return (
                f"Connection check: could not connect to {host}:{port} "
                f"({self._normalize_network_error_message(str(exc))})"
            )

        request = Request(normalized, headers={"User-Agent": "SpriteFactory/1.2 (Connection Check)"})
        try:
            with urlopen(request, timeout=8.0) as response:
                status = getattr(response, "status", None)
                code = int(status) if isinstance(status, int) else 200
                return f"Connection check passed: DNS, connection, and HTTP {code} for {host}:{port}"
        except Exception as first_exc:
            if self._is_socket_access_denied(first_exc):
                return f"Connection check: {self.WINDOWS_BLOCKED_ACCESS_TEXT}"
            try:
                direct_opener = build_opener(ProxyHandler({}))
                with direct_opener.open(request, timeout=8.0) as response:
                    status = getattr(response, "status", None)
                    code = int(status) if isinstance(status, int) else 200
                    return f"Connection check passed without proxy: DNS, connection, and HTTP {code} for {host}:{port}"
            except Exception as second_exc:
                if self._is_socket_access_denied(second_exc):
                    return f"Connection check: {self.WINDOWS_BLOCKED_ACCESS_TEXT}"
                detail = self._normalize_network_error_message(str(first_exc))
                return f"Connection check partial: DNS and connection passed, but the page request failed ({detail})"

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
        prefix = "Web Sources download cancelled" if cancelled else "Web Sources download"
        message = (
            f"{prefix}: downloaded {downloaded}, reused {reused} cached, "
            f"skipped {skipped}, failed {failed}, loaded {loaded} into the workspace"
        )
        sample = WebSourcesService.summarize_failures(tuple(getattr(report, "failed", ()) or ()), limit=2)
        return f"{message} | sample failures: {sample}" if sample else message
