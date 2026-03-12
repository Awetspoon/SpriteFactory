# spritefactory.spec
# Stable PyInstaller spec for Sprite Factory (PySide6) on PyInstaller 6.x
# - Avoids deprecated Qt helper imports (collect_qt_plugins/collect_qt_translations)
# - Relies on PyInstaller's built-in PySide6 hooks to bundle Qt plugins
# - Adds runtime hook to ensure Qt plugin path is set correctly at runtime
# - Excludes optional Pillow AVIF module/plugin not required by Sprite Factory

from __future__ import annotations

import os
from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

spec_file = globals().get('__file__')
if spec_file:
    project_root = os.path.abspath(os.path.dirname(spec_file))
else:
    project_root = os.path.abspath(os.getcwd())
src_root = os.path.join(project_root, "image_engine_app")
pathex = [src_root]

entry_script = os.path.join(src_root, "app", "main.py")

# Your internal packages (ensure dynamic imports are included)
hiddenimports = []
hiddenimports += collect_submodules("app")
hiddenimports += collect_submodules("ui")
hiddenimports += collect_submodules("engine")

# Bundle non-.py package data (if any)
datas = []
datas += collect_data_files("app", include_py_files=False)
datas += collect_data_files("ui", include_py_files=False)
datas += collect_data_files("engine", include_py_files=False)

# Bundle runtime icon files so Qt can load them directly in frozen mode.
for icon_name in ("spritefactory.png", "spritefactory.ico"):
    icon_data = os.path.join(project_root, icon_name)
    if os.path.exists(icon_data):
        datas.append((icon_data, "."))

# Runtime hook: fixes Qt plugin lookup when running from dist/
rthook = os.path.join(project_root, "pyinstaller_rthooks", "pyside6_plugin_path.py")
runtime_hooks = [rthook] if os.path.exists(rthook) else []

# Exclude optional Pillow AVIF modules not needed by this app.
excludes = [
    "PIL.AvifImagePlugin",
    "PIL._avif",
]

a = Analysis(
    [entry_script],
    pathex=pathex,
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=runtime_hooks,
    excludes=excludes,
    noarchive=False,
)

# Defensive filter for any hook-collected AVIF binary remnants.
_filtered_binaries = []
for item in a.binaries:
    blob = " ".join(str(part).lower() for part in item if isinstance(part, (str, bytes)))
    if "pil" in blob and "avif" in blob:
        continue
    _filtered_binaries.append(item)
a.binaries = _filtered_binaries

pyz = PYZ(a.pure)

exe_kwargs = dict(
    name="SpriteFactory",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

icon_file = os.path.join(project_root, "spritefactory.ico")
if os.path.exists(icon_file):
    exe_kwargs["icon"] = icon_file

version_file = os.path.join(project_root, "pyinstaller_version_info.py")
if os.path.exists(version_file):
    try:
        from PyInstaller.utils.win32 import versioninfo as pyi_versioninfo
        pyi_versioninfo.load_version_info_from_text_file(version_file)
        exe_kwargs["version"] = version_file
    except Exception:
        # Keep build functional when version text is not PyInstaller-evaluable.
        pass

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    **exe_kwargs,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="SpriteFactory",
)
