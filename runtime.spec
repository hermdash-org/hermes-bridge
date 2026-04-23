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
import pathlib
spec_dir = pathlib.Path.cwd()
hermes_agent_path = str(spec_dir.parent / 'hermes-agent')
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

# Bundle hermes-agent/skills/ → skills/ inside the binary.
# skills_sync.py locates these at Path(__file__).parent.parent / "skills"
# which resolves to sys._MEIPASS/skills/ in the frozen binary.
# This is how fresh users get seeded with the 25 bundled skill categories.
skills_path = str(spec_dir.parent / 'hermes-agent' / 'skills')
if os.path.exists(skills_path):
    bridge_datas.append((skills_path, 'skills'))
    print(f"[OK] Bundling skills from {skills_path}")
else:
    print(f"[WARN] Skills directory not found at {skills_path} -- binary will have no bundled skills")

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

# ── Cython Obfuscation: swap .py source with compiled .so/.pyd ──────────
# PyInstaller used the .py files above for import analysis.
# Now we strip those .py modules from the bundle and keep only the
# compiled Cython extensions (.so on Linux/Mac, .pyd on Windows).
# This prevents anyone from extracting readable Python source.
import glob as _glob

_cython_exts = []
_cython_mod_names = set()

for _pattern in ['bridge/**/*.so', 'bridge/**/*.pyd']:
    for _filepath in _glob.glob(_pattern, recursive=True):
        _dirname = os.path.dirname(_filepath)
        _filename = os.path.basename(_filepath)
        # Extract module name: bridge/app.cpython-311-x86_64-linux-gnu.so → bridge.app
        _modname = _filename.split('.')[0]
        _fullmod = _dirname.replace(os.sep, '.') + '.' + _modname if _dirname else _modname
        _cython_mod_names.add(_fullmod)
        _cython_exts.append((_filepath, _dirname))

if _cython_mod_names:
    print(f"[OBFUSCATION] Found {len(_cython_mod_names)} Cython-compiled modules")
    # Remove .py/.pyc source versions from the pure modules list
    _before = len(a.pure)
    a.pure = [_item for _item in a.pure if _item[0] not in _cython_mod_names]
    _stripped = _before - len(a.pure)
    print(f"[OBFUSCATION] Stripped {_stripped} .py source modules from bundle")
    # Add compiled .so/.pyd extensions as binaries
    a.binaries += _cython_exts
    print(f"[OBFUSCATION] Added {len(_cython_exts)} compiled extensions to bundle")
    for _mod in sorted(_cython_mod_names):
        print(f"  🔒 {_mod}")
else:
    print("[OBFUSCATION] No Cython extensions found — bundling .py as-is")

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
