"""Preview panel with Current/Final panes and live view-only zoom.

This panel now supports only the real app flow: current working preview and
final/export preview. The legacy before pane was temporary and has been fully
removed so the section stays focused and easier to maintain.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtGui import QColor, QImage, QImageReader, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from image_engine_app.ui.common.state_bindings import EngineUIState


@dataclass
class _PaneWidgets:
    title: QLabel
    reset_button: QToolButton
    canvas: QLabel
    scroll: QScrollArea
    overlay: QLabel
    badge: QLabel
    source_path: str | None = None
    source_mtime_ns: int | None = None
    source_size: int | None = None
    qimage: QImage | None = None
    last_render_size: tuple[int, int] = (0, 0)
    zoom_factor: float = 1.0
    auto_follow_zoom: bool = True
    animation_frames: tuple[QImage, ...] = ()
    animation_frame_delays_ms: tuple[int, ...] = ()
    animation_frame_index: int = 0
    animation_timer: QTimer | None = None

class PreviewPanel(QWidget):
    """Preview panel with current/final compare views."""
    VIEW_COMPARE = "compare"
    VIEW_CURRENT = "current"
    VIEW_FINAL = "final"
    MIN_ZOOM = 0.25
    MAX_ZOOM = 16.0
    WHEEL_ZOOM_IN_FACTOR = 1.12

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ui_state: EngineUIState | None = None
        self._panes: dict[str, _PaneWidgets] = {}
        self._pane_grid: QGridLayout | None = None
        self._pane_containers: dict[str, QWidget] = {}
        self._format_badge = QLabel("--", self)
        self._zoom_snap_button = QToolButton(self)
        self._pixel_snap: bool = False
        self._zoom_snap_enabled: bool = True
        self._view_mode: str = self.VIEW_COMPARE
        self._pan_active_key: str | None = None
        self._pan_last_global: tuple[float, float] | None = None
        self._build_ui()

    def preview_view_mode(self) -> str:
        return self._view_mode

    def set_view_mode(self, mode_value: str) -> str:
        mode = str(mode_value or "").strip().lower()
        if mode not in {self.VIEW_COMPARE, self.VIEW_CURRENT, self.VIEW_FINAL}:
            mode = self.VIEW_COMPARE
        if self._view_mode == mode:
            return mode
        self._view_mode = mode
        self._layout_panes()
        self._render_all_panes(rescale_only=False)
        return mode

    def restore_default_view(self) -> None:
        self.set_view_mode(self.VIEW_COMPARE)

    def bind_state(self, ui_state: EngineUIState) -> None:
        """Bind preview panel visuals to the shared UI state object."""

        self._ui_state = ui_state
        ui_state.active_asset_changed.connect(self._on_active_asset_changed)
        ui_state.sync_changed.connect(self._on_sync_changed)
        ui_state.reset_view_requested.connect(self._on_reset_view_requested)
        self._on_sync_changed(ui_state.active_asset.edit_state.sync_current_final if ui_state.active_asset else True)
        self._on_active_asset_changed(ui_state.active_asset)

    def _build_ui(self) -> None:
        self.setObjectName("previewPanelRoot")
        self.setMinimumHeight(460)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        header = QHBoxLayout()
        header.setSpacing(10)

        title = QLabel("Preview Studio", self)
        title.setObjectName("shellTitle")
        header.addWidget(title, 0)

        self._format_badge.setObjectName("shellBadgeAccent")
        header.addWidget(self._format_badge, 0)

        zoom_hint = QLabel("Preview-first workspace. Wheel to zoom; use Reset on either pane to refit.", self)
        zoom_hint.setObjectName("shellHint")
        zoom_hint.setToolTip("Resize changes output size. Zoom is view-only. Crisp On keeps sprite-sized previews sharp at clean zoom steps.")
        header.addWidget(zoom_hint, 0)

        self._zoom_snap_button.setObjectName("shellWarmToggle")
        self._zoom_snap_button.setCheckable(True)
        self._zoom_snap_button.setChecked(True)
        self._zoom_snap_button.setText("Crisp On")
        self._zoom_snap_button.setToolTip("On = crisp nearest-neighbor (best for sprites). Off = smooth zoom rendering.")
        self._zoom_snap_button.toggled.connect(self._on_zoom_snap_toggled)
        header.addWidget(self._zoom_snap_button, 0)

        header.addStretch(1)
        outer.addLayout(header)

        panel_frame = QFrame(self)
        panel_frame.setFrameShape(QFrame.Shape.StyledPanel)
        panel_frame.setObjectName("previewPanelFrame")
        panel_frame.setMinimumHeight(400)
        grid = QGridLayout(panel_frame)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setHorizontalSpacing(0)
        grid.setVerticalSpacing(8)

        self._pane_grid = grid

        self._panes["current"] = self._create_pane("Current")
        self._panes["final"] = self._create_pane("Final")

        self._pane_containers["current"] = self._pane_container(self._panes["current"])
        self._pane_containers["final"] = self._pane_container(self._panes["final"])
        self._layout_panes()

        outer.addWidget(panel_frame, 1)

    def _create_pane(self, title: str) -> _PaneWidgets:
        title_label = QLabel(title, self)
        title_label.setObjectName("shellTitle")

        reset_button = QToolButton(self)
        reset_button.setObjectName("previewPaneResetButton")
        reset_button.setText("Reset")
        reset_button.setToolTip(f"Reset the {title.lower()} preview back to fit view.")

        canvas = QLabel("No image", self)
        canvas.setObjectName("previewCanvas")
        canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        canvas.setMinimumSize(240, 240)
        canvas.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        canvas.setFrameShape(QFrame.Shape.Box)
        canvas.setScaledContents(False)

        scroll = QScrollArea(self)
        scroll.setWidget(canvas)
        scroll.setWidgetResizable(False)
        scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMinimumHeight(380)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Wheel zoom + drag pan events are captured from both viewport and label.
        scroll.viewport().installEventFilter(self)
        canvas.installEventFilter(self)

        overlay = QLabel("WxH: -- | Scale: -- | Zoom: 100%", self)
        overlay.setObjectName("shellHint")

        badge = QLabel("ANIM", self)
        badge.setObjectName("previewAnimBadge")
        badge.setVisible(False)

        pane = _PaneWidgets(title=title_label, reset_button=reset_button, canvas=canvas, scroll=scroll, overlay=overlay, badge=badge)
        reset_button.clicked.connect(lambda _checked=False, p=pane: self._reset_pane_view(p))
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda p=pane: self._advance_animation_frame(p))
        pane.animation_timer = timer
        return pane

    def _pane_container(self, pane: _PaneWidgets) -> QFrame:
        container = QFrame(self)
        container.setObjectName("previewPaneContainer")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(4)
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)
        header_row.addWidget(pane.title, 1)
        header_row.addWidget(pane.reset_button, 0)
        layout.addLayout(header_row)
        canvas_stack = QWidget(container)
        stack_layout = QGridLayout(canvas_stack)
        stack_layout.setContentsMargins(0, 0, 0, 0)
        stack_layout.setSpacing(0)
        stack_layout.addWidget(pane.scroll, 0, 0)
        stack_layout.addWidget(
            pane.badge,
            0,
            0,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
        )
        layout.addWidget(canvas_stack, 1)
        layout.addWidget(pane.overlay)
        return container

    def _layout_panes(self) -> None:
        if self._pane_grid is None:
            return

        if self._view_mode == self.VIEW_CURRENT:
            order = ("current",)
        elif self._view_mode == self.VIEW_FINAL:
            order = ("final",)
        else:
            order = ("current", "final")

        for container in self._pane_containers.values():
            self._pane_grid.removeWidget(container)
            container.setVisible(False)
        self._pane_grid.setColumnStretch(0, 0)
        self._pane_grid.setColumnStretch(1, 0)

        for col, key in enumerate(order):
            container = self._pane_containers.get(key)
            if container is None:
                continue
            container.setVisible(True)
            self._pane_grid.addWidget(container, 0, col)
            self._pane_grid.setColumnStretch(col, 1)

        self._update_pane_dividers(order)

    def _update_pane_dividers(self, order: tuple[str, ...]) -> None:
        count = len(order)
        for idx, key in enumerate(order):
            container = self._pane_containers.get(key)
            if container is None:
                continue
            border = "none" if idx == (count - 1) else "1px solid #bfd2d4"
            container.setStyleSheet(
                f"QFrame#previewPaneContainer {{ border-right: {border}; }}"
            )

    def _on_sync_changed(self, enabled: bool) -> None:
        _ = enabled
        # Sync still matters to edit behavior, but the preview layout is now fixed to Current + Final.
        self._layout_panes()

    def _on_zoom_snap_toggled(self, enabled: bool) -> None:
        self._zoom_snap_enabled = bool(enabled)
        self._zoom_snap_button.setText("Crisp On" if self._zoom_snap_enabled else "Crisp Off")
        self._render_all_panes(rescale_only=False)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        self._render_all_panes(rescale_only=True)

    def eventFilter(self, watched: object, event: object) -> bool:
        key = self._pane_key_for_widget(watched)
        if key is None:
            return super().eventFilter(watched, event)

        pane = self._panes[key]

        if event.type() == QEvent.Type.Wheel:
            delta = event.angleDelta().y()
            if delta == 0:
                return True
            factor = self.WHEEL_ZOOM_IN_FACTOR if delta > 0 else (1.0 / self.WHEEL_ZOOM_IN_FACTOR)
            self._set_pane_zoom(pane, pane.zoom_factor * factor, manual=True)
            return True

        if event.type() == QEvent.Type.MouseButtonDblClick:
            self._reset_pane_view(pane)
            return True

        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton and pane.zoom_factor > 1.0:
                pos = event.globalPosition()
                self._pan_active_key = key
                self._pan_last_global = (float(pos.x()), float(pos.y()))
                self._refresh_pan_cursor(pane)
                return True

        if event.type() == QEvent.Type.MouseMove:
            if self._pan_active_key == key and self._pan_last_global is not None:
                pos = event.globalPosition()
                prev_x, prev_y = self._pan_last_global
                dx = float(pos.x()) - prev_x
                dy = float(pos.y()) - prev_y
                self._pan_last_global = (float(pos.x()), float(pos.y()))

                hbar = pane.scroll.horizontalScrollBar()
                vbar = pane.scroll.verticalScrollBar()
                hbar.setValue(hbar.value() - int(round(dx)))
                vbar.setValue(vbar.value() - int(round(dy)))
                return True

        if event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton and self._pan_active_key == key:
                self._pan_active_key = None
                self._pan_last_global = None
                self._refresh_pan_cursor(pane)
                return True

        return super().eventFilter(watched, event)

    def _pane_key_for_widget(self, watched: object) -> str | None:
        panes = getattr(self, "_panes", None)
        if not isinstance(panes, dict):
            return None
        for key, pane in panes.items():
            if watched is pane.canvas or watched is pane.scroll.viewport():
                return key
        return None

    def _refresh_pan_cursor(self, pane: _PaneWidgets) -> None:
        viewport = pane.scroll.viewport()
        active_zoom = pane.zoom_factor if not pane.auto_follow_zoom else 1.0
        if active_zoom > 1.0:
            if self._pan_active_key is not None:
                viewport.setCursor(Qt.CursorShape.ClosedHandCursor)
            else:
                viewport.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            viewport.unsetCursor()

    def _set_pane_zoom(
        self,
        pane: _PaneWidgets,
        zoom_factor: float,
        *,
        manual: bool = False,
        auto_follow: bool | None = None,
    ) -> None:
        pane.zoom_factor = max(self.MIN_ZOOM, min(self.MAX_ZOOM, float(zoom_factor)))
        if auto_follow is not None:
            pane.auto_follow_zoom = bool(auto_follow)
        elif manual:
            pane.auto_follow_zoom = False
        self._refresh_pan_cursor(pane)
        self._render_pane("", pane, rescale_only=False)

    def _on_reset_view_requested(self) -> None:
        self._reset_all_views()

    def _reset_pane_view(self, pane: _PaneWidgets) -> None:
        pane.zoom_factor = 1.0
        pane.auto_follow_zoom = True
        self._refresh_pan_cursor(pane)
        self._render_pane("", pane, rescale_only=False)

    def _reset_all_views(self) -> None:
        self._pan_active_key = None
        self._pan_last_global = None
        for pane in self._panes.values():
            self._reset_pane_view(pane)

    def _on_active_asset_changed(self, asset: object) -> None:
        if asset is None:
            self._format_badge.setText("--")
            self._format_badge.setToolTip("Format: unavailable")
            for pane in self._panes.values():
                self._clear_pane(pane)
            return

        fmt = getattr(getattr(asset, "format", None), "value", "--")
        self._format_badge.setText(str(fmt).upper())
        self._format_badge.setToolTip(f"Format: {str(fmt).upper()}")

        pixel_settings = getattr(getattr(getattr(asset, "edit_state", None), "settings", None), "pixel", None)
        self._pixel_snap = bool(getattr(pixel_settings, "pixel_snap", False))

        for key, pane in self._panes.items():
            source_path = self._resolve_preview_path_for_view(asset, key)
            self._set_pane_source(pane, source_path)

        self._update_animation_badges(asset)
        self._render_all_panes(rescale_only=False)

    def _update_animation_badges(self, asset: object) -> None:
        """Show an animation badge when any pane has an animated source."""

        is_anim = bool(getattr(getattr(asset, "capabilities", None), "is_animated", False))

        for pane in self._panes.values():
            show = is_anim or (len(pane.animation_frames) > 1)
            if show:
                pane.badge.setText("ANIM")
                pane.badge.setVisible(True)
            else:
                pane.badge.setVisible(False)

    def _resolve_preview_path(self, asset: object) -> Path | None:
        """Return a local file path suitable for QImageReader, if available."""

        cache = getattr(asset, "cache_path", None)
        if isinstance(cache, str) and cache.strip():
            candidate = Path(cache)
            if candidate.exists():
                return candidate

        uri = getattr(asset, "source_uri", None)
        if isinstance(uri, str) and uri.strip():
            candidate = Path(uri)
            if candidate.exists():
                return candidate

        return None

    def _set_pane_source(self, pane: _PaneWidgets, path: Path | None) -> None:
        new_path = str(path) if path is not None else None
        mtime_ns: int | None = None
        size: int | None = None
        if path is not None:
            try:
                stat = path.stat()
                mtime_ns = int(stat.st_mtime_ns)
                size = int(stat.st_size)
            except OSError:
                mtime_ns = None
                size = None

        same_source = pane.source_path == new_path
        same_signature = pane.source_mtime_ns == mtime_ns and pane.source_size == size
        if same_source and same_signature and pane.qimage is not None:
            return

        preserve_zoom = pane.qimage is not None and ((not pane.auto_follow_zoom) or same_source)

        self._stop_animation(pane)

        pane.source_path = new_path
        pane.source_mtime_ns = mtime_ns
        pane.source_size = size

        if path is not None:
            image, anim_frames, anim_delays = self._load_image_source(path)
        else:
            image, anim_frames, anim_delays = (None, (), ())

        pane.qimage = image
        pane.animation_frames = anim_frames
        pane.animation_frame_delays_ms = anim_delays
        pane.animation_frame_index = 0

        pane.last_render_size = (0, 0)
        if not preserve_zoom:
            pane.zoom_factor = 1.0
            pane.auto_follow_zoom = True

        if len(pane.animation_frames) > 1:
            pane.qimage = pane.animation_frames[0]
            self._start_animation(pane)

        self._refresh_pan_cursor(pane)

    @staticmethod
    def _transform_mode_for_scale(
        *,
        pixel_snap: bool,
        zoom_snap_enabled: bool,
        effective_scale: float,
        source_extent: int = 0,
    ) -> Qt.TransformationMode:
        if pixel_snap:
            return Qt.TransformationMode.FastTransformation
        if not zoom_snap_enabled:
            return Qt.TransformationMode.SmoothTransformation
        if effective_scale < 1.0:
            return Qt.TransformationMode.SmoothTransformation
        if source_extent > 256:
            return Qt.TransformationMode.SmoothTransformation
        if abs(effective_scale - round(effective_scale)) <= 0.01:
            return Qt.TransformationMode.FastTransformation
        return Qt.TransformationMode.SmoothTransformation

    @staticmethod
    def _load_image_source(path: Path) -> tuple[QImage | None, tuple[QImage, ...], tuple[int, ...]]:
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)

        first = reader.read()
        if first.isNull():
            return None, (), ()

        if not reader.supportsAnimation():
            return first, (), ()

        frames: list[QImage] = [first.copy()]

        def _delay_or_default(raw_delay: object) -> int:
            try:
                value = int(raw_delay)
            except Exception:
                value = 0
            return max(20, value if value > 0 else 100)

        delays: list[int] = [_delay_or_default(reader.nextImageDelay())]

        max_frames = 120
        for _ in range(max_frames - 1):
            nxt = reader.read()
            if nxt.isNull():
                break
            frames.append(nxt.copy())
            delays.append(_delay_or_default(reader.nextImageDelay()))

        if len(frames) <= 1:
            return first, (), ()

        return frames[0], tuple(frames), tuple(delays)

    def _stop_animation(self, pane: _PaneWidgets) -> None:
        timer = pane.animation_timer
        if timer is not None and timer.isActive():
            timer.stop()
        pane.animation_frames = ()
        pane.animation_frame_delays_ms = ()
        pane.animation_frame_index = 0

    def _start_animation(self, pane: _PaneWidgets) -> None:
        if len(pane.animation_frames) <= 1:
            return
        pane.animation_frame_index = 0
        pane.qimage = pane.animation_frames[0]
        self._schedule_next_animation_frame(pane)

    def _schedule_next_animation_frame(self, pane: _PaneWidgets) -> None:
        timer = pane.animation_timer
        if timer is None:
            return
        delays = pane.animation_frame_delays_ms
        if not delays:
            delay_ms = 100
        else:
            idx = min(max(int(pane.animation_frame_index), 0), len(delays) - 1)
            delay_ms = int(delays[idx])
        timer.start(max(20, delay_ms))

    def _advance_animation_frame(self, pane: _PaneWidgets) -> None:
        frames = pane.animation_frames
        if len(frames) <= 1:
            return
        pane.animation_frame_index = (int(pane.animation_frame_index) + 1) % len(frames)
        pane.qimage = frames[pane.animation_frame_index]
        self._render_pane("", pane, rescale_only=False)
        self._schedule_next_animation_frame(pane)

    def _clear_pane(self, pane: _PaneWidgets) -> None:
        self._stop_animation(pane)
        pane.source_path = None
        pane.source_mtime_ns = None
        pane.source_size = None
        pane.qimage = None
        pane.last_render_size = (0, 0)
        pane.zoom_factor = 1.0
        pane.auto_follow_zoom = True
        pane.canvas.clear()
        pane.canvas.setText("No image")
        pane.canvas.setFixedSize(180, 180)
        pane.overlay.setText("WxH: -- | Scale: -- | Zoom: 100%")
        self._refresh_pan_cursor(pane)

    def _render_all_panes(self, *, rescale_only: bool) -> None:
        for key, pane in self._panes.items():
            self._render_pane(key, pane, rescale_only=rescale_only)

    def _render_pane(self, key: str, pane: _PaneWidgets, *, rescale_only: bool) -> None:
        _ = key
        if pane.qimage is None:
            pane.canvas.clear()
            pane.canvas.setText("No image")
            pane.canvas.setFixedSize(180, 180)
            pane.overlay.setText("WxH: -- | Scale: -- | Zoom: 100%")
            pane.badge.setVisible(False)
            self._refresh_pan_cursor(pane)
            return

        viewport = pane.scroll.viewport()
        w = max(1, int(viewport.width()))
        h = max(1, int(viewport.height()))
        if rescale_only and pane.last_render_size == (w, h):
            return

        pane.last_render_size = (w, h)

        orig_w = int(pane.qimage.width())
        orig_h = int(pane.qimage.height())
        if orig_w <= 0 or orig_h <= 0:
            pane.canvas.clear()
            pane.canvas.setText("No image")
            pane.overlay.setText("WxH: -- | Scale: -- | Zoom: 100%")
            self._refresh_pan_cursor(pane)
            return

        fit_scale = min(w / orig_w, h / orig_h)
        # Auto-fit should downscale oversized images but avoid auto-upscaling tiny sprites.
        base_scale = min(1.0, fit_scale)
        display_zoom = 1.0 if pane.auto_follow_zoom else pane.zoom_factor
        effective_scale = max(0.01, base_scale * display_zoom)

        # For sprite-sized previews, crisp zoom works best at clean integer magnification.
        if self._zoom_snap_enabled and max(orig_w, orig_h) <= 256 and effective_scale >= 1.0:
            if not pane.auto_follow_zoom:
                effective_scale = max(1.0, float(round(effective_scale)))
            else:
                effective_scale = max(1.0, effective_scale)

        target_w = max(1, int(round(orig_w * effective_scale)))
        target_h = max(1, int(round(orig_h * effective_scale)))

        transform = self._transform_mode_for_scale(
            pixel_snap=self._pixel_snap,
            zoom_snap_enabled=self._zoom_snap_enabled,
            effective_scale=effective_scale,
            source_extent=max(orig_w, orig_h),
        )

        scaled = pane.qimage.scaled(
            target_w,
            target_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            transform,
        )
        pane.canvas.setPixmap(QPixmap.fromImage(self._compose_preview_surface(scaled)))
        pane.canvas.setText("")
        pane.canvas.setFixedSize(scaled.width(), scaled.height())

        view_w = int(scaled.width())
        view_h = int(scaled.height())
        scale_pct = min(view_w / orig_w, view_h / orig_h) * 100.0

        zoom_mode = "auto" if pane.auto_follow_zoom else "manual"
        pane.overlay.setText(
            f"WxH: {orig_w}x{orig_h} | View: {view_w}x{view_h} ({scale_pct:.0f}%) | Zoom: {display_zoom * 100.0:.0f}% ({zoom_mode})"
        )
        self._refresh_pan_cursor(pane)

    @classmethod
    def _compose_preview_surface(cls, image: QImage) -> QImage:
        if image.isNull() or not image.hasAlphaChannel():
            return image

        composed = cls._checkerboard_surface(image.width(), image.height())
        painter = QPainter(composed)
        painter.drawImage(0, 0, image)
        painter.end()
        return composed

    @staticmethod
    def _checkerboard_surface(width: int, height: int, *, cell_size: int = 8) -> QImage:
        surface = QImage(max(1, width), max(1, height), QImage.Format.Format_ARGB32_Premultiplied)
        painter = QPainter(surface)
        light = QColor("#f7fbfb")
        dark = QColor("#dde8ea")
        for top in range(0, surface.height(), cell_size):
            for left in range(0, surface.width(), cell_size):
                fill = light if ((left // cell_size) + (top // cell_size)) % 2 == 0 else dark
                painter.fillRect(left, top, cell_size, cell_size, fill)
        painter.end()
        return surface

    def _resolve_preview_path_for_view(self, asset: object, view_key: str) -> Path | None:
        """Resolve the best local preview path for the current/final preview flow."""

        source_path = self._resolve_preview_path(asset)

        if view_key == "current":
            candidates = (
                getattr(asset, "derived_current_path", None),
                source_path,
                getattr(asset, "derived_final_path", None),
            )
        else:
            candidates = (
                getattr(asset, "derived_final_path", None),
                getattr(asset, "derived_current_path", None),
                source_path,
            )

        for candidate in candidates:
            if isinstance(candidate, Path):
                if candidate.exists() and candidate.is_file():
                    return candidate
                continue
            if isinstance(candidate, str) and candidate:
                try:
                    path = Path(candidate)
                    if path.exists() and path.is_file():
                        return path
                except Exception:
                    continue

        return source_path




















