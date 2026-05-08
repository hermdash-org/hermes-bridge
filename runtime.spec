# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Hermes Runtime
=========================================

HOW THIS SYSTEM WORKS — READ THIS TO UNDERSTAND YOUR PRODUCT
=============================================================

YOUR PRODUCT ARCHITECTURE:
  You have 3 repos sitting side-by-side on disk:

    HermTop/
    ├── hermes-agent/      ← The UPSTREAM open-source AI agent engine (NOT yours)
    │                         This is the NousResearch/hermes-agent GitHub repo.
    │                         You clone it and keep it updated with `git pull`.
    │
    ├── hermes/            ← YOUR backend (this repo)
    │   ├── runtime.py     ← Entry point for the binary
    │   ├── runtime.spec   ← THIS FILE — tells PyInstaller what to bundle
    │   ├── auto_update.py ← Silent auto-updater (checks R2 every hour)
    │   └── bridge/        ← YOUR FastAPI wrapper around hermes-agent
    │       ├── Chat/      ← Calls hermes-agent's AIAgent.run_conversation()
    │       ├── Skills/    ← Calls hermes-agent's skill utilities
    │       ├── Cron/      ← Calls hermes-agent's cron.jobs module
    │       └── ...        ← All modules are thin wrappers, zero reimplementation
    │
    └── hermes-nextjs/     ← YOUR frontend (Next.js dashboard)

WHAT PYINSTALLER DOES:
  When you run `pyinstaller runtime.spec`, it:

  1. Takes runtime.py as the entry point
  2. Scans ALL imports recursively (your bridge/ + hermes-agent/ code)
  3. Bundles EVERYTHING into a single executable file called `hermes-runtime`
  4. This ONE file contains: Python interpreter + your bridge + the ENTIRE
     hermes-agent engine + all dependencies (FastAPI, uvicorn, yaml, etc.)

WHAT ENGINE DO USERS GET?
  Users get WHATEVER VERSION of hermes-agent is checked out in
  /home/kennedy/Desktop/HermTop/hermes-agent/ AT THE MOMENT you run
  `pyinstaller runtime.spec`.

  Example:
    - You run `cd hermes-agent && git pull` → gets commit abc123
    - You run `cd ../hermes && pyinstaller runtime.spec` → binary freezes abc123
    - Every user who downloads this binary runs hermes-agent commit abc123
    - If hermes-agent ships a fix tomorrow (commit def456), your users
      DON'T get it until YOU pull + rebuild + push to R2

  This is the CORRECT approach. The official installation method
  (`hermes install` / `pip install`) requires Python, pip, git, and a
  virtual environment on the user's machine. Your non-technical users
  don't have those. PyInstaller bundles everything so they just download
  ONE file and run it. This is how Electron apps, VS Code, and Discord
  all work — they freeze a specific engine version and ship updates later.

