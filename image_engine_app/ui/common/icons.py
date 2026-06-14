"""Minimal icon helpers for the Qt UI shell."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QApplication, QStyle


STANDARD_ICON_MAP: dict[str, QStyle.StandardPixmap] = {
    "new": QStyle.StandardPixmap.SP_FileIcon,
    "import": QStyle.StandardPixmap.SP_FileDialogStart,
    "open": QStyle.StandardPixmap.SP_DirOpenIcon,
    "save": QStyle.StandardPixmap.SP_DialogSaveButton,
    "undo": QStyle.StandardPixmap.SP_ArrowBack,
    "redo": QStyle.StandardPixmap.SP_ArrowForward,
    "skip": QStyle.StandardPixmap.SP_ArrowForward,
    "apply": QStyle.StandardPixmap.SP_DialogApplyButton,
    "export": QStyle.StandardPixmap.SP_DialogSaveButton,
    "reset": QStyle.StandardPixmap.SP_BrowserReload,
    "tools": QStyle.StandardPixmap.SP_FileDialogDetailedView,
    "workspace": QStyle.StandardPixmap.SP_FileDialogListView,
    "web": QStyle.StandardPixmap.SP_DriveNetIcon,
    "help": QStyle.StandardPixmap.SP_MessageBoxQuestion,
    "image": QStyle.StandardPixmap.SP_FileIcon,
}


def icon(name: str) -> QIcon:
    """Return a standard Qt icon fallback for a symbolic name."""

    custom = _custom_line_icon(name)
    if not custom.isNull():
        return custom

    app = QApplication.instance()
    if app is None:
        return QIcon()
    style = app.style()
    pix = STANDARD_ICON_MAP.get(name)
    if pix is None:
        return QIcon()
    return style.standardIcon(pix)


def _custom_line_icon(name: str) -> QIcon:
    """Return small studio-shell line icons used by custom navigation tiles."""

    supported = {
        "settings-pixel",
        "settings-color",
        "settings-detail",
        "settings-cleanup",
        "settings-edges",
        "settings-alpha",
        "settings-ai",
        "settings-gif",
        "settings-export",
        "settings-encoding",
    }
    if name not in supported:
        return QIcon()

    pixmap = QPixmap(36, 36)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor("#40555e"), 2.2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    if name == "settings-pixel":
        painter.drawRect(QRectF(9, 9, 18, 18))
        painter.drawLine(15, 9, 15, 27)
        painter.drawLine(21, 9, 21, 27)
        painter.drawLine(9, 15, 27, 15)
        painter.drawLine(9, 21, 27, 21)
    elif name == "settings-color":
        painter.drawEllipse(QRectF(8, 8, 20, 20))
        painter.setBrush(QBrush(QColor("#40555e")))
        for point in (QPointF(15, 14), QPointF(21, 15), QPointF(14, 21)):
            painter.drawEllipse(point, 1.5, 1.5)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(18, 20, 7, 7), 20 * 16, 180 * 16)
    elif name == "settings-detail":
        painter.drawEllipse(QRectF(9, 9, 16, 16))
        painter.drawLine(23, 23, 29, 29)
        painter.drawLine(17, 13, 17, 21)
        painter.drawLine(13, 17, 21, 17)
    elif name == "settings-cleanup":
        painter.drawLine(12, 25, 24, 13)
        painter.drawRect(QRectF(20, 8, 7, 8))
        painter.drawLine(10, 26, 15, 31)
        painter.drawLine(15, 31, 25, 21)
    elif name == "settings-edges":
        dash_pen = QPen(QColor("#40555e"), 2)
        dash_pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(dash_pen)
        painter.drawRect(QRectF(10, 10, 16, 16))
    elif name == "settings-alpha":
        painter.drawEllipse(QRectF(8, 8, 20, 20))
        painter.drawLine(8, 18, 28, 18)
        painter.drawLine(18, 8, 18, 28)
        painter.drawLine(11, 11, 25, 25)
        painter.drawLine(25, 11, 11, 25)
    elif name == "settings-ai":
        painter.drawPolygon(QPolygonF([QPointF(18, 7), QPointF(21, 15), QPointF(29, 18), QPointF(21, 21), QPointF(18, 29), QPointF(15, 21), QPointF(7, 18), QPointF(15, 15)]))
    elif name == "settings-gif":
        painter.drawRect(QRectF(9, 8, 18, 22))
        painter.drawLine(14, 8, 14, 30)
        painter.drawLine(22, 8, 22, 30)
        for y in (12, 18, 24):
            painter.drawPoint(11, y)
            painter.drawPoint(25, y)
    elif name == "settings-export":
        painter.drawRect(QRectF(10, 18, 16, 10))
        painter.drawLine(18, 8, 18, 22)
        painter.drawLine(18, 8, 13, 13)
        painter.drawLine(18, 8, 23, 13)
    elif name == "settings-encoding":
        painter.drawLine(14, 10, 8, 18)
        painter.drawLine(8, 18, 14, 26)
        painter.drawLine(22, 10, 28, 18)
        painter.drawLine(28, 18, 22, 26)
        painter.drawLine(20, 9, 16, 27)

    painter.end()
    return QIcon(pixmap)
