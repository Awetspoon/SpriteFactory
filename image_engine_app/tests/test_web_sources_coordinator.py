"""Web Sources coordinator contract tests."""

from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from image_engine_app.app.services.web_sources_network import normalize_network_error_message
from image_engine_app.app.services.web_sources_workflow import WebSourcesWorkflowService
from image_engine_app.app.web_sources_models import (
    Confidence,
    ImportTarget,
    ScanOrigin,
    ScanResults,
    SmartOptions,
    WebDiagnosticsRequest,
    WebDownloadRequest,
    WebIndexLink,
    WebItem,
    WebLinkDiscoveryRequest,
    WebPageBookmark,
    WebSavePagesRequest,
    WebScanRequest,
    WebSourcesState,
)
from image_engine_app.engine.ingest.import_result import ImportResult, ImportedAsset
from image_engine_app.engine.models import AssetRecord, SourceType
from image_engine_app.ui.main_window import web_sources_coordinator as coordinator_module
from image_engine_app.ui.main_window.web_sources_coordinator import WebSourcesCoordinator


class _FakeSignal:
    def __init__(self) -> None:
        self._callbacks: list = []

    def connect(self, callback) -> None:  # noqa: ANN001
        self._callbacks.append(callback)

    def disconnect(self, callback) -> None:  # noqa: ANN001
        self._callbacks = [entry for entry in self._callbacks if entry is not callback]


class _FakeProgressDialog:
    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        _ = (args, kwargs)
        self.canceled = _FakeSignal()
        self._maximum = 1
        self._value = 0

    def setWindowTitle(self, _title: str) -> None:
        return

    def setWindowModality(self, _modality) -> None:  # noqa: ANN001
        return

    def setMinimumDuration(self, _value: int) -> None:
        return

    def setAutoClose(self, _enabled: bool) -> None:
        return

    def setAutoReset(self, _enabled: bool) -> None:
        return

    def setLabelText(self, _text: str) -> None:
        return

    def setMaximum(self, value: int) -> None:
        self._maximum = int(value)

    def maximum(self) -> int:
        return self._maximum

    def setValue(self, value: int) -> None:
        self._value = int(value)

    def show(self) -> None:
        return

    def hide(self) -> None:
        return

    def deleteLater(self) -> None:
        return


class _FakeApp:
    @staticmethod
    def processEvents() -> None:
        return


class _FakePanel:
    def __init__(self) -> None:
        self.status_messages: list[str] = []
        self.state = WebSourcesState()
        self.last_outcome = None
        self.confirm_result = True
        self.confirm_calls: list[tuple[int, int]] = []

    def set_status(self, message: str) -> None:
        self.status_messages.append(str(message))

    def set_state(self, state: WebSourcesState) -> None:
        self.state = state

    def show_scan_outcome(self, outcome) -> None:  # noqa: ANN001
        self.last_outcome = outcome
        self.state = outcome.state

    def confirm_large_page_scan(self, count: int, *, cap: int | None = None) -> bool:
        self.confirm_calls.append((int(count), int(cap or 0)))
        return self.confirm_result


class _FakeNetwork:
    def __init__(self) -> None:
        self.scan_results = ScanResults(items=())
        self.scan_error: Exception | None = None
        self.scanned_urls: list[str] = []
        self.discovery_url = ""
        self.download_report = ImportResult()

    def scan_pages(self, urls: list[str], **kwargs) -> ScanResults:  # noqa: ANN003
        self.scanned_urls = list(urls)
        callback = kwargs.get("progress_callback")
        if callback is not None:
            callback(len(urls), len(urls), "Scan complete")
        if self.scan_error is not None:
            raise self.scan_error
        return self.scan_results

    def discover_links(self, url: str, **_kwargs) -> tuple[WebIndexLink, ...]:
        self.discovery_url = url
        return (
            WebIndexLink("Page One", f"{url.rstrip('/')}/one", source_page=url),
            WebIndexLink("Page Two", f"{url.rstrip('/')}/two", source_page=url),
        )

    def download_items(self, *_args, **_kwargs) -> ImportResult:
        return self.download_report


