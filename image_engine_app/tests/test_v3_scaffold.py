"""Smoke checks for the parallel v3 scaffold."""

from __future__ import annotations

from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from image_engine_v3.app.bootstrap import build_config  # noqa: E402
from image_engine_v3.app.main import main as v3_main  # noqa: E402


class V3ScaffoldTests(unittest.TestCase):
    def test_build_config_defaults_under_repo(self) -> None:
        config = build_config()
        self.assertTrue(str(config.app_data_dir).endswith("_ui_check_v3"))

    def test_entrypoint_runs(self) -> None:
        with io.StringIO() as stream, redirect_stdout(stream):
            code = v3_main(["--app-data-dir", "./_tmp_v3"])
        self.assertEqual(0, code)


if __name__ == "__main__":
    unittest.main()
