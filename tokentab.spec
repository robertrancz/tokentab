# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for a standalone TokenTab executable."""

from PyInstaller.utils.hooks import collect_all, collect_data_files

block_cipher = None

textual_datas, textual_binaries, textual_hiddenimports = collect_all("textual")
rich_datas, rich_binaries, rich_hiddenimports = collect_all("rich")
keyring_datas, keyring_binaries, keyring_hiddenimports = collect_all("keyring")

tokentab_datas = collect_data_files("tokentab")

a = Analysis(
    ["src/tokentab/__main__.py"],
    pathex=[],
    binaries=textual_binaries + rich_binaries + keyring_binaries,
    datas=textual_datas + rich_datas + keyring_datas + tokentab_datas,
    hiddenimports=textual_hiddenimports
    + rich_hiddenimports
    + keyring_hiddenimports
    + [
        "tokentab",
        "tokentab.cli",
        "tokentab.app",
        "tokentab.ui.overview",
        "tokentab.ui.models_view",
        "tokentab.ui.sources",
        "tokentab.ui.seats_view",
        "tokentab.ui.forecast_view",
        "keyring.backends",
        "keyring.backends.Windows",
        "win32ctypes",
        "win32ctypes.core",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="tokentab",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
