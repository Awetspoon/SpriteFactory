"""Application composition for Sprite Factory.

This module creates application services without importing Qt. Presentation code
receives the completed context instead of constructing engine dependencies itself.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from pathlib import Path
import sys
from typing import Callable
from uuid import uuid4

from image_engine_app.app.logging_config import configure_logging
from image_engine_app.app.paths import AppPaths, ensure_app_paths
from image_engine_app.app.settings_store import SessionStore
from image_engine_app.app.ui_controller import ImageEngineUIController
from image_engine_app.engine.models import SessionState


@dataclass(frozen=True)
class StartupArguments:
    """Application-owned arguments separated from arguments passed to Qt."""

    app_data_dir: str | None
    smoke_test: bool
    qt_args: tuple[str, ...]


@dataclass(frozen=True)
class ApplicationContext:
    """Fully composed non-visual dependencies for one application run."""

    paths: AppPaths
    logger: logging.Logger
    controller: ImageEngineUIController
    session_store: SessionStore
    startup_session: SessionState


def parse_startup_arguments(argv: list[str] | None = None) -> StartupArguments:
    """Parse Sprite Factory options while preserving unrelated Qt arguments."""

    parser = argparse.ArgumentParser(description="Launch the Sprite Factory UI shell")
    parser.add_argument("--app-data-dir", default=None, help="Override app data directory (for local testing)")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Launch the desktop shell briefly, then exit with a process status for release verification",
    )
    raw_args = list(sys.argv[1:] if argv is None else argv)
    args, qt_args = parser.parse_known_args(raw_args)
    return StartupArguments(
        app_data_dir=args.app_data_dir,
        smoke_test=bool(args.smoke_test),
        qt_args=tuple(qt_args),
    )


def build_startup_session(
    *,
    session_id: str | None = None,
    opened_at: datetime | None = None,
) -> SessionState:
    """Create the clean, empty session used for a new application run."""

    return SessionState(
        session_id=session_id or f"session-{uuid4().hex[:8]}",
        opened_at=opened_at or datetime.now(timezone.utc),
        active_tab_asset_id=None,
        tab_order=[],
        pinned_tabs=set(),
        batch_queue=[],
        macros=[],
        last_export_dir=None,
    )


def build_application_context(
    *,
    app_data_dir: str | Path | None = None,
    controller_factory: Callable[..., ImageEngineUIController] = ImageEngineUIController,
    session_store_factory: Callable[[AppPaths], SessionStore] = SessionStore,
    logger_factory: Callable[[Path], logging.Logger] = configure_logging,
) -> ApplicationContext:
    """Create the application dependency graph in one testable composition root."""

    paths = ensure_app_paths(base_dir=app_data_dir)
    logger = logger_factory(paths.logs)
    logger.info("App data root: %s", paths.root)

    controller = controller_factory(app_paths=paths)
    session_store = session_store_factory(paths)
    return ApplicationContext(
        paths=paths,
        logger=logger,
        controller=controller,
        session_store=session_store,
        startup_session=build_startup_session(),
    )
