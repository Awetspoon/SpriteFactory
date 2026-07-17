"""Tests for runtime path resolution in the packaged launcher."""

from __future__ import annotations

from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from image_engine_app import launcher
from image_engine_app.app.bootstrap import parse_startup_arguments
from image_engine_app.app.identity import APP_NAME, APP_TITLE, APP_VERSION
from image_engine_app.ui.desktop_runtime import resolve_runtime_icon_candidates


class LauncherTests(unittest.TestCase):
    def test_public_identity_is_sprite_factory(self) -> None:
        self.assertEqual("Sprite Factory", APP_NAME)
        self.assertEqual("1.2.4", APP_VERSION)
        self.assertEqual("Sprite Factory v1.2.4", APP_TITLE)

    def test_app_startup_arguments_do_not_leak_into_qt_arguments(self) -> None:
        startup = parse_startup_arguments(["--app-data-dir", ".\\runtime", "-platform", "offscreen"])

        self.assertEqual(Path(startup.app_data_dir), Path(".\\runtime"))
        self.assertFalse(startup.smoke_test)
        self.assertEqual(startup.qt_args, ("-platform", "offscreen"))

    def test_smoke_test_argument_is_owned_by_the_application(self) -> None:
        startup = parse_startup_arguments(
            ["--smoke-test", "--app-data-dir", ".\\runtime", "-platform", "offscreen"]
        )

        self.assertTrue(startup.smoke_test)
        self.assertEqual(startup.qt_args, ("-platform", "offscreen"))

    def test_extract_cli_app_data_dir_supports_separate_value(self) -> None:
        target = launcher._extract_cli_app_data_dir(["--app-data-dir", ".\\runtime"])
        self.assertEqual(Path(".\\runtime").expanduser().resolve(), target)

    def test_extract_cli_app_data_dir_supports_equals_value(self) -> None:
        target = launcher._extract_cli_app_data_dir(["--app-data-dir=.\\runtime"])
        self.assertEqual(Path(".\\runtime").expanduser().resolve(), target)

    def test_resolve_runtime_dir_uses_legacy_env_only_as_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {launcher.LEGACY_RUNTIME_ENV_VAR: temp_dir}, clear=False):
                resolved, inject_override = launcher._resolve_runtime_dir([])

        self.assertEqual(Path(temp_dir).resolve(), resolved)
        self.assertTrue(inject_override)

    def test_resolve_runtime_dir_prefers_cli_over_legacy_env(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cli_target = Path(temp_dir) / "cli-runtime"
            with patch.dict(os.environ, {launcher.LEGACY_RUNTIME_ENV_VAR: str(Path(temp_dir) / "env-runtime")}, clear=False):
                resolved, inject_override = launcher._resolve_runtime_dir(["--app-data-dir", str(cli_target)])

        self.assertEqual(cli_target.resolve(), resolved)
        self.assertFalse(inject_override)

    def test_runtime_icon_prefers_multi_size_ico_before_png(self) -> None:
        names = [path.name for path in resolve_runtime_icon_candidates()]

        self.assertIn("spritefactory.ico", names)
        self.assertIn("spritefactory.png", names)
        self.assertNotIn("spritefactory_pro.ico", names)
        self.assertNotIn("spritefactory_pro.png", names)
        self.assertLess(names.index("spritefactory.ico"), names.index("spritefactory.png"))


if __name__ == "__main__":
    unittest.main()
