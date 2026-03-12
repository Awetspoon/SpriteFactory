# UTF-8
#
# Windows version info for PyInstaller.
# Edit version numbers/strings here when you cut a release.

from PyInstaller.utils.win32.versioninfo import (
    VSVersionInfo,
    FixedFileInfo,
    StringFileInfo,
    StringTable,
    StringStruct,
    VarFileInfo,
    VarStruct,
)

VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=(1, 0, 3, 0),
        prodvers=(1, 0, 3, 0),
        mask=0x3F,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "040904B0",
                    [
                        StringStruct("CompanyName", "Marcus Apps"),
                        StringStruct("FileDescription", "Sprite Factory"),
                        StringStruct("FileVersion", "1.0.3"),
                        StringStruct("InternalName", "SpriteFactory"),
                        StringStruct("OriginalFilename", "SpriteFactory.exe"),
                        StringStruct("ProductName", "Sprite Factory"),
                        StringStruct("ProductVersion", "1.0.3"),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)
