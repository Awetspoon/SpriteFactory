"""Logging startup resilience tests."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from image_engine_app.app.logging_config import _close_handlers, configure_logging


class LoggingConfigTests(unittest.TestCase):
    def tearDown(self) -> None:
        _close_handlers(logging.getLogger("image_engine_app.batch"))
        _close_handlers(logging.getLogger("image_engine_app"))

    def test_configure_logging_replaces_handlers_and_writes_expected_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                log_dir = Path(temp_dir) / "logs"
                first_logger = configure_logging(log_dir)
                second_logger = configure_logging(log_dir)
                second_logger.info("logging test")
                for handler in second_logger.handlers:
                    handler.flush()

                self.assertIs(first_logger, second_logger)
                self.assertEqual(2, len(second_logger.handlers))
                self.assertTrue((log_dir / "image_engine_app.log").exists())
                self.assertTrue((log_dir / "batch_debug.log").exists())
            finally:
                self.tearDown()

    def test_unwritable_primary_log_uses_process_specific_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                root = Path(temp_dir)
                blocked_log_dir = root / "blocked"
                blocked_log_dir.write_text("not a directory", encoding="utf-8")
                fallback_dir = root / "fallback"

                with patch(
                    "image_engine_app.app.logging_config._fallback_log_dir",
                    return_value=fallback_dir,
                ):
                    logger = configure_logging(blocked_log_dir)
                    logger.info("fallback test")
                    for handler in logger.handlers:
                        handler.flush()

                self.assertTrue((fallback_dir / f"image_engine_app_{os.getpid()}.log").exists())
                self.assertTrue((fallback_dir / "batch_debug.log").exists())
            finally:
                self.tearDown()


if __name__ == "__main__":
    unittest.main()
