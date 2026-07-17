"""Architecture checks for Stage 5 controls and preview ownership."""

from __future__ import annotations

from pathlib import Path
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


class EditArchitectureTests(unittest.TestCase):
    def test_widgets_do_not_mutate_asset_edit_state(self) -> None:
        for relative in (
            "ui/common/state_bindings.py",
            "ui/main_window/settings_panel.py",
            "ui/main_window/control_strip.py",
            "ui/main_window/export_bar.py",
        ):
            text = (PACKAGE_ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn("asset.edit_state =", text, relative)
            self.assertNotIn("asset.edit_state.settings", text, relative)

    def test_retired_two_view_edit_contract_is_gone(self) -> None:
        model_text = (PACKAGE_ROOT / "engine/models/asset_record.py").read_text(encoding="utf-8")
        preset_text = (PACKAGE_ROOT / "engine/process/presets_apply.py").read_text(encoding="utf-8")
        for retired_name in ("ApplyTarget", "sync_current_final", "auto_apply_light", "ViewEditStates"):
            self.assertNotIn(retired_name, model_text + preset_text)

    def test_current_has_no_derived_asset_path(self) -> None:
        model_text = (PACKAGE_ROOT / "engine/models/asset_record.py").read_text(encoding="utf-8")
        preview_text = (PACKAGE_ROOT / "ui/main_window/preview_panel.py").read_text(encoding="utf-8")
        self.assertNotIn("derived_current_path", model_text)
        self.assertNotIn("derived_current_path", preview_text)


if __name__ == "__main__":
    unittest.main()
