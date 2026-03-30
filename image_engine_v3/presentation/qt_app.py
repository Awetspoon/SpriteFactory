"""V3 Qt app bridge."""

from __future__ import annotations

from image_engine_v3.app.bootstrap import V3AppConfig


def launch_qt_app(config: V3AppConfig) -> int:
    """Launch the current Qt shell through the repository-aware launcher.

    The v3 architecture layers are already used by the active app for workspace/session
    behavior, but the dedicated v3 presentation shell does not yet diverge visually.
    Until that split is ready, the v3 entrypoint delegates to the current launcher so the
    code path is real and testable instead of remaining a dead no-op path.
    """

    from image_engine_app.launcher import main as launch_current_app

    return int(launch_current_app(["--app-data-dir", str(config.app_data_dir)]))
