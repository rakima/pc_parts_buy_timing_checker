# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules


tkinter_hiddenimports = collect_submodules("tkinter")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[("assets/images", "assets/images")],
    # Python 3.14 distributions can expose tkinter at runtime without letting
    # PyInstaller's static analysis discover it from the entry point.
    hiddenimports=tkinter_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Victor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