class _FakeController:
    def __init__(self, network: _FakeNetwork | None = None, *, page_limit: int = 100) -> None:
        self.network = network or _FakeNetwork()
        self.workflow = WebSourcesWorkflowService(
            app_paths=None,
            scanner=self.network,
            downloader=self.network,
            diagnostics=lambda _url: "Connection check passed",
            page_limit=page_limit,
        )

    def web_sources_state(self):  # noqa: ANN201
        return self.workflow.state()

    def save_web_sources_pages(self, request):  # noqa: ANN001, ANN201
        return self.workflow.save_pages(request)

    def remove_web_sources_page(self, request):  # noqa: ANN001, ANN201
        return self.workflow.remove_saved_page(request)

    def remove_web_sources_website(self, request):  # noqa: ANN001, ANN201
        return self.workflow.remove_saved_website(request)

    def update_web_sources_preferences(self, options):  # noqa: ANN001, ANN201
        return self.workflow.update_preferences(options)

    def plan_web_sources_scan(self, request):  # noqa: ANN001, ANN201
        return self.workflow.plan_scan(request)

    def run_web_sources_scan(self, plan, **kwargs):  # noqa: ANN001, ANN003, ANN201
        return self.workflow.run_scan(plan, **kwargs)

    def discover_web_sources_links(self, request, **kwargs):  # noqa: ANN001, ANN003, ANN201
        return self.workflow.discover_links(request, **kwargs)

    def clear_web_sources_links(self):  # noqa: ANN201
        return self.workflow.clear_linked_pages()

    def clear_web_sources_found_files(self):  # noqa: ANN201
        return self.workflow.clear_found_files()

    def download_web_sources(self, request, **kwargs):  # noqa: ANN001, ANN003, ANN201
        return self.workflow.download(request, **kwargs)

    def diagnose_web_source(self, request):  # noqa: ANN001, ANN201
        return self.workflow.diagnose(request)

    @staticmethod
    def friendly_web_sources_error(error: object) -> str:
        return normalize_network_error_message(error)

    @staticmethod
    def format_web_sources_download_status(report: object) -> str:
        return WebSourcesWorkflowService.format_download_status(report)


class _MalformedDownloadController(_FakeController):
    def download_web_sources(self, _request, **_kwargs):  # noqa: ANN201
        return SimpleNamespace(
            downloaded=("a.png",),
            reused=(),
            skipped=(),
            failed=(),
            assets=("invalid",),
            cancelled=False,
        )


class _FakeWindow:
    def __init__(self, controller=None) -> None:  # noqa: ANN001
        self.controller = controller or _FakeController()
        self.web_sources_panel = _FakePanel()
        self.status_updates: list[str] = []
        self.register_calls: list[tuple[list[AssetRecord], bool]] = []

    def _status(self, message: str) -> None:
        self.status_updates.append(str(message))

    def _register_assets(self, assets: list[AssetRecord], *, set_active: bool) -> None:
        self.register_calls.append((list(assets), bool(set_active)))


