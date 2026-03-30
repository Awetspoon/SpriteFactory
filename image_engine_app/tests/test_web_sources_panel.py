"""Web Sources panel behavior tests."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest


try:
    from PySide6.QtWidgets import QApplication
except Exception:  # pragma: no cover - optional dependency in some environments
    QApplication = None  # type: ignore[assignment]

from image_engine_app.app.web_sources_models import Confidence, ImportTarget, ScanResults, WebItem  # noqa: E402
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

    def test_add_custom_website_url_builds_switchable_path_areas_and_dedupes(self) -> None:
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
            panel._add_site_btn.click()

            registry = panel.sources_registry()
            example = next((entry for entry in registry if entry.get("name") == "example.com"), None)
            self.assertIsNotNone(example)
            areas = example.get("areas") if isinstance(example, dict) else []
            self.assertEqual(5, len(areas))

            area_urls = [str(area.get("url", "")) for area in areas if isinstance(area, dict)]
            self.assertIn("https://example.com/", area_urls)
            self.assertIn("https://example.com/sprites", area_urls)
            self.assertIn("https://example.com/sprites/pokemon", area_urls)
            self.assertIn("https://example.com/sprites/pokemon/gen1", area_urls)
            self.assertIn("https://example.com/sprites/pokemon/gen1?form=alt", area_urls)

            panel._custom_url.setText("https://example.com/sprites/pokemon/gen1?form=alt")
            panel._add_site_btn.click()

            registry_after = panel.sources_registry()
            example_after = next((entry for entry in registry_after if entry.get("name") == "example.com"), None)
            self.assertIsNotNone(example_after)
            areas_after = example_after.get("areas") if isinstance(example_after, dict) else []
            self.assertEqual(5, len(areas_after))
            self.assertGreaterEqual(len(changes), 2)
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
            panel._diagnose_btn.click()

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

    def test_jpg_filter_is_available_and_enabled_by_default(self) -> None:
        app, owns_app, panel = self._setup_panel()
        try:
            self.assertEqual("JPG", panel._filter_jpg.text())
            self.assertTrue(panel._filter_jpg.isChecked())
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
            self.assertIn("Scanning custom URL", panel._status.text())
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








