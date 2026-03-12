"""PyInstaller runtime hook for reliable PySide6/Qt plugin loading on Windows.

This prevents common errors like:
- "This application failed to start because no Qt platform plugin could be initialized."
- missing qwindows.dll plugin

PyInstaller extracts bundled files to sys._MEIPASS at runtime (especially in onefile builds).
We set the plugin env vars to point at the bundled plugin folders if they exist.
"""

from __future__ import annotations

import os
import sys


def _set_if_dir(env_key: str, path: str) -> None:
    if not os.environ.get(env_key) and os.path.isdir(path):
        os.environ[env_key] = path


def _main() -> None:
    # Only relevant in frozen builds.
    if not getattr(sys, "frozen", False):
        return

    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return

    # Common bundle layout when using collect_qt_plugins("PySide6")
    qt_plugins = os.path.join(base, "PySide6", "Qt", "plugins")
    platforms = os.path.join(qt_plugins, "platforms")

    _set_if_dir("QT_PLUGIN_PATH", qt_plugins)
    _set_if_dir("QT_QPA_PLATFORM_PLUGIN_PATH", platforms)

    # Helpful for debugging packaged builds if needed:
    # os.environ.setdefault("QT_DEBUG_PLUGINS", "1")


_main()
