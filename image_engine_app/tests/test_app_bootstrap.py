"""Tests for the Stage 1 application composition boundary."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from image_engine_app.app import main as app_main
from image_engine_app.app.bootstrap import (
    ApplicationContext,
    build_application_context,
    build_startup_session,
)


class ApplicationBootstrapTests(unittest.TestCase):
    def test_startup_session_is_empty_and_deterministic_when_values_are_supplied(self) -> None:
        opened_at = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)

        session = build_startup_session(session_id="session-checkpoint", opened_at=opened_at)

        self.assertEqual(session.session_id, "session-checkpoint")
        self.assertEqual(session.opened_at, opened_at)
        self.assertEqual(session.tab_order, [])
        self.assertEqual(session.batch_queue, [])
        self.assertIsNone(session.active_tab_asset_id)

    def test_application_context_builds_non_visual_dependencies_in_one_place(self) -> None:
        controller = Mock()
        session_store = Mock()
        logger = Mock(spec=logging.Logger)
        controller_factory = Mock(return_value=controller)
        session_store_factory = Mock(return_value=session_store)
        logger_factory = Mock(return_value=logger)

        with tempfile.TemporaryDirectory() as temp_dir:
            context = build_application_context(
                app_data_dir=temp_dir,
                controller_factory=controller_factory,
                session_store_factory=session_store_factory,
                logger_factory=logger_factory,
            )

            self.assertEqual(context.paths.root, Path(temp_dir))
            self.assertTrue(context.paths.cache.is_dir())
            self.assertTrue(context.paths.sessions.is_dir())
            controller_factory.assert_called_once_with(app_paths=context.paths)
            session_store_factory.assert_called_once_with(context.paths)
            logger_factory.assert_called_once_with(context.paths.logs)
            self.assertIs(context.logger, logger)
            self.assertIs(context.controller, controller)
            self.assertIs(context.session_store, session_store)

    def test_main_routes_composed_context_to_desktop_runtime(self) -> None:
        context = Mock(spec=ApplicationContext)
        with (
            patch("image_engine_app.app.main.build_application_context", return_value=context) as build_context,
            patch("image_engine_app.app.main.run_desktop_application", return_value=17) as run_desktop,
        ):
            result = app_main.main(
                [
                    "--smoke-test",
                    "--app-data-dir",
                    ".\\runtime",
                    "-platform",
                    "offscreen",
                ]
            )

        self.assertEqual(result, 17)
        build_context.assert_called_once_with(app_data_dir=".\\runtime")
        run_desktop.assert_called_once_with(
            context,
            ("-platform", "offscreen"),
            smoke_test=True,
        )


if __name__ == "__main__":
    unittest.main()
