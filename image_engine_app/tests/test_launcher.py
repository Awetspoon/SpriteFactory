"""Tests for runtime path resolution in the packaged launcher."""

from __future__ import annotations

from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from image_engine_app import launcher


class LauncherTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
