# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['app\\main.py'],
    pathex=[],
    binaries=[],
    datas=[('app/assets', 'app/assets')],
    hiddenimports=['PySide6.QtSvg', 'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets'],
    runtime_hooks=['desktop\\runtime_test_api.py'],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='TKCrossBorderAssistantTestDebug',
    debug=True,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)
