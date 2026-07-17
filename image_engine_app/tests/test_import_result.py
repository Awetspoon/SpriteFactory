"""Tests for the shared import outcome contract."""

from __future__ import annotations

import unittest

from image_engine_app.engine.ingest.import_result import (
    ImportIssueKind,
    ImportResult,
    ImportedAsset,
)
from image_engine_app.engine.models import AssetRecord


def _entry(name: str, *, reused: bool = False) -> ImportedAsset:
    asset = AssetRecord(original_name=name, source_uri=f"source/{name}")
    return ImportedAsset(asset=asset, source=asset.source_uri, reused=reused)


class ImportResultTests(unittest.TestCase):
    def test_extend_preserves_assets_reuse_issues_and_cancellation(self) -> None:
        first = ImportResult(entries=[_entry("new.png")])
        second = ImportResult(entries=[_entry("cached.gif", reused=True)], cancelled=True)
        second.add_issue(ImportIssueKind.DUPLICATE, "duplicate.png", "same content")
        second.add_issue(ImportIssueKind.SKIPPED, "disabled.zip", "ZIP imports are disabled")
        second.add_issue(ImportIssueKind.FAILED, "broken.webp", "invalid signature")

        first.extend(second)

        self.assertEqual(("new.png",), first.downloaded)
        self.assertEqual(("cached.gif",), first.reused)
        self.assertEqual(("duplicate.png",), first.duplicates)
        self.assertEqual(("duplicate.png", "disabled.zip"), first.skipped)
        self.assertEqual(("broken.webp: invalid signature",), first.failed)
        self.assertTrue(first.cancelled)
        self.assertEqual(2, len(first.assets))


if __name__ == "__main__":
    unittest.main()
