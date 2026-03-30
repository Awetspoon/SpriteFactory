"""Shared application stylesheet for the Sprite Factory shell."""

from __future__ import annotations


def build_app_stylesheet() -> str:
    """Return the shared stylesheet used across the desktop shell."""

    return """
    QMainWindow#imageEngineMainWindow,
    QWidget#mainShellCentral,
    QWidget#shellHelperPage,
    QWidget#workspacePage {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f8f4ee, stop:0.5 #f5f1ea, stop:1 #eef0ec);
        color: #2b383d;
    }
    QWidget {
        color: #2b383d;
        selection-background-color: #e6ece8;
        selection-color: #243237;
    }
    QToolBar#shellTopToolbar {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f8f1e8, stop:0.42 #f6f2eb, stop:1 #edf0ed);
        border: none;
        border-bottom: 1px solid #cfd4cf;
        spacing: 5px;
        padding: 6px 10px;
    }
    QToolBar#shellTopToolbar::separator {
        background: #d0d6d2;
        width: 1px;
        margin: 6px 6px;
    }
    QFrame#toolbarBrandLockup {
        border: 1px solid #ced4cf;
        border-radius: 16px;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #fbf8f2, stop:0.55 #f6f4ef, stop:1 #eef2f0);
    }
    QLabel#toolbarBrandMark {
        border: 1px solid #94b8ba;
        border-radius: 14px;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #7aaeb1, stop:1 #4b8b90);
        color: #ffffff;
        font-weight: 800;
        font-size: 11px;
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
        font-size: 9px;
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
        padding: 3px 8px;
        font-size: 9px;
        font-weight: 700;
    }
    QToolButton#toolbarMenuButton,
    QToolBar#shellTopToolbar QToolButton {
        min-height: 22px;
        padding: 2px 8px;
        border: 1px solid #d2d7d2;
        border-radius: 10px;
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #fbf9f4, stop:1 #f3f0ea);
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
    QComboBox#toolbarModeCombo,
    QToolBar#shellTopToolbar QComboBox {
        min-height: 22px;
        padding: 2px 8px;
        border: 1px solid #d2d7d2;
        border-radius: 10px;
        background: #fbf9f4;
        color: #273840;
        font-size: 10px;
    }
    QToolBar#shellTopToolbar QComboBox::drop-down {
        border: none;
        width: 18px;
    }
    QToolButton#toolbarMenuButton::menu-indicator {
        width: 8px;
    }
    QFrame#workspaceRailShell,
    QFrame#workspaceEditorShell,
    QFrame#workspaceInspectorShell {
        border: 1px solid #d4d8d3;
        border-radius: 22px;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f9f5ef, stop:0.5 #f5f1ea, stop:1 #eef1ed);
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
        border-radius: 10px;
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
        border-radius: 10px;
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
        border-radius: 10px;
        background: #fbf9f4;
        color: #26353b;
        padding: 2px 8px;
        font-size: 10px;
    }
    QLineEdit:focus,
    QComboBox:focus,
    QSpinBox:focus,
    QDoubleSpinBox:focus {
        border-color: #91b1ab;
        background: #fffefc;
    }
    QComboBox::drop-down {
        border: none;
        width: 18px;
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
    QWidget#settingsGroupNavRail {
        background: transparent;
    }
    QPushButton#settingsGroupNavButton {
        min-height: 30px;
        padding: 5px 14px;
        border: 1px solid #ccd4ce;
        border-radius: 13px;
        background: #f6f1ea;
        color: #304047;
        font-size: 10px;
        font-weight: 700;
        text-align: left;
    }
    QPushButton#settingsGroupNavButton:hover {
        background: #faf6f0;
        border-color: #bcc8c1;
    }
    QPushButton#settingsGroupNavButton:pressed {
        background: #ede7dd;
        border-color: #aebbb4;
    }
    QPushButton#settingsGroupNavButton:checked {
        background: #edf2ee;
        border-color: #b3c4bc;
        color: #305851;
    }
    QPushButton#settingsGroupNavButton:disabled {
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
        border-radius: 14px;
        background: #faf8f4;
        padding: 8px;
    }
    QDialog#presetManagerDialog {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f8f4ee, stop:0.5 #f5f1ea, stop:1 #eef0ec);
    }
    QFrame#presetManagerCard {
        border: 1px solid #d3d8d3;
        border-radius: 18px;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #faf8f4, stop:0.55 #f5f1ea, stop:1 #eef1ed);
    }
    QDialog#presetManagerDialog QPlainTextEdit {
        border: 1px solid #d1d7d2;
        border-radius: 12px;
        background: #fbf9f4;
        color: #26353b;
        padding: 8px;
        font-size: 10px;
    }
    QListWidget#workspaceAssetList {
        border: 1px solid #d3d8d3;
        border-radius: 14px;
        background: #faf8f4;
        padding: 6px;
    }
    QListWidget#workspaceAssetList::item {
        border: 1px solid transparent;
        border-radius: 10px;
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
    QFrame#workspaceAssetTabsCard,
    QFrame#workspaceExportCard,
    QFrame#webSourcesCard,
    QFrame#settingsHeaderCard,
    QFrame#controlStripRoot,
    QFrame#shellGuideCard {
        border: 1px solid #d3d8d3;
        border-radius: 18px;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #faf8f4, stop:0.55 #f5f1ea, stop:1 #eef1ed);
    }
    QFrame#previewPanelFrame {
        border: 1px solid #cfd8d4;
        border-radius: 18px;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #fffefd, stop:0.55 #fbfaf7, stop:1 #f5f8f8);
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
    QWidget#toolbarPresetStrip {
        background: transparent;
        border: none;
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
        border-radius: 12px;
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f5f2ed, stop:1 #ecefe9);
        color: #5f7075;
        padding: 4px 12px;
        font-size: 9px;
        font-weight: 700;
        min-height: 24px;
    }
    QToolButton#shellWarmToggle {
        min-height: 22px;
        padding: 2px 10px;
        border: 1px solid #c2cdc8;
        border-radius: 12px;
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
        border-radius: 10px;
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
        border-radius: 10px;
        font-size: 10px;
    }
    QToolButton {
        min-width: 0;
    }
    QFrame#controlStripGroup {
        border: 1px solid #d8ddd8;
        border-radius: 14px;
        background: #f7f4ee;
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
        border-radius: 999px;
        border: 1px solid #d2d8d3;
        background: #f3efe8;
        color: #55686e;
        padding: 4px 10px;
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
        border-radius: 10px;
        background: #faf8f3;
        color: #294047;
        font-weight: 600;
        font-size: 9px;
    }
    QToolButton#controlStripMenuAction {
        min-height: 22px;
        padding: 3px 18px 3px 8px;
        border: 1px solid #d1d7d2;
        border-radius: 10px;
        background: #faf8f3;
        color: #294047;
        font-weight: 600;
        font-size: 9px;
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
        border-radius: 10px;
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
    QToolButton#controlStripMenuAction::menu-indicator {
        subcontrol-origin: padding;
        subcontrol-position: right center;
        width: 10px;
    }
    QWidget#settingsGroupPage,
    QWidget#settingsGroupControls {
        background: transparent;
    }
    QLabel#previewCanvas {
        border: 1px dashed #9fb4af;
        border-radius: 12px;
        background: transparent;
        color: #5f7278;
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
        border-radius: 10px;
        padding: 7px 10px;
    }
    QScrollArea {
        background: transparent;
    }
    QSplitter#workspaceShellSplitter::handle:horizontal {
        background: #cad3ce;
        border-radius: 4px;
        margin: 22px 0;
    }
    QSplitter#workspaceEditorSplitter::handle:vertical {
        background: #cad3ce;
        border-radius: 3px;
        margin: 6px 0;
    }
    """
