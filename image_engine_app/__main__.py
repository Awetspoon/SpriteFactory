"""Package entrypoint for `python -m image_engine_app`."""

from __future__ import annotations

from image_engine_app.launcher import main


if __name__ == "__main__":
    raise SystemExit(main())
