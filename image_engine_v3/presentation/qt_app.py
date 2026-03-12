"""V3 Qt app surface placeholder."""

from __future__ import annotations

from image_engine_v3.app.bootstrap import V3AppConfig


def launch_qt_app(config: V3AppConfig) -> int:
    """Placeholder launch hook for future v3 Qt wiring."""

    print(f"[v3] qt placeholder launch. app_data_dir={config.app_data_dir}")
    return 0
