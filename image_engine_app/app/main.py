"""Application entrypoint for the Sprite Factory Qt desktop UI."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import logging
from pathlib import Path
import sys
from uuid import uuid4

from image_engine_app.app.logging_config import configure_logging
from image_engine_app.app.paths import AppPaths, ensure_app_paths
from image_engine_app.app.settings_store import SessionStore, load_user_settings, save_user_settings
from image_engine_app.app.ui_controller import ImageEngineUIController
from image_engine_app.engine.models import SessionState
from image_engine_app.ui.common.shell_theme import build_app_stylesheet


APP_ICON_NAMES = ("spritefactory_pro.ico", "spritefactory.ico", "spritefactory_pro.png", "spritefactory.png")


def build_startup_session() -> SessionState:
    """Create a clean empty startup session (no demo assets)."""

    return SessionState(
        session_id=f"session-{uuid4().hex[:8]}",
        opened_at=datetime.now(timezone.utc),
        active_tab_asset_id=None,
        tab_order=[],
        pinned_tabs=set(),
        batch_queue=[],
        macros=[],
        last_export_dir=None,
    )


def _save_window_settings(window, paths: AppPaths) -> None:  # noqa: ANN001 - PySide object type only available when Qt installed
    settings = load_user_settings(paths)
    geometry = window.normalGeometry() if (window.isMinimized() or window.isMaximized()) else window.geometry()
    compact_ui = bool(window.compact_ui_enabled()) if hasattr(window, "compact_ui_enabled") else False
    settings["ui"] = {
        "window_x": geometry.x(),
        "window_y": geometry.y(),
        "window_width": geometry.width(),
        "window_height": geometry.height(),
        "compact_ui": compact_ui,
    }
    save_user_settings(paths, settings)


def _resolve_runtime_icon_candidates() -> list[Path]:
    """Return ordered icon candidates for runtime window/taskbar icon."""

    candidates: list[Path] = []

    try:
        if getattr(sys, "frozen", False):
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                base = Path(str(meipass))
                for icon_root in (base / "image_engine_app" / "assets" / "icons", base):
                    for icon_name in APP_ICON_NAMES:
                        candidates.append(icon_root / icon_name)

            exe_path = Path(sys.executable)
            candidates.append(exe_path)
        else:
            root = Path(__file__).resolve().parents[2]
            icon_root = root / "image_engine_app" / "assets" / "icons"
            for icon_name in APP_ICON_NAMES:
                candidates.append(icon_root / icon_name)
            for icon_name in APP_ICON_NAMES:
                candidates.append(root / icon_name)
    except Exception:
        return []

    out: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists():
            out.append(candidate)
    return out


def _set_windows_app_user_model_id(app_id: str, logger: logging.Logger) -> None:
    """Set Windows AppUserModelID so taskbar identity/icon grouping is stable."""

    if not sys.platform.startswith("win"):
        return

    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception as exc:
        logger.warning("Unable to set AppUserModelID (%s): %s", app_id, exc)


def _apply_clean_pro_theme(app) -> None:  # noqa: ANN001 - QApplication imported only at runtime
    """Apply a clean professional brand theme to core Qt widgets."""

    app.setStyleSheet(build_app_stylesheet())


def _parse_startup_args(argv: list[str] | None) -> tuple[argparse.Namespace, list[str]]:
    """Parse Sprite Factory options and leave unrelated options for Qt."""

    parser = argparse.ArgumentParser(description="Launch the Sprite Factory UI shell")
    parser.add_argument("--app-data-dir", default=None, help="Override app data directory (for local testing)")
    raw_args = list(sys.argv[1:] if argv is None else argv)
    return parser.parse_known_args(raw_args)


def main(argv: list[str] | None = None) -> int:
    """Launch the Sprite Factory UI shell."""

    args, qt_args = _parse_startup_args(argv)

    paths = ensure_app_paths(base_dir=args.app_data_dir)
    logger = configure_logging(paths.logs)
    logger.info("App data root: %s", paths.root)

    try:
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication, QStyleFactory
        from image_engine_app.ui.main_window.main_window import ImageEngineMainWindow
    except ImportError as exc:
        logger.error("PySide6 is required to launch the UI: %s", exc)
        print("PySide6 is not installed. Install it with: pip install PySide6", file=sys.stderr)
        return 1

    _set_windows_app_user_model_id("Marcus.SpriteFactory.Windows.PythonV2", logger)

    app = QApplication([sys.argv[0], *qt_args])

    # Prefer native Windows style so min/max/titlebar behavior matches user expectations.
    try:
        styles = {str(name).lower(): str(name) for name in QStyleFactory.keys()}
        for key in ("windowsvista", "windows"):
            style_name = styles.get(key)
            if style_name:
                app.setStyle(style_name)
                break
    except Exception:
        pass

    _apply_clean_pro_theme(app)

    app.setApplicationName("Sprite Factory Pro")
    app.setOrganizationName("Sprite Factory Pro")

    runtime_icon = None
    runtime_icon_path = None
    for candidate in _resolve_runtime_icon_candidates():
        icon_obj = QIcon(str(candidate))
        if icon_obj.isNull():
            continue
        runtime_icon = icon_obj
        runtime_icon_path = candidate
        break

    if runtime_icon is not None:
        app.setWindowIcon(runtime_icon)
        logger.info("Runtime icon loaded: %s", runtime_icon_path)
    else:
        logger.warning("Runtime icon not found/usable")

    controller = ImageEngineUIController(app_paths=paths)
    session_store = SessionStore(paths)
    window = ImageEngineMainWindow(controller=controller, session_store=session_store)
    if runtime_icon is not None:
        window.setWindowIcon(runtime_icon)

    user_settings = load_user_settings(paths)
    ui_settings = user_settings.get("ui", {}) if isinstance(user_settings, dict) else {}
    if isinstance(ui_settings, dict):
        width = int(ui_settings.get("window_width", 1460))
        height = int(ui_settings.get("window_height", 920))
        window.resize(max(960, width), max(640, height))
        if all(key in ui_settings for key in ("window_x", "window_y")):
            window.move(int(ui_settings["window_x"]), int(ui_settings["window_y"]))
        if bool(ui_settings.get("compact_ui", False)):
            window.set_compact_ui(True)

    window.set_session(build_startup_session())
    window.set_active_asset(None)

    def _on_about_to_quit() -> None:
        try:
            _save_window_settings(window, paths)
        except Exception as exc:  # pragma: no cover - shutdown path
            logger.exception("Failed to save app state on exit: %s", exc)

    app.aboutToQuit.connect(_on_about_to_quit)
    window.showMaximized()
    logger.info("UI shell launched")
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())


