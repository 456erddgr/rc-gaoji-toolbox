# -*- mode: python ; coding: utf-8 -*-
import os
import sys

ROOT = os.path.abspath(SPECPATH)

a = Analysis(
    [os.path.join(ROOT, 'installer', 'app.py')],
    pathex=[ROOT, os.path.join(ROOT, 'app')],
    binaries=[],
    # 主程序以 ASCII 文件名内置，安装后即 RC2Toolbox.exe
    datas=[
        (os.path.join(ROOT, 'payload_build', 'RCGaojiToolbox.exe'), 'payload'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['numpy', 'pandas', 'matplotlib', 'scipy', 'PIL',
              'PyQt5', 'PySide2', 'PySide6', 'webview'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='RC搞机工具箱-安装程序',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, 'app.ico'),
)
