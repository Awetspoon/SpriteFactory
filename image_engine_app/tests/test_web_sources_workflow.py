"""Application workflow tests for Web Sources state and orchestration."""

from __future__ import annotations

import tempfile
import unittest

from image_engine_app.app.paths import ensure_app_paths
from image_engine_app.app.services.web_sources_workflow import WebSourcesWorkflowService
from image_engine_app.app.settings_store import load_web_sources_settings
from image_engine_app.app.web_sources_models import (
    Confidence,
    ScanOrigin,
    ScanResults,
    SmartOptions,
    WebDownloadRequest,
    WebIndexLink,
    WebItem,
    WebLinkDiscoveryRequest,
    WebPageBookmark,
    WebRemoveSavedPageRequest,
    WebSavePagesRequest,
    WebScanRequest,
)
from image_engine_app.engine.ingest.import_result import ImportResult
from image_engine_app.engine.ingest.webpage_scan import WebpageScanCancelledError


def _item(name: str, *, source: str = "https://example.com/page") -> WebItem:
    return WebItem(
        url=f"https://cdn.example.com/{name}",
        name=name,
        ext="." + name.rsplit(".", 1)[-1].lower(),
        confidence=Confidence.DIRECT,
        source_page=source,
    )


class _Network:
    def __init__(self) -> None:
        self.scan_results = ScanResults(items=())
        self.scan_calls: list[list[str]] = []
        self.discovery_calls: list[str] = []
        self.download_calls: list[WebDownloadRequest] = []
        self.scan_error: Exception | None = None

    def scan_pages(self, urls: list[str], **kwargs) -> ScanResults:  # noqa: ANN003
        self.scan_calls.append(list(urls))
        callback = kwargs.get("progress_callback")
        if callback is not None:
            callback(len(urls), len(urls), "Scanned")
        if self.scan_error is not None:
            raise self.scan_error
        return self.scan_results

    def discover_links(self, url: str, **_kwargs) -> tuple[WebIndexLink, ...]:
        self.discovery_calls.append(url)
        return (
            WebIndexLink("Page One", f"{url.rstrip('/')}/one", source_page=url),
            WebIndexLink("Page Two", f"{url.rstrip('/')}/two", source_page=url),
        )

    def download_items(self, items, target, **kwargs) -> ImportResult:  # noqa: ANN001, ANN003
        self.download_calls.append(
            WebDownloadRequest(
                items=tuple(items),
                target=target,
                smart=kwargs["smart"],
            )
        )
        return ImportResult()


