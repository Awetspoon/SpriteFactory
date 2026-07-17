"""Architecture checks for Stage 6 preset ownership."""

from __future__ import annotations

from pathlib import Path
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


class PresetArchitectureTests(unittest.TestCase):
    def test_controller_and_batch_do_not_reimplement_preset_application(self) -> None:
        controller = (PACKAGE_ROOT / "app" / "ui_controller.py").read_text(encoding="utf-8")
        batch = (PACKAGE_ROOT / "engine" / "batch" / "batch_runner.py").read_text(encoding="utf-8")

        self.assertNotIn("apply_preset_to_edit_state", controller)
        self.assertNotIn("preset_matches_asset", controller)
        self.assertNotIn("apply_preset_to_edit_state", batch)
        self.assertNotIn("preset_matches_asset", batch)
        self.assertIn("_preset_workflow.apply_named", controller)
        self.assertIn("plan_preset_application", batch)

    def test_preset_manager_has_no_independent_store(self) -> None:
        manager = (PACKAGE_ROOT / "ui" / "windows" / "preset_manager.py").read_text(encoding="utf-8")

        self.assertNotIn("PresetStore(", manager)
        self.assertIn("_controller.upsert_user_preset", manager)
        self.assertIn("_controller.delete_user_preset", manager)


if __name__ == "__main__":
    unittest.main()
