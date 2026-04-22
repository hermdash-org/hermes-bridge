# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Hermes Runtime
Builds a standalone executable with Python + hermes-agent + bridge
"""

import sys
from PyInstaller.utils.hooks import collect_all, collect_data_files

block_cipher = None

# Collect all bridge modules
bridge_datas = []
bridge_hiddenimports = []

# Add bridge package
datas, binaries, hiddenimports = collect_all('bridge')
bridge_datas += datas
bridge_hiddenimports += hiddenimports

# Add hermes-agent if installed
try:
    hermes_datas, hermes_binaries, hermes_hiddenimports = collect_all('hermes')
    bridge_datas += hermes_datas
    bridge_hiddenimports += hermes_hiddenimports
except:
    pass

# FastAPI/Uvicorn dependencies
bridge_hiddenimports += [
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
]

a = Analysis(
    ['runtime.py'],
    pathex=[],
    binaries=[],
    datas=bridge_datas,
    hiddenimports=bridge_hiddenimports,
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
    name='hermes-runtime',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Show console for logs
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon later
)