class WebSourcesCoordinatorTests(unittest.TestCase):
    def _progress_patches(self):  # noqa: ANN201
        return (
            patch.object(coordinator_module, "QProgressDialog", _FakeProgressDialog),
            patch.object(coordinator_module, "QApplication", _FakeApp),
        )

    @staticmethod
    def _scan_request(*urls: str) -> WebScanRequest:
        return WebScanRequest(
            urls=tuple(urls),
            smart=SmartOptions(show_likely=True),
            origin=ScanOrigin.ENTERED,
        )

    def test_init_and_saved_page_mutations_render_workflow_state(self) -> None:
        window = _FakeWindow()
        coordinator = WebSourcesCoordinator(window)
        coordinator.init_panel()
        coordinator.on_save_pages_requested(
            WebSavePagesRequest(
                pages=(WebPageBookmark("https://example.com/sprites"),),
            )
        )

        self.assertEqual(1, len(window.web_sources_panel.state.websites))
        self.assertIn("Saved 1 new page", window.web_sources_panel.status_messages[-1])

    def test_all_page_sources_use_one_scan_and_accumulate(self) -> None:
        network = _FakeNetwork()
        window = _FakeWindow(_FakeController(network))
        coordinator = WebSourcesCoordinator(window)
        first_patch, second_patch = self._progress_patches()
        with first_patch, second_patch:
            network.scan_results = ScanResults(
                items=(
                    WebItem(
                        url="https://cdn.example.com/one.png",
                        name="one.png",
                        ext=".png",
                        confidence=Confidence.DIRECT,
                    ),
                )
            )
            coordinator.on_scan_requested(self._scan_request("https://example.com/one"))
            network.scan_results = ScanResults(
                items=(
                    WebItem(
                        url="https://cdn.example.com/two.png",
                        name="two.png",
                        ext=".png",
                        confidence=Confidence.DIRECT,
                    ),
                )
            )
            coordinator.on_scan_requested(
                WebScanRequest(
                    urls=("https://example.com/two",),
                    origin=ScanOrigin.SAVED,
                )
            )

        self.assertEqual(2, len(window.web_sources_panel.state.found_files))
        self.assertTrue(any("scan complete" in message.casefold() for message in window.status_updates))

    def test_scan_dedupes_and_caps_before_network_call(self) -> None:
        network = _FakeNetwork()
        window = _FakeWindow(_FakeController(network, page_limit=2))
        coordinator = WebSourcesCoordinator(window)
        first_patch, second_patch = self._progress_patches()
        with first_patch, second_patch:
            coordinator.on_scan_requested(
                self._scan_request(
                    "https://example.com/one",
                    "https://example.com/one#duplicate",
                    "https://example.com/two",
                    "https://example.com/three",
                )
            )

        self.assertEqual([(3, 2)], window.web_sources_panel.confirm_calls)
        self.assertEqual(
            ["https://example.com/one", "https://example.com/two"],
            network.scanned_urls,
        )

    def test_large_scan_can_be_cancelled_before_network_call(self) -> None:
        network = _FakeNetwork()
        window = _FakeWindow(_FakeController(network, page_limit=1))
        window.web_sources_panel.confirm_result = False
        coordinator = WebSourcesCoordinator(window)
        coordinator.on_scan_requested(
            self._scan_request("https://example.com/one", "https://example.com/two")
        )

        self.assertEqual([], network.scanned_urls)
        self.assertIn("cancelled before starting", window.web_sources_panel.status_messages[-1])

    def test_partial_and_hard_failures_keep_previous_results(self) -> None:
        network = _FakeNetwork()
        window = _FakeWindow(_FakeController(network))
        coordinator = WebSourcesCoordinator(window)
        first_patch, second_patch = self._progress_patches()
        with first_patch, second_patch:
            network.scan_results = ScanResults(
                items=(
                    WebItem(
                        url="https://cdn.example.com/good.png",
                        name="good.png",
                        ext=".png",
                        confidence=Confidence.DIRECT,
                    ),
                ),
                failed_pages=("https://example.com/bad: HTTP Error 502: Bad Gateway",),
            )
            coordinator.on_scan_requested(
                self._scan_request("https://example.com/good", "https://example.com/bad")
            )
            network.scan_error = RuntimeError("HTTP Error 403: Forbidden")
            coordinator.on_scan_requested(self._scan_request("https://example.com/blocked"))

        self.assertEqual(1, len(window.web_sources_panel.state.found_files))
        self.assertIn("HTTP 403", window.web_sources_panel.status_messages[-1])

    def test_discovery_only_updates_linked_pages(self) -> None:
        network = _FakeNetwork()
        window = _FakeWindow(_FakeController(network))
        coordinator = WebSourcesCoordinator(window)
        first_patch, second_patch = self._progress_patches()
        with first_patch, second_patch:
            coordinator.on_discover_links_requested(
                WebLinkDiscoveryRequest(url="https://example.com/index")
            )

        self.assertEqual("https://example.com/index", network.discovery_url)
        self.assertEqual(2, len(window.web_sources_panel.state.linked_pages))
        self.assertEqual(0, len(window.web_sources_panel.state.found_files))

    def test_download_registers_only_valid_assets(self) -> None:
        network = _FakeNetwork()
        asset = AssetRecord(
            source_type=SourceType.WEBPAGE_ITEM,
            source_uri="https://cdn.example.com/a.png",
            cache_path="cache/a.png",
            original_name="a.png",
        )
        network.download_report = ImportResult(
            entries=[ImportedAsset(asset=asset, source=asset.source_uri)]
        )
        window = _FakeWindow(_FakeController(network))
        coordinator = WebSourcesCoordinator(window)
        item = WebItem(
            url=asset.source_uri,
            name="a.png",
            ext=".png",
            confidence=Confidence.DIRECT,
        )
        first_patch, second_patch = self._progress_patches()
        with first_patch, second_patch:
            coordinator.on_download_requested(
                WebDownloadRequest(items=(item,), target=ImportTarget.NORMAL)
            )

        self.assertEqual(1, len(window.register_calls))
        self.assertEqual("a.png", window.register_calls[0][0][0].original_name)

    def test_malformed_download_assets_are_ignored_without_crashing(self) -> None:
        window = _FakeWindow(_MalformedDownloadController())
        coordinator = WebSourcesCoordinator(window)
        item = WebItem(
            url="https://cdn.example.com/a.png",
            name="a.png",
            ext=".png",
            confidence=Confidence.DIRECT,
        )
        first_patch, second_patch = self._progress_patches()
        with first_patch, second_patch:
            coordinator.on_download_requested(WebDownloadRequest(items=(item,)))

        self.assertEqual([], window.register_calls)
        self.assertTrue(any("downloaded 1" in message.casefold() for message in window.status_updates))

    def test_diagnostics_and_invalid_requests_use_only_their_operation(self) -> None:
        window = _FakeWindow()
        coordinator = WebSourcesCoordinator(window)
        coordinator.on_diagnostics_requested(WebDiagnosticsRequest(url="https://example.com"))
        coordinator.on_scan_requested({"urls": ["https://example.com"]})
        coordinator.on_discover_links_requested(self._scan_request("https://example.com"))

        self.assertEqual("Connection check passed", window.web_sources_panel.status_messages[0])
        self.assertIn("invalid", window.web_sources_panel.status_messages[1].casefold())
        self.assertIn("valid page", window.web_sources_panel.status_messages[2].casefold())


if __name__ == "__main__":
    unittest.main()
