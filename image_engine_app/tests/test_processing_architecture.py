"""Architecture checks for the rebuilt image-processing boundary."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROCESS_ROOT = PACKAGE_ROOT / "engine" / "process"


def _defined_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


class ProcessingArchitectureTests(unittest.TestCase):
    def test_removed_light_steps_monolith_is_not_reintroduced(self) -> None:
        self.assertFalse((PROCESS_ROOT / "light_steps.py").exists())

    def test_gif_quantization_has_one_engine_owner(self) -> None:
        owners = []
        for path in (PACKAGE_ROOT / "engine").rglob("*.py"):
            if "quantize_gif_frame" in _defined_functions(path):
                owners.append(path.relative_to(PACKAGE_ROOT).as_posix())

        self.assertEqual(["engine/process/animation.py"], owners)

    def test_processing_modules_do_not_import_application_or_ui(self) -> None:
        invalid: list[str] = []
        for path in PROCESS_ROOT.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
            for node in ast.walk(tree):
                module = None
                if isinstance(node, ast.ImportFrom):
                    module = node.module
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith(("image_engine_app.app", "image_engine_app.ui", "PySide6")):
                            invalid.append(f"{path.name} -> {alias.name}")
                if module and module.startswith(("image_engine_app.app", "image_engine_app.ui", "PySide6")):
                    invalid.append(f"{path.name} -> {module}")

        self.assertEqual([], invalid)


if __name__ == "__main__":
    unittest.main()
