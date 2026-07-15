"""Web Sources coordinator contract tests."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from image_engine_app.app.web_sources_models import (
    Confidence,
    DownloadReport,
    FoundFilesStore,
    ImportTarget,
    ScanOrigin,
    ScanResults,
    SmartOptions,
    WebDiagnosticsRequest,
    WebDownloadRequest,
    WebIndexLink,
    WebItem,
    WebLinkDiscoveryRequest,
    WebScanRequest,
)
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

    def value(self) -> int:
        return self._value

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
    PAGE_SCAN_CAP = 100

    def __init__(self) -> None:
        self.status_messages: list[str] = []
        self._store = FoundFilesStore()
        self.index_links: tuple[WebIndexLink, ...] = ()
        self.sources: list[dict] = []
        self.smart = SmartOptions()
        self.confirm_result = True
        self.confirm_calls: list[tuple[int, int]] = []

    def set_status(self, message: str) -> None:
        self.status_messages.append(str(message))

    def add_results(self, results: ScanResults):  # noqa: ANN201
        return self._store.add(results)

    def found_items(self) -> tuple[WebItem, ...]:
        return self._store.items

    def set_index_links(self, links) -> None:  # noqa: ANN001
        self.index_links = tuple(links)

    def confirm_large_page_scan(self, count: int, *, cap: int | None = None) -> bool:
        self.confirm_calls.append((int(count), int(cap or 0)))
        return self.confirm_result

    def set_sources(
        self,
        *,
        websites: list[dict],
        selected_website_id: str | None = None,
        selected_area_id: str | None = None,
    ) -> None:
        _ = (selected_website_id, selected_area_id)
        self.sources = list(websites)

    def set_smart_options(self, smart: SmartOptions) -> None:
        self.smart = smart

    def smart_options(self) -> SmartOptions:
        return self.smart

    def sources_registry(self) -> list[dict]:
        return list(self.sources)

    def selected_source_ids(self) -> tuple[str | None, str | None]:
        return None, None


class _FakeController:
    app_paths = None

    def __init__(self) -> None:
        self.scanned_urls: list[str] = []
        self.discovery_url = ""

    def load_web_sources_registry(self, registry=None):  # noqa: ANN001
        return list(registry) if isinstance(registry, list) else []

    def scan_web_source_pages(self, urls: list[str], **_kwargs) -> ScanResults:
        self.scanned_urls = list(urls)
        return ScanResults(
            items=tuple(
                WebItem(
                    url=f"https://cdn.example.com/{index}.png",
                    name=f"{index}.png",
                    ext=".png",
                    confidence=Confidence.DIRECT,
                    source_page=url,
                )
                for index, url in enumerate(urls, start=1)
            )
        )

    def discover_web_source_index_links(self, url: str, **_kwargs) -> tuple[WebIndexLink, ...]:
        self.discovery_url = url
        return (
            WebIndexLink("Page One", f"{url.rstrip('/')}/one", source_page=url),
            WebIndexLink("Page Two", f"{url.rstrip('/')}/two", source_page=url),
        )

    def download_web_sources_items(self, *_args, **_kwargs) -> DownloadReport:
        asset = AssetRecord(
            source_type=SourceType.WEBPAGE_ITEM,
            source_uri="https://cdn.example.com/a.png",
            cache_path="cache/a.png",
            original_name="a.png",
        )
        return DownloadReport(
            downloaded=("a.png",),
            skipped=(),
            failed=(),
            assets=(asset,),
        )


class _PartialFailureController(_FakeController):
    def scan_web_source_pages(self, urls: list[str], **_kwargs) -> ScanResults:
        self.scanned_urls = list(urls)
        return ScanResults(
            items=(
                WebItem(
                    url="https://cdn.example.com/good.png",
                    name="good.png",
                    ext=".png",
                    confidence=Confidence.DIRECT,
                ),
            ),
            failed_pages=(f"{urls[-1]}: HTTP Error 502: Bad Gateway",),
        )


class _HardFailureController(_FakeController):
    def scan_web_source_pages(self, _urls: list[str], **_kwargs) -> ScanResults:
        raise RuntimeError("HTTP Error 403: Forbidden")


class _MalformedDownloadController(_FakeController):
    def download_web_sources_items(self, *_args, **_kwargs) -> DownloadReport:
        return DownloadReport(
            downloaded=("a.png",),
            skipped=(),
            failed=(),
            assets=("invalid",),  # type: ignore[arg-type]
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

    def test_all_page_sources_use_the_one_scan_call_and_accumulate(self) -> None:
        window = _FakeWindow()
        coordinator = WebSourcesCoordinator(window)
        first_patch, second_patch = self._progress_patches()
        with first_patch, second_patch:
            coordinator.on_scan_requested(self._scan_request("https://example.com/one"))
            coordinator.on_scan_requested(
                WebScanRequest(
                    urls=("https://example.com/two", "https://example.com/three"),
                    origin=ScanOrigin.SAVED,
                )
            )

        self.assertEqual(
            ["https://example.com/two", "https://example.com/three"],
            window.controller.scanned_urls,
        )
        self.assertEqual(2, len(window.web_sources_panel.found_items()))
        self.assertTrue(any("scan complete" in message.lower() for message in window.status_updates))

    def test_scan_dedupes_request_urls_before_service_call(self) -> None:
        window = _FakeWindow()
        coordinator = WebSourcesCoordinator(window)
        first_patch, second_patch = self._progress_patches()
        with first_patch, second_patch:
            coordinator.on_scan_requested(
                self._scan_request(
                    "https://example.com/page",
                    "https://example.com/page",
                )
            )
        self.assertEqual(["https://example.com/page"], window.controller.scanned_urls)

    def test_large_scan_uses_one_central_warning_and_cap(self) -> None:
        window = _FakeWindow()
        coordinator = WebSourcesCoordinator(window)
        urls = tuple(f"https://example.com/{index}" for index in range(150))
        first_patch, second_patch = self._progress_patches()
        with first_patch, second_patch:
            coordinator.on_scan_requested(self._scan_request(*urls))
        self.assertEqual([(150, 100)], window.web_sources_panel.confirm_calls)
        self.assertEqual(100, len(window.controller.scanned_urls))

    def test_large_scan_can_be_cancelled_before_network_call(self) -> None:
        window = _FakeWindow()
        window.web_sources_panel.confirm_result = False
        coordinator = WebSourcesCoordinator(window)
        coordinator.on_scan_requested(
            self._scan_request(*(f"https://example.com/{index}" for index in range(101)))
        )
        self.assertEqual([], window.controller.scanned_urls)
        self.assertIn("cancelled before starting", window.web_sources_panel.status_messages[-1])

    def test_partial_failures_keep_successes_and_receive_plain_error_text(self) -> None:
        window = _FakeWindow(_PartialFailureController())
        coordinator = WebSourcesCoordinator(window)
        first_patch, second_patch = self._progress_patches()
        with first_patch, second_patch:
            coordinator.on_scan_requested(
                self._scan_request("https://example.com/good", "https://example.com/bad")
            )
        self.assertEqual(1, len(window.web_sources_panel.found_items()))
        failure = window.web_sources_panel._store.results.failed_pages[0]
        self.assertIn("HTTP 502", failure)
        self.assertIn("scan fewer pages", failure)

    def test_hard_scan_failure_is_mapped_without_clearing_existing_results(self) -> None:
        window = _FakeWindow(_HardFailureController())
        window.web_sources_panel._store.add(
            ScanResults(
                items=(
                    WebItem(
                        url="https://cdn.example.com/existing.png",
                        name="existing.png",
                        ext=".png",
                        confidence=Confidence.DIRECT,
                    ),
                )
            )
        )
        coordinator = WebSourcesCoordinator(window)
        first_patch, second_patch = self._progress_patches()
        with first_patch, second_patch:
            coordinator.on_scan_requested(self._scan_request("https://example.com/blocked"))
        self.assertEqual(1, len(window.web_sources_panel.found_items()))
        self.assertIn("HTTP 403", window.web_sources_panel.status_messages[-1])

    def test_discovery_has_its_own_call_and_only_updates_linked_pages(self) -> None:
        window = _FakeWindow()
        coordinator = WebSourcesCoordinator(window)
        first_patch, second_patch = self._progress_patches()
        with first_patch, second_patch:
            coordinator.on_discover_links_requested(
                WebLinkDiscoveryRequest(url="https://example.com/index")
            )
        self.assertEqual("https://example.com/index", window.controller.discovery_url)
        self.assertEqual(2, len(window.web_sources_panel.index_links))
        self.assertEqual(0, len(window.web_sources_panel.found_items()))

    def test_download_registers_only_valid_assets_into_workspace(self) -> None:
        window = _FakeWindow()
        coordinator = WebSourcesCoordinator(window)
        item = WebItem(
            url="https://cdn.example.com/a.png",
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

    def test_download_ignores_malformed_report_assets_without_crashing(self) -> None:
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
        self.assertTrue(any("downloaded 1" in message.lower() for message in window.status_updates))

    def test_diagnostics_uses_only_the_diagnostics_call(self) -> None:
        window = _FakeWindow()
        coordinator = WebSourcesCoordinator(window)
        with patch.object(coordinator, "_diagnostics_summary_for_url", return_value="Connection check passed"):
            coordinator.on_diagnostics_requested(WebDiagnosticsRequest(url="https://example.com"))
        self.assertEqual("Connection check passed", window.web_sources_panel.status_messages[-1])
        self.assertEqual([], window.controller.scanned_urls)

    def test_registry_update_accepts_empty_list_without_touching_results(self) -> None:
        window = _FakeWindow()
        window.web_sources_panel.sources = [{"id": "old"}]
        window.web_sources_panel._store.add(
            ScanResults(
                items=(
                    WebItem(
                        url="https://cdn.example.com/a.png",
                        name="a.png",
                        ext=".png",
                        confidence=Confidence.DIRECT,
                    ),
                )
            )
        )
        coordinator = WebSourcesCoordinator(window)
        coordinator.on_registry_changed([])
        self.assertEqual([], window.web_sources_panel.sources)
        self.assertEqual(1, len(window.web_sources_panel.found_items()))

    def test_invalid_request_types_do_not_call_the_wrong_operation(self) -> None:
        window = _FakeWindow()
        coordinator = WebSourcesCoordinator(window)
        coordinator.on_scan_requested({"urls": ["https://example.com"]})
        coordinator.on_discover_links_requested(self._scan_request("https://example.com"))
        coordinator.on_download_requested(WebDiagnosticsRequest(url="https://example.com"))
        self.assertEqual([], window.controller.scanned_urls)
        self.assertEqual("", window.controller.discovery_url)
        self.assertEqual(3, len(window.web_sources_panel.status_messages))


if __name__ == "__main__":
    unittest.main()
