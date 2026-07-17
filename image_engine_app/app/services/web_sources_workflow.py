"""Application workflow and state owner for Web Sources."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from image_engine_app.app.paths import AppPaths
from image_engine_app.app.services.web_sources_network import (
    diagnose_url,
    friendly_scan_results_failures,
    normalize_network_error_message,
)
from image_engine_app.app.services.web_sources_downloader import WebSourcesDownloader
from image_engine_app.app.services.web_sources_registry import (
    WebSourcesRegistryService,
    normalize_page_url,
)
from image_engine_app.app.services.web_sources_scanner import WebSourcesScanner
from image_engine_app.app.settings_store import load_web_sources_settings, save_web_sources_settings
from image_engine_app.app.web_sources_models import (
    ScanMergeResult,
    ScanResults,
    SmartOptions,
    WebDiagnosticsRequest,
    WebDiscoveryOutcome,
    WebDownloadRequest,
    WebLinkDiscoveryRequest,
    WebRemoveSavedPageRequest,
    WebRemoveSavedWebsiteRequest,
    WebSavePagesRequest,
    WebScanOutcome,
    WebScanPlan,
    WebScanRequest,
    WebSourcesMutation,
    WebSourcesState,
    coerce_smart_options,
    merge_scan_results,
)
from image_engine_app.engine.ingest.import_result import ImportResult
from image_engine_app.engine.ingest.url_ingest import DownloadGuards
from image_engine_app.engine.models import AssetRecord


class WebSourcesWorkflowService:
    """Own saved pages, linked pages, Found Files, and all Web Sources calls."""

    DEFAULT_PAGE_LIMIT = 100

    def __init__(
        self,
        *,
        app_paths: AppPaths | None,
        scanner: WebSourcesScanner,
        downloader: WebSourcesDownloader,
        registry: WebSourcesRegistryService | None = None,
        diagnostics: Callable[[str], str] = diagnose_url,
        page_limit: int = DEFAULT_PAGE_LIMIT,
    ) -> None:
        self._app_paths = app_paths
        self._scanner = scanner
        self._downloader = downloader
        self._registry = registry or WebSourcesRegistryService()
        self._diagnostics = diagnostics
        self._page_limit = max(1, int(page_limit))
        self._state = self._load_initial_state()

    @property
    def page_limit(self) -> int:
        return self._page_limit

    def state(self) -> WebSourcesState:
        return self._state

    def replace_registry(self, payload: object) -> WebSourcesMutation:
        websites = self._registry.from_payload(payload)
        selected_website_id, selected_page_id = self._registry.resolve_selection(
            websites,
            self._state.selected_website_id,
            self._state.selected_page_id,
        )
        self._state = replace(
            self._state,
            websites=websites,
            selected_website_id=selected_website_id,
            selected_page_id=selected_page_id,
        )
        self._persist()
        return WebSourcesMutation(self._state, "Saved pages updated. Found Files were kept.")

    def save_pages(self, request: WebSavePagesRequest) -> WebSourcesMutation:
        if not isinstance(request, WebSavePagesRequest):
            raise TypeError("Invalid saved-page request")
        result = self._registry.save_pages(self._state.websites, request.pages)
        self._state = replace(
            self._state,
            websites=result.websites,
            selected_website_id=result.selected_website_id,
            selected_page_id=result.selected_page_id,
        )
        self._persist()
        message = f"Saved {result.added_count} new page(s)"
        details: list[str] = []
        if result.duplicate_count:
            details.append(f"skipped {result.duplicate_count} already saved")
        if result.invalid_count:
            details.append(f"skipped {result.invalid_count} invalid")
        if details:
            message += "; " + ", ".join(details)
        return WebSourcesMutation(self._state, message + ".")

    def remove_saved_page(self, request: WebRemoveSavedPageRequest) -> WebSourcesMutation:
        if not isinstance(request, WebRemoveSavedPageRequest):
            raise TypeError("Invalid remove-page request")
        result = self._registry.remove_page(
            self._state.websites,
            request.website_id,
            request.page_id,
        )
        self._state = replace(
            self._state,
            websites=result.websites,
            selected_website_id=result.selected_website_id,
            selected_page_id=result.selected_page_id,
        )
        self._persist()
        message = (
            "Saved page removed. Found Files were kept."
            if result.duplicate_count == 0
            else "The selected saved page no longer exists."
        )
        return WebSourcesMutation(self._state, message)

    def remove_saved_website(self, request: WebRemoveSavedWebsiteRequest) -> WebSourcesMutation:
        if not isinstance(request, WebRemoveSavedWebsiteRequest):
            raise TypeError("Invalid remove-website request")
        result = self._registry.remove_website(self._state.websites, request.website_id)
        self._state = replace(
            self._state,
            websites=result.websites,
            selected_website_id=result.selected_website_id,
            selected_page_id=result.selected_page_id,
        )
        self._persist()
        message = (
            "Saved website removed. Found Files were kept."
            if result.duplicate_count == 0
            else "The selected saved website no longer exists."
        )
        return WebSourcesMutation(self._state, message)

    def update_preferences(self, options: SmartOptions) -> WebSourcesState:
        if not isinstance(options, SmartOptions):
            raise TypeError("Invalid Web Sources preferences")
        self._state = replace(self._state, smart=replace(options, auto_sort=True))
        self._persist()
        return self._state

    def plan_scan(self, request: WebScanRequest) -> WebScanPlan:
        if not isinstance(request, WebScanRequest):
            raise TypeError("Invalid page scan request")

        urls: list[str] = []
        seen: set[str] = set()
        for raw_url in request.urls:
            normalized = normalize_page_url(raw_url)
            if normalized is None:
                continue
            key = normalized.casefold()
            if key in seen:
                continue
            seen.add(key)
            urls.append(normalized)

        if not urls:
            raise ValueError("Choose at least one valid page URL to scan.")

        return WebScanPlan(
            request=request,
            urls=tuple(urls[: self._page_limit]),
            requested_count=len(urls),
            page_limit=self._page_limit,
        )

    def run_scan(
        self,
        plan: WebScanPlan,
        *,
        opener=None,
        progress_callback=None,
        cancel_requested=None,
    ) -> WebScanOutcome:
        if not isinstance(plan, WebScanPlan):
            raise TypeError("Invalid page scan plan")

        latest = self._scanner.scan_pages(
            list(plan.urls),
            show_likely=plan.request.smart.show_likely,
            opener=opener,
            progress_callback=progress_callback,
            cancel_requested=cancel_requested,
        )
        latest = ScanResults(
            items=tuple(latest.items),
            filtered_count=int(latest.filtered_count or 0),
            failed_pages=friendly_scan_results_failures(tuple(latest.failed_pages or ())),
        )
        current = ScanResults(items=self._state.found_files)
        merge = merge_scan_results(current, latest)
        self._state = replace(
            self._state,
            found_files=merge.results.items,
            latest_scan=latest,
            selected_website_id=plan.request.website_id or self._state.selected_website_id,
            selected_page_id=plan.request.page_id or self._state.selected_page_id,
            smart=replace(plan.request.smart, auto_sort=True),
        )
        self._persist()
        return WebScanOutcome(state=self._state, latest=latest, merge=merge)

    def discover_links(
        self,
        request: WebLinkDiscoveryRequest,
        *,
        opener=None,
        cancel_requested=None,
    ) -> WebDiscoveryOutcome:
        if not isinstance(request, WebLinkDiscoveryRequest):
            raise TypeError("Invalid linked-page discovery request")
        normalized_url = normalize_page_url(request.url)
        if normalized_url is None:
            raise ValueError("Choose a valid page before finding linked pages.")

        links = self._scanner.discover_links(
            normalized_url,
            opener=opener,
            cancel_requested=cancel_requested,
        )
        self._state = replace(
            self._state,
            linked_pages=tuple(links),
            selected_website_id=request.website_id or self._state.selected_website_id,
            selected_page_id=request.page_id or self._state.selected_page_id,
        )
        self._persist()
        return WebDiscoveryOutcome(state=self._state, links=tuple(links))

    def clear_linked_pages(self) -> WebSourcesMutation:
        self._state = replace(self._state, linked_pages=())
        return WebSourcesMutation(self._state, "Linked pages cleared. Found Files were kept.")

    def clear_found_files(self) -> WebSourcesMutation:
        self._state = replace(
            self._state,
            found_files=(),
            latest_scan=ScanResults(items=()),
        )
        return WebSourcesMutation(self._state, "Found Files cleared.")

    def download(
        self,
        request: WebDownloadRequest,
        *,
        guards: DownloadGuards | None = None,
        opener=None,
        progress_callback=None,
        cancel_requested=None,
    ) -> ImportResult:
        if not isinstance(request, WebDownloadRequest) or not request.items:
            raise ValueError("Select at least one found file to download.")
        self._state = replace(
            self._state,
            selected_website_id=request.website_id or self._state.selected_website_id,
            selected_page_id=request.page_id or self._state.selected_page_id,
            smart=replace(request.smart, auto_sort=True),
        )
        self._persist()
        return self._downloader.download_items(
            list(request.items),
            request.target,
            smart=self._state.smart,
            guards=guards,
            opener=opener,
            progress_callback=progress_callback,
            cancel_requested=cancel_requested,
        )

    def diagnose(self, request: WebDiagnosticsRequest) -> str:
        if not isinstance(request, WebDiagnosticsRequest):
            raise TypeError("Invalid connection-check request")
        return self._diagnostics(request.url)

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
        reused_values = getattr(report, "reused", None)
        reused = (
            len(tuple(reused_values or ()))
            if reused_values is not None
            else max(0, loaded - downloaded)
        )
        cancelled = bool(getattr(report, "cancelled", False))
        prefix = "Web Sources download cancelled" if cancelled else "Web Sources download"
        message = (
            f"{prefix}: downloaded {downloaded}, reused {reused} cached, "
            f"skipped {skipped}, failed {failed}, loaded {loaded} into the workspace"
        )
        failures = tuple(getattr(report, "failed", ()) or ())
        if failures:
            sample = "; ".join(str(item).strip() for item in failures[:2] if str(item).strip())
            if len(failures) > 2:
                sample += f"; +{len(failures) - 2} more"
            if sample:
                message += f" | sample failures: {sample}"
        return message

    @staticmethod
    def friendly_error(error: object) -> str:
        return normalize_network_error_message(error)

    def _load_initial_state(self) -> WebSourcesState:
        if self._app_paths is None:
            return WebSourcesState()

        try:
            config = load_web_sources_settings(self._app_paths)
            websites = self._registry.from_payload(config.get("registry"))
            selected = config.get("last_selected")
            if not isinstance(selected, dict):
                selected = {}
            selected_website_id, selected_page_id = self._registry.resolve_selection(
                websites,
                str(selected.get("website_id")) if selected.get("website_id") else None,
                str(selected.get("page_id")) if selected.get("page_id") else None,
            )
            smart = coerce_smart_options(config.get("options"))
            return WebSourcesState(
                websites=websites,
                selected_website_id=selected_website_id,
                selected_page_id=selected_page_id,
                smart=replace(smart, auto_sort=True),
            )
        except Exception:
            return WebSourcesState()

    def _persist(self) -> None:
        if self._app_paths is None:
            return
        try:
            save_web_sources_settings(
                self._app_paths,
                registry=self._registry.to_payload(self._state.websites),
                last_selected={
                    "website_id": self._state.selected_website_id,
                    "page_id": self._state.selected_page_id,
                },
                options={
                    "show_likely": self._state.smart.show_likely,
                    "auto_sort": True,
                    "skip_duplicates": self._state.smart.skip_duplicates,
                    "allow_zip": self._state.smart.allow_zip,
                },
            )
        except Exception:
            # A settings write must never block scanning or downloading.
            return
