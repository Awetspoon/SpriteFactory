"""Shared application stylesheet for the Sprite Factory shell."""

from __future__ import annotations

from pathlib import Path

from image_engine_app.ui.common.shell_tokens import SHELL_GEOMETRY, SHELL_PALETTE


def build_app_stylesheet() -> str:
    """Return the shared stylesheet used across the desktop shell."""

    chevron_down = Path(__file__).with_name("chevron_down.svg").as_posix()
    chevron_up = Path(__file__).with_name("chevron_up.svg").as_posix()

    stylesheet = """
    QMainWindow#imageEngineMainWindow,
    QWidget#mainShellCentral,
    QWidget#shellHelperPage,
    QWidget#workspacePage {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f8f4ee, stop:0.5 __CANVAS__, stop:1 __CANVAS_COOL__);
        color: __TEXT__;
    }
    QWidget {
        font-family: "Segoe UI", "Arial", sans-serif;
        color: __TEXT__;
        selection-background-color: #e6ece8;
        selection-color: #243237;
    }
    QToolBar#shellTopToolbar {
        background: __TOOLBAR__;
        border: none;
        border-bottom: 1px solid #cfd8d4;
        spacing: 3px;
        padding: 4px 8px;
    }
    QToolBar#shellTopToolbar::separator {
        background: #d0d6d2;
        width: 1px;
        margin: 5px 5px;
    }
    QFrame#toolbarBrandLockup {
        border: 1px solid #ced4cf;
        border-radius: 8px;
        background: #fbfaf6;
    }
    QLabel#toolbarBrandMark {
        border: 1px solid #94b8ba;
        border-radius: 12px;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #7aaeb1, stop:1 #4b8b90);
        color: #ffffff;
        font-weight: 800;
        font-size: 10px;
    }
    QLabel#toolbarBrandTitle {
        background: transparent;
        color: #24333a;
        font-size: 11px;
        font-weight: 700;
    }
    QLabel#toolbarBrandSubtitle {
        background: transparent;
        color: #7a807b;
        font-size: 8px;
        font-weight: 600;
    }
    QLabel#toolbarLabel {
        background: transparent;
        color: #6e7a7c;
        font-weight: 700;
        padding: 0 2px;
        font-size: 10px;
    }
    QLabel#toolbarBadge {
        border: 1px solid #d1d6d1;
        border-radius: 10px;
        background: #faf8f3;
        color: #365159;
        padding: 2px 7px;
        font-size: 9px;
        font-weight: 700;
    }
    QToolButton#toolbarMenuButton,
    QToolBar#shellTopToolbar QToolButton {
        min-height: 20px;
        padding: 2px 7px;
        border: 1px solid #d2d7d2;
        border-radius: 7px;
        background: #fbfaf6;
        color: #273840;
        font-weight: 600;
        font-size: 10px;
    }
    QToolButton#toolbarMenuButton:hover,
    QToolBar#shellTopToolbar QToolButton:hover {
        border-color: #b4c0bb;
        background: #f8f5ef;
    }
    QToolButton#toolbarMenuButton:pressed,
    QToolBar#shellTopToolbar QToolButton:pressed {
        background: #ece8e0;
        border-color: #9fb2ac;
    }
    QToolButton#toolbarMenuButton:checked,
    QToolBar#shellTopToolbar QToolButton:checked {
        background: #edf2ee;
        border-color: #a9bbb5;
        color: #425b5a;
    }
    QToolBar#shellTopToolbar QComboBox {
        min-height: 20px;
        padding: 2px 24px 2px 8px;
        border: 1px solid #d2d7d2;
        border-radius: 7px;
        background: #fbf9f4;
        color: #273840;
        font-size: 10px;
    }
    QToolBar#shellTopToolbar QComboBox::drop-down {
        subcontrol-origin: padding;
        subcontrol-position: top right;
        border-left: 1px solid #d3dbd6;
        border-top-right-radius: 7px;
        border-bottom-right-radius: 7px;
        background: #eef4f1;
        width: 20px;
    }
    QToolBar#shellTopToolbar QComboBox::down-arrow {
        image: url("__CHEVRON_DOWN__");
        width: 10px;
        height: 7px;
    }
    QToolButton#toolbarMenuButton::menu-indicator {
        width: 8px;
    }
    QFrame#shellPageRail {
        border: 1px solid #d4d8d3;
        border-radius: 14px;
        background: #fbfaf7;
    }
    QToolButton#shellPageRailButton {
        min-width: __PAGE_BUTTON_CONTENT_WIDTH__px;
        min-height: __PAGE_BUTTON_CONTENT_HEIGHT__px;
        padding: 4px 2px;
        border: 1px solid transparent;
        border-radius: 12px;
        background: transparent;
        color: #617174;
        font-size: 8px;
        font-weight: 800;
    }
    QToolButton#shellPageRailButton:hover {
        background: #fbfaf6;
        border-color: #d3dbd6;
    }
    QToolButton#shellPageRailButton:checked {
        background: #eaf2ef;
        border-color: #a7c2ba;
        color: #315e58;
    }
    QStackedWidget#shellPageStack {
        background: transparent;
        border: none;
    }
    QSplitter#workspaceMainSplitter {
        background: transparent;
        border: none;
    }
    QSplitter#workspaceMainSplitter::handle {
        background: #dfe5e1;
        width: __SPLITTER_WIDTH__px;
        margin: 12px 0;
        border-radius: 2px;
    }
    QSplitter#workspaceMainSplitter::handle:hover {
        background: #b9cac4;
    }
    QFrame#workspaceRailShell,
    QFrame#workspaceEditorShell,
    QFrame#workspaceInspectorShell {
        border: 1px solid #d4d8d3;
        border-radius: 14px;
        background: #fbfaf7;
    }
    QFrame#workspacePreviewStage,
    QFrame#workspaceActionShelf {
        background: transparent;
        border: none;
    }
    QStatusBar {
        background: #f2eee7;
        border-top: 1px solid #d2d7d2;
        color: #6a797d;
    }
    QPushButton,
    QToolButton {
        min-height: 20px;
        padding: 2px 8px;
        border: 1px solid #d1d7d2;
        border-radius: 7px;
        background: #faf8f3;
        color: #273840;
        font-size: 10px;
    }
    QPushButton:hover,
    QToolButton:hover {
        border-color: #b2c0bb;
        background: #f7f4ee;
    }
    QPushButton:pressed,
    QToolButton:pressed {
        background: #ece8e0;
        border-color: #9fb2ac;
    }
    QPushButton:checked,
    QToolButton:checked {
        background: #eef3ee;
        border-color: #a7beb6;
        color: #405a58;
    }
    QPushButton#shellPrimaryAction {
        background: #4a8f93;
        border: 1px solid #3c7e82;
        border-radius: 7px;
        color: #ffffff;
        font-weight: 700;
    }
    QPushButton#shellPrimaryAction:hover {
        background: #53989b;
        border-color: #467f83;
    }
    QPushButton#shellPrimaryAction:pressed {
        background: #3d787d;
        border-color: #35686c;
    }
    QPushButton#shellPrimaryAction:disabled {
        background: #c8d2d0;
        border-color: #c8d2d0;
        color: #f4f6f5;
    }
    QLineEdit,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox {
        min-height: 20px;
        border: 1px solid #d1d7d2;
        border-radius: 7px;
        background: #fbf9f4;
        color: #26353b;
        padding: 2px 8px;
        font-size: 10px;
    }
    QSpinBox,
    QDoubleSpinBox {
        padding: 2px 24px 2px 8px;
    }
    QSpinBox::up-button,
    QDoubleSpinBox::up-button {
        subcontrol-origin: border;
        subcontrol-position: top right;
        width: 20px;
        border-left: 1px solid #d3dbd6;
        border-bottom: 1px solid #d3dbd6;
        border-top-right-radius: 6px;
        background: #eef4f1;
    }
    QSpinBox::down-button,
    QDoubleSpinBox::down-button {
        subcontrol-origin: border;
        subcontrol-position: bottom right;
        width: 20px;
        border-left: 1px solid #d3dbd6;
        border-bottom-right-radius: 6px;
        background: #eef4f1;
    }
    QSpinBox::up-arrow,
    QDoubleSpinBox::up-arrow {
        image: url("__CHEVRON_UP__");
        width: 8px;
        height: 6px;
    }
    QSpinBox::down-arrow,
    QDoubleSpinBox::down-arrow {
        image: url("__CHEVRON_DOWN__");
        width: 8px;
        height: 6px;
    }
    QSpinBox::up-button:hover,
    QSpinBox::down-button:hover,
    QDoubleSpinBox::up-button:hover,
    QDoubleSpinBox::down-button:hover {
        background: #e5efeb;
    }
    QSpinBox::up-button:pressed,
    QSpinBox::down-button:pressed,
    QDoubleSpinBox::up-button:pressed,
    QDoubleSpinBox::down-button:pressed {
        background: #d9e7e2;
    }
    QComboBox {
        padding-right: 26px;
    }
    QLineEdit:focus,
    QComboBox:focus,
    QSpinBox:focus,
    QDoubleSpinBox:focus {
        border-color: #91b1ab;
        background: #fffefc;
    }
    QComboBox::drop-down {
        subcontrol-origin: padding;
        subcontrol-position: top right;
        border-left: 1px solid #d3dbd6;
        border-top-right-radius: 7px;
        border-bottom-right-radius: 7px;
        background: #eef4f1;
        width: 22px;
    }
    QComboBox::down-arrow {
        image: url("__CHEVRON_DOWN__");
        width: 10px;
        height: 7px;
    }
    QComboBox::drop-down:hover {
        background: #e5efeb;
    }
    QTabWidget::pane {
        border: none;
        background: transparent;
    }
    QTabBar::tab {
        background: #f3efe8;
        color: #5a6b71;
        border: 1px solid #d2d8d2;
        border-bottom: none;
        padding: 5px 10px;
        margin-right: 4px;
        border-top-left-radius: 10px;
        border-top-right-radius: 10px;
        font-size: 10px;
    }
    QTabBar::tab:selected {
        background: #faf8f4;
        color: #26353b;
        border-color: #bdc9c3;
    }
    QTabBar::tab:hover {
        background: #f6f2ec;
    }
    QTabBar#workspaceAssetTabBar::tab {
        border: 1px solid #d1d7d2;
        border-radius: 10px;
        padding: 5px 8px;
        margin-right: 4px;
        background: #f4f0e9;
        color: #40545a;
        min-width: 72px;
        max-width: 220px;
        font-size: 10px;
    }
    QTabBar#workspaceAssetTabBar::tab:selected {
        background: #faf8f4;
        border-color: #bdc9c3;
        color: #26353b;
    }
    QTabBar#workspaceAssetTabBar::tab:hover {
        background: #f6f2ec;
    }
    QFrame#settingsGroupToolbox {
        background: transparent;
        border: none;
    }
    QFrame#settingsGroupPickerCard {
        border: 1px solid #d8ddd8;
        border-radius: 12px;
        background: #fffdfa;
    }
    QLabel#settingsPickerTitle {
        background: transparent;
        color: #405158;
        font-size: 10px;
        font-weight: 800;
    }
    QWidget#settingsGroupTileGrid {
        background: transparent;
    }
    QToolButton#settingsGroupNavButton {
        min-width: __SETTINGS_TILE_CONTENT_WIDTH__px;
        min-height: __SETTINGS_TILE_CONTENT_HEIGHT__px;
        padding: 5px 3px;
        border: 1px solid #dfe4df;
        border-radius: 12px;
        background: #fbfaf7;
        color: #283840;
        font-size: 8px;
        font-weight: 700;
    }
    QToolButton#settingsGroupNavButton:hover {
        background: #f6faf8;
        border-color: #c9d8d3;
    }
    QToolButton#settingsGroupNavButton:pressed {
        background: #edf4f1;
        border-color: #aebfb9;
    }
    QToolButton#settingsGroupNavButton:checked {
        background: #eaf5f1;
        border: 1px solid #4a9a92;
        color: #24574f;
    }
    QToolButton#settingsGroupNavButton[linkedExport="true"] {
        background: #dfeeea;
        border: 1px solid #73a9a4;
        color: #1f605c;
    }
    QToolButton#settingsGroupNavButton[linkedExport="true"]:hover {
        background: #d4e9e4;
        border-color: #4a8f93;
    }
    QToolButton#settingsGroupNavButton[linkedExport="true"]:checked {
        background: #4a8f93;
        border-color: #3c7e82;
        color: #ffffff;
    }
    QToolButton#settingsGroupNavButton:disabled {
        background: #f1ede7;
        border-color: #d7ddd8;
        color: #90a0a0;
    }
    QStackedWidget#settingsGroupStackPages {
        background: transparent;
        border: none;
    }
    QProgressBar {
        border: 1px solid #cfd5d0;
        border-radius: 8px;
        background: #f3efe8;
        text-align: center;
        color: #26353b;
    }
    QProgressBar::chunk {
        background: #5b98a0;
        border-radius: 7px;
    }
    QListWidget#shellListPanel,
    QTextBrowser#shellGuideBrowser,
    QLabel#shellInsetCard {
        border: 1px solid #d3d8d3;
        border-radius: 8px;
        background: #faf8f4;
        padding: 8px;
    }
    QDialog#presetManagerDialog {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f8f4ee, stop:0.5 #f5f1ea, stop:1 #eef0ec);
    }
    QDialog#batchManagerDialog {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f8f4ee, stop:0.5 #f5f1ea, stop:1 #eef0ec);
    }
    QDialog#batchManagerDialog QGroupBox {
        margin-top: 10px;
        border: 1px solid #d3d8d3;
        border-radius: 10px;
        background: #fffdfa;
        font-size: 10px;
        font-weight: 700;
    }
    QDialog#batchManagerDialog QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 10px;
        padding: 0 4px;
        color: #405158;
        background: #f5f1ea;
    }
    QListWidget#batchQueueList {
        border: 1px solid #d3d8d3;
        border-radius: 8px;
        background: #fffdfa;
        padding: 5px;
    }
    QListWidget#batchQueueList::item {
        min-height: 20px;
        border-radius: 5px;
        padding: 2px 5px;
    }
    QListWidget#batchQueueList::item:selected {
        background: #e8f2ee;
        color: #254b4d;
    }
    QProgressBar#batchProgressBar {
        border: 1px solid #cfd5d0;
        border-radius: 7px;
        background: #f3efe8;
    }
    QProgressBar#batchProgressBar::chunk {
        border-radius: 6px;
        background: #4a8f93;
    }
    QLabel#batchStatusText {
        color: #52686e;
        font-size: 10px;
    }
    QLabel#batchWarningText {
        color: #805f30;
        font-size: 10px;
    }
    QSplitter#presetManagerSplitter::handle {
        background: #dfe5e1;
        width: __SPLITTER_WIDTH__px;
        margin: 12px 0;
        border-radius: 2px;
    }
    QSplitter#presetManagerSplitter::handle:hover {
        background: #b9cac4;
    }
    QFrame#presetManagerCard {
        border: 1px solid #d3d8d3;
        border-radius: 8px;
        background: #fbfaf6;
    }
    QDialog#presetManagerDialog QPlainTextEdit {
        border: 1px solid #d1d7d2;
        border-radius: 7px;
        background: #fbf9f4;
        color: #26353b;
        padding: 8px;
        font-size: 10px;
    }
    QListWidget#workspaceAssetList {
        border: 1px solid #d3d8d3;
        border-radius: 8px;
        background: #faf8f4;
        padding: 6px;
    }
    QLabel#workspaceEmptyImportCard {
        border: 1px dashed #d8dedb;
        border-radius: 8px;
        background: #fbfaf7;
        color: #7c8b8d;
        font-size: 10px;
        font-weight: 600;
        padding: 12px;
    }
    QComboBox#workspaceSectionCombo {
        min-height: 22px;
        max-height: 22px;
        border-radius: 8px;
        padding: 1px 24px 1px 8px;
        font-size: 10px;
        background: #fffdfa;
        border: 1px solid #d1d8d2;
    }
    QToolButton#workspacePagerButton {
        min-width: 22px;
        max-width: 22px;
        min-height: 22px;
        max-height: 22px;
        padding: 0;
        border: 1px solid #d1d8d2;
        border-radius: 8px;
        background: #fffdfa;
        color: #38555c;
        font-size: 15px;
        font-weight: 800;
    }
    QToolButton#workspacePagerButton:hover {
        background: #f5faf7;
        border-color: #abc1ba;
    }
    QToolButton#workspacePagerButton:disabled {
        background: #f5f2ec;
        border-color: #e0ddd7;
        color: #b5bfbd;
    }
    QToolButton#workspaceMoreButton {
        min-height: 24px;
        max-height: 24px;
        padding: 0 10px;
        border: 1px solid #d1d8d2;
        border-radius: 8px;
        background: #fffdfa;
        color: #38555c;
        font-size: 10px;
        font-weight: 700;
    }
    QToolButton#workspaceMoreButton:hover {
        background: #f5faf7;
        border-color: #abc1ba;
    }
    QToolButton#workspaceMoreButton:disabled {
        background: #f5f2ec;
        border-color: #e0ddd7;
        color: #b5bfbd;
    }
    QListWidget#workspaceAssetList::item {
        border: 1px solid transparent;
        border-radius: 7px;
        padding: 6px 8px;
        margin: 1px 0;
        color: #1b3d43;
    }
    QListWidget#workspaceAssetList::item:hover {
        background: #f5f1ea;
        border-color: #d9ddd9;
    }
    QListWidget#workspaceAssetList::item:selected {
        background: #f2f5f2;
        border-color: #b6c5bf;
        color: #26353b;
    }
    QWidget#settingsPanelViewport {
        background: transparent;
    }
    QFrame#workspaceAssetTabsCard,
    QFrame#workspaceExportCard,
    QFrame#webSourcesCard,
    QFrame#webSourcesSectionCard,
    QFrame#settingsHeaderCard,
    QFrame#controlStripRoot,
    QFrame#shellGuideCard {
        border: 1px solid #d3d8d3;
        border-radius: 12px;
        background: #fffdfa;
    }
    QFrame#webSourcesSectionCard {
        background: #fbfaf7;
        border-color: #d5dcd5;
    }
    QFrame#webSourcesSectionCard QLabel#shellTitle {
        font-size: 10px;
        font-weight: 800;
        color: #213940;
    }
    QFrame#webSourcesSectionCard QLabel#shellHint {
        font-size: 9px;
        color: #65777c;
    }
    QFrame#webSourcesSectionCard QLineEdit,
    QFrame#webSourcesSectionCard QComboBox {
        min-height: 24px;
        max-height: 24px;
        border-radius: 8px;
        background: #fffdfa;
        border: 1px solid #d1d8d2;
    }
    QFrame#webSourcesSectionCard QPushButton,
    QFrame#webSourcesSectionCard QToolButton {
        min-height: 24px;
        max-height: 24px;
        border-radius: 8px;
        padding: 2px 10px;
        background: #fffdfa;
        border: 1px solid #d1d8d2;
        font-size: 10px;
        font-weight: 600;
    }
    QFrame#webSourcesSectionCard QPushButton:hover,
    QFrame#webSourcesSectionCard QToolButton:hover {
        background: #f5faf7;
        border-color: #abc1ba;
    }
    QPushButton#webSourcesPrimaryAction {
        background: #e8f3ef;
        border-color: #9dbab2;
        color: #285d5b;
        font-weight: 800;
    }
    QLabel#webSourcesCountBadge {
        border: 1px solid #d2d9d3;
        border-radius: 8px;
        background: #f5f3ed;
        color: #5a6d72;
        padding: 3px 7px;
        font-size: 9px;
        font-weight: 700;
    }
    QListWidget#webSourcesIndexList,
    QTreeWidget#webSourcesSavedTree,
    QTreeWidget#webSourcesResultsTree,
    QPlainTextEdit#webSourcesUrlList {
        border: 1px solid #d2d9d3;
        border-radius: 9px;
        background: #fffdfa;
        padding: 5px;
        color: #243940;
        font-size: 10px;
    }
    QListWidget#webSourcesIndexList::item,
    QTreeWidget#webSourcesSavedTree::item,
    QTreeWidget#webSourcesResultsTree::item {
        min-height: 20px;
        border-radius: 5px;
        padding: 2px 5px;
    }
    QListWidget#webSourcesIndexList::item:selected,
    QTreeWidget#webSourcesSavedTree::item:selected,
    QTreeWidget#webSourcesResultsTree::item:selected {
        background: #e8f2ee;
        color: #254b4d;
    }
    QTreeWidget#webSourcesResultsTree QHeaderView::section {
        background: #f2f0ea;
        color: #465b61;
        border: none;
        border-bottom: 1px solid #d3dad4;
        padding: 4px 6px;
        font-size: 9px;
        font-weight: 700;
    }
    QFrame#previewPanelFrame {
        border: 1px solid #cfd8d4;
        border-radius: 14px;
        background: #fffefd;
    }
    QLabel#shellTitle {
        background: transparent;
        color: #27353b;
        font-size: 11px;
        font-weight: 700;
    }
    QLabel#shellSubtitle,
    QLabel#shellHint {
        background: transparent;
        color: #6f7c81;
        font-size: 10px;
    }
    QLabel#shellBadge {
        border: 1px solid #d1d7d2;
        border-radius: 999px;
        background: #f5f2ec;
        color: #496068;
        padding: 3px 8px;
        font-size: 9px;
        font-weight: 700;
    }
    QLabel#shellBadgeAccent {
        border: 1px solid #bccbc4;
        border-radius: 999px;
        background: #eef2ef;
        color: #3f675f;
        padding: 3px 8px;
        font-size: 9px;
        font-weight: 700;
    }
    QLabel#shellBadgeWarm {
        border: 1px solid #c9cfc9;
        border-radius: 999px;
        background: #f3efe8;
        color: #627277;
        padding: 3px 8px;
        font-size: 9px;
        font-weight: 700;
    }
    QLabel#exportSizeBadge {
        border: 1px solid #c5d0cb;
        border-radius: 7px;
        background: #f2f4ef;
        color: #5f7075;
        padding: 4px 12px;
        font-size: 9px;
        font-weight: 700;
        min-height: 16px;
    }
    QToolButton#exportBarMenuAction {
        min-width: 40px;
        min-height: 20px;
        max-height: 20px;
        padding: 2px 18px 2px 9px;
        border: 1px solid #d1d8d2;
        border-radius: 7px;
        background: #fffdfa;
        color: #38555c;
        font-size: 10px;
        font-weight: 700;
    }
    QToolButton#exportBarMenuAction:hover {
        background: #f5faf7;
        border-color: #abc1ba;
    }
    QToolButton#exportBarMenuAction:disabled {
        background: #f5f2ec;
        border-color: #e0ddd7;
        color: #a9b6b4;
    }
    QToolButton#exportBarMenuAction::menu-indicator {
        subcontrol-origin: padding;
        subcontrol-position: right center;
        width: 10px;
    }
    QToolButton#shellWarmToggle {
        min-height: 22px;
        padding: 2px 10px;
        border: 1px solid #c2cdc8;
        border-radius: 7px;
        background: #f3efe8;
        color: #627277;
        font-weight: 700;
    }
    QToolButton#shellWarmToggle:checked {
        background: #e9efeb;
        border-color: #a8b9b2;
        color: #4a6462;
    }
    QToolButton#previewPaneResetButton {
        min-height: 20px;
        padding: 2px 8px;
        border: 1px solid #d2d8d3;
        border-radius: 7px;
        background: #faf8f4;
        color: #5d6f75;
        font-size: 10px;
    }
    QToolButton#previewPaneResetButton:hover {
        border-color: #bcc9c2;
        background: #f6f3ed;
    }
    QPushButton#settingsResetButton {
        min-height: 22px;
        padding: 3px 10px;
        border-radius: 7px;
        font-size: 10px;
    }
    QToolButton {
        min-width: 0;
    }
    QFrame#controlStripGroup {
        border: 1px solid #d8ddd8;
        border-radius: 8px;
        background: #f8f6f1;
    }
    QLabel#controlStripEyebrow {
        color: #7a7f7b;
        font-size: 8px;
        font-weight: 700;
        letter-spacing: 0.08em;
    }
    QLabel#controlStripSummary {
        color: #2a3a41;
        font-size: 9px;
        font-weight: 600;
    }
    QLabel#controlStripSectionLabel {
        color: #7b8585;
        font-size: 8px;
        font-weight: 700;
        letter-spacing: 0.05em;
    }
    QLabel#controlStripHeaderBadge {
        border-radius: 7px;
        border: 1px solid #d2d8d3;
        background: #f3efe8;
        color: #55686e;
        padding: 2px 8px;
        font-size: 9px;
        font-weight: 700;
    }
    QLabel#controlStripHeaderBadge[tone="disabled"] {
        border: 1px solid #d8e1e3;
        background: #f4f7f8;
        color: #6f878c;
    }
    QLabel#controlStripHeaderBadge[tone="neutral"] {
        border: 1px solid #d7ddd8;
        background: #faf8f3;
        color: #55686e;
    }
    QLabel#controlStripHeaderBadge[tone="ready"] {
        border: 1px solid #cfe2df;
        background: #edf7f5;
        color: #17584e;
    }
    QLabel#controlStripHeaderBadge[tone="queued"] {
        border: 1px solid #e6d7ac;
        background: #fff6de;
        color: #7c5b0d;
    }
    QLabel#controlStripHeaderBadge[tone="running"] {
        border: 1px solid #c9d9f2;
        background: #e9f1ff;
        color: #29508c;
    }
    QToolButton#controlStripChip,
    QToolButton#controlStripToggle,
    QPushButton#controlStripSecondaryAction,
    QToolButton#controlStripSecondaryAction {
        min-height: 22px;
        padding: 3px 8px;
        border: 1px solid #d1d7d2;
        border-radius: 7px;
        background: #faf8f3;
        color: #294047;
        font-weight: 600;
        font-size: 9px;
    }
    QToolButton#controlStripHeaderMenuAction,
    QToolButton#controlStripMenuAction {
        padding: 3px 18px 3px 8px;
        border: 1px solid #d1d7d2;
        border-radius: 7px;
        background: #faf8f3;
        color: #294047;
        font-weight: 600;
        font-size: 9px;
    }
    QToolButton#controlStripHeaderMenuAction {
        min-width: 58px;
        min-height: 18px;
    }
    QToolButton#controlStripMenuAction {
        min-height: 22px;
    }
    QToolButton#controlStripChip:checked,
    QToolButton#controlStripToggle:checked {
        border-color: #c4d5ce;
        background: #eef4f0;
        color: #40635d;
    }
    QPushButton#controlStripPrimaryAction {
        min-height: 22px;
        padding: 3px 10px;
        border: 1px solid #417d81;
        border-radius: 7px;
        background: #4a8f93;
        color: #ffffff;
        font-weight: 700;
        font-size: 9px;
    }
    QPushButton#controlStripPrimaryAction:disabled {
        background: #c7d1cf;
        border-color: #c7d1cf;
        color: #f2f5f4;
    }
    QToolButton#controlStripHeaderMenuAction::menu-indicator,
    QToolButton#controlStripMenuAction::menu-indicator {
        subcontrol-origin: padding;
        subcontrol-position: right center;
        width: 10px;
    }
    QWidget#settingsGroupPage {
        border: 1px solid #d8ddd8;
        border-radius: 12px;
        background: #fffdfa;
    }
    QWidget#settingsGroupControls {
        background: transparent;
    }
    QWidget#settingsEditorRow {
        background: transparent;
    }
    QLabel#settingsSourceInfo {
        background: #f1f7f4;
        border: 1px solid #cfddd7;
        border-radius: 7px;
        color: #45635f;
        padding: 6px 8px;
        font-size: 9px;
    }
    QToolButton#settingsInlineResetButton {
        min-width: 22px;
        max-width: 22px;
        min-height: 22px;
        max-height: 22px;
        padding: 0;
        border: 1px solid #b8cbc5;
        border-radius: 7px;
        background: #edf5f2;
        color: #2d6862;
    }
    QToolButton#settingsInlineResetButton:hover {
        background: #dcece7;
        border-color: #6eaaa3;
    }
    QLabel#settingsEditorTitle {
        background: transparent;
        color: #253840;
        font-size: 12px;
        font-weight: 800;
    }
    QLabel#previewCanvas {
        border: 1px dashed #bfcfca;
        border-radius: 12px;
        background: #fffefd;
        color: #25343d;
        font-size: 11px;
        font-weight: 700;
    }
    QFrame#previewPaneContainer {
        background: transparent;
        border: none;
    }
    QLabel#previewAnimBadge {
        background: #5e99a0;
        color: #ffffff;
        padding: 3px 7px;
        border-radius: 7px;
        font-size: 9px;
        font-weight: 700;
    }
    QLabel#settingsHelpText {
        background: transparent;
        color: #707d82;
        font-size: 10px;
    }
    QLabel#settingsLockLabel {
        color: #8b6748;
        background: #fcf0e4;
        border: 1px solid #dfc3a0;
        border-radius: 7px;
        padding: 7px 10px;
    }
    QScrollArea {
        background: transparent;
    }
    QScrollBar:vertical {
        width: 10px;
        margin: 2px;
        border: none;
        background: transparent;
    }
    QScrollBar::handle:vertical {
        min-height: 28px;
        border-radius: 4px;
        background: #c5cfca;
    }
    QScrollBar::handle:vertical:hover {
        background: #aebdb7;
    }
    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical,
    QScrollBar::sub-page:vertical {
        height: 0;
        background: transparent;
    }
    QScrollBar:horizontal {
        height: 10px;
        margin: 2px;
        border: none;
        background: transparent;
    }
    QScrollBar::handle:horizontal {
        min-width: 28px;
        border-radius: 4px;
        background: #c5cfca;
    }
    QScrollBar::handle:horizontal:hover {
        background: #aebdb7;
    }
    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal,
    QScrollBar::add-page:horizontal,
    QScrollBar::sub-page:horizontal {
        width: 0;
        background: transparent;
    }
    """
    replacements = {
        "__CHEVRON_DOWN__": chevron_down,
        "__CHEVRON_UP__": chevron_up,
        "__CANVAS__": SHELL_PALETTE.canvas,
        "__CANVAS_COOL__": SHELL_PALETTE.canvas_cool,
        "__TOOLBAR__": SHELL_PALETTE.toolbar,
        "__TEXT__": SHELL_PALETTE.text,
        "__PAGE_BUTTON_CONTENT_WIDTH__": str(SHELL_GEOMETRY.page_button_width - 6),
        "__PAGE_BUTTON_CONTENT_HEIGHT__": str(SHELL_GEOMETRY.page_button_height - 10),
        "__SPLITTER_WIDTH__": str(SHELL_GEOMETRY.splitter_handle_width),
        "__SETTINGS_TILE_CONTENT_WIDTH__": str(SHELL_GEOMETRY.settings_tile_width - 8),
        "__SETTINGS_TILE_CONTENT_HEIGHT__": str(SHELL_GEOMETRY.settings_tile_height - 12),
    }
    for placeholder, value in replacements.items():
        stylesheet = stylesheet.replace(placeholder, value)
    return stylesheet
