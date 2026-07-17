"""Tests for the pure saved-page registry service."""

from __future__ import annotations

import unittest

from image_engine_app.app.services.web_sources_registry import (
    WebSourcesRegistryService,
    normalize_page_url,
)
from image_engine_app.app.web_sources_models import (
    SavedWebPage,
    SavedWebsite,
    WebPageBookmark,
)


class WebSourcesRegistryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = WebSourcesRegistryService()

    def test_payload_is_normalized_deduplicated_and_typed(self) -> None:
        websites = self.service.from_payload(
            [
                {
                    "name": "example.com",
                    "areas": [
                        {"label": "Sprites", "url": "example.com/sprites#top"},
                        {"label": "Duplicate", "url": "https://example.com/sprites"},
                        {"label": "Invalid", "url": "not a url"},
                    ],
                }
            ]
        )

        self.assertEqual(1, len(websites))
        self.assertEqual("example_com", websites[0].id)
        self.assertEqual(1, len(websites[0].pages))
        self.assertEqual("https://example.com/sprites", websites[0].pages[0].url)

    def test_save_pages_groups_hosts_and_reports_duplicates(self) -> None:
        result = self.service.save_pages(
            (),
            (
                WebPageBookmark("https://one.example/sprites/gen-1"),
                WebPageBookmark("https://two.example/art"),
                WebPageBookmark("https://one.example/sprites/gen-1#duplicate"),
            ),
        )

        self.assertEqual(2, result.added_count)
        self.assertEqual(1, result.duplicate_count)
        self.assertEqual(2, len(result.websites))
        self.assertEqual(
            {"one.example", "two.example"},
            {website.name for website in result.websites},
        )

    def test_save_pages_reuses_existing_website_and_keeps_discovered_label(self) -> None:
        existing = (
            SavedWebsite(
                id="project_pokemon",
                name="My Pokemon Library",
                pages=(
                    SavedWebPage(
                        id="root",
                        label="Root",
                        url="https://projectpokemon.org/",
                    ),
                ),
            ),
        )

        result = self.service.save_pages(
            existing,
            (
                WebPageBookmark(
                    url="https://projectpokemon.org/home/docs/spriteindex_148/",
                    label="Sprite Index",
                ),
                WebPageBookmark(
                    url="https://projectpokemon.org/home/docs/spriteindex_148/gen-1/",
                    label="Generation 1 Pokemon",
                ),
            ),
        )

        self.assertEqual(1, len(result.websites))
        self.assertEqual(3, len(result.websites[0].pages))
        self.assertEqual(
            ("Root", "Sprite Index", "Generation 1 Pokemon"),
            tuple(page.label for page in result.websites[0].pages),
        )

    def test_payload_reads_legacy_areas_and_writes_pages(self) -> None:
        websites = self.service.from_payload(
            [
                {
                    "id": "example",
                    "name": "example.com",
                    "areas": [
                        {"id": "root", "label": "Root", "url": "https://example.com/"}
                    ],
                }
            ]
        )

        payload = self.service.to_payload(websites)

        self.assertIn("pages", payload[0])
        self.assertNotIn("areas", payload[0])

    def test_remove_page_prunes_empty_website_and_resolves_selection(self) -> None:
        websites = (
            SavedWebsite(
                id="one",
                name="one.example",
                pages=(SavedWebPage(id="page", label="Page", url="https://one.example/page"),),
            ),
            SavedWebsite(
                id="two",
                name="two.example",
                pages=(SavedWebPage(id="other", label="Other", url="https://two.example/other"),),
            ),
        )

        result = self.service.remove_page(websites, "one", "page")

        self.assertEqual(("two",), tuple(website.id for website in result.websites))
        self.assertEqual("two", result.selected_website_id)
        self.assertEqual("other", result.selected_page_id)

    def test_normalize_page_url_accepts_plain_host_and_removes_fragment(self) -> None:
        self.assertEqual(
            "https://example.com/sprites?generation=1",
            normalize_page_url("example.com/sprites?generation=1#top"),
        )
        self.assertIsNone(normalize_page_url("not a url"))


if __name__ == "__main__":
    unittest.main()
