"""Minimal icon helpers for the Qt UI shell."""

from __future__ import annotations

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QStyle


STANDARD_ICON_MAP: dict[str, QStyle.StandardPixmap] = {
    "new": QStyle.StandardPixmap.SP_FileIcon,
    "open": QStyle.StandardPixmap.SP_DirOpenIcon,
    "save": QStyle.StandardPixmap.SP_DialogSaveButton,
    "undo": QStyle.StandardPixmap.SP_ArrowBack,
    "redo": QStyle.StandardPixmap.SP_ArrowForward,
    "skip": QStyle.StandardPixmap.SP_ArrowForward,
    "apply": QStyle.StandardPixmap.SP_DialogApplyButton,
    "export": QStyle.StandardPixmap.SP_DialogSaveButton,
    "reset": QStyle.StandardPixmap.SP_BrowserReload,
    "tools": QStyle.StandardPixmap.SP_FileDialogDetailedView,
}


def icon(name: str) -> QIcon:
    """Return a standard Qt icon fallback for a symbolic name."""

    app = QApplication.instance()
    if app is None:
        return QIcon()
    style = app.style()
    pix = STANDARD_ICON_MAP.get(name)
    if pix is None:
        return QIcon()
    return style.standardIcon(pix)
