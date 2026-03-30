"""Main Qt window shell wiring preview/settings/export UI to engine state."""

from __future__ import annotations

from pathlib import Path

from image_engine_app.app.settings_store import SessionStore
from image_engine_app.app.ui_controller import ImageEngineUIController
from image_engine_app.engine.models import AssetRecord, EditMode, SessionState

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTextBrowser,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from image_engine_app.engine.ingest.local_ingest import SUPPORTED_FORMATS_BY_EXTENSION
from image_engine_app.ui.common.icons import icon
from image_engine_app.ui.common.state_bindings import EngineUIState
from image_engine_app.ui.main_window.apply_coordinator import ApplyCoordinator
from image_engine_app.ui.main_window.asset_tabs import WorkspaceAssetTabs
from image_engine_app.ui.main_window.batch_coordinator import BatchCoordinator
from image_engine_app.ui.main_window.control_strip import ControlStrip
from image_engine_app.ui.main_window.export_bar import ExportBar
from image_engine_app.ui.main_window.export_coordinator import ExportCoordinator
from image_engine_app.ui.main_window.encoding_coordinator import EncodingCoordinator
from image_engine_app.ui.main_window.preview_panel import PreviewPanel
from image_engine_app.ui.main_window.presets_bar import PresetsBar
from image_engine_app.ui.main_window.settings_panel import SettingsPanel
from image_engine_app.ui.main_window.shell_coordinator import ShellCoordinator
from image_engine_app.ui.main_window.workspace_coordinator import WorkspaceCoordinator
from image_engine_app.ui.main_window.session_coordinator import SessionCoordinator
from image_engine_app.ui.main_window.local_import_coordinator import LocalImportCoordinator
from image_engine_app.ui.main_window.web_sources_panel import WebSourcesPanel
from image_engine_app.ui.main_window.web_sources_coordinator import WebSourcesCoordinator
from image_engine_app.ui.windows.batch_manager import BatchManagerDialog
from image_engine_app.ui.windows.export_encoding import ExportEncodingDialog
from image_engine_app.ui.windows.preset_manager import PresetManagerDialog