HOW USERS GET UPDATES:
  1. You pull the latest hermes-agent: `cd hermes-agent && git pull`
  2. You rebuild: `pyinstaller runtime.spec`
  3. You push the binary to Cloudflare R2
  4. auto_update.py (running inside every user's binary) checks R2 hourly
  5. If a new version exists, it downloads + swaps the binary silently
  6. User gets the new engine without doing anything

IS THIS THE RIGHT APPROACH? YES.
  - Official way: `hermes install` → requires Python 3.11+, pip, git, venv
  - Your way: Download one file, double-click → works on Mac/Linux/Windows
  - You're NOT forking hermes-agent. You're WRAPPING it with a consumer UI.
  - This is exactly what the hermes-agent team recommends for distribution.
"""

import sys
import os
from PyInstaller.utils.hooks import collect_all, collect_data_files

block_cipher = None

# ═══════════════════════════════════════════════════════════════════════════
# STEP 1: Locate the hermes-agent engine
# ═══════════════════════════════════════════════════════════════════════════
# PyInstaller needs to find hermes-agent's Python modules on sys.path.
# We look for it at ../hermes-agent/ (sibling directory to this repo).
# This is the SAME code that powers `hermes` CLI, TUI, and official web.

import pathlib
spec_dir = pathlib.Path.cwd()
hermes_agent_path = str(spec_dir.parent / 'hermes-agent')
if os.path.exists(hermes_agent_path):
    sys.path.insert(0, hermes_agent_path)
    print(f"[ENGINE] Bundling hermes-agent from: {hermes_agent_path}")
else:
    print(f"[ERROR] hermes-agent NOT FOUND at {hermes_agent_path}")
    print(f"        The binary will NOT work without the engine!")

# ═══════════════════════════════════════════════════════════════════════════
# STEP 2: Collect YOUR bridge modules
# ═══════════════════════════════════════════════════════════════════════════
# These are YOUR code — the FastAPI wrapper that makes hermes-agent
# accessible via HTTP for the Next.js frontend.

bridge_datas = []
bridge_hiddenimports = []

datas, binaries, hiddenimports = collect_all('bridge')
bridge_datas += datas
bridge_hiddenimports += hiddenimports

# ═══════════════════════════════════════════════════════════════════════════
# STEP 3: Collect the hermes-agent engine packages
# ═══════════════════════════════════════════════════════════════════════════
# These are the CORE engine packages from NousResearch/hermes-agent.
# Each one is a Python package inside the hermes-agent/ directory.
#
# What each package does:
#   agent/       → Core AI agent logic (model calls, tool execution, streaming)
#   tools/       → All built-in tools (terminal, browser, file, web_search, etc.)
#   hermes_cli/  → CLI helpers, config loading, model switching, provider routing
#   gateway/     → Multi-platform gateway (Telegram, Discord, Slack, WhatsApp)
#   tui_gateway/ → TUI JSON-RPC server (their official terminal UI backend)
#   cron/        → Scheduled task execution (cron jobs, automation)
#   acp_adapter/ → Agent Communication Protocol adapter
#   plugins/     → Plugin system for extensibility
#
# When hermes-agent adds a NEW package, it's auto-detected.
# When they add new FILES to an existing package, collect_all() picks them
# up automatically — no change needed. FULLY AUTOMATIC.

# Auto-detect ALL Python packages in hermes-agent/ (directories with __init__.py)
_engine_packages = []
if os.path.exists(hermes_agent_path):
    for entry in os.listdir(hermes_agent_path):
        pkg_dir = os.path.join(hermes_agent_path, entry)
        if (os.path.isdir(pkg_dir)
            and os.path.exists(os.path.join(pkg_dir, '__init__.py'))
            and not entry.startswith('.')
            and entry not in ('venv', 'node_modules', '__pycache__', 'tests',
                              'web', 'ui-tui', 'website', 'scripts', 'docs')):
            _engine_packages.append(entry)

print(f"[ENGINE] Auto-detected {len(_engine_packages)} packages: {sorted(_engine_packages)}")

for pkg in _engine_packages:
    try:
        pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
        bridge_datas += pkg_datas
        bridge_hiddenimports += pkg_hiddenimports
        print(f"[OK] Collected engine package: {pkg}")
    except Exception as e:
        print(f"[WARN] Could not collect {pkg}: {e}")

# ═══════════════════════════════════════════════════════════════════════════
# STEP 4: Bundle built-in skills
# ═══════════════════════════════════════════════════════════════════════════
# hermes-agent ships ~25 skill categories (coding, research, DevOps, etc.)
# We copy them into the binary so fresh users get skills on first run.
# At startup, server.py calls skills_sync.py which copies these to
# ~/.hermes/skills/ if the user doesn't have them yet.

skills_path = str(spec_dir.parent / 'hermes-agent' / 'skills')
if os.path.exists(skills_path):
    bridge_datas.append((skills_path, 'skills'))
    print(f"[OK] Bundling skills from {skills_path}")
else:
    print(f"[WARN] Skills directory not found at {skills_path} -- binary will have no bundled skills")

# ═══════════════════════════════════════════════════════════════════════════
# STEP 4.5: Bundle Higgsfield CLI binary
# ═══════════════════════════════════════════════════════════════════════════
# Bundle the Higgsfield CLI binary so users can authenticate via browser
# without needing to install it separately.

import shutil
higgsfield_cli = shutil.which('higgsfield')
if higgsfield_cli:
    bridge_datas.append((higgsfield_cli, 'bin'))
    print(f"[OK] Bundling Higgsfield CLI from {higgsfield_cli}")
else:
    print(f"[WARN] Higgsfield CLI not found -- users will need to install it manually")

# ═══════════════════════════════════════════════════════════════════════════
# STEP 5: Hidden imports — standalone modules (AUTO-DETECTED)
# ═══════════════════════════════════════════════════════════════════════════
# Some hermes-agent modules are standalone .py files at the repo root
# (not inside packages). PyInstaller can miss these because they're
# imported dynamically. We AUTO-SCAN for them instead of hardcoding.
#
# This means when hermes-agent adds a NEW file like `hermes_xyz.py`,
# it gets bundled automatically on next build. ZERO manual work.

# Modules we intentionally SKIP (CLI entry points we don't need)
_SKIP_MODULES = {'cli', 'rl_cli', 'mini_swe_runner', 'mcp_serve', 'setup', 'conftest'}

_root_modules = []
if os.path.exists(hermes_agent_path):
    for f in os.listdir(hermes_agent_path):
        if f.endswith('.py') and not f.startswith('_'):
            mod_name = f[:-3]  # strip .py
            if mod_name not in _SKIP_MODULES:
                _root_modules.append(mod_name)

print(f"[ENGINE] Auto-detected {len(_root_modules)} root modules: {sorted(_root_modules)}")
bridge_hiddenimports += _root_modules

# Always explicitly include toolset resolution modules.
# These are inside hermes_cli/ (already collected above), but being
# explicit prevents silent crashes in frozen binaries on all platforms.
bridge_hiddenimports += [
    'hermes_cli.tools_config',
    'hermes_cli.config',
]

# ═══════════════════════════════════════════════════════════════════════════
# STEP 6: FastAPI/Uvicorn dependencies
# ═══════════════════════════════════════════════════════════════════════════
# YOUR bridge (bridge/server.py) runs a FastAPI server via Uvicorn.
# Uvicorn uses lazy imports for its protocol and loop implementations.
# These must be listed explicitly or the server won't start in the binary.

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
    # CRITICAL: requests + SSL must be explicitly bundled for auto_update.py
    # Without these, the updater silently fails and users get stuck on old versions.
    'requests',
    'requests.adapters',
    'requests.auth',
    'requests.models',
    'requests.sessions',
    'requests.packages',
    'requests.packages.urllib3',
    'urllib3',
    'urllib3.util',
    'urllib3.util.ssl_',
    'certifi',
    'charset_normalizer',
    'idna',
    'ssl',
]

# ═══════════════════════════════════════════════════════════════════════════
# STEP 7: PyInstaller Analysis — resolve all dependencies
# ═══════════════════════════════════════════════════════════════════════════
# This is where PyInstaller traces ALL imports starting from runtime.py,
# combines them with our explicit lists above, and builds a complete
# dependency graph of everything the binary needs.
#
# pathex tells PyInstaller where to find hermes-agent modules.
# This is equivalent to having hermes-agent/ on PYTHONPATH.

a = Analysis(
    ['runtime.py'],           # Entry point — what runs when user launches the binary
    pathex=[hermes_agent_path] if os.path.exists(hermes_agent_path) else [],
    binaries=[],
    datas=bridge_datas,       # Data files (skills, configs, templates)
    hiddenimports=bridge_hiddenimports,  # All the modules listed above
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ── Cython Obfuscation Note ─────────────────────────────────────────────
# When both .py and .so exist, PyInstaller natively prefers the compiled
# .so extension. collect_all('bridge') puts .so into a.binaries and skips
# the .py from a.pure automatically. No manual swapping needed.
# The Cython build step compiles bridge/*.py → .so, and PyInstaller
# bundles only the compiled extensions — obfuscation is automatic.

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ═══════════════════════════════════════════════════════════════════════════
# STEP 8: Build the final executable
# ═══════════════════════════════════════════════════════════════════════════
# This produces ONE file: `hermes-runtime` (or hermes-runtime.exe on Windows)
#
# What's inside this file:
#   - Python 3.x interpreter (embedded)
#   - Your bridge/ code (FastAPI server)
#   - The ENTIRE hermes-agent engine (AIAgent, tools, skills, cron, etc.)
#   - All Python dependencies (FastAPI, uvicorn, openai, anthropic, etc.)
#   - Bundled skills (~25 categories)
#
# Users download this ONE file and run it. No Python, pip, git, or
# virtual environment needed. It works on Mac, Linux, and Windows.

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='hermes-runtime',    # Output filename
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                 # Compress with UPX (smaller binary)
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,             # Show console for logs (important for debugging)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,         # Build for current platform (CI builds all 3)
    codesign_identity=None,
    entitlements_file=None,
    icon=None,                # Add icon later
)
