# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath('.')

# vgamepad 是虚拟手柄依赖（ViGEm），它有子包和动态导入，必须整包收
_vg_datas, _vg_bins, _vg_hidden = collect_all('vgamepad')

a = Analysis(
    ['run_app.py'],
    pathex=[os.path.join(ROOT, 'app'), ROOT],
    binaries=_vg_bins,
    datas=[
        ('ui', 'ui'),
        ('tools/platform-tools', 'tools/platform-tools'),
        ('tools/scrcpy', 'tools/scrcpy'),
    ] + _vg_datas,
    hiddenimports=['engine', 'features', 'server', 'main_api', 'mirror', 'gamepad'] + _vg_hidden,
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
