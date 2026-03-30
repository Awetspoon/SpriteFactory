"""Smoke checks for the parallel v3 scaffold."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from image_engine_v3.app.bootstrap import build_config  # noqa: E402
from image_engine_v3.app.main import main as v3_main  # noqa: E402
from image_engine_v3.presentation.qt_app import launch_qt_app  # noqa: E402


class V3ScaffoldTests(unittest.TestCase):
    def test_build_config_defaults_under_repo(self) -> None:
        config = build_config()
        self.assertEqual(Path.cwd() / ".local" / "ui-check-v3", config.app_data_dir)

    def test_entrypoint_delegates_to_qt_bridge(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("image_engine_v3.app.main.launch_qt_app", return_value=0) as launch_mock:
                code = v3_main(["--app-data-dir", temp_dir])
            self.assertEqual(0, code)
            launch_mock.assert_called_once()
            forwarded = launch_mock.call_args.args[0]
            self.assertEqual(Path(temp_dir).resolve(), forwarded.app_data_dir)

    def test_qt_bridge_delegates_to_current_launcher(self) -> None:
        config = build_config(app_data_dir="C:/Temp/SpriteFactory-V3")

        with patch("image_engine_app.launcher.main", return_value=0) as launch_mock:
            code = launch_qt_app(config)

        self.assertEqual(0, code)
        launch_mock.assert_called_once_with(["--app-data-dir", str(config.app_data_dir)])


if __name__ == "__main__":
    unittest.main()
