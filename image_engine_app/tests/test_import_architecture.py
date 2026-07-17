"""Architecture checks for the rebuilt import and workspace boundary."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


class ImportArchitectureTests(unittest.TestCase):
    def test_one_import_result_contract_owns_all_import_outcomes(self) -> None:
        owners: list[str] = []
        for path in PACKAGE_ROOT.rglob("*.py"):
            if "tests" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
            if any(isinstance(node, ast.ClassDef) and node.name == "ImportResult" for node in ast.walk(tree)):
                owners.append(path.relative_to(PACKAGE_ROOT).as_posix())

        self.assertEqual(["engine/ingest/import_result.py"], owners)

    def test_removed_split_result_contracts_are_not_reintroduced(self) -> None:
        production_text = "\n".join(
            path.read_text(encoding="utf-8-sig")
            for path in PACKAGE_ROOT.rglob("*.py")
            if "tests" not in path.parts
        )
        for removed_name in ("LocalImportSummary", "UrlImportSummary", "DownloadReport", "LocalIngestResult"):
            self.assertNotIn(removed_name, production_text)

    def test_qt_local_import_coordinator_does_not_extract_archives(self) -> None:
        source = (PACKAGE_ROOT / "ui" / "main_window" / "local_import_coordinator.py").read_text(
            encoding="utf-8-sig"
        )
        self.assertNotIn("zip_extract", source)
        self.assertNotIn("extract_images_only", source)

    def test_main_window_does_not_mutate_workspace_asset_list_directly(self) -> None:
        source = (PACKAGE_ROOT / "ui" / "main_window" / "main_window.py").read_text(encoding="utf-8-sig")
        self.assertNotIn("_workspace_assets.append", source)
        self.assertNotIn("_workspace_assets.extend", source)


if __name__ == "__main__":
    unittest.main()
