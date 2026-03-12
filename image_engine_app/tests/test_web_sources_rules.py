"""Tests for Web Sources URL confidence and extension inference rules."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.web_sources_models import Confidence  # noqa: E402
from engine.ingest.web_sources_rules import (  # noqa: E402
    ALLOWED_ARCHIVE_EXTS_DEFAULT,
    ALLOWED_IMAGE_EXTS_DEFAULT,
    confidence_for,
    normalize_ext,
)


class WebSourcesRulesTests(unittest.TestCase):
    def test_normalize_ext_reads_query_filename(self) -> None:
        url = "https://example.com/download?id=42&file=bulbasaur.png"
        self.assertEqual(".png", normalize_ext(url))

    def test_normalize_ext_reads_format_value(self) -> None:
        url = "https://example.com/render?format=webp"
        self.assertEqual(".webp", normalize_ext(url))

    def test_confidence_marks_download_like_path_as_likely(self) -> None:
        url = "https://example.com/files/1234/?do=download"
        allowed = set(ALLOWED_IMAGE_EXTS_DEFAULT) | set(ALLOWED_ARCHIVE_EXTS_DEFAULT)
        self.assertEqual(Confidence.LIKELY, confidence_for(url, allowed_exts=allowed))

    def test_confidence_marks_unrelated_page_as_unknown(self) -> None:
        url = "https://example.com/about/team"
        allowed = set(ALLOWED_IMAGE_EXTS_DEFAULT) | set(ALLOWED_ARCHIVE_EXTS_DEFAULT)
        self.assertEqual(Confidence.UNKNOWN, confidence_for(url, allowed_exts=allowed))


if __name__ == "__main__":
    unittest.main()
