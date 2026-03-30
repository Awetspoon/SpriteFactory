# spritefactory_onefile.spec
# One-file PyInstaller spec for Sprite Factory (PySide6) on PyInstaller 6.x
# Hardened to avoid problematic AVIF binary extraction in onefile mode.

from __future__ import annotations

import os
from PyInstaller.building.build_main import Analysis, EXE, PYZ
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

spec_file = globals().get('__file__')
if spec_file:
    project_root = os.path.abspath(os.path.dirname(spec_file))
else:
    project_root = os.path.abspath(os.getcwd())
pathex = [project_root]

entry_script = os.path.join(project_root, "main.py")

hiddenimports = []
# Only keep the lazy-exported main-window package as an explicit hidden-import set.
# The rest of the app is imported statically from the root entrypoint.
hiddenimports += collect_submodules("image_engine_app.ui.main_window")

datas = []
datas += collect_data_files("image_engine_app", include_py_files=False)

# Bundle runtime icon files so Qt can load them directly in frozen mode.
for icon_name in ("spritefactory_pro.png", "spritefactory_pro.ico", "spritefactory.png", "spritefactory.ico"):
    icon_data = os.path.join(project_root, icon_name)
    if os.path.exists(icon_data):
        datas.append((icon_data, "."))

rthook = os.path.join(project_root, "pyinstaller_rthooks", "pyside6_plugin_path.py")
runtime_hooks = [rthook] if os.path.exists(rthook) else []

# Exclude optional Pillow AVIF modules that are not needed by Sprite Factory and can
# trigger onefile extraction failures on some systems.
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

# Defensive binary filter in case hook-collected AVIF binaries still appear.
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

# Onefile build: include binaries/datas directly in EXE and set exclude_binaries=False
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    exclude_binaries=False,
    **exe_kwargs,
)
