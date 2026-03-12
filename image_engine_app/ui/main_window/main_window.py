"""Main Qt window shell wiring preview/settings/export UI to engine state."""

from __future__ import annotations

from pathlib import Path

from app.settings_store import SessionStore
from app.ui_controller import ImageEngineUIController
from engine.models import AssetRecord, EditMode, SessionState

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QToolButton,
    QMenu,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from engine.ingest.local_ingest import SUPPORTED_FORMATS_BY_EXTENSION
from ui.common.icons import icon
from ui.common.state_bindings import EngineUIState
from ui.main_window.apply_coordinator import ApplyCoordinator
from ui.main_window.asset_tabs import WorkspaceAssetTabs
from ui.main_window.batch_coordinator import BatchCoordinator
from ui.main_window.control_strip import ControlStrip
from ui.main_window.export_bar import ExportBar
from ui.main_window.export_coordinator import ExportCoordinator
from ui.main_window.encoding_coordinator import EncodingCoordinator
from ui.main_window.preview_panel import PreviewPanel
from ui.main_window.presets_bar import PresetsBar
from ui.main_window.settings_panel import SettingsPanel
from ui.main_window.shell_coordinator import ShellCoordinator
from ui.main_window.workspace_coordinator import WorkspaceCoordinator
from ui.main_window.session_coordinator import SessionCoordinator
from ui.main_window.local_import_coordinator import LocalImportCoordinator
from ui.main_window.web_sources_panel import WebSourcesPanel
from ui.main_window.web_sources_coordinator import WebSourcesCoordinator
from ui.windows.batch_manager import BatchManagerDialog
from ui.windows.export_encoding import ExportEncodingDialog
from ui.windows.preset_manager import PresetManagerDialog


