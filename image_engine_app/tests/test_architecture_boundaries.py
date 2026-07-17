"""Dependency-direction checks for the staged rebuild."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def _imports_for(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_application_bootstrap_has_no_presentation_dependency(self) -> None:
        imports = _imports_for(PACKAGE_ROOT / "app" / "bootstrap.py")

        self.assertFalse(any(name.startswith("image_engine_app.ui") for name in imports))
        self.assertFalse(any(name.startswith("PySide6") for name in imports))

    def test_engine_has_no_application_or_presentation_dependency(self) -> None:
        invalid: list[str] = []
        for path in (PACKAGE_ROOT / "engine").rglob("*.py"):
            for imported in _imports_for(path):
                if imported.startswith(("image_engine_app.app", "image_engine_app.ui", "PySide6")):
                    invalid.append(f"{path.relative_to(PACKAGE_ROOT)} -> {imported}")

        self.assertEqual(invalid, [])


if __name__ == "__main__":
    unittest.main()
