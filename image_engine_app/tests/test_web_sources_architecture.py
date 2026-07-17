"""Architecture guards for the rebuilt Web Sources slice."""

from __future__ import annotations

from pathlib import Path
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


class WebSourcesArchitectureTests(unittest.TestCase):
    def test_panel_does_not_own_registry_or_found_files_store(self) -> None:
        source = (PACKAGE_ROOT / "ui" / "main_window" / "web_sources_panel.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("FoundFilesStore", source)
        self.assertNotIn("merge_scan_results(", source)
        self.assertNotIn("save_web_sources_settings", source)
        self.assertNotIn("registry_changed", source)

    def test_coordinator_contains_no_network_or_settings_implementation(self) -> None:
        source = (PACKAGE_ROOT / "ui" / "main_window" / "web_sources_coordinator.py").read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "socket.create_connection",
            "socket.getaddrinfo",
            "urlopen(",
            "save_web_sources_settings",
            "load_web_sources_settings",
            "merge_scan_results(",
        ):
            self.assertNotIn(forbidden, source)

    def test_controller_exposes_one_workflow_api_without_retired_wrappers(self) -> None:
        source = (PACKAGE_ROOT / "app" / "ui_controller.py").read_text(encoding="utf-8")
        for retired in (
            "def load_web_sources_registry(",
            "def scan_web_source_pages(",
            "def discover_web_source_index_links(",
            "def download_web_sources_items(",
        ):
            self.assertNotIn(retired, source)
        self.assertIn("WebSourcesWorkflowService(", source)

    def test_workflow_owns_persistence_and_result_accumulation(self) -> None:
        source = (
            PACKAGE_ROOT / "app" / "services" / "web_sources_workflow.py"
        ).read_text(encoding="utf-8")
        self.assertIn("merge_scan_results(", source)
        self.assertIn("save_web_sources_settings(", source)
        self.assertIn("def clear_found_files(", source)

    def test_scanner_and_downloader_do_not_recombine(self) -> None:
        services = PACKAGE_ROOT / "app" / "services"
        scanner = (services / "web_sources_scanner.py").read_text(encoding="utf-8")
        downloader = (services / "web_sources_downloader.py").read_text(encoding="utf-8")

        self.assertIn("def scan_page(", scanner)
        self.assertIn("def discover_links(", scanner)
        self.assertNotIn("def download_items(", scanner)
        self.assertIn("def download_items(", downloader)
        self.assertNotIn("def scan_page(", downloader)
        self.assertNotIn("def scan_pages(", downloader)
        self.assertNotIn("def discover_links(", downloader)


if __name__ == "__main__":
    unittest.main()