class ImageEngineMainWindow(QMainWindow):
    """Prompt 16 main window shell for the Sprite Factory app."""

    MAX_RENDERED_WORKSPACE_TABS = 100
    DEFAULT_WORKSPACE_RAIL_WIDTH = 248
    DEFAULT_WORKSPACE_INSPECTOR_WIDTH = 328

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        controller: ImageEngineUIController | None = None,
        session_store: SessionStore | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("imageEngineMainWindow")
        self._configure_native_window_chrome()
        self.setWindowTitle("Sprite Factory Pro v1.2.0")
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
        self._badge_format = QLabel("--", self)
        self._badge_alpha = QLabel("A-", self)
        self._badge_frames = QLabel("1F", self)
        self._page_tabs: QTabWidget | None = None
        self._top_toolbar: QToolBar | None = None
        self._workspace_splitter: QSplitter | None = None
        self._workspace_editor_splitter: QSplitter | None = None
        self._workspace_left_panel: QFrame | None = None
        self._workspace_inspector_panel: QFrame | None = None
        self._compact_ui_action: QAction | None = None
        self._compact_ui_enabled = False
        self._preview_compare_action: QAction | None = None
        self._preview_current_action: QAction | None = None
        self._preview_final_action: QAction | None = None
        self._cpu_action: QAction | None = None
        self._gpu_action: QAction | None = None
        self._helper_tab_index: int | None = None
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
        self._build_center_shell()
        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("UI shell ready")

    def _build_top_toolbar(self) -> None:
        toolbar = QToolBar("Top Bar", self)
        toolbar.setObjectName("shellTopToolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toolbar.setIconSize(QSize(14, 14))
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        self._top_toolbar = toolbar

        self._add_toolbar_brand_lockup(toolbar)
        toolbar.addSeparator()

        # Session/import menus
        self._add_toolbar_menu_button(
            toolbar,
            text="Session",
            icon_name=None,
            actions=self._build_session_menu_actions(),
        )
        self._add_toolbar_menu_button(
            toolbar,
            text="Import",
            icon_name=None,
            actions=self._build_import_menu_actions(),
        )
        toolbar.addSeparator()

        # Mode selector
        mode_label = QLabel("Mode", toolbar)
        mode_label.setObjectName("toolbarLabel")
        toolbar.addWidget(mode_label)
        self._mode_combo.setObjectName("toolbarModeCombo")
        self._mode_combo.setMinimumContentsLength(6)
        self._mode_combo.setMaximumWidth(108)
        self._mode_combo.setToolTip("Edit mode")
        for mode in EditMode:
            self._mode_combo.addItem(mode.value.title(), userData=mode.value)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_combo_changed)
        toolbar.addWidget(self._mode_combo)

        toolbar.addSeparator()

        # Format badges
        for badge in (self._badge_format, self._badge_alpha, self._badge_frames):
            badge.setObjectName("toolbarBadge")
            toolbar.addWidget(badge)

        toolbar.addSeparator()
        self._build_toolbar_performance_section(toolbar)

        toolbar.addSeparator()
        toolbar.addWidget(self.presets_bar)
        toolbar.addSeparator()
        self._add_toolbar_spacer(toolbar)

        batch_action = QAction("Batch", self)
        batch_action.triggered.connect(self._show_batch_manager)
        presets_action = QAction("Presets", self)
        if self.preset_manager_dialog is not None:
            presets_action.triggered.connect(self.preset_manager_dialog.show)
        else:
            presets_action.setEnabled(False)
        toolbar.addAction(batch_action)
        toolbar.addAction(presets_action)

        toolbar.addSeparator()
        self._compact_ui_action = QAction("Compact UI", self, checkable=True)
        self._compact_ui_action.toggled.connect(self.set_compact_ui)
        self._add_toolbar_popup_menu_button(
            toolbar,
            text="View",
            menu=self._build_view_menu(),
            tooltip="View options",
        )

    def _build_toolbar_performance_section(self, toolbar: QToolBar) -> None:
        perf_group = QActionGroup(self)
        perf_group.setExclusive(True)
        self._cpu_action = QAction("CPU", self, checkable=True)
        self._gpu_action = QAction("GPU", self, checkable=True)
        self._cpu_action.setToolTip("CPU heavy processing")
        self._gpu_action.setToolTip("GPU heavy processing")
        self._cpu_action.setChecked(True)
        self._cpu_action.triggered.connect(lambda checked=False: self.set_performance_mode("cpu"))
        self._gpu_action.triggered.connect(lambda checked=False: self.set_performance_mode("gpu"))
        perf_group.addAction(self._cpu_action)
        perf_group.addAction(self._gpu_action)
        toolbar.addAction(self._cpu_action)
        toolbar.addAction(self._gpu_action)

    def _build_view_menu(self) -> QMenu:
        preview_group = QActionGroup(self)
        preview_group.setExclusive(True)
        self._preview_compare_action = QAction("Compare View", self, checkable=True)
        self._preview_current_action = QAction("Current Only", self, checkable=True)
        self._preview_final_action = QAction("Final Only", self, checkable=True)
        for action in (
            self._preview_compare_action,
            self._preview_current_action,
            self._preview_final_action,
        ):
            preview_group.addAction(action)
        self._preview_compare_action.triggered.connect(lambda _checked=False: self._set_preview_view_mode(PreviewPanel.VIEW_COMPARE))
        self._preview_current_action.triggered.connect(lambda _checked=False: self._set_preview_view_mode(PreviewPanel.VIEW_CURRENT))
        self._preview_final_action.triggered.connect(lambda _checked=False: self._set_preview_view_mode(PreviewPanel.VIEW_FINAL))
        self._sync_preview_view_actions()

        reset_panels_action = QAction("Reset Shell", self)
        reset_panels_action.triggered.connect(self._reset_panels_layout)
        view_menu = QMenu(self)
        view_menu.addAction(self._preview_compare_action)
        view_menu.addAction(self._preview_current_action)
        view_menu.addAction(self._preview_final_action)
        view_menu.addSeparator()
        view_menu.addAction(self._compact_ui_action)
        view_menu.addSeparator()
        view_menu.addAction(reset_panels_action)
        return view_menu

    def _add_toolbar_brand_lockup(self, toolbar: QToolBar) -> None:
        brand = QFrame(toolbar)
        brand.setObjectName("toolbarBrandLockup")
        layout = QHBoxLayout(brand)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)

        mark = QLabel("SF", brand)
        mark.setObjectName("toolbarBrandMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(28, 28)
        layout.addWidget(mark, 0, Qt.AlignmentFlag.AlignVCenter)

        text_wrap = QWidget(brand)
        text_layout = QVBoxLayout(text_wrap)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(0)

        title = QLabel("Sprite Factory Pro", text_wrap)
        title.setObjectName("toolbarBrandTitle")
        subtitle = QLabel("Sprite editing and batch export", text_wrap)
        subtitle.setObjectName("toolbarBrandSubtitle")
        text_layout.addWidget(title)
        text_layout.addWidget(subtitle)
        layout.addWidget(text_wrap, 0, Qt.AlignmentFlag.AlignVCenter)

        toolbar.addWidget(brand)

    def _add_toolbar_menu_button(
        self,
        toolbar: QToolBar,
        *,
        text: str,
        icon_name: str | None,
        actions: list[QAction],
        tooltip: str | None = None,
    ) -> None:
        menu = QMenu(self)
        for action in actions:
            menu.addAction(action)

        button = QToolButton(toolbar)
        button.setObjectName("toolbarMenuButton")
        button.setText(text)
        if icon_name:
            button.setIcon(icon(icon_name))
            button.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonIconOnly
                if not text
                else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            )
        else:
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setMenu(menu)
        button.setToolTip(tooltip or text)
        toolbar.addWidget(button)

    def _add_toolbar_popup_menu_button(
        self,
        toolbar: QToolBar,
        *,
        text: str,
        menu: QMenu,
        tooltip: str | None = None,
    ) -> None:
        button = QToolButton(toolbar)
        button.setObjectName("toolbarMenuButton")
        button.setText(text)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setMenu(menu)
        button.setToolTip(tooltip or text)
        toolbar.addWidget(button)

    @staticmethod
    def _add_toolbar_spacer(toolbar: QToolBar) -> None:
        spacer = QWidget(toolbar)
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

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

    def _build_center_shell(self) -> None:
        central = QWidget(self)
        central.setObjectName("mainShellCentral")
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(10, 10, 10, 10)
        central_layout.setSpacing(10)

        page_tabs = QTabWidget(central)
        page_tabs.setObjectName("shellPageTabs")
        self._page_tabs = page_tabs

        workspace_page = QWidget(page_tabs)
        workspace_page.setObjectName("workspacePage")
        workspace_layout = QVBoxLayout(workspace_page)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(10)

        workspace_splitter = QSplitter(Qt.Orientation.Horizontal, workspace_page)
        workspace_splitter.setObjectName("workspaceShellSplitter")
        workspace_splitter.setChildrenCollapsible(False)
        workspace_splitter.setHandleWidth(10)

        left_shell = QFrame(workspace_splitter)
        left_shell.setObjectName("workspaceRailShell")
        left_shell.setMinimumWidth(208)
        left_shell.setMaximumWidth(312)
        left_layout = QVBoxLayout(left_shell)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(10)
        left_layout.addWidget(self.asset_tabs, 1)
        self._workspace_left_panel = left_shell

        editor_shell = QFrame(workspace_splitter)
        editor_shell.setObjectName("workspaceEditorShell")
        editor_shell.setMinimumWidth(700)
        editor_layout = QVBoxLayout(editor_shell)
        editor_layout.setContentsMargins(10, 10, 10, 10)
        editor_layout.setSpacing(10)

        editor_splitter = QSplitter(Qt.Orientation.Vertical, editor_shell)
        editor_splitter.setChildrenCollapsible(False)
        editor_splitter.setHandleWidth(10)
        editor_splitter.setObjectName("workspaceEditorSplitter")

        preview_shell = QFrame(editor_splitter)
        preview_shell.setObjectName("workspacePreviewStage")
        preview_layout = QVBoxLayout(preview_shell)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)
        preview_layout.addWidget(self.preview_panel)

        action_shell = QFrame(editor_splitter)
        action_shell.setObjectName("workspaceActionShelf")
        action_layout = QVBoxLayout(action_shell)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(10)
        action_layout.addWidget(self.control_strip)
        action_layout.addWidget(self.export_bar)

        editor_splitter.addWidget(preview_shell)
        editor_splitter.addWidget(action_shell)
        editor_splitter.setStretchFactor(0, 6)
        editor_splitter.setStretchFactor(1, 1)
        editor_splitter.setSizes([760, 220])
        self._workspace_editor_splitter = editor_splitter
        editor_layout.addWidget(editor_splitter, 1)

        inspector_shell = QFrame(workspace_splitter)
        inspector_shell.setObjectName("workspaceInspectorShell")
        inspector_shell.setMinimumWidth(296)
        inspector_shell.setMaximumWidth(430)
        inspector_layout = QVBoxLayout(inspector_shell)
        inspector_layout.setContentsMargins(10, 10, 10, 10)
        inspector_layout.setSpacing(0)
        inspector_layout.addWidget(self.settings_panel, 1)
        self._workspace_inspector_panel = inspector_shell

        workspace_splitter.addWidget(left_shell)
        workspace_splitter.addWidget(editor_shell)
        workspace_splitter.addWidget(inspector_shell)
        workspace_splitter.setStretchFactor(0, 0)
        workspace_splitter.setStretchFactor(1, 1)
        workspace_splitter.setStretchFactor(2, 0)
        workspace_splitter.setCollapsible(0, False)
        workspace_splitter.setCollapsible(1, False)
        workspace_splitter.setCollapsible(2, True)
        workspace_splitter.setSizes(self._default_workspace_splitter_sizes())
        self._workspace_splitter = workspace_splitter

        workspace_layout.addWidget(workspace_splitter, 1)
        page_tabs.addTab(workspace_page, "Workspace")
        page_tabs.addTab(self.web_sources_panel, "Web Sources")
        self._helper_tab_index = page_tabs.addTab(self._build_helper_tab_page(page_tabs), "Helper")

        central_layout.addWidget(page_tabs, 1)
        self.setCentralWidget(central)

    def _default_workspace_splitter_sizes(self) -> list[int]:
        return [
            int(self.DEFAULT_WORKSPACE_RAIL_WIDTH),
            1180,
            int(self.DEFAULT_WORKSPACE_INSPECTOR_WIDTH),
        ]

    def _build_helper_tab_page(self, parent: QWidget) -> QWidget:
        page = QWidget(parent)
        page.setObjectName("shellHelperPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("Pro Workflow Helper", page)
        title.setObjectName("shellTitle")
        layout.addWidget(title)

        subtitle = QLabel(
            "Use this guide to understand each part of Sprite Factory Pro before you start editing.",
            page,
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("shellSubtitle")
        layout.addWidget(subtitle)

        guide = QTextBrowser(page)
        guide.setObjectName("shellGuideBrowser")
        guide.setOpenExternalLinks(False)
        guide.setReadOnly(True)
        guide.setHtml(
            "<h3>Quick Start</h3>"
            "<ol>"
            "<li><b>Start a session</b>: use <b>Session</b> for New, Open, Save, or Clear.</li>"
            "<li><b>Add assets</b>: use <b>Import</b> or the <b>Web Sources</b> tab.</li>"
            f"<li><b>Supported formats</b>: {self._local_extensions_label()}.</li>"
            "<li><b>Edit in the studio shell</b>: quick presets in the top bar, preview in the center, settings on the right.</li>"
            "<li><b>Finish the asset</b>: use <b>Preview</b>, <b>Apply</b>, <b>Skip</b>, or <b>Export</b>.</li>"
            "</ol>"
            "<h3>Studio Shell</h3>"
            "<ul>"
            "<li><b>Left rail</b>: the workspace list lives here so asset switching stays out of the preview area.</li>"
            "<li><b>Center stage</b>: Current and Final previews stay largest so comparisons remain easy at full screen.</li>"
            "<li><b>Right inspector</b>: settings groups, search, and reset tools are kept in one editing column.</li>"
            "<li><b>Bottom shelf</b>: control strip and export footer sit below the preview instead of crowding the header.</li>"
            "</ul>"
            "<h3>Top Toolbar</h3>"
            "<ul>"
            "<li><b>Session</b>: New Session, Open Session, Save Session, Clear Session, and Sessions Folder.</li>"
            "<li><b>Import</b>: import files, folders, or ZIPs into the workspace.</li>"
            "<li><b>Mode</b>: Simple, Advanced, and Expert unlock different settings depth.</li>"
            "<li><b>FMT / Alpha / Frames</b>: quick readout for the selected asset.</li>"
            "<li><b>CPU / GPU</b>: chooses the preferred path for heavy tools only. GPU appears only when a supported runtime is available.</li>"
            "<li><b>Batch / Presets</b>: open the queue manager and advanced preset editor directly.</li>"
            "<li><b>View</b>: Compare View, Current Only, Final Only, Compact UI, and Reset Shell live here.</li>"
            "</ul>"
            "<h3>Workspace Flow</h3>"
            "<ol>"
            "<li>Pick an asset from the left rail, or import a new one from the toolbar.</li>"
            "<li>The workspace list shows loaded assets directly, and large queues are sectioned in windows of 100 for performance.</li>"
            "<li>Use the top-bar quick preset for a clean starting point, then adjust detailed settings on the right.</li>"
            "<li><b>Target</b> chooses which preview receives the next apply.</li>"
            "<li><b>Live</b> controls let you link views and toggle auto-preview while editing.</li>"
            "<li><b>BG</b> sets background handling for the active asset: keep, remove white, or remove black.</li>"
            "<li><b>More</b> contains <b>Reset Edits</b> and <b>Reset View</b> so image reset and zoom reset stay separate.</li>"
            "<li>The preview header gives you Crisp zoom plus per-pane Reset buttons to refit Current or Final quickly.</li>"
            "<li>The export footer gives you <b>Skip</b>, <b>Export</b>, destination folder, auto-next, and predicted size.</li>"
            "</ol>"
            "<h3>Settings Groups</h3>"
            "<ul>"
            "<li><b>Pixel and Resolution</b>: resize %, DPI metadata, target width/height, scale method.</li>"
            "<li><b>Color and Light</b>, <b>Detail</b>, <b>Cleanup</b>, <b>Edges</b>: core visual tuning controls.</li>"
            "<li><b>Transparency</b>: keep the background, remove white, or remove black, then refine alpha/matte.</li>"
            "<li><b>GIF Controls</b>: only enabled for animated assets.</li>"
            "<li><b>Export</b>: format/quality/metadata options.</li>"
            "<li><b>Expert Encoding</b>: advanced compression/chroma/palette tuning and Encoding Window launch.</li>"
            "<li><b>Filter sections</b>: narrows the right-side section list by section title only.</li>"
            "</ul>"
            "<h3>Presets</h3>"
            "<ul>"
            "<li>Quick presets in the top bar are filtered to the active asset type.</li>"
            "<li>Quick preset clicks reset the active asset back to a clean baseline before applying, so presets do not silently stack.</li>"
            "<li>The preset manager is for experienced users: duplicate a system template, set scope formats/tags, edit the JSON settings delta, then save your own user preset.</li>"
            "<li>Animated GIFs only show animation-safe presets in quick pickers and batch tools.</li>"
            "</ul>"
            "<h3>Web Sources Tab</h3>"
            "<ol>"
            "<li>Pick <b>Website</b> and <b>Area</b>, or paste a URL in <b>Custom Website URL</b>.</li>"
            "<li>Use <b>Scan Area</b> to find links, then filter by PNG/GIF/WEBP/JPG/ZIP.</li>"
            "<li>Select files and click <b>Download Selected</b>; Sprite Factory routes them into the workspace automatically.</li>"
            "<li>Downloaded items appear in the workspace rail and can be edited immediately.</li>"
            "<li>Use <b>Network Check</b> for DNS/TCP/HTTP diagnostics when scan/import fails.</li>"
            "<li>Right-click Website/Area dropdown entries to remove custom URLs and keep the list clean.</li>"
            "</ol>"
            "<h3>Batch</h3>"
            "<ul>"
            "<li>Select queued assets and click <b>Run Batch</b> for one-by-one automatic export.</li>"
            "<li>Optional overrides can apply the current edit stack, a preset, and white/black background removal before export.</li>"
            "<li>Progress and result state show processed, failed, and skipped items.</li>"
            "<li>Set naming template and export folder for consistent output filenames.</li>"
            "</ul>"
            "<h3>Troubleshooting</h3>"
            "<ul>"
            "<li>If Web Sources returns blocked errors (for example WinError 10013), check firewall/VPN/proxy/antivirus web shield.</li>"
            "<li>If a site blocks scan requests (HTTP 403/429), try Network Check or use direct image URLs.</li>"
            "<li>Some settings groups lock automatically when the active asset does not support that feature.</li>"
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
            self._refresh_preset_entries()
            self._sync_performance_actions()

        self.ui_state.status_message_changed.connect(self._status)
        self.ui_state.active_asset_changed.connect(self._on_active_asset_changed)
        self.ui_state.mode_changed.connect(self._on_mode_changed)
        self.ui_state.performance_mode_changed.connect(self._on_performance_mode_changed)
        self.ui_state.export_profile_changed.connect(lambda _value: self._refresh_export_prediction())
        self.ui_state.apply_requested.connect(self._on_apply_requested)
        self.ui_state.light_preview_requested.connect(self._on_light_preview_requested)
        self.ui_state.export_requested.connect(self._on_export_requested)
        self.export_bar.skip_requested.connect(self._on_skip_requested)
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
                lambda _code=0: self._refresh_preset_entries()
            )

        self._init_web_sources_panel()
        self._on_performance_mode_changed(self.ui_state.performance_mode)

    def performance_mode(self) -> str:
        return self.ui_state.performance_mode

    def set_performance_mode(self, mode_value: str, *, announce: bool = True) -> None:
        resolved_mode = mode_value
        status_message = None
        if self.controller is not None:
            resolution = self.controller.set_performance_mode(mode_value)
            resolved_mode = resolution.effective_mode
            status_message = resolution.status_message
        self.ui_state.set_performance_mode(
            resolved_mode,
            announce=announce,
            status_message=status_message,
        )
        self._sync_performance_actions()

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

    def _on_performance_mode_changed(self, mode_value: str) -> None:
        self._sync_performance_actions(mode_value)

    def _sync_performance_actions(self, mode_value: str | None = None) -> None:
        if self._cpu_action is None or self._gpu_action is None:
            return

        selected_mode = "gpu" if str(mode_value or self.ui_state.performance_mode).strip().lower() == "gpu" else "cpu"
        availability = self.controller.performance_availability() if self.controller is not None else None

        gpu_enabled = True
        gpu_tooltip = "GPU heavy processing"
        if availability is not None:
            gpu_enabled = bool(availability.gpu_available)
            if availability.gpu_available:
                label = availability.gpu_backend_label or "GPU backend available"
                gpu_tooltip = f"{label} for heavy processing"
            else:
                gpu_tooltip = availability.gpu_disabled_reason or "GPU backend unavailable on this machine"

        self._cpu_action.setEnabled(True)
        self._cpu_action.setToolTip("CPU heavy processing")
        self._gpu_action.setEnabled(gpu_enabled)
        self._gpu_action.setToolTip(gpu_tooltip)

        self._cpu_action.blockSignals(True)
        self._gpu_action.blockSignals(True)
        self._cpu_action.setChecked(selected_mode != "gpu")
        self._gpu_action.setChecked(selected_mode == "gpu" and gpu_enabled)
        self._cpu_action.blockSignals(False)
        self._gpu_action.blockSignals(False)

    def _set_preview_view_mode(self, mode_value: str) -> None:
        resolved = self.preview_panel.set_view_mode(mode_value)
        self._sync_preview_view_actions(resolved)
        label_map = {
            PreviewPanel.VIEW_COMPARE: "Compare view",
            PreviewPanel.VIEW_CURRENT: "Current-only view",
            PreviewPanel.VIEW_FINAL: "Final-only view",
        }
        self._status(f"{label_map.get(resolved, 'Preview view')} enabled")

    def _sync_preview_view_actions(self, mode_value: str | None = None) -> None:
        if (
            self._preview_compare_action is None
            or self._preview_current_action is None
            or self._preview_final_action is None
        ):
            return
        selected = str(mode_value or self.preview_panel.preview_view_mode()).strip().lower()
        self._preview_compare_action.blockSignals(True)
        self._preview_current_action.blockSignals(True)
        self._preview_final_action.blockSignals(True)
        self._preview_compare_action.setChecked(selected == PreviewPanel.VIEW_COMPARE)
        self._preview_current_action.setChecked(selected == PreviewPanel.VIEW_CURRENT)
        self._preview_final_action.setChecked(selected == PreviewPanel.VIEW_FINAL)
        self._preview_compare_action.blockSignals(False)
        self._preview_current_action.blockSignals(False)
        self._preview_final_action.blockSignals(False)

    def _on_active_asset_changed(self, asset: object) -> None:
        if asset is None:
            self._badge_format.setText("FMT: --")
            self._badge_format.setToolTip("Format: unavailable")
            self._badge_alpha.setText("Alpha: --")
            self._badge_alpha.setToolTip("Alpha: no asset")
            self._badge_frames.setText("Frames: --")
            self._badge_frames.setToolTip("Frames: no asset")
            self._refresh_preset_entries()
            return

        fmt = getattr(getattr(asset, "format", None), "value", "--")
        caps = getattr(asset, "capabilities", None)
        has_alpha = bool(getattr(caps, "has_alpha", False))
        is_animated = bool(getattr(caps, "is_animated", False))

        self._badge_format.setText(f"FMT: {str(fmt).upper()}")
        self._badge_format.setToolTip(f"Format: {str(fmt).upper()}")
        self._badge_alpha.setText("Alpha: Yes" if has_alpha else "Alpha: No")
        self._badge_alpha.setToolTip("Alpha: yes" if has_alpha else "Alpha: no")
        self._badge_frames.setText("Frames: GIF" if is_animated else "Frames: 1")
        self._badge_frames.setToolTip("Frames: animated" if is_animated else "Frames: static")
        asset_id = getattr(asset, "id", None)
        if isinstance(asset_id, str):
            self.asset_tabs.set_active_asset(asset_id)
            if self.asset_tabs.active_asset_id() != asset_id:
                self._sync_workspace_tabs()
        self._refresh_preset_entries()
        self._refresh_export_prediction()

    def _refresh_preset_entries(self) -> None:
        if self.controller is None:
            return
        active_asset = self.ui_state.active_asset
        if active_asset is None:
            self.presets_bar.set_presets([])
            self.presets_bar.set_context_hint("Select an asset to see compatible quick presets.")
            return
        try:
            self.presets_bar.set_presets(self.controller.available_preset_entries(active_asset, compatible_only=True))
            self.presets_bar.set_context_hint(self.controller.describe_asset_scope(active_asset))
        except Exception:
            self.presets_bar.set_presets(self.controller.available_preset_names())
            self.presets_bar.set_context_hint("Showing all presets")

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

    def _on_skip_requested(self) -> None:
        self._export_coordinator.on_skip_requested()


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
            self.ui_state.set_export_prediction_text("Size --")
            return

        if self.controller is not None:
            text = self.controller.format_prediction_text(asset)
        else:
            text = "Size --"
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
                self.batch_manager_dialog.set_available_presets(self.controller.available_preset_entries())
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

















