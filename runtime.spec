# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Hermes Runtime
Builds a standalone executable with Python + hermes-agent + bridge
"""

import sys
import os
from PyInstaller.utils.hooks import collect_all, collect_data_files

block_cipher = None

# Add hermes-agent to path if it exists
hermes_agent_path = os.path.join(os.path.dirname(__file__), '..', 'hermes-agent')
if os.path.exists(hermes_agent_path):
    sys.path.insert(0, hermes_agent_path)

# Collect all bridge modules
bridge_datas = []
bridge_hiddenimports = []

# Add bridge package
datas, binaries, hiddenimports = collect_all('bridge')
bridge_datas += datas
bridge_hiddenimports += hiddenimports

# Add all hermes-agent packages
for pkg in ['agent', 'tools', 'hermes_cli', 'gateway', 'tui_gateway', 'cron', 'acp_adapter', 'plugins']:
    try:
        pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
        bridge_datas += pkg_datas
        bridge_hiddenimports += pkg_hiddenimports
    except Exception as e:
        print(f"Warning: Could not collect {pkg}: {e}")

# Add standalone hermes-agent modules
bridge_hiddenimports += [
    'run_agent',
    'model_tools',
    'toolsets',
    'batch_runner',
    'trajectory_compressor',
    'toolset_distributions',
    'hermes_constants',
    'hermes_state',
    'hermes_time',
    'hermes_logging',
    'utils',
]

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
    pathex=[hermes_agent_path] if os.path.exists(hermes_agent_path) else [],
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
