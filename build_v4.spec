# -*- mode: python ; coding: utf-8 -*-
import os
ROOT = os.path.abspath('.')

a = Analysis(
    ['run_app.py'],
    pathex=[os.path.join(ROOT, 'app'), ROOT],
    binaries=[],
    datas=[
        ('ui', 'ui'),
        ('tools/platform-tools', 'tools/platform-tools'),
        ('tools/scrcpy', 'tools/scrcpy'),
    ],
    hiddenimports=['engine', 'features', 'server', 'main_api'],
    hookspath=[],
    runtime_hooks=[],
    excludes=['numpy', 'pandas', 'matplotlib', 'PIL', 'scipy', 'webview',
              'PyQt5', 'PySide2', 'PySide6'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="RC搞机工具箱",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=os.path.join(ROOT, 'app.ico'),
)
