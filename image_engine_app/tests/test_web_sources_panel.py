"""Web Sources panel behavior tests."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest


try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QMessageBox
except Exception:  # pragma: no cover - optional dependency in some environments
    Qt = None  # type: ignore[assignment]
    QApplication = None  # type: ignore[assignment]
    QMessageBox = None  # type: ignore[assignment]

from image_engine_app.app.web_sources_models import Confidence, ImportTarget, ScanResults, WebIndexLink, WebItem  # noqa: E402
from image_engine_app.ui.main_window.web_sources_panel import WebSourcesPanel  # noqa: E402


@unittest.skipIf(QApplication is None, "PySide6 not installed")
class WebSourcesPanelTests(unittest.TestCase):
    def _setup_panel(self) -> tuple[QApplication, bool, WebSourcesPanel]:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QApplication([])

        panel = WebSourcesPanel()
        return app, owns_app, panel

    def test_menu_only_actions_do_not_leave_floating_button_widgets(self) -> None:
        app, owns_app, panel = self._setup_panel()
        try:
            self.assertFalse(hasattr(panel, "_scan_selected_pages_btn"))
            self.assertFalse(hasattr(panel, "_clear_manual_links_btn"))
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_add_custom_website_url_saves_exact_page_and_dedupes(self) -> None:
        app, owns_app, panel = self._setup_panel()
        panel.set_sources(
            websites=[
                {
                    "id": "pokemon_db",
                    "name": "PokemonDB",
                    "areas": [
                        {
                            "id": "sprites_root",
                            "label": "Sprites (All Pokemon)",
                            "url": "https://pokemondb.net/sprites",
                        }
                    ],
                }
            ]
        )

        changes: list[list[dict]] = []
        panel.registry_changed.connect(lambda payload: changes.append(payload if isinstance(payload, list) else []))

        try:
            panel._custom_url.setText("https://example.com/sprites/pokemon/gen1?form=alt")
            panel._add_custom_website()

            registry = panel.sources_registry()
            example = next((entry for entry in registry if entry.get("name") == "example.com"), None)
            self.assertIsNotNone(example)
            areas = example.get("areas") if isinstance(example, dict) else []
            self.assertEqual(1, len(areas))

            area_urls = [str(area.get("url", "")) for area in areas if isinstance(area, dict)]
            self.assertEqual(["https://example.com/sprites/pokemon/gen1?form=alt"], area_urls)

            panel._custom_url.setText("https://example.com/sprites/pokemon/gen1?form=alt")
            panel._add_custom_website()

            registry_after = panel.sources_registry()
            example_after = next((entry for entry in registry_after if entry.get("name") == "example.com"), None)
            self.assertIsNotNone(example_after)
            areas_after = example_after.get("areas") if isinstance(example_after, dict) else []
            self.assertEqual(1, len(areas_after))
            self.assertGreaterEqual(len(changes), 2)
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_area_dropdown_uses_compact_decoded_labels_and_tooltips(self) -> None:
        app, owns_app, panel = self._setup_panel()
        try:
            panel.set_sources(
                websites=[
                    {
                        "id": "project_pokemon",
                        "name": "Project Pokemon",
                        "areas": [
                            {
                                "id": "gen1",
                                "label": "Home / Docs / Spriteindex 148 / 3d Models Generation 1 Pok%C3%A9mon R90",
                                "url": "https://example.com/home/docs/spriteindex_148/3d-models-generation-1-pok%C3%A9mon-r90",
                            }
                        ],
                    }
                ]
            )

            self.assertEqual("... / Docs / Spriteindex 148 / 3d Models Generation 1 Pokemon R90", panel._area.itemText(0))
            self.assertEqual(
                "https://example.com/home/docs/spriteindex_148/3d-models-generation-1-pok%C3%A9mon-r90",
                panel._area.itemData(0, Qt.ItemDataRole.ToolTipRole),
            )
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_added_website_page_uses_generic_url_path_label(self) -> None:
        app, owns_app, panel = self._setup_panel()
        try:
            panel._custom_url.setText("https://example.com/sprites/pokemon/gen1?form=alt")
            panel._add_custom_website()

            labels = [panel._area.itemText(index) for index in range(panel._area.count())]
            self.assertEqual(["Sprites / Pokemon / Gen1 (Query)"], labels)
            self.assertIn("Selected page:", panel._selected_page_hint.text())
            self.assertIn("https://example.com/sprites/pokemon/gen1?form=alt", panel._selected_page_hint.text())
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_scan_all_saved_pages_emits_multi_scan_for_every_saved_page(self) -> None:
        app, owns_app, panel = self._setup_panel()
        scans: list[object] = []
        panel.multi_scan_requested.connect(scans.append)

        try:
            panel.set_sources(
                websites=[
                    {
                        "id": "example_com",
                        "name": "example.com",
                        "areas": [
                            {"id": "root", "label": "Root", "url": "https://example.com/"},
                            {"id": "sprites", "label": "Sprites", "url": "https://example.com/sprites"},
                        ],
                    },
                    {
                        "id": "other_com",
                        "name": "other.com",
                        "areas": [
                            {"id": "free", "label": "Freebies", "url": "https://other.com/freebies"},
                        ],
                    },
                ]
            )

            panel._emit_saved_pages_scan()

            self.assertEqual(1, len(scans))
            payload = scans[0]
            self.assertIsInstance(payload, dict)
            pages = payload.get("pages") if isinstance(payload, dict) else []
            self.assertEqual(
                ["https://example.com/", "https://example.com/sprites", "https://other.com/freebies"],
                [page.get("url") for page in pages],
            )
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_saved_page_picker_selects_and_scans_saved_area(self) -> None:
        app, owns_app, panel = self._setup_panel()
        scans: list[object] = []
        panel.scan_requested.connect(scans.append)

        try:
            panel.set_sources(
                websites=[
                    {
                        "id": "example_com",
                        "name": "example.com",
                        "areas": [
                            {
                                "id": "root",
                                "label": "Root",
                                "url": "https://example.com/",
                            },
                            {
                                "id": "sprites_gen1",
                                "label": "Sprites / Gen1",
                                "url": "https://example.com/sprites/gen1",
                            },
                        ],
                    },
                    {
                        "id": "archive_org",
                        "name": "archive.example",
                        "areas": [
                            {
                                "id": "animated",
                                "label": "Animated",
                                "url": "https://archive.example/animated",
                            }
                        ],
                    },
                ]
            )

            for index in range(panel._saved_page.count()):
                if panel._saved_page.itemData(index, Qt.ItemDataRole.ToolTipRole) == "https://archive.example/animated":
                    panel._saved_page.setCurrentIndex(index)
                    break

            panel._scan_saved_btn.click()

            self.assertEqual(1, len(scans))
            payload = scans[0]
            self.assertIsInstance(payload, dict)
            if isinstance(payload, dict):
                self.assertEqual("https://archive.example/animated", payload.get("area_url"))
                self.assertEqual("archive_org", payload.get("website_id"))
                self.assertEqual("animated", payload.get("area_id"))
            self.assertIn("archive.example", panel._saved_page.currentText())
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_network_diagnostics_emits_payload_for_custom_url(self) -> None:
        app, owns_app, panel = self._setup_panel()
        diagnostics: list[object] = []
        panel.network_diagnostics_requested.connect(diagnostics.append)

        try:
            panel._custom_url.setText("example.com/sprites")
            panel._emit_custom_url_network_diagnostics()

            self.assertEqual(1, len(diagnostics))
            payload = diagnostics[0]
            self.assertIsInstance(payload, dict)
            if isinstance(payload, dict):
                self.assertEqual("https://example.com/sprites", payload.get("area_url"))
                self.assertIsNone(payload.get("website_id"))
                self.assertIsNone(payload.get("area_id"))
            self.assertIn("Running network diagnostics", panel._status.text())
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_more_menus_have_section_specific_actions(self) -> None:
        app, owns_app, panel = self._setup_panel()

        def action_labels(button) -> list[str]:
            menu = button.menu()
            self.assertIsNotNone(menu)
            if menu is None:
                return []
            return [action.text() for action in menu.actions() if not action.isSeparator()]

        try:
            self.assertEqual(
                ["Save URL as Page", "Clear URL", "Clear Page List", "Check Pasted URL"],
                action_labels(panel._url_more_btn),
            )
            self.assertEqual(
                ["Scan All Saved", "Remove Saved Page", "Remove Website", "Check Saved Page"],
                action_labels(panel._source_more_btn),
            )
            self.assertEqual(
                [
                    "Scan Selected Links",
                    "Find and Scan First 100",
                    "Select Visible Links",
                    "Clear Link Selection",
                    "Clear Linked Pages",
                ],
                action_labels(panel._index_more_btn),
            )
            self.assertEqual(
                ["Select All Results", "Clear Result Selection", "Clear Found Files"],
                action_labels(panel._download_more_btn),
            )
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_saved_page_network_diagnostics_ignores_pasted_url(self) -> None:
        app, owns_app, panel = self._setup_panel()
        diagnostics: list[object] = []
        panel.network_diagnostics_requested.connect(diagnostics.append)

        try:
            panel.set_sources(
                websites=[
                    {
                        "id": "example_com",
                        "name": "example.com",
                        "areas": [
                            {
                                "id": "sprites",
                                "label": "Sprites",
                                "url": "https://example.com/sprites",
                            }
                        ],
                    }
                ],
                selected_website_id="example_com",
                selected_area_id="sprites",
            )
            panel._custom_url.setText("https://other.example/manual")
            panel._emit_saved_page_network_diagnostics()

            self.assertEqual(1, len(diagnostics))
            payload = diagnostics[0]
            self.assertIsInstance(payload, dict)
            if isinstance(payload, dict):
                self.assertEqual("https://example.com/sprites", payload.get("area_url"))
                self.assertEqual("example_com", payload.get("website_id"))
                self.assertEqual("sprites", payload.get("area_id"))
            self.assertIn("saved page", panel._status.text())
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_jpg_filter_is_available_and_enabled_by_default(self) -> None:
        app, owns_app, panel = self._setup_panel()
        try:
            self.assertEqual("JPG", panel._filter_jpg.text())
            self.assertTrue(panel._filter_jpg.isChecked())
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_index_keyword_filter_limits_scan_selected_pages_payload(self) -> None:
        app, owns_app, panel = self._setup_panel()
        scans: list[object] = []
        panel.multi_scan_requested.connect(scans.append)

        try:
            panel.set_index_links(
                [
                    WebIndexLink(
                        label="HOME Sprites: Gen 1",
                        url="https://example.com/home-gen-1",
                        source_page="https://example.com/index",
                    ),
                    WebIndexLink(
                        label="HOME Sprites: Gen 2",
                        url="https://example.com/home-gen-2",
                        source_page="https://example.com/index",
                    ),
                ]
            )
            panel._index_keyword.setText("gen 1")
            panel._select_visible_index_links()
            panel._emit_multi_page_scan()

            self.assertEqual(1, len(scans))
            payload = scans[0]
            self.assertIsInstance(payload, dict)
            if isinstance(payload, dict):
                pages = payload.get("pages")
                self.assertIsInstance(pages, list)
                if isinstance(pages, list):
                    self.assertEqual(1, len(pages))
                    self.assertEqual("HOME Sprites: Gen 1", pages[0].get("label"))
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_found_index_links_are_selected_by_default_for_scanning(self) -> None:
        app, owns_app, panel = self._setup_panel()
        scans: list[object] = []
        panel.multi_scan_requested.connect(scans.append)

        try:
            panel.set_index_links(
                [
                    WebIndexLink(
                        label="HOME Sprites: Gen 1",
                        url="https://example.com/home-gen-1",
                        source_page="https://example.com/index",
                    ),
                    WebIndexLink(
                        label="Animations",
                        url="https://example.com/animations",
                        source_page="https://example.com/index",
                    ),
                ]
            )
            panel._emit_multi_page_scan()

            self.assertEqual(1, len(scans))
            payload = scans[0]
            self.assertIsInstance(payload, dict)
            if isinstance(payload, dict):
                pages = payload.get("pages")
                self.assertIsInstance(pages, list)
                if isinstance(pages, list):
                    self.assertEqual(2, len(pages))
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_scan_selected_uses_visible_links_when_selection_was_cleared(self) -> None:
        app, owns_app, panel = self._setup_panel()
        scans: list[object] = []
        panel.multi_scan_requested.connect(scans.append)

        try:
            panel.set_index_links(
                [
                    WebIndexLink(
                        label="HOME Sprites: Gen 1",
                        url="https://example.com/home-gen-1",
                        source_page="https://example.com/index",
                    ),
                    WebIndexLink(
                        label="HOME Sprites: Gen 2",
                        url="https://example.com/home-gen-2",
                        source_page="https://example.com/index",
                    ),
                ]
            )
            panel._index_keyword.setText("gen 2")
            panel._index_links.clearSelection()
            panel._emit_multi_page_scan()

            self.assertEqual(1, len(scans))
            payload = scans[0]
            self.assertIsInstance(payload, dict)
            if isinstance(payload, dict):
                pages = payload.get("pages")
                self.assertIsInstance(pages, list)
                if isinstance(pages, list):
                    self.assertEqual(1, len(pages))
                    self.assertEqual("HOME Sprites: Gen 2", pages[0].get("label"))
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_large_selected_page_scan_warns_and_caps_payload(self) -> None:
        app, owns_app, panel = self._setup_panel()
        scans: list[object] = []
        panel.multi_scan_requested.connect(scans.append)

        try:
            panel.set_index_links(
                [
                    WebIndexLink(
                        label=f"Page {index}",
                        url=f"https://example.com/page-{index}",
                        source_page="https://example.com/index",
                    )
                    for index in range(panel.LINKED_PAGE_SCAN_CAP + 5)
                ]
            )
            panel._select_visible_index_links()

            original_confirm = panel.confirm_large_linked_page_scan
            confirm_calls: list[tuple[int, int]] = []

            def confirm(page_count: int, *, cap: int | None = None) -> bool:
                confirm_calls.append((page_count, int(cap or 0)))
                return True

            panel.confirm_large_linked_page_scan = confirm  # type: ignore[method-assign]
            try:
                panel._emit_multi_page_scan()
            finally:
                panel.confirm_large_linked_page_scan = original_confirm  # type: ignore[method-assign]

            self.assertEqual([(panel.LINKED_PAGE_SCAN_CAP + 5, panel.LINKED_PAGE_SCAN_CAP)], confirm_calls)
            self.assertEqual(1, len(scans))
            payload = scans[0]
            self.assertIsInstance(payload, dict)
            if isinstance(payload, dict):
                pages = payload.get("pages")
                self.assertIsInstance(pages, list)
                if isinstance(pages, list):
                    self.assertEqual(panel.LINKED_PAGE_SCAN_CAP, len(pages))
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_large_selected_page_scan_can_be_cancelled_before_emit(self) -> None:
        app, owns_app, panel = self._setup_panel()
        scans: list[object] = []
        panel.multi_scan_requested.connect(scans.append)

        try:
            panel.set_index_links(
                [
                    WebIndexLink(label=f"Page {index}", url=f"https://example.com/page-{index}")
                    for index in range(panel.LINKED_PAGE_SCAN_CAP + 1)
                ]
            )
            panel._select_visible_index_links()
            panel.confirm_large_linked_page_scan = lambda *_args, **_kwargs: False  # type: ignore[method-assign]
            panel._emit_multi_page_scan()

            self.assertEqual([], scans)
            self.assertIn("cancelled", panel._status.text().lower())
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_manual_page_urls_emit_multi_scan_payload_with_dedupe(self) -> None:
        app, owns_app, panel = self._setup_panel()
        scans: list[object] = []
        panel.multi_scan_requested.connect(scans.append)

        try:
            panel._manual_links.setPlainText(
                "\n".join(
                    [
                        "example.com/sprites/gen-1",
                        "https://example.com/sprites/gen-1",
                        "ftp://example.com/bad",
                        "https://example.com/sprites/gen-2",
                    ]
                )
            )
            panel._scan_manual_links_btn.click()

            self.assertEqual(1, len(scans))
            payload = scans[0]
            self.assertIsInstance(payload, dict)
            if isinstance(payload, dict):
                pages = payload.get("pages")
                self.assertIsInstance(pages, list)
                if isinstance(pages, list):
                    self.assertEqual(2, len(pages))
                    self.assertEqual("https://example.com/sprites/gen-1", pages[0].get("url"))
                    self.assertEqual("https://example.com/sprites/gen-2", pages[1].get("url"))
            self.assertIn("skipped", panel._status.text().lower())
            self.assertIn("invalid", panel._status.text().lower())
            self.assertIn("duplicate", panel._status.text().lower())
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_large_manual_page_scan_warns_and_caps_payload(self) -> None:
        app, owns_app, panel = self._setup_panel()
        scans: list[object] = []
        panel.multi_scan_requested.connect(scans.append)

        try:
            panel._manual_links.setPlainText(
                "\n".join(
                    f"https://example.com/page-{index}"
                    for index in range(panel.LINKED_PAGE_SCAN_CAP + 3)
                )
            )
            confirm_calls: list[tuple[int, int]] = []

            def confirm(page_count: int, *, cap: int | None = None) -> bool:
                confirm_calls.append((page_count, int(cap or 0)))
                return True

            panel.confirm_large_linked_page_scan = confirm  # type: ignore[method-assign]
            panel._scan_manual_links_btn.click()

            self.assertEqual([(panel.LINKED_PAGE_SCAN_CAP + 3, panel.LINKED_PAGE_SCAN_CAP)], confirm_calls)
            self.assertEqual(1, len(scans))
            payload = scans[0]
            self.assertIsInstance(payload, dict)
            if isinstance(payload, dict):
                pages = payload.get("pages")
                self.assertIsInstance(pages, list)
                if isinstance(pages, list):
                    self.assertEqual(panel.LINKED_PAGE_SCAN_CAP, len(pages))
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_find_linked_pages_emits_custom_index_url_payload(self) -> None:
        app, owns_app, panel = self._setup_panel()
        requests: list[object] = []
        panel.index_links_requested.connect(requests.append)

        try:
            panel._custom_url.setText("example.com/sprite-index")
            panel._find_index_links_btn.click()

            self.assertEqual(1, len(requests))
            payload = requests[0]
            self.assertIsInstance(payload, dict)
            if isinstance(payload, dict):
                self.assertEqual("https://example.com/sprite-index", payload.get("index_url"))
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_find_and_scan_all_emits_custom_index_url_payload(self) -> None:
        app, owns_app, panel = self._setup_panel()
        requests: list[object] = []
        panel.index_scan_all_requested.connect(requests.append)

        try:
            panel._custom_url.setText("example.com/sprite-index")
            panel._emit_index_scan_all()

            self.assertEqual(1, len(requests))
            payload = requests[0]
            self.assertIsInstance(payload, dict)
            if isinstance(payload, dict):
                self.assertEqual("https://example.com/sprite-index", payload.get("index_url"))
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_result_search_matches_url_and_source_page(self) -> None:
        app, owns_app, panel = self._setup_panel()
        try:
            panel.set_results(
                ScanResults(
                    items=(
                        WebItem(
                            url="https://cdn.example.com/bulbasaur.png",
                            name="001.png",
                            ext=".png",
                            confidence=Confidence.DIRECT,
                            source_page="https://example.com/home-gen-1",
                        ),
                        WebItem(
                            url="https://cdn.example.com/charmander.png",
                            name="004.png",
                            ext=".png",
                            confidence=Confidence.DIRECT,
                            source_page="https://example.com/home-gen-1",
                        ),
                    ),
                    filtered_count=0,
                )
            )
            panel._search.setText("bulbasaur")
            self.assertEqual(1, panel._results.count())
            panel._search.setText("home-gen-1")
            self.assertEqual(2, panel._results.count())
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_result_exclude_keywords_hide_matching_names_urls_and_source_pages(self) -> None:
        app, owns_app, panel = self._setup_panel()
        try:
            panel.set_results(
                ScanResults(
                    items=(
                        WebItem(
                            url="https://cdn.example.com/bulbasaur.png",
                            name="bulbasaur.png",
                            ext=".png",
                            confidence=Confidence.DIRECT,
                            source_page="https://example.com/home-gen-1",
                        ),
                        WebItem(
                            url="https://cdn.example.com/bulbasaur_shiny.png",
                            name="bulbasaur_shiny.png",
                            ext=".png",
                            confidence=Confidence.DIRECT,
                            source_page="https://example.com/home-gen-1",
                        ),
                        WebItem(
                            url="https://cdn.example.com/charmander.png",
                            name="charmander.png",
                            ext=".png",
                            confidence=Confidence.DIRECT,
                            source_page="https://example.com/shiny-index",
                        ),
                    ),
                    filtered_count=0,
                )
            )

            panel._exclude_keywords.setText("shiny")

            self.assertEqual(1, panel._results.count())
            self.assertIn("bulbasaur.png", panel._results.item(0).text())
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_set_results_explains_when_search_filters_hide_all_items(self) -> None:
        app, owns_app, panel = self._setup_panel()
        try:
            panel._search.setText("missing")
            panel.set_results(
                ScanResults(
                    items=(
                        WebItem(
                            url="https://cdn.example.com/bulbasaur.png",
                            name="bulbasaur.png",
                            ext=".png",
                            confidence=Confidence.DIRECT,
                            source_page="https://example.com/home-gen-1",
                        ),
                    ),
                    filtered_count=0,
                )
            )

            self.assertEqual(0, panel._results.count())
            self.assertIn("hide", panel._status.text().lower())
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_set_results_reports_failed_pages_from_multi_page_scan(self) -> None:
        app, owns_app, panel = self._setup_panel()
        try:
            panel.set_results(
                ScanResults(
                    items=(
                        WebItem(
                            url="https://cdn.example.com/bulbasaur.png",
                            name="bulbasaur.png",
                            ext=".png",
                            confidence=Confidence.DIRECT,
                            source_page="https://example.com/good",
                        ),
                    ),
                    filtered_count=0,
                    failed_pages=("https://example.com/slow: timed out",),
                )
            )

            self.assertEqual(1, panel._results.count())
            self.assertIn("1 page failed", panel._status.text())
            self.assertIn("Hover for details", panel._status.text())
            self.assertIn("https://example.com/slow", panel._status.toolTip())
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_set_results_reports_when_all_pages_failed(self) -> None:
        app, owns_app, panel = self._setup_panel()
        try:
            panel.set_results(
                ScanResults(
                    items=(),
                    filtered_count=0,
                    failed_pages=("https://example.com/slow: timed out",),
                )
            )

            self.assertEqual(0, panel._results.count())
            self.assertIn("Found 0 item", panel._status.text())
            self.assertIn("1 page failed", panel._status.text())
            self.assertIn("https://example.com/slow", panel._status.toolTip())
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_download_area_uses_auto_destination_hint_and_forces_smart_routing(self) -> None:
        app, owns_app, panel = self._setup_panel()
        downloads: list[object] = []
        panel.download_requested.connect(downloads.append)
        panel.set_sources(
            websites=[
                {
                    "id": "pokemon_fandom_com",
                    "name": "pokemon.fandom.com",
                    "areas": [
                        {
                            "id": "item_sprites",
                            "label": "Wiki / Category:item Sprites (Query)",
                            "url": "https://pokemon.fandom.com/wiki/Category:Item_sprites",
                        }
                    ],
                }
            ],
            selected_website_id="pokemon_fandom_com",
            selected_area_id="item_sprites",
        )
        panel.set_results(
            ScanResults(
                items=(
                    WebItem(
                        url="https://example.com/a.png",
                        name="a.png",
                        ext=".png",
                        confidence=Confidence.DIRECT,
                        source_page="https://pokemon.fandom.com/wiki/Category:Item_sprites",
                    ),
                ),
                filtered_count=0,
            )
        )
        panel._select_all_visible()

        try:
            self.assertFalse(hasattr(panel, "_target"))
            self.assertIn("Sprite Factory routes downloads", panel._destination_hint.text())
            self.assertTrue(panel.smart_options().auto_sort)

            panel._emit_download()
            self.assertEqual(1, len(downloads))
            payload = downloads[0]
            self.assertIsInstance(payload, dict)
            if isinstance(payload, dict):
                self.assertEqual(ImportTarget.NORMAL.value, payload.get("target"))
                self.assertEqual("https://pokemon.fandom.com/wiki/Category:Item_sprites", payload.get("area_url"))
                self.assertEqual("Wiki / Category:item Sprites (Query)", payload.get("area_label"))
                smart = payload.get("smart")
                self.assertIsInstance(smart, dict)
                if isinstance(smart, dict):
                    self.assertTrue(smart.get("auto_sort"))
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_scan_emits_payload_for_custom_url_without_adding_site(self) -> None:
        app, owns_app, panel = self._setup_panel()
        scans: list[object] = []
        panel.scan_requested.connect(scans.append)

        try:
            panel._custom_url.setText("example.com/sprites")
            panel._scan_btn.click()

            self.assertEqual(1, len(scans))
            payload = scans[0]
            self.assertIsInstance(payload, dict)
            if isinstance(payload, dict):
                self.assertEqual("https://example.com/sprites", payload.get("area_url"))
                self.assertIsNone(payload.get("website_id"))
                self.assertIsNone(payload.get("area_id"))
            self.assertIn("Scanning URL", panel._status.text())
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_scan_rejects_invalid_custom_url(self) -> None:
        app, owns_app, panel = self._setup_panel()
        scans: list[object] = []
        panel.scan_requested.connect(scans.append)

        try:
            panel._custom_url.setText("ftp://example.com/sprites")
            panel._scan_btn.click()

            self.assertEqual(0, len(scans))
            self.assertEqual("Invalid URL. Use http(s)://domain/path.", panel._status.text())
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()



    def test_remove_selected_custom_area_updates_registry_and_emits_change(self) -> None:
        app, owns_app, panel = self._setup_panel()
        panel.set_sources(
            websites=[
                {
                    "id": "project_pokemon",
                    "name": "Project Pokemon",
                    "areas": [
                        {
                            "id": "spriteindex_root",
                            "label": "Sprite Index (root)",
                            "url": "https://projectpokemon.org/home/docs/spriteindex_148/",
                        },
                        {
                            "id": "custom_docs",
                            "label": "Custom Docs",
                            "url": "https://projectpokemon.org/home/docs/spriteindex_148/3d-models",
                        },
                    ],
                }
            ],
            selected_website_id="project_pokemon",
            selected_area_id="custom_docs",
        )

        changes: list[list[dict]] = []
        panel.registry_changed.connect(lambda payload: changes.append(payload if isinstance(payload, list) else []))

        try:
            panel._remove_selected_area()

            registry = panel.sources_registry()
            self.assertEqual(1, len(registry))
            areas = registry[0].get("areas") if isinstance(registry[0], dict) else []
            urls = [str(area.get("url", "")) for area in areas if isinstance(area, dict)]
            self.assertIn("https://projectpokemon.org/home/docs/spriteindex_148/", urls)
            self.assertNotIn("https://projectpokemon.org/home/docs/spriteindex_148/3d-models", urls)
            self.assertTrue(changes)
            self.assertIn("Removed URL:", panel._status.text())
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_remove_selected_area_is_allowed_without_builtins(self) -> None:
        app, owns_app, panel = self._setup_panel()
        panel.set_sources(
            websites=[
                {
                    "id": "pokemon_db",
                    "name": "PokemonDB",
                    "areas": [
                        {
                            "id": "sprites_root",
                            "label": "Sprites (All Pokemon)",
                            "url": "https://pokemondb.net/sprites",
                        }
                    ],
                }
            ],
            selected_website_id="pokemon_db",
            selected_area_id="sprites_root",
        )

        try:
            panel._remove_selected_area()
            registry = panel.sources_registry()

            self.assertEqual([], registry)
            self.assertIn("Removed URL:", panel._status.text())
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()

    def test_remove_selected_custom_website_updates_registry(self) -> None:
        app, owns_app, panel = self._setup_panel()
        panel.set_sources(
            websites=[
                {
                    "id": "pokemon_db",
                    "name": "PokemonDB",
                    "areas": [
                        {
                            "id": "sprites_root",
                            "label": "Sprites (All Pokemon)",
                            "url": "https://pokemondb.net/sprites",
                        }
                    ],
                },
                {
                    "id": "example_com",
                    "name": "example.com",
                    "areas": [
                        {
                            "id": "root",
                            "label": "Root",
                            "url": "https://example.com/",
                        }
                    ],
                },
            ],
            selected_website_id="example_com",
            selected_area_id="root",
        )

        changes: list[list[dict]] = []
        panel.registry_changed.connect(lambda payload: changes.append(payload if isinstance(payload, list) else []))

        try:
            panel._remove_selected_website()

            registry = panel.sources_registry()
            ids = [str(entry.get("id", "")) for entry in registry if isinstance(entry, dict)]
            self.assertIn("pokemon_db", ids)
            self.assertNotIn("example_com", ids)
            self.assertTrue(changes)
            self.assertIn("Removed website:", panel._status.text())
        finally:
            panel.close()
            if owns_app and app is not None:
                app.quit()
if __name__ == "__main__":
    unittest.main()