class ImageEngineMainWindow(QMainWindow):
    """Prompt 16 main window shell for the Sprite Factory app."""

    MAX_RENDERED_WORKSPACE_TABS = 100

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        controller: ImageEngineUIController | None = None,
        session_store: SessionStore | None = None,
    ) -> None:
        super().__init__(parent)
        self._configure_native_window_chrome()
        self.setWindowTitle("Sprite Factory Pro v1.1.0")
        self.resize(1460, 920)
        self.setMinimumSize(1180, 760)

        self.ui_state = EngineUIState()
        self.controller = controller
        self.session_store = session_store
        self._workspace_assets: list[AssetRecord] = []
        self._batch_thread: object | None = None
        self._batch_worker: object | None = None
        self._batch_dialog_queue_signature: tuple[str, ...] = ()

        self._mode_combo = QComboBox(self)
        self._badge_format = QLabel("FMT: --", self)
        self._badge_alpha = QLabel("Alpha: --", self)
        self._badge_frames = QLabel("Frames: --", self)
        self._page_tabs: QTabWidget | None = None
        self._top_toolbar: QToolBar | None = None
        self._workspace_splitter: QSplitter | None = None
        self._workspace_helper_panel: QWidget | None = None
        self._compact_ui_action: QAction | None = None
        self._compact_ui_enabled = False
        self._helper_tab_index: int | None = None
        self._settings_dock: QDockWidget | None = None
        self._workspace_tab_window_start = 0
        self._workspace_tab_window_size = int(self.MAX_RENDERED_WORKSPACE_TABS)
        self.preview_panel = PreviewPanel(self)
        self.control_strip = ControlStrip(self)
        self.asset_tabs = WorkspaceAssetTabs(self)
        self.presets_bar = PresetsBar(self)
        self.export_bar = ExportBar(self)
        self.settings_panel = SettingsPanel(self)
        self.web_sources_panel = WebSourcesPanel(self)
        self._apply_coordinator = ApplyCoordinator(self)
        self._workspace_coordinator = WorkspaceCoordinator(self)
        self._web_sources_coordinator = WebSourcesCoordinator(self)
        self._shell_coordinator = ShellCoordinator(self)

        self.batch_manager_dialog = BatchManagerDialog(self)
        self._batch_coordinator = BatchCoordinator(self)
        self._session_coordinator = SessionCoordinator(self)
        self._local_import_coordinator = LocalImportCoordinator(self)
        self._export_coordinator = ExportCoordinator(self)
        self.export_encoding_dialog = ExportEncodingDialog(self)
        self._encoding_coordinator = EncodingCoordinator(self)
        self.preset_manager_dialog = PresetManagerDialog(self.controller, self) if self.controller is not None else None

        self._build_ui()
        self._bind_state()

    def set_session(self, session: SessionState | None) -> None:
        """Assign the active session to the UI state."""

        self.ui_state.set_session(session)
        self._sync_export_directory_from_session(session)
        self._sync_workspace_tabs()
        self._sync_batch_dialog_items()

    def set_active_asset(self, asset: AssetRecord | None) -> None:
        """Assign the active asset to the UI state."""

        if asset is not None:
            self._register_assets([asset], set_active=False)
        self.ui_state.set_active_asset(asset)
        self._sync_session_active_asset(asset)
        self._refresh_export_prediction()

    @property
    def workspace_assets(self) -> list[AssetRecord]:
        """Return a shallow copy of current workspace assets for persistence."""

        return list(self._workspace_assets)

    def load_workspace_state(self, session: SessionState, assets: list[AssetRecord]) -> None:
        """Replace the current workspace/session state from a persisted bundle."""

        self._workspace_assets = []
        self._workspace_tab_window_start = 0
        self.set_session(session)
        if assets:
            self._register_assets(list(assets), set_active=False)
            target = None
            if session.active_tab_asset_id:
                target = self._find_workspace_asset(session.active_tab_asset_id)
            if target is None and self._workspace_assets:
                ordered = self._ordered_workspace_assets()
                target = ordered[0] if ordered else self._workspace_assets[0]
            self.ui_state.set_active_asset(target)
            self._sync_session_active_asset(target)
        else:
            self.ui_state.set_active_asset(None)
            self._sync_session_active_asset(None)
        self._sync_batch_dialog_items()
        self._sync_workspace_tabs()
        self._refresh_export_prediction()


    def _configure_native_window_chrome(self) -> None:
        """Force native Windows-like title bar buttons/chrome."""

        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, False)
        self.setWindowFlag(Qt.WindowType.WindowTitleHint, True)
        self.setWindowFlag(Qt.WindowType.WindowSystemMenuHint, True)
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, True)

    def _build_ui(self) -> None:
        self._build_top_toolbar()
        self._build_center_and_dock()
        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("UI shell ready")

    def _build_top_toolbar(self) -> None:
        toolbar = QToolBar("Top Bar", self)
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        self._top_toolbar = toolbar

        # Session/import menus
        self._add_toolbar_menu_button(
            toolbar,
            text="Session",
            icon_name="open",
            actions=self._build_session_menu_actions(),
        )
        self._add_toolbar_menu_button(
            toolbar,
            text="Import",
            icon_name="new",
            actions=self._build_import_menu_actions(),
        )
        toolbar.addSeparator()

        # Mode selector
        mode_label = QLabel("Mode", self)
        toolbar.addWidget(mode_label)
        for mode in EditMode:
            self._mode_combo.addItem(mode.value.title(), userData=mode.value)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_combo_changed)
        toolbar.addWidget(self._mode_combo)

        toolbar.addSeparator()

        # Format badges
        for badge in (self._badge_format, self._badge_alpha, self._badge_frames):
            badge.setStyleSheet(
                "QLabel { border:1px solid #b7ced0; border-radius:6px; padding:3px 8px; background:#ecf6f6; color:#1f4b51; }"
            )
            toolbar.addWidget(badge)

        toolbar.addSeparator()

        # Performance toggles (CPU/GPU)
        perf_group = QActionGroup(self)
        perf_group.setExclusive(True)
        cpu_action = QAction("CPU", self, checkable=True)
        gpu_action = QAction("GPU", self, checkable=True)
        cpu_action.setChecked(True)
        cpu_action.triggered.connect(lambda checked=False: self.ui_state.set_performance_mode("cpu"))
        gpu_action.triggered.connect(lambda checked=False: self.ui_state.set_performance_mode("gpu"))
        perf_group.addAction(cpu_action)
        perf_group.addAction(gpu_action)
        toolbar.addAction(cpu_action)
        toolbar.addAction(gpu_action)

        toolbar.addSeparator()

        # Secondary windows shortcuts
        batch_action = QAction("Batch Manager", self)
        batch_action.triggered.connect(self._show_batch_manager)
        presets_action = QAction("Preset Manager", self)
        if self.preset_manager_dialog is not None:
            presets_action.triggered.connect(self.preset_manager_dialog.show)
        else:
            presets_action.setEnabled(False)
        toolbar.addAction(batch_action)
        toolbar.addAction(presets_action)

        toolbar.addSeparator()
        self._compact_ui_action = QAction("Compact UI", self, checkable=True)
        self._compact_ui_action.toggled.connect(self.set_compact_ui)
        toolbar.addAction(self._compact_ui_action)

        reset_panels_action = QAction("Reset Panels", self)
        reset_panels_action.triggered.connect(self._reset_panels_layout)
        toolbar.addAction(reset_panels_action)

    def _add_toolbar_menu_button(
        self,
        toolbar: QToolBar,
        *,
        text: str,
        icon_name: str,
        actions: list[QAction],
    ) -> None:
        menu = QMenu(self)
        for action in actions:
            menu.addAction(action)

        button = QToolButton(toolbar)
        button.setText(text)
        button.setIcon(icon(icon_name))
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setMenu(menu)
        toolbar.addWidget(button)

    def _build_session_menu_actions(self) -> list[QAction]:
        new_action = QAction(icon("new"), "New Session", self)
        new_action.triggered.connect(self._new_session)

        open_action = QAction(icon("open"), "Open Session", self)
        open_action.triggered.connect(self._open_session_file)

        save_action = QAction(icon("save"), "Save Session", self)
        save_action.triggered.connect(self._save_session_file)

        clear_action = QAction("Clear Session", self)
        clear_action.triggered.connect(self._clear_session)

        sessions_folder_action = QAction("Sessions Folder", self)
        sessions_folder_action.triggered.connect(self._open_sessions_folder)

        return [new_action, open_action, save_action, clear_action, sessions_folder_action]

    def _build_import_menu_actions(self) -> list[QAction]:
        import_files_action = QAction("Import File(s)...", self)
        import_files_action.triggered.connect(self._import_files)

        import_folder_action = QAction("Import Folder...", self)
        import_folder_action.triggered.connect(self._import_folder)

        import_zip_action = QAction("Import ZIP...", self)
        import_zip_action.triggered.connect(self._import_zip_archive)

        return [import_files_action, import_folder_action, import_zip_action]

    def _build_center_and_dock(self) -> None:
        central = QWidget(self)
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(8, 8, 8, 8)
        central_layout.setSpacing(8)

        page_tabs = QTabWidget(central)
        self._page_tabs = page_tabs

        workspace_page = QWidget(page_tabs)
        workspace_layout = QVBoxLayout(workspace_page)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(8)

        # Workspace page (single panel; helper moved to dedicated Helper tab)
        self._workspace_splitter = None
        self._workspace_helper_panel = None

        left_panel = QWidget(workspace_page)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        left_layout.addWidget(self.asset_tabs)
        left_layout.addWidget(self.presets_bar)
        left_layout.addWidget(self.preview_panel, 1)
        left_layout.addWidget(self.control_strip)

        workspace_layout.addWidget(left_panel, 1)
        workspace_layout.addWidget(self.export_bar)
        page_tabs.addTab(workspace_page, "Workspace")
        page_tabs.addTab(self.web_sources_panel, "Web Sources")
        self._helper_tab_index = page_tabs.addTab(self._build_helper_tab_page(page_tabs), "Helper")

        central_layout.addWidget(page_tabs, 1)
        self.setCentralWidget(central)

        # Right docked settings panel (scrollable)
        dock = QDockWidget("Settings", self)
        dock.setObjectName("settingsDock")
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.settings_panel.setMinimumWidth(360)
        dock.setMinimumWidth(360)
        dock.setMaximumWidth(620)
        dock.setWidget(self.settings_panel)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.resizeDocks([dock], [430], Qt.Orientation.Horizontal)
        self._settings_dock = dock

    def _build_helper_tab_page(self, parent: QWidget) -> QWidget:
        page = QWidget(parent)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("Pro Workflow Helper", page)
        title.setStyleSheet("font-size:16px; font-weight:600; color:#0f3338;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Use this guide to understand each part of Sprite Factory Pro before you start editing.",
            page,
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color:#3f5f64;")
        layout.addWidget(subtitle)

        guide = QTextBrowser(page)
        guide.setOpenExternalLinks(False)
        guide.setReadOnly(True)
        guide.setStyleSheet(
            "QTextBrowser { border:1px solid #bfd2d4; border-radius:8px; background:#ffffff; padding:8px; color:#173a40; }"
        )
        guide.setHtml(
            "<h3>Quick Workflow</h3>"
            "<ol>"
            "<li><b>Load assets</b>: open a saved session or download files from <b>Web Sources</b>.</li>"
            f"<li><b>Supported formats</b>: {self._local_extensions_label()}.</li>"
            "<li><b>Tune settings</b>: start in Pixel + Color + Detail, then use Cleanup/Edges only if needed.</li>"
            "<li><b>Preview</b>: compare Before vs Final before exporting.</li>"
            "<li><b>Export</b>: choose profile/format, check predicted size, then export.</li>"
            "</ol>"
            "<h3>Top Toolbar (What Each Control Does)</h3>"
            "<ul>"
            "<li><b>Session menu</b>: New/Open/Save/Clear plus quick access to Sessions Folder.</li>"
            "<li><b>Import menu</b>: import local file(s), folder, or ZIP archives into Workspace.</li>"
            "<li><b>Mode</b>: Simple, Advanced, Expert (unlocks more settings groups).</li>"
            "<li><b>FMT/Alpha/Frames badges</b>: quick readout of active asset type/capabilities.</li>"
            "<li><b>CPU/GPU</b>: processing mode selection.</li>"
            "<li><b>Batch/Presets</b>: advanced workflow windows.</li><li><b>Encoding Window</b>: open from Settings -> Expert Encoding.</li>"
            "</ul>"
            "<h3>Workspace Area</h3>"
            "<ul>"
            "<li><b>Workspace Tabs</b>: every imported image gets a tab."
            " Large batches are split into sections of 100 for stability.</li>"
            "<li><b>Preset dropdown</b>: choose a preset to apply and sync settings controls instantly.</li>"
            "<li><b>Preview panes</b>: Before (source) and Final (output). Zoom is view-only.</li>"
            "<li><b>Apply</b>: commits current light/heavy edits to Final.</li>"
            "<li><b>Export bar</b>: export profile, Export button, folder browse/open actions, Auto-next, predicted output size.</li>"
            "</ul>"
            "<h3>Web Sources Tab</h3>"
            "<ol>"
            "<li>Select Website + Area (or use Custom URL).</li>"
            "<li>Scan links and filter by type (PNG/GIF/WEBP/ZIP).</li>"
            "<li>Select items and choose Save target bucket.</li>"
            "<li>Download selected items into workspace/library.</li>"
            "</ol>"
            "<h3>Settings Groups Explained</h3>"
            "<ul>"
            "<li><b>Pixel and Resolution</b>: real output size, DPI metadata, target width/height, scale method.</li>"
            "<li><b>Color and Light</b>: brightness/contrast/saturation/gamma tone controls.</li>"
            "<li><b>Detail</b>: sharpen/clarity/texture for crispness (use small increments).</li>"
            "<li><b>Cleanup</b>: noise/artifact/halo/banding reduction.</li>"
            "<li><b>Edges</b>: antialias/refine/feather/grow-shrink for edge control.</li>"
            "<li><b>Transparency</b>: alpha smoothing/matte fixes for cutout sprites.</li>"
            "<li><b>AI Enhance</b>: heavier enhancement controls (best used after baseline tuning).</li>"
            "<li><b>GIF Controls</b>: animation delay/palette/loop/optimization (GIF assets only).</li>"
            "<li><b>Export</b>: final quality + metadata behavior.</li>"
            "<li><b>Expert Encoding</b>: advanced compression/chroma/palette tuning.</li>"
            "</ul>"
            "<h3>Recommended Quality Flow</h3>"
            "<ol>"
            "<li>Keep Resize at 100% first, clean/tune details, then resize last.</li>"
            "<li>Use Nearest for pixel-art upscales; Bicubic/Lanczos for smoother icons/sprites.</li>"
            "<li>Adjust controls in small steps (0.05 to 0.25), then re-check Final pane.</li>"
            "<li>Export once quality is stable in Final preview.</li>"
            "</ol>"
            "<h3>Common Pitfalls</h3>"
            "<ul>"
            "<li>Over-sharpening can create crunchy edges and noise.</li>"
            "<li>Large resize first can amplify artifacts; clean first, scale second.</li>"
            "<li>GIF/Transparency groups stay locked when the active asset does not support them.</li>"
            "</ul>"
        )
        layout.addWidget(guide, 1)
        return page
    @staticmethod
    def _supported_local_extensions() -> list[str]:
        return sorted({ext.lower() for ext in SUPPORTED_FORMATS_BY_EXTENSION})

    @classmethod
    def _local_extensions_label(cls) -> str:
        labels = [ext.lstrip(".").upper() for ext in cls._supported_local_extensions()]
        return ", ".join(labels)

    @classmethod
    def _local_file_dialog_filter(cls) -> str:
        patterns = " ".join(f"*{ext}" for ext in cls._supported_local_extensions())
        return f"Supported Images ({patterns});;All Files (*)"

    def _bind_state(self) -> None:
        self.preview_panel.bind_state(self.ui_state)
        self.control_strip.bind_state(self.ui_state)
        self.presets_bar.bind_state(self.ui_state)
        self.export_bar.bind_state(self.ui_state)
        self.settings_panel.bind_state(self.ui_state)
        self.settings_panel.open_encoding_window_requested.connect(self._show_export_encoding_window)
        if self.controller is not None:
            self.presets_bar.set_presets(self.controller.available_preset_names())

        self.ui_state.status_message_changed.connect(self._status)
        self.ui_state.active_asset_changed.connect(self._on_active_asset_changed)
        self.ui_state.mode_changed.connect(self._on_mode_changed)
        self.ui_state.export_profile_changed.connect(lambda _value: self._refresh_export_prediction())
        self.ui_state.apply_requested.connect(self._on_apply_requested)
        self.ui_state.light_preview_requested.connect(self._on_light_preview_requested)
        self.ui_state.export_requested.connect(self._on_export_requested)
        self.export_bar.browse_export_dir_requested.connect(self._on_export_directory_browse_requested)
        self.export_bar.open_export_dir_requested.connect(self._on_export_directory_open_requested)
        self.ui_state.preset_requested.connect(self._on_preset_requested)
        self.ui_state.global_reset_requested.connect(self._on_global_reset_requested)
        self.asset_tabs.asset_selected.connect(self._on_workspace_asset_selected)
        self.asset_tabs.pin_active_requested.connect(self._on_workspace_pin_requested)
        self.asset_tabs.asset_close_requested.connect(self._on_workspace_asset_close_requested)
        self.asset_tabs.window_prev_requested.connect(self._on_workspace_prev_window_requested)
        self.asset_tabs.window_next_requested.connect(self._on_workspace_next_window_requested)
        self.asset_tabs.window_section_requested.connect(self._on_workspace_window_section_requested)
        self.batch_manager_dialog.run_requested.connect(self._on_batch_run_requested)
        self.batch_manager_dialog.cancel_run_requested.connect(self._on_batch_cancel_requested)
        self.export_encoding_dialog.apply_requested.connect(self._on_export_encoding_apply_requested)
        self.web_sources_panel.registry_changed.connect(self._on_web_sources_registry_changed)
        self.web_sources_panel.scan_requested.connect(self._on_web_sources_scan_requested)
        self.web_sources_panel.download_requested.connect(self._on_web_sources_download_requested)
        self.web_sources_panel.network_diagnostics_requested.connect(self._on_web_sources_network_diagnostics_requested)

        if self.preset_manager_dialog is not None and self.controller is not None:
            # Refresh preset chips when the dialog closes (after saves/deletes).
            self.preset_manager_dialog.finished.connect(
                lambda _code=0: self.presets_bar.set_presets(self.controller.available_preset_names())
            )

        self._init_web_sources_panel()

    def _on_mode_combo_changed(self) -> None:
        mode_value = self._mode_combo.currentData()
        if isinstance(mode_value, str):
            self.ui_state.set_mode(mode_value)

    def _on_mode_changed(self, mode_value: str) -> None:
        for idx in range(self._mode_combo.count()):
            if self._mode_combo.itemData(idx) == mode_value:
                self._mode_combo.blockSignals(True)
                self._mode_combo.setCurrentIndex(idx)
                self._mode_combo.blockSignals(False)
                break
        self._status(f"Mode changed to {mode_value}")

    def _on_active_asset_changed(self, asset: object) -> None:
        if asset is None:
            self._badge_format.setText("FMT: --")
            self._badge_alpha.setText("Alpha: --")
            self._badge_frames.setText("Frames: --")
            return

        fmt = getattr(getattr(asset, "format", None), "value", "--")
        caps = getattr(asset, "capabilities", None)
        has_alpha = bool(getattr(caps, "has_alpha", False))
        is_animated = bool(getattr(caps, "is_animated", False))

        self._badge_format.setText(f"FMT: {str(fmt).upper()}")
        self._badge_alpha.setText(f"Alpha: {'Yes' if has_alpha else 'No'}")
        self._badge_frames.setText(f"Frames: {'Animated' if is_animated else 'Static'}")
        asset_id = getattr(asset, "id", None)
        if isinstance(asset_id, str):
            self.asset_tabs.set_active_asset(asset_id)
            if self.asset_tabs.active_asset_id() != asset_id:
                self._sync_workspace_tabs()
        self._refresh_export_prediction()

    def _on_light_preview_requested(self) -> None:
        self._apply_coordinator.on_light_preview_requested()

    def _on_apply_requested(self) -> None:
        self._apply_coordinator.on_apply_requested()

    def _on_preset_requested(self, preset_name: str) -> None:
        self._apply_coordinator.on_preset_requested(preset_name)

    def _on_global_reset_requested(self) -> None:
        self._apply_coordinator.on_global_reset_requested()

    def _on_workspace_asset_selected(self, asset_id: str) -> None:
        self._workspace_coordinator.on_workspace_asset_selected(asset_id)

    def _on_workspace_asset_close_requested(self, asset_id: str) -> None:
        self._workspace_coordinator.on_workspace_asset_close_requested(asset_id)

    def _on_workspace_pin_requested(self, asset_id: str) -> None:
        self._workspace_coordinator.on_workspace_pin_requested(asset_id)

    def _on_workspace_prev_window_requested(self) -> None:
        self._workspace_coordinator.on_workspace_prev_window_requested()

    def _on_workspace_next_window_requested(self) -> None:
        self._workspace_coordinator.on_workspace_next_window_requested()

    def _on_workspace_window_section_requested(self, start_index: int) -> None:
        self._workspace_coordinator.on_workspace_window_section_requested(start_index)


    def _on_export_requested(self) -> None:
        self._export_coordinator.on_export_requested()


    def _sync_export_directory_from_session(self, session: SessionState | None) -> None:
        self._export_coordinator.sync_export_directory_from_session(session)


    def _on_export_directory_browse_requested(self) -> None:
        self._export_coordinator.on_export_directory_browse_requested()

    def _on_export_directory_open_requested(self) -> None:
        self._export_coordinator.on_export_directory_open_requested()

    def _new_session(self) -> None:
        self._session_coordinator.new_session()

    def _save_session_file(self) -> None:
        self._session_coordinator.save_session_file()

    def _open_session_file(self) -> None:
        self._session_coordinator.open_session_file()

    def _open_sessions_folder(self) -> None:
        self._session_coordinator.open_sessions_folder()

    def _clear_session(self) -> None:
        self._session_coordinator.clear_session()

    def _import_files(self) -> None:
        self._local_import_coordinator.import_files()

    def _import_folder(self) -> None:
        self._local_import_coordinator.import_folder()

    def _import_zip_archive(self) -> None:
        self._local_import_coordinator.import_zip_archive()

    def _load_workspace_from_file(self, path: Path, *, source_label: str) -> None:
        self._session_coordinator.load_workspace_from_file(path, source_label=source_label)

    def _show_batch_manager(self) -> None:
        self._batch_coordinator.show_manager()

    def _show_export_encoding_window(self) -> None:
        self._encoding_coordinator.show_export_encoding_window()

    def _on_export_encoding_apply_requested(self, options_obj: object) -> None:
        self._encoding_coordinator.on_export_encoding_apply_requested(options_obj)

    def compact_ui_enabled(self) -> bool:
        return self._shell_coordinator.compact_ui_enabled()

    def set_compact_ui(self, enabled: bool) -> None:
        self._shell_coordinator.set_compact_ui(enabled)

    def _reset_panels_layout(self) -> None:
        self._shell_coordinator.reset_panels_layout()

    def _init_web_sources_panel(self) -> None:
        self._web_sources_coordinator.init_panel()

    def _on_web_sources_registry_changed(self, payload: object) -> None:
        self._web_sources_coordinator.on_registry_changed(payload)

    def _on_web_sources_scan_requested(self, payload: object) -> None:
        self._web_sources_coordinator.on_scan_requested(payload)

    def _on_web_sources_download_requested(self, payload: object) -> None:
        self._web_sources_coordinator.on_download_requested(payload)

    def _on_web_sources_network_diagnostics_requested(self, payload: object) -> None:
        self._web_sources_coordinator.on_network_diagnostics_requested(payload)

    def _on_batch_run_requested(self, options_obj: object) -> None:
        self._batch_coordinator.on_run_requested(options_obj)

    def _on_batch_cancel_requested(self) -> None:
        self._batch_coordinator.on_cancel_requested()

    def _refresh_export_prediction(self) -> None:
        asset = self.ui_state.active_asset
        if asset is None:
            self.ui_state.set_export_prediction_text("Predicted size: --")
            return

        if self.controller is not None:
            text = self.controller.format_prediction_text(asset)
        else:
            text = "Predicted size: --"
        self.ui_state.set_export_prediction_text(text)

    def _status(self, text: str) -> None:
        if self.statusBar() is not None:
            self.statusBar().showMessage(text, 5000)

    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)

    def _register_assets(self, assets: list[AssetRecord], *, set_active: bool) -> None:
        if not assets:
            return

        existing_ids = {asset.id for asset in self._workspace_assets}
        added_assets: list[AssetRecord] = []

        session = self.ui_state.session
        session_tab_ids = set(session.tab_order) if session is not None else set()

        for asset in assets:
            if asset.id in existing_ids:
                continue

            self._workspace_assets.append(asset)
            existing_ids.add(asset.id)
            added_assets.append(asset)

            if session is not None:
                if asset.id not in session_tab_ids:
                    session.tab_order.append(asset.id)
                    session_tab_ids.add(asset.id)
                if session.active_tab_asset_id is None:
                    session.active_tab_asset_id = asset.id
        if set_active:
            target = None
            if added_assets:
                target = added_assets[-1]
                ordered_after_add = self._ordered_workspace_assets()
                target_index = next((idx for idx, item in enumerate(ordered_after_add) if item.id == target.id), None)
                if target_index is not None:
                    max_tabs = max(1, int(self._workspace_tab_window_size))
                    self._workspace_tab_window_start = (target_index // max_tabs) * max_tabs
            elif self.ui_state.active_asset is None and assets:
                target = self._find_workspace_asset(assets[-1].id)

            if target is not None:
                self.ui_state.set_active_asset(target)
                self._sync_session_active_asset(target)

        self._sync_batch_dialog_items()
        self._sync_workspace_tabs()

    def _sync_batch_dialog_items(self) -> None:
        if not hasattr(self, "batch_manager_dialog"):
            return
        items = [
            (asset.id, (asset.original_name or asset.id))
            for asset in self._workspace_assets
        ]
        signature = tuple(asset_id for asset_id, _label in items)
        if signature != self._batch_dialog_queue_signature:
            self.batch_manager_dialog.set_queue_assets(items)
            self._batch_dialog_queue_signature = signature
        if self.controller is not None:
            try:
                self.batch_manager_dialog.set_available_presets(self.controller.available_preset_names())
            except Exception:
                pass
        self.batch_manager_dialog.set_export_directory(self.export_bar.export_directory())


    def _sync_session_active_asset(self, asset: AssetRecord | None) -> None:
        session = self.ui_state.session
        if session is None:
            return
        session.active_tab_asset_id = asset.id if asset is not None else None

    def _sync_workspace_tabs(self) -> None:
        self._workspace_coordinator.sync_workspace_tabs()

    def _ordered_workspace_assets(self) -> list[AssetRecord]:
        return self._workspace_coordinator.ordered_workspace_assets()

    def _find_workspace_asset(self, asset_id: str) -> AssetRecord | None:
        return self._workspace_coordinator.find_workspace_asset(asset_id)















