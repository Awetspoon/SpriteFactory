"""Main entrypoint for Sprite Factory v3 scaffold."""

from __future__ import annotations

import argparse

from image_engine_v3.app.bootstrap import build_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sprite Factory v3 scaffold")
    parser.add_argument("--app-data-dir", default=None)
    args = parser.parse_args(argv)

    config = build_config(app_data_dir=args.app_data_dir)
    print(f"[v3] scaffold ready. app_data_dir={config.app_data_dir}")
    print("[v3] UI/runtime wiring is intentionally not connected yet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
