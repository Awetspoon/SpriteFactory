"""Architecture checks for Stage 7 export and Batch ownership."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def _defined_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


class ExportArchitectureTests(unittest.TestCase):
    def test_auto_format_and_extension_have_one_engine_owner(self) -> None:
        format_owners: list[str] = []
        extension_owners: list[str] = []
        for path in (PACKAGE_ROOT / "engine").rglob("*.py"):
            functions = _defined_functions(path)
            relative = path.relative_to(PACKAGE_ROOT).as_posix()
            if "resolve_export_format" in functions:
                format_owners.append(relative)
            if "extension_for_export_format" in functions:
                extension_owners.append(relative)

        self.assertEqual(["engine/export/format_resolver.py"], format_owners)
        self.assertEqual(["engine/export/format_resolver.py"], extension_owners)

    def test_batch_runner_delegates_file_output_to_shared_asset_export(self) -> None:
        source = (PACKAGE_ROOT / "engine" / "batch" / "batch_runner.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("export_asset_to_file", source)
        self.assertNotIn("ExportRequest(", source)
        self.assertNotIn("predict_export_size(", source)
        self.assertNotIn("render_name_template(", source)
        self.assertNotIn("ensure_unique_path(", source)
        self.assertNotIn("resolve_export_source(", source)

    def test_batch_preparation_is_not_owned_by_qt_presentation(self) -> None:
        self.assertFalse(
            (PACKAGE_ROOT / "ui" / "main_window" / "batch_run_prep.py").exists()
        )
        coordinator = (
            PACKAGE_ROOT / "ui" / "main_window" / "batch_coordinator.py"
        ).read_text(encoding="utf-8")
        self.assertIn("controller.prepare_batch_assets", coordinator)


if __name__ == "__main__":
    unittest.main()
