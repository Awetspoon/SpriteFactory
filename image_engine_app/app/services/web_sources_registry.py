"""Pure saved-website and saved-page operations for Web Sources."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from urllib.parse import unquote, urlparse, urlunparse

from image_engine_app.app.web_sources_models import (
    SavedWebPage,
    SavedWebsite,
    WebPageBookmark,
)


@dataclass(frozen=True)
class RegistryEditResult:
    websites: tuple[SavedWebsite, ...]
    selected_website_id: str | None
    selected_page_id: str | None
    added_count: int = 0
    duplicate_count: int = 0
    invalid_count: int = 0


class WebSourcesRegistryService:
    """Validate, edit, and serialize the user's saved page library."""

    def from_payload(self, raw: object) -> tuple[SavedWebsite, ...]:
        if not isinstance(raw, list):
            return ()

        websites: list[SavedWebsite] = []
        used_website_ids: set[str] = set()
        seen_urls: set[str] = set()

        for raw_website in raw:
            if not isinstance(raw_website, dict):
                continue

            name = str(raw_website.get("name", "")).strip() or "Website"
            website_id = self._unique_id(
                str(raw_website.get("id", "")).strip() or self._slugify(name) or "website",
                used_website_ids,
            )
            used_website_ids.add(website_id)

            pages: list[SavedWebPage] = []
            used_page_ids: set[str] = set()
            raw_pages = raw_website.get("pages")
            if not isinstance(raw_pages, list):
                # Older releases called saved pages "areas". Read that schema
                # once, then write the clearer pages schema on the next save.
                raw_pages = raw_website.get("areas")
            if not isinstance(raw_pages, list):
                raw_pages = []

            for raw_page in raw_pages:
                if not isinstance(raw_page, dict):
                    continue
                normalized_url = normalize_page_url(raw_page.get("url"))
                if normalized_url is None:
                    continue
                url_key = normalized_url.casefold()
                if url_key in seen_urls:
                    continue

                label = str(raw_page.get("label", "")).strip() or page_label(normalized_url)
                page_id = self._unique_id(
                    str(raw_page.get("id", "")).strip() or self._slugify(label) or "page",
                    used_page_ids,
                )
                used_page_ids.add(page_id)
                seen_urls.add(url_key)
                pages.append(SavedWebPage(id=page_id, label=label, url=normalized_url))

            if pages:
                websites.append(SavedWebsite(id=website_id, name=name, pages=tuple(pages)))

        return tuple(websites)

    @staticmethod
    def to_payload(websites: tuple[SavedWebsite, ...]) -> list[dict]:
        return [
            {
                "id": website.id,
                "name": website.name,
                "pages": [
                    {"id": page.id, "label": page.label, "url": page.url}
                    for page in website.pages
                ],
            }
            for website in websites
            if website.pages
        ]

    def save_pages(
        self,
        websites: tuple[SavedWebsite, ...],
        pages_to_save: tuple[WebPageBookmark, ...],
    ) -> RegistryEditResult:
        mutable = [
            {
                "id": website.id,
                "name": website.name,
                "pages": list(website.pages),
            }
            for website in websites
        ]
        known_pages = {
            page.url.casefold(): (website.id, page.id)
            for website in websites
            for page in website.pages
        }
        used_website_ids = {website.id for website in websites}
        added_count = 0
        duplicate_count = 0
        invalid_count = 0
        selected_website_id: str | None = None
        selected_page_id: str | None = None

        for page_to_save in pages_to_save:
            if not isinstance(page_to_save, WebPageBookmark):
                invalid_count += 1
                continue
            normalized_url = normalize_page_url(page_to_save.url)
            if normalized_url is None:
                invalid_count += 1
                continue
            url_key = normalized_url.casefold()
            if url_key in known_pages:
                duplicate_count += 1
                selected_website_id, selected_page_id = known_pages[url_key]
                continue

            parsed = urlparse(normalized_url)
            host = (parsed.hostname or parsed.netloc).strip().lower()
            website = next(
                (entry for entry in mutable if self._website_host(entry) == host),
                None,
            )
            if website is None:
                website_id = self._unique_id(self._slugify(host) or "website", used_website_ids)
                used_website_ids.add(website_id)
                website = {"id": website_id, "name": host, "pages": []}
                mutable.append(website)

            pages = website["pages"]
            page_ids = {page.id for page in pages}
            label = self._clean_label(page_to_save.label) or page_label(normalized_url)
            page_id = self._unique_id(self._slugify(label) or "page", page_ids)
            pages.append(SavedWebPage(id=page_id, label=label, url=normalized_url))
            selected_website_id = str(website["id"])
            selected_page_id = page_id
            known_pages[url_key] = (selected_website_id, selected_page_id)
            added_count += 1

        updated = tuple(
            SavedWebsite(
                id=str(website["id"]),
                name=str(website["name"]),
                pages=tuple(website["pages"]),
            )
            for website in mutable
            if website["pages"]
        )
        selected_website_id, selected_page_id = self.resolve_selection(
            updated,
            selected_website_id,
            selected_page_id,
        )
        return RegistryEditResult(
            websites=updated,
            selected_website_id=selected_website_id,
            selected_page_id=selected_page_id,
            added_count=added_count,
            duplicate_count=duplicate_count,
            invalid_count=invalid_count,
        )

    def remove_page(
        self,
        websites: tuple[SavedWebsite, ...],
        website_id: str,
        page_id: str,
    ) -> RegistryEditResult:
        updated: list[SavedWebsite] = []
        removed = False
        for website in websites:
            if website.id != website_id:
                updated.append(website)
                continue
            pages = tuple(page for page in website.pages if page.id != page_id)
            removed = len(pages) != len(website.pages)
            if pages:
                updated.append(SavedWebsite(id=website.id, name=website.name, pages=pages))

        resolved_website, resolved_page = self.resolve_selection(tuple(updated), website_id, None)
        return RegistryEditResult(
            websites=tuple(updated),
            selected_website_id=resolved_website,
            selected_page_id=resolved_page,
            added_count=0,
            duplicate_count=0 if removed else 1,
        )

    def remove_website(
        self,
        websites: tuple[SavedWebsite, ...],
        website_id: str,
    ) -> RegistryEditResult:
        updated = tuple(website for website in websites if website.id != website_id)
        removed = len(updated) != len(websites)
        resolved_website, resolved_page = self.resolve_selection(updated, None, None)
        return RegistryEditResult(
            websites=updated,
            selected_website_id=resolved_website,
            selected_page_id=resolved_page,
            added_count=0,
            duplicate_count=0 if removed else 1,
        )

    @staticmethod
    def resolve_selection(
        websites: tuple[SavedWebsite, ...],
        website_id: str | None,
        page_id: str | None,
    ) -> tuple[str | None, str | None]:
        for website in websites:
            if website.id != website_id:
                continue
            if page_id and any(page.id == page_id for page in website.pages):
                return website.id, page_id
            if website.pages:
                return website.id, website.pages[0].id

        for website in websites:
            if website.pages:
                return website.id, website.pages[0].id
        return None, None

    @staticmethod
    def _website_host(website: dict) -> str:
        pages = website.get("pages")
        if isinstance(pages, list) and pages:
            host = (urlparse(pages[0].url).hostname or "").strip().lower()
            if host:
                return host
        return str(website.get("name", "")).strip().casefold()

    @staticmethod
    def _clean_label(value: object) -> str:
        return " ".join(str(value or "").split())

    @staticmethod
    def _slugify(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", str(value or "").casefold()).strip("_")

    @staticmethod
    def _unique_id(base: str, existing: set[str]) -> str:
        root = base or "item"
        candidate = root
        suffix = 2
        while candidate in existing:
            candidate = f"{root}_{suffix}"
            suffix += 1
        return candidate


def normalize_page_url(raw_url: object) -> str | None:
    candidate = str(raw_url or "").strip()
    if not candidate:
        return None
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.netloc
        or any(character.isspace() for character in parsed.netloc)
    ):
        return None
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path or "/",
            parsed.params,
            parsed.query,
            "",
        )
    )


def page_label(url: str) -> str:
    parsed = urlparse(url)
    parts = [_friendly_segment(part) for part in parsed.path.split("/") if part]
    label = " / ".join(parts[-3:]) if parts else "Root"
    if len(parts) > 3:
        label = f"... / {label}"
    if parsed.query:
        label += " (Query)"
    return label


def _friendly_segment(segment: str) -> str:
    normalized = unicodedata.normalize("NFKD", unquote(str(segment or "")))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    words = ascii_text.replace("-", " ").replace("_", " ").split()
    return " ".join(word.capitalize() for word in words) or "Page"