class WebSourcesWorkflowServiceTests(unittest.TestCase):
    def test_saved_pages_and_options_are_persisted_by_the_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_app_paths(base_dir=temp_dir)
            network = _Network()
            workflow = WebSourcesWorkflowService(
                app_paths=paths,
                scanner=network,
                downloader=network,
            )

            mutation = workflow.save_pages(
                WebSavePagesRequest(
                    pages=(
                        WebPageBookmark("https://one.example/sprites"),
                        WebPageBookmark("https://two.example/art"),
                    )
                )
            )
            workflow.update_preferences(
                SmartOptions(show_likely=True, skip_duplicates=False, allow_zip=False)
            )

            self.assertEqual(2, len(mutation.state.websites))
            restored = load_web_sources_settings(paths)
            self.assertEqual(2, len(restored["registry"]))
            self.assertTrue(restored["options"]["show_likely"])
            self.assertFalse(restored["options"]["skip_duplicates"])

    def test_scan_plan_normalizes_deduplicates_and_caps_pages(self) -> None:
        network = _Network()
        workflow = WebSourcesWorkflowService(
            app_paths=None,
            scanner=network,
            downloader=network,
            page_limit=2,
        )
        plan = workflow.plan_scan(
            WebScanRequest(
                urls=(
                    "example.com/one",
                    "https://example.com/one#duplicate",
                    "https://example.com/two",
                    "https://example.com/three",
                )
            )
        )

        self.assertEqual(3, plan.requested_count)
        self.assertEqual(
            ("https://example.com/one", "https://example.com/two"),
            plan.urls,
        )
        self.assertTrue(plan.requires_confirmation)
        self.assertTrue(plan.was_capped)

    def test_scans_accumulate_results_and_keep_latest_failures_separate(self) -> None:
        network = _Network()
        workflow = WebSourcesWorkflowService(
            app_paths=None,
            scanner=network,
            downloader=network,
        )

        network.scan_results = ScanResults(items=(_item("a.png"),))
        first = workflow.run_scan(
            workflow.plan_scan(WebScanRequest(urls=("https://example.com/one",)))
        )

        network.scan_results = ScanResults(
            items=(_item("a.png"), _item("b.gif")),
            failed_pages=("https://example.com/bad: HTTP Error 502: Bad Gateway",),
        )
        second = workflow.run_scan(
            workflow.plan_scan(
                WebScanRequest(
                    urls=("https://example.com/two", "https://example.com/bad"),
                    origin=ScanOrigin.SAVED,
                )
            )
        )

        self.assertEqual(1, first.merge.added_count)
        self.assertEqual(("a.png", "b.gif"), tuple(item.name for item in second.state.found_files))
        self.assertEqual(1, second.merge.added_count)
        self.assertEqual(1, second.merge.duplicate_count)
        self.assertIn("HTTP 502", second.latest.failed_pages[0])
        self.assertIn("scan fewer pages", second.latest.failed_pages[0])

    def test_failed_or_cancelled_scan_does_not_clear_previous_results(self) -> None:
        network = _Network()
        workflow = WebSourcesWorkflowService(
            app_paths=None,
            scanner=network,
            downloader=network,
        )
        network.scan_results = ScanResults(items=(_item("existing.png"),))
        workflow.run_scan(
            workflow.plan_scan(WebScanRequest(urls=("https://example.com/good",)))
        )

        network.scan_error = RuntimeError("HTTP Error 403: Forbidden")
        with self.assertRaises(RuntimeError):
            workflow.run_scan(
                workflow.plan_scan(WebScanRequest(urls=("https://example.com/blocked",)))
            )
        self.assertEqual(("existing.png",), tuple(item.name for item in workflow.state().found_files))

        network.scan_error = WebpageScanCancelledError("Scan cancelled")
        with self.assertRaises(WebpageScanCancelledError):
            workflow.run_scan(
                workflow.plan_scan(WebScanRequest(urls=("https://example.com/slow",)))
            )
        self.assertEqual(("existing.png",), tuple(item.name for item in workflow.state().found_files))

    def test_only_clear_found_files_empties_the_result_basket(self) -> None:
        network = _Network()
        workflow = WebSourcesWorkflowService(
            app_paths=None,
            scanner=network,
            downloader=network,
        )
        network.scan_results = ScanResults(items=(_item("a.png"),))
        workflow.run_scan(
            workflow.plan_scan(WebScanRequest(urls=("https://example.com/page",)))
        )
        workflow.save_pages(
            WebSavePagesRequest(
                pages=(WebPageBookmark("https://example.com/page"),),
            )
        )
        workflow.discover_links(WebLinkDiscoveryRequest(url="https://example.com/page"))
        workflow.clear_linked_pages()
        page = workflow.state().websites[0].pages[0]
        workflow.remove_saved_page(
            WebRemoveSavedPageRequest(
                website_id=workflow.state().websites[0].id,
                page_id=page.id,
            )
        )

        self.assertEqual(1, len(workflow.state().found_files))
        workflow.clear_found_files()
        self.assertEqual((), workflow.state().found_files)

    def test_discovery_and_download_use_separate_operations(self) -> None:
        network = _Network()
        workflow = WebSourcesWorkflowService(
            app_paths=None,
            scanner=network,
            downloader=network,
        )
        discovery = workflow.discover_links(
            WebLinkDiscoveryRequest(url="https://example.com/index")
        )
        item = _item("a.png")
        workflow.download(WebDownloadRequest(items=(item,)))

        self.assertEqual(2, len(discovery.links))
        self.assertEqual(["https://example.com/index"], network.discovery_calls)
        self.assertEqual(1, len(network.download_calls))
        self.assertEqual((), workflow.state().found_files)


if __name__ == "__main__":
    unittest.main()
