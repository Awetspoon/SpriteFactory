"""Application entrypoint for the Sprite Factory desktop UI."""

from __future__ import annotations

from image_engine_app.app.bootstrap import build_application_context, parse_startup_arguments
from image_engine_app.ui.desktop_runtime import run_desktop_application


def main(argv: list[str] | None = None) -> int:
    """Compose the application, then hand it to the desktop presentation runtime."""

    startup = parse_startup_arguments(argv)
    context = build_application_context(app_data_dir=startup.app_data_dir)
    return run_desktop_application(
        context,
        startup.qt_args,
        smoke_test=startup.smoke_test,
    )


if __name__ == "__main__":
    raise SystemExit(main())
