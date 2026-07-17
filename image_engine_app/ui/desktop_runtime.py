"""Qt desktop runtime for an already-composed Sprite Factory application."""

from __future__ import annotations

import logging
from pathlib import Path
import sys

from image_engine_app.app.bootstrap import ApplicationContext
from image_engine_app.app.paths import AppPaths
from image_engine_app.app.settings_store import load_user_settings, save_user_settings
from image_engine_app.ui.common.shell_theme import build_app_stylesheet
from image_engine_app.ui.common.shell_tokens import SHELL_GEOMETRY


APP_ICON_NAMES = ("spritefactory_pro.ico", "spritefactory.ico", "spritefactory_pro.png", "spritefactory.png")


def resolve_runtime_icon_candidates() -> list[Path]:
    """Return existing runtime icon candidates in preferred order."""

    candidates: list[Path] = []
    try:
        if getattr(sys, "frozen", False):
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                base = Path(str(meipass))
                for icon_root in (base / "image_engine_app" / "assets" / "icons", base):
                    candidates.extend(icon_root / name for name in APP_ICON_NAMES)
            candidates.append(Path(sys.executable))
        else:
            root = Path(__file__).resolve().parents[2]
            icon_root = root / "image_engine_app" / "assets" / "icons"
            candidates.extend(icon_root / name for name in APP_ICON_NAMES)
            candidates.extend(root / name for name in APP_ICON_NAMES)
    except (OSError, RuntimeError, TypeError):
        return []

    existing: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).casefold()
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists():
            existing.append(candidate)
    return existing


def save_window_settings(window: object, paths: AppPaths) -> None:
    """Persist UI-only window state without exposing Qt to application services."""

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


def restore_window_settings(window: object, paths: AppPaths) -> None:
    """Restore persisted window geometry and compact-view preference."""

    user_settings = load_user_settings(paths)
    ui_settings = user_settings.get("ui", {}) if isinstance(user_settings, dict) else {}
    if not isinstance(ui_settings, dict):
        return

    width = int(ui_settings.get("window_width", SHELL_GEOMETRY.window_default_width))
    height = int(ui_settings.get("window_height", SHELL_GEOMETRY.window_default_height))
    window.resize(
        max(SHELL_GEOMETRY.window_min_width, width),
        max(SHELL_GEOMETRY.window_min_height, height),
    )
    if all(key in ui_settings for key in ("window_x", "window_y")):
        window.move(int(ui_settings["window_x"]), int(ui_settings["window_y"]))
    if bool(ui_settings.get("compact_ui", False)):
        window.set_compact_ui(True)


def _set_windows_app_user_model_id(app_id: str, logger: logging.Logger) -> None:
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception as exc:  # pragma: no cover - platform integration
        logger.warning("Unable to set AppUserModelID (%s): %s", app_id, exc)


def _apply_native_style(app: object, style_factory: object) -> None:
    try:
        styles = {str(name).lower(): str(name) for name in style_factory.keys()}
        for key in ("windowsvista", "windows"):
            style_name = styles.get(key)
            if style_name:
                app.setStyle(style_name)
                return
    except Exception:
        return


def run_desktop_application(
    context: ApplicationContext,
    qt_args: tuple[str, ...],
    *,
    smoke_test: bool = False,
) -> int:
    """Run the Qt presentation using dependencies supplied by the composition root."""

    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication, QStyleFactory
        from image_engine_app.ui.main_window.main_window import ImageEngineMainWindow
    except ImportError as exc:
        context.logger.error("PySide6 is required to launch the UI: %s", exc)
        print("PySide6 is not installed. Install it with: pip install PySide6", file=sys.stderr)
        return 1

    _set_windows_app_user_model_id("Marcus.SpriteFactory.Windows.PythonV2", context.logger)
    app = QApplication([sys.argv[0], *qt_args])
    _apply_native_style(app, QStyleFactory)
    app.setStyleSheet(build_app_stylesheet())
    app.setApplicationName("Sprite Factory Pro")
    app.setOrganizationName("Sprite Factory Pro")

    runtime_icon = None
    runtime_icon_path = None
    for candidate in resolve_runtime_icon_candidates():
        candidate_icon = QIcon(str(candidate))
        if candidate_icon.isNull():
            continue
        runtime_icon = candidate_icon
        runtime_icon_path = candidate
        break

    if runtime_icon is not None:
        app.setWindowIcon(runtime_icon)
        context.logger.info("Runtime icon loaded: %s", runtime_icon_path)
    else:
        context.logger.warning("Runtime icon not found/usable")

    window = ImageEngineMainWindow(controller=context.controller, session_store=context.session_store)
    if runtime_icon is not None:
        window.setWindowIcon(runtime_icon)
    restore_window_settings(window, context.paths)
    window.set_session(context.startup_session)
    window.set_active_asset(None)

    def on_about_to_quit() -> None:
        try:
            save_window_settings(window, context.paths)
        except Exception as exc:  # pragma: no cover - shutdown path
            context.logger.exception("Failed to save app state on exit: %s", exc)

    app.aboutToQuit.connect(on_about_to_quit)
    if smoke_test:
        window.show()
        QTimer.singleShot(1500, app.quit)
    else:
        window.showMaximized()
    context.logger.info("UI shell launched")
    return int(app.exec())
