"""Main Qt window shell wiring preview/settings/export UI to engine state."""

from __future__ import annotations

from image_engine_app.app.settings_store import SessionStore
from image_engine_app.app.ui_controller import ImageEngineUIController
from image_engine_app.engine.models import AssetRecord, SessionState

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QStatusBar,
    QStackedWidget,
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
from image_engine_app.ui.main_window.preview_panel import PreviewPanel
from image_engine_app.ui.main_window.settings_panel import SettingsPanel
from image_engine_app.ui.main_window.shell_coordinator import ShellCoordinator
from image_engine_app.ui.main_window.workspace_coordinator import WorkspaceCoordinator
from image_engine_app.ui.main_window.session_coordinator import SessionCoordinator
from image_engine_app.ui.main_window.local_import_coordinator import LocalImportCoordinator
from image_engine_app.ui.main_window.web_sources_panel import WebSourcesPanel
from image_engine_app.ui.main_window.web_sources_coordinator import WebSourcesCoordinator
from image_engine_app.ui.windows.batch_manager import BatchManagerDialog
from image_engine_app.ui.windows.preset_manager import PresetManagerDialog


class ImageEngineMainWindow(QMainWindow):
    """Main Sprite Factory window and coordinator wiring."""

    MAX_RENDERED_WORKSPACE_TABS = 100
    MOCK_PAGE_RAIL_WIDTH = 86
    MOCK_WORKSPACE_PANEL_WIDTH = 276
    MOCK_INSPECTOR_PANEL_WIDTH = 398

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
        self.setWindowTitle("Sprite Factory Pro v1.2.2")
        self.resize(1460, 920)
        self.setMinimumSize(1180, 760)

        self.ui_state = EngineUIState()
        self.controller = controller
        self.session_store = session_store
        self._workspace_assets: list[AssetRecord] = []
        self._batch_thread: object | None = None
        self._batch_worker: object | None = None
        self._batch_dialog_queue_signature: tuple[str, ...] = ()

        self._badge_format = QLabel("Format --", self)
        self._badge_alpha = QLabel("Alpha --", self)
        self._badge_frames = QLabel("Frames --", self)
        self._page_tabs: QStackedWidget | None = None
        self._page_nav_buttons: dict[int, QToolButton] = {}
        self._top_toolbar: QToolBar | None = None
        self._workspace_splitter: QWidget | None = None
        self._workspace_editor_splitter: QWidget | None = None
        self._workspace_left_panel: QFrame | None = None
        self._workspace_inspector_panel: QFrame | None = None
        self._compact_ui_action: QAction | None = None
        self._compact_ui_enabled = False
        self._preview_compare_action: QAction | None = None
        self._preview_current_action: QAction | None = None
        self._preview_final_action: QAction | None = None
        self._helper_tab_index: int | None = None
        self._workspace_tab_window_start = 0
        self._workspace_tab_window_size = int(self.MAX_RENDERED_WORKSPACE_TABS)
        self.preview_panel = PreviewPanel(self)
        self.control_strip = ControlStrip(self)
        self.asset_tabs = WorkspaceAssetTabs(self)
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
        self.preset_manager_dialog = (
            PresetManagerDialog(
                self.controller,
                self,
                active_asset_provider=lambda: self.ui_state.active_asset,
            )
            if self.controller is not None
            else None
        )

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

        # Workspace files and local imports share one conventional File menu.
        self._add_toolbar_popup_menu_button(
            toolbar,
            text="File",
            menu=self._build_file_menu(),
            tooltip="Workspace and local file actions",
        )
        toolbar.addSeparator()

        # Format badges
        for badge in (self._badge_format, self._badge_alpha, self._badge_frames):
            badge.setObjectName("toolbarBadge")
            badge.setFixedSize(86, 30)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            toolbar.addWidget(badge)

        toolbar.addSeparator()
        self._add_toolbar_command_button(toolbar, text="Batch", callback=self._show_batch_manager)

        toolbar.addSeparator()
        self._compact_ui_action = QAction("Compact UI", self, checkable=True)
        self._compact_ui_action.toggled.connect(self.set_compact_ui)
        self._add_toolbar_popup_menu_button(
            toolbar,
            text="View",
            menu=self._build_view_menu(),
            tooltip="View options",
        )

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
        brand.setFixedSize(204, 40)
        layout = QHBoxLayout(brand)
        layout.setContentsMargins(8, 3, 9, 3)
        layout.setSpacing(7)

        mark = QLabel("SF", brand)
        mark.setObjectName("toolbarBrandMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(24, 24)
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
        button.setFixedSize(72, 30)
        toolbar.addWidget(button)

    def _add_toolbar_command_button(
        self,
        toolbar: QToolBar,
        *,
        text: str,
        callback,
        width: int = 72,
        tooltip: str | None = None,
    ) -> None:
        button = QToolButton(toolbar)
        button.setObjectName("toolbarMenuButton")
        button.setText(text)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button.setFixedSize(width, 30)
        button.setToolTip(tooltip or text)
        button.setEnabled(callback is not None)
        if callback is not None:
            button.clicked.connect(callback)
        toolbar.addWidget(button)

    def _build_file_menu(self) -> QMenu:
        menu = QMenu(self)

        new_action = menu.addAction(icon("new"), "New Workspace")
        new_action.triggered.connect(self._new_workspace)

        open_action = menu.addAction(icon("open"), "Open Workspace...")
        open_action.triggered.connect(self._open_workspace_file)

        save_action = menu.addAction(icon("save"), "Save Workspace...")
        save_action.triggered.connect(self._save_workspace_file)

        menu.addSeparator()

        add_files_action = menu.addAction("Add Files...")
        add_files_action.triggered.connect(self._import_files)

        add_folder_action = menu.addAction("Add Folder...")
        add_folder_action.triggered.connect(self._import_folder)

        return menu

    def _build_center_shell(self) -> None:
        central = QWidget(self)
        central.setObjectName("mainShellCentral")
        central_layout = QHBoxLayout(central)
        central_layout.setContentsMargins(6, 8, 6, 8)
        central_layout.setSpacing(8)

        page_nav = QFrame(central)
        page_nav.setObjectName("shellPageRail")
        page_nav.setFixedWidth(self.MOCK_PAGE_RAIL_WIDTH)
        page_nav_layout = QVBoxLayout(page_nav)
        page_nav_layout.setContentsMargins(7, 10, 7, 10)
        page_nav_layout.setSpacing(10)

        page_stack = QStackedWidget(central)
        page_stack.setObjectName("shellPageStack")
        self._page_tabs = page_stack

        workspace_page = QWidget(page_stack)
        workspace_page.setObjectName("workspacePage")
        workspace_layout = QHBoxLayout(workspace_page)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(8)

        left_shell = QFrame(workspace_page)
        left_shell.setObjectName("workspaceRailShell")
        left_shell.setFixedWidth(self.MOCK_WORKSPACE_PANEL_WIDTH)
        left_layout = QVBoxLayout(left_shell)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(10)
        left_layout.addWidget(self.asset_tabs, 1)
        self._workspace_left_panel = left_shell

        editor_shell = QFrame(workspace_page)
        editor_shell.setObjectName("workspaceEditorShell")
        editor_shell.setMinimumWidth(620)
        editor_layout = QVBoxLayout(editor_shell)
        editor_layout.setContentsMargins(10, 10, 10, 10)
        editor_layout.setSpacing(10)

        editor_stack = QWidget(editor_shell)
        editor_stack.setObjectName("workspaceEditorStack")
        editor_stack_layout = QVBoxLayout(editor_stack)
        editor_stack_layout.setContentsMargins(0, 0, 0, 0)
        editor_stack_layout.setSpacing(8)

        preview_shell = QFrame(editor_stack)
        preview_shell.setObjectName("workspacePreviewStage")
        preview_layout = QVBoxLayout(preview_shell)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)
        preview_layout.addWidget(self.preview_panel)

        action_shell = QFrame(editor_stack)
        action_shell.setObjectName("workspaceActionShelf")
        action_layout = QVBoxLayout(action_shell)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(8)
        action_layout.addWidget(self.control_strip)
        action_layout.addWidget(self.export_bar)

        editor_stack_layout.addWidget(preview_shell, 1)
        editor_stack_layout.addWidget(action_shell, 0)
        self._workspace_editor_splitter = editor_stack
        editor_layout.addWidget(editor_stack, 1)

        inspector_shell = QFrame(workspace_page)
        inspector_shell.setObjectName("workspaceInspectorShell")
        inspector_shell.setFixedWidth(self.MOCK_INSPECTOR_PANEL_WIDTH)
        inspector_layout = QVBoxLayout(inspector_shell)
        inspector_layout.setContentsMargins(12, 12, 12, 12)
        inspector_layout.setSpacing(0)
        inspector_layout.addWidget(self.settings_panel, 1)
        self._workspace_inspector_panel = inspector_shell

        workspace_layout.addWidget(left_shell, 0)
        workspace_layout.addWidget(editor_shell, 1)
        workspace_layout.addWidget(inspector_shell, 0)
        self._workspace_splitter = workspace_page

        workspace_index = page_stack.addWidget(workspace_page)
        web_index = page_stack.addWidget(self.web_sources_panel)
        self._helper_tab_index = page_stack.addWidget(self._build_helper_tab_page(page_stack))

        nav_group = QButtonGroup(self)
        nav_group.setExclusive(True)
        self._add_page_nav_button(
            page_nav_layout,
            group=nav_group,
            index=workspace_index,
            label="Workspace",
            icon_name="workspace",
        )
        self._add_page_nav_button(
            page_nav_layout,
            group=nav_group,
            index=web_index,
            label="Web Sources",
            icon_name="web",
        )
        self._add_page_nav_button(
            page_nav_layout,
            group=nav_group,
            index=self._helper_tab_index,
            label="Helper",
            icon_name="help",
        )
        page_nav_layout.addStretch(1)
        self._page_nav_buttons.get(workspace_index, QToolButton()).setChecked(True)

        central_layout.addWidget(page_nav, 0)
        central_layout.addWidget(page_stack, 1)
        self.setCentralWidget(central)

    def _add_page_nav_button(
        self,
        layout: QVBoxLayout,
        *,
        group: QButtonGroup,
        index: int,
        label: str,
        icon_name: str,
    ) -> None:
        button = QToolButton(self)
        button.setObjectName("shellPageRailButton")
        button.setText(label)
        button.setIcon(icon(icon_name))
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        button.setCheckable(True)
        button.setToolTip(label)
        button.setIconSize(QSize(18, 18))
        button.setFixedSize(74, 64)
        button.clicked.connect(lambda _checked=False, idx=index: self._set_page_index(idx))
        group.addButton(button, index)
        self._page_nav_buttons[index] = button
        layout.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)

    def _set_page_index(self, index: int) -> None:
        if self._page_tabs is None or index < 0 or index >= self._page_tabs.count():
            return
        self._page_tabs.setCurrentIndex(index)
        for button_index, button in self._page_nav_buttons.items():
            button.blockSignals(True)
            button.setChecked(button_index == index)
            button.blockSignals(False)

    def _build_helper_tab_page(self, parent: QWidget) -> QWidget:
        page = QWidget(parent)
        page.setObjectName("shellHelperPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("Sprite Factory Helper", page)
        title.setObjectName("shellTitle")
        layout.addWidget(title)

        subtitle = QLabel(
            "Current guide for the redesigned Sprite Factory Pro workspace.",
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
            "<li><b>Start</b>: open <b>File</b> to create, open, or save a workspace.</li>"
            "<li><b>Add assets</b>: use <b>File</b> for images, folders, or ZIPs, or <b>Web Sources</b> for website scans.</li>"
            f"<li><b>Supported formats</b>: {self._local_extensions_label()}.</li>"
            "<li><b>Edit</b>: use the center previews, bottom tools, and right-side edit settings.</li>"
            "<li><b>Finish</b>: review the automatically updated Final pane, then Export, Skip, or send selected assets through Batch.</li>"
            "</ol>"
            "<h3>Studio Shell</h3>"
            "<ul>"
            "<li><b>Left rail</b>: Workspace, Web Sources, and Helper.</li>"
            "<li><b>Workspace panel</b>: asset list, empty state, and 100-item queue paging.</li>"
            "<li><b>Preview Studio</b>: Current and Final stay central; use per-pane Reset to refit either side.</li>"
            "<li><b>Tools shelf</b>: compatible Presets, background handling, Final refresh, processing, and reset actions.</li>"
            "<li><b>Edit Settings</b>: right-side tiles jump to Pixel, Color, Detail, Cleanup, Edges, Alpha, GIF, and Export.</li>"
            "</ul>"
            "<h3>Top Toolbar</h3>"
            "<ul>"
            "<li><b>File</b>: New Workspace, Open Workspace, Save Workspace, Add Files, and Add Folder.</li>"
            "<li><b>Add Files</b>: choose one or more supported images or ZIP archives. ZIP images are safely extracted and added through the same import workflow.</li>"
            "<li><b>New / Open Workspace</b>: if the current workspace contains work, Sprite Factory asks whether to save, discard, or cancel before replacing it.</li>"
            "<li><b>Format / Alpha / Frames</b>: quick readout for the selected asset.</li>"
            "<li><b>Batch</b>: open the queue manager for multi-asset editing and export.</li>"
            "<li><b>View</b>: Compare View, Current Only, Final Only, Compact UI, and Reset Shell live here.</li>"
            "</ul>"
            "<h3>Workspace Flow</h3>"
            "<ol>"
            "<li>Import or download assets, then choose one from Workspace.</li>"
            "<li><b>Current</b> always shows the untouched source; <b>Final</b> shows your active edits.</li>"
            "<li>Visual control changes refresh <b>Final</b> automatically. Use <b>Refresh Final</b> to rebuild it manually whenever needed.</li>"
            "<li>When a preset queues heavier processing, the same Run button changes to <b>Run Heavy</b>.</li>"
            "<li>Use the background menu to keep the image background, remove white, or remove black.</li>"
            "<li><b>Reset Edits</b> restores the controls detected for that asset at import. <b>Reset View</b> changes zoom only.</li>"
            "<li>The export footer has Profile, Export, Skip, folder output, Auto-next, and Estimate.</li>"
            "</ol>"
            "<h3>Settings Groups</h3>"
            "<ul>"
            "<li><b>Pixel and Resolution</b>: Output size offers 2x/3x/4x/8x sprite scaling and 240p-2160p output heights. Standard heights keep width on Auto to preserve proportions.</li>"
            "<li><b>Resize % / target dimensions</b>: these change real pixel dimensions. <b>DPI</b> changes print metadata only and does not create extra image detail.</li>"
            "<li><b>Color and Light</b>, <b>Detail</b>, <b>Cleanup</b>, <b>Edges</b>: core visual tuning controls.</li>"
            "<li><b>Transparency</b>: keep/remove backgrounds, refine alpha, and check matte handling.</li>"
            "<li><b>GIF Controls</b>: timing, looping, palette, dithering, and frame optimization for animated GIFs.</li>"
            "<li><b>Export</b>: profile, format, quality, metadata, PNG compression, JPEG chroma, and ICO sizes in one place.</li>"
            "<li><b>Choose what to edit</b>: tiles jump directly to the matching settings card.</li>"
            "</ul>"
            "<h3>Presets</h3>"
            "<ul>"
            "<li>Each imported asset keeps its own detected control baseline. A preset starts from that baseline rather than blank defaults.</li>"
            "<li><b>Preset</b> in the Tools shelf applies one compatible preset to the active asset and refreshes Final.</li>"
            "<li><b>Manage Presets...</b> at the bottom of the Tools preset menu opens Preset Studio. Choose <b>New from Active</b> or <b>Use Active Controls</b>; only controls changed from the detected baseline are saved.</li>"
            "<li>The Tools menu, Preset Studio, and Batch all use the same preset library. Bundled presets and your saved presets are merged once, then filtered for the active asset.</li>"
            "<li>Format and asset-type scopes are filled from the active asset. The JSON editor is optional under Advanced.</li>"
            "<li>User presets appear in Workspace and Batch immediately. Compatibility checks protect animated GIFs and format-specific assets. Reset Edits restores the detected controls from before the preset was chosen.</li>"
            "</ul>"
            "<h3>Web Sources</h3>"
            "<p>Web Sources uses one scan system for entered URLs, saved pages, and linked pages. Every successful scan adds unique files to the same Found Files list instead of replacing earlier results.</p>"
            "<h4>1. Scan Pages</h4>"
            "<ul>"
            "<li>Paste one full page URL per line. The list can contain pages from several different websites.</li>"
            "<li><b>Scan Pages</b> validates the list, removes repeated URLs, applies the safety limit, and sends the remaining pages through the same scan call.</li>"
            "<li><b>More</b> contains only entered-URL actions: Save Entered Pages, Check First URL, Include uncertain image links, and Clear Entered URLs.</li>"
            "<li>Include uncertain image links is optional. Enable it when a website hides useful image links behind URLs that do not end with a normal file extension.</li>"
            "</ul>"
            "<h4>2. Saved Pages</h4>"
            "<ul>"
            "<li><b>Save Entered Pages</b> groups entered URLs by website and stores each exact page once.</li>"
            "<li>Expand a website and check individual pages, or check the website row to choose all of its pages. Pages from different websites can be checked together.</li>"
            "<li><b>Scan Selected</b> sends every checked page through the normal scan call. If nothing is checked, the currently highlighted page is used.</li>"
            "<li><b>More</b> contains saved-page actions only: check the current page, clear checked pages, check the current page connection, remove the current page, or remove the current website.</li>"
            "<li>Changing or removing a saved shortcut never clears Found Files.</li>"
            "</ul>"
            "<h4>3. Find Linked Pages</h4>"
            "<ul>"
            "<li>This optional section is for index, category, or directory pages that link to many separate sprite pages.</li>"
            "<li>Use <b>Discover from</b> to choose exactly which entered or saved page will be inspected, then click <b>Find Pages</b>.</li>"
            "<li>Search the discovered page list, select the pages you need, then click <b>Scan Selected</b>. Finding pages does not download or scan files by itself.</li>"
            "<li><b>More</b> contains linked-page actions only: select visible pages, clear page selection, and clear linked pages.</li>"
            "<li>Any scan above 100 pages asks for confirmation and scans only the first 100, reducing the chance of a freeze or website rate limit.</li>"
            "</ul>"
            "<h4>4. Found Files and Download</h4>"
            "<ul>"
            "<li>Found Files is a persistent basket. New scans add unique file URLs; repeated URLs and failed pages do not erase earlier results.</li>"
            "<li>Search matches filenames, URLs, and source pages. Hide words excludes matching results. File Types controls PNG, GIF, WEBP, JPG/JPEG, and ZIP visibility.</li>"
            "<li><b>More</b> contains result actions only: select all visible files, clear file selection, and Clear Found Files.</li>"
            "<li><b>Download Options</b> controls skipping files already downloaded and whether ZIP extraction is allowed.</li>"
            "<li><b>Download Selected</b> imports selected files and automatically routes them into Main, Shiny, Animated, or Items in the workspace.</li>"
            "<li>Only Clear Found Files empties the result basket. Search filters, URL clearing, saved-page changes, linked-page clearing, cancellation, and failed scans keep it intact.</li>"
            "</ul>"
            "<h4>Web Source Status and Errors</h4>"
            "<ul>"
            "<li>The status line reports new files, total stored files, duplicates, filtered links, and failed pages. Hover a failure message for page details.</li>"
            "<li>A connection check tests the selected page but never starts a scan. HTTP 403/429 usually means the website blocked or limited automated requests; HTTP 5xx means the website server failed.</li>"
            "</ul>"
            "<h3>Batch</h3>"
            "<ul>"
            "<li>Select queue items, choose one edit source, then click <b>Run Selected</b>.</li>"
            "<li>Use <b>Queue</b> for Select all, Select failed, and Clear selection.</li>"
            "<li><b>Keep each asset's controls</b> uses every file exactly as it is currently configured.</li>"
            "<li><b>Apply one preset</b> starts from each asset's detected baseline and applies the same compatible saved preset.</li>"
            "<li><b>Copy active asset controls</b> deliberately copies the selected Workspace asset's controls to the batch.</li>"
            "<li><b>Smart match each asset</b> chooses at most one compatible system preset per asset; it never stacks hidden presets.</li>"
            "<li>Background override is applied after the chosen edit source. Use <b>Options</b> only for Export after processing and Fast run.</li>"
            "<li>Use naming/output options for clean filenames and a consistent export folder.</li>"
            "<li>Failed items can be selected again after the run.</li>"
            "</ul>"
            "<h3>Troubleshooting</h3>"
            "<ul>"
            "<li>If Web Sources returns blocked errors such as WinError 10013, check firewall/VPN/proxy/antivirus web shield.</li>"
            "<li>If a site blocks scan requests (HTTP 403/429), try the section's connection check or use direct image URLs.</li>"
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
    def _local_import_dialog_filter(cls) -> str:
        patterns = " ".join(f"*{ext}" for ext in cls._supported_local_extensions())
        return (
            f"Supported Images and ZIPs ({patterns} *.zip);;"
            f"Supported Images ({patterns});;"
            "ZIP Archives (*.zip);;All Files (*)"
        )

    def _bind_state(self) -> None:
        self.preview_panel.bind_state(self.ui_state)
        self.control_strip.bind_state(self.ui_state)
        self.export_bar.bind_state(self.ui_state)
        self.settings_panel.bind_state(self.ui_state)

        self.ui_state.status_message_changed.connect(self._status)
        self.ui_state.active_asset_changed.connect(self._on_active_asset_changed)
        self.ui_state.export_profile_changed.connect(lambda _value: self._refresh_export_prediction())
        self.ui_state.apply_requested.connect(self._on_apply_requested)
        self.ui_state.light_preview_requested.connect(self._on_light_preview_requested)
        self.ui_state.export_requested.connect(self._on_export_requested)
        self.control_strip.preset_selected.connect(self._on_control_preset_selected)
        self.control_strip.preset_manager_requested.connect(self._show_preset_manager)
        self.export_bar.skip_requested.connect(self._on_skip_requested)
        self.export_bar.browse_export_dir_requested.connect(self._on_export_directory_browse_requested)
        self.export_bar.open_export_dir_requested.connect(self._on_export_directory_open_requested)
        self.ui_state.global_reset_requested.connect(self._on_global_reset_requested)
        self.asset_tabs.asset_selected.connect(self._on_workspace_asset_selected)
        self.asset_tabs.pin_active_requested.connect(self._on_workspace_pin_requested)
        self.asset_tabs.asset_close_requested.connect(self._on_workspace_asset_close_requested)
        self.asset_tabs.window_prev_requested.connect(self._on_workspace_prev_window_requested)
        self.asset_tabs.window_next_requested.connect(self._on_workspace_next_window_requested)
        self.asset_tabs.window_section_requested.connect(self._on_workspace_window_section_requested)
        self.batch_manager_dialog.run_requested.connect(self._on_batch_run_requested)
        self.batch_manager_dialog.cancel_run_requested.connect(self._on_batch_cancel_requested)
        self.web_sources_panel.registry_changed.connect(self._on_web_sources_registry_changed)
        self.web_sources_panel.scan_requested.connect(self._on_web_sources_scan_requested)
        self.web_sources_panel.discover_links_requested.connect(self._on_web_sources_discover_links_requested)
        self.web_sources_panel.download_requested.connect(self._on_web_sources_download_requested)
        self.web_sources_panel.diagnostics_requested.connect(self._on_web_sources_diagnostics_requested)
        self.web_sources_panel.preferences_changed.connect(self._on_web_sources_preferences_changed)

        if self.preset_manager_dialog is not None and self.controller is not None:
            self.preset_manager_dialog.presets_changed.connect(self._refresh_preset_surfaces)

        self._init_web_sources_panel()
        self._refresh_preset_surfaces()

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
            self._badge_format.setText("Format --")
            self._badge_format.setToolTip("Format: unavailable")
            self._badge_alpha.setText("Alpha --")
            self._badge_alpha.setToolTip("Alpha: no asset")
            self._badge_frames.setText("Frames --")
            self._badge_frames.setToolTip("Frames: no asset")
            self._refresh_control_presets()
            return

        fmt = getattr(getattr(asset, "format", None), "value", "--")
        caps = getattr(asset, "capabilities", None)
        has_alpha = bool(getattr(caps, "has_alpha", False))
        is_animated = bool(getattr(caps, "is_animated", False))

        self._badge_format.setText(f"Format {str(fmt).upper()}")
        self._badge_format.setToolTip(f"Format: {str(fmt).upper()}")
        self._badge_alpha.setText("Alpha Yes" if has_alpha else "Alpha No")
        self._badge_alpha.setToolTip("Alpha: yes" if has_alpha else "Alpha: no")
        self._badge_frames.setText("Animated" if is_animated else "Static")
        self._badge_frames.setToolTip("Frames: animated" if is_animated else "Frames: static")
        asset_id = getattr(asset, "id", None)
        if isinstance(asset_id, str):
            self.asset_tabs.set_active_asset(asset_id)
            if self.asset_tabs.active_asset_id() != asset_id:
                self._sync_workspace_tabs()
        self._refresh_export_prediction()
        self._refresh_control_presets()

    def _on_light_preview_requested(self) -> None:
        self._apply_coordinator.on_light_preview_requested()

    def _on_apply_requested(self) -> None:
        self._apply_coordinator.on_apply_requested()

    def _on_control_preset_selected(self, preset_name: str) -> None:
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

    def _new_workspace(self) -> None:
        self._session_coordinator.new_workspace()

    def _save_workspace_file(self) -> None:
        self._session_coordinator.save_workspace_file()

    def _open_workspace_file(self) -> None:
        self._session_coordinator.open_workspace_file()

    def _import_files(self) -> None:
        self._local_import_coordinator.import_files()

    def _import_folder(self) -> None:
        self._local_import_coordinator.import_folder()

    def _show_batch_manager(self) -> None:
        self._batch_coordinator.show_manager()

    def _show_preset_manager(self) -> None:
        if self.preset_manager_dialog is None:
            self._status("Preset Manager unavailable")
            return
        self.preset_manager_dialog.refresh_from_controller()
        self.preset_manager_dialog.show()
        self.preset_manager_dialog.raise_()
        self.preset_manager_dialog.activateWindow()

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

    def _on_web_sources_discover_links_requested(self, payload: object) -> None:
        self._web_sources_coordinator.on_discover_links_requested(payload)

    def _on_web_sources_download_requested(self, payload: object) -> None:
        self._web_sources_coordinator.on_download_requested(payload)

    def _on_web_sources_diagnostics_requested(self, payload: object) -> None:
        self._web_sources_coordinator.on_diagnostics_requested(payload)

    def _on_web_sources_preferences_changed(self, payload: object) -> None:
        self._web_sources_coordinator.on_preferences_changed(payload)

    def _on_batch_run_requested(self, options_obj: object) -> None:
        self._batch_coordinator.on_run_requested(options_obj)

    def _on_batch_cancel_requested(self) -> None:
        self._batch_coordinator.on_cancel_requested()

    def _refresh_export_prediction(self) -> None:
        asset = self.ui_state.active_asset
        if asset is None:
            self.ui_state.set_export_prediction_text("Estimate --")
            return

        if self.controller is not None:
            text = self.controller.format_prediction_text(asset)
        else:
            text = "Estimate --"
        if text.startswith("Size"):
            text = f"Estimate{text[4:]}"
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

    def _refresh_control_presets(self) -> None:
        asset = self.ui_state.active_asset
        if self.controller is None or asset is None:
            self.control_strip.set_preset_entries([], has_asset=asset is not None)
            return
        try:
            entries = self.controller.available_preset_entries(asset, compatible_only=True)
        except Exception:
            entries = []
        self.control_strip.set_preset_entries(entries, has_asset=True)

    def _refresh_preset_surfaces(self) -> None:
        self._sync_batch_dialog_items()
        self._refresh_control_presets()

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

















