"""Main window UI components (lazy exports to avoid eager import coupling)."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

__all__ = [
    "ApplyCoordinator",
    "BatchCoordinator",
    "ControlStrip",
    "EncodingCoordinator",
    "ExportBar",
    "ExportCoordinator",
    "ImageEngineMainWindow",
    "LocalImportCoordinator",
    "PreviewPanel",
    "PresetsBar",
    "SessionCoordinator",
    "SettingsPanel",
    "ShellCoordinator",
    "WorkspaceAssetTabs",
    "WorkspaceCoordinator",
    "WebSourcesPanel",
    "WebSourcesCoordinator",
]

_EXPORT_MODULES = {
    "ApplyCoordinator": "apply_coordinator",
    "WorkspaceAssetTabs": "asset_tabs",
    "BatchCoordinator": "batch_coordinator",
    "ControlStrip": "control_strip",
    "EncodingCoordinator": "encoding_coordinator",
    "ExportBar": "export_bar",
    "ExportCoordinator": "export_coordinator",
    "ImageEngineMainWindow": "main_window",
    "LocalImportCoordinator": "local_import_coordinator",
    "PreviewPanel": "preview_panel",
    "PresetsBar": "presets_bar",
    "SessionCoordinator": "session_coordinator",
    "SettingsPanel": "settings_panel",
    "ShellCoordinator": "shell_coordinator",
    "WorkspaceCoordinator": "workspace_coordinator",
    "WebSourcesPanel": "web_sources_panel",
    "WebSourcesCoordinator": "web_sources_coordinator",
}


def __getattr__(name: str) -> object:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(f".{module_name}", __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value


if TYPE_CHECKING:
    from .apply_coordinator import ApplyCoordinator
    from .asset_tabs import WorkspaceAssetTabs
    from .batch_coordinator import BatchCoordinator
    from .control_strip import ControlStrip
    from .encoding_coordinator import EncodingCoordinator
    from .export_bar import ExportBar
    from .export_coordinator import ExportCoordinator
    from .local_import_coordinator import LocalImportCoordinator
    from .main_window import ImageEngineMainWindow
    from .preview_panel import PreviewPanel
    from .presets_bar import PresetsBar
    from .session_coordinator import SessionCoordinator
    from .settings_panel import SettingsPanel
    from .shell_coordinator import ShellCoordinator
    from .workspace_coordinator import WorkspaceCoordinator
    from .web_sources_coordinator import WebSourcesCoordinator
    from .web_sources_panel import WebSourcesPanel
