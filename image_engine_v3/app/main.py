"""Main entrypoint for Sprite Factory v3 scaffold."""

from __future__ import annotations

import argparse

from image_engine_v3.app.bootstrap import build_config
from image_engine_v3.presentation.qt_app import launch_qt_app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Launch the Sprite Factory v3 bridge")
    parser.add_argument("--app-data-dir", default=None)
    args = parser.parse_args(argv)

    config = build_config(app_data_dir=args.app_data_dir)
    return int(launch_qt_app(config))


if __name__ == "__main__":
    raise SystemExit(main())
