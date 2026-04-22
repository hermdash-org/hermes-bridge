# PyInstaller Runtime Build Guide

## What We're Building

**Standalone executable** that bundles:
- ✅ Python interpreter
- ✅ Your bridge code (FastAPI server)
- ✅ hermes-agent
- ✅ All dependencies

**Does NOT bundle:**
- ❌ Next.js UI (served from hermesdashboard.com)
- ❌ Heavy assets

---

## Architecture

```
PWA (hermesdashboard.com)
         ↓
    localhost:8521
         ↓
hermes-runtime.exe
├── Python
├── bridge/
├── hermes-agent
└── FastAPI server
```

---

## Build Steps

### 1. Install PyInstaller

```bash
pip install pyinstaller
```

### 2. Build Runtime

```bash
cd hermdocker
./build-runtime.sh
```

### 3. Test Runtime

```bash
./dist/hermes-runtime
```

Should see:
```
🌉 HemUI Bridge v1.0.0 on http://127.0.0.1:8521
📡 POST /chat  →  GET /chat/stream/{sid}  →  GET /chat/status/{tid}
🔑 API key: set
📌 Profile: default
```

### 4. Test from PWA

Open your Next.js app, it should connect to `localhost:8521`

---

## File Structure

```
hermdocker/
├── runtime.py          ← Entry point for PyInstaller
├── runtime.spec        ← PyInstaller configuration
├── build-runtime.sh    ← Build script
├── bridge/             ← Your existing bridge code
└── dist/
    └── hermes-runtime  ← Final executable (~100-150MB)
```

---

## Next Steps

### For Development:
- Keep using Docker (easy testing)

### For Distribution:
1. Build runtime with PyInstaller
2. Upload to GitHub Releases
3. PWA detects no local runtime → shows download button
4. User downloads runtime.exe once
5. PWA connects to localhost:8521

---

## Auto-Update Strategy

Add to `runtime.py`:

```python
import requests

def check_for_updates():
    """Check GitHub for new version"""
    response = requests.get('https://api.github.com/repos/yourname/hermes/releases/latest')
    latest = response.json()['tag_name']
    
    if latest > VERSION:
        print(f"🆕 Update available: {latest}")
        # Download and replace self
```

---

## Code Signing (Optional)

### Free Option:
Apply to [SignPath Foundation](https://signpath.org) for free OSS signing

### Paid Option:
- Sectigo: ~$65/year
- SSL.com: ~$84/year

---

## Platform-Specific Builds

**Windows:**
```bash
pyinstaller runtime.spec
# Output: dist/hermes-runtime.exe
```

**Mac:**
```bash
pyinstaller runtime.spec
# Output: dist/hermes-runtime.app
```

**Linux:**
```bash
pyinstaller runtime.spec
# Output: dist/hermes-runtime
```

Build on each platform to get native executables.

---

## Troubleshooting

### "Module not found" errors
Add to `runtime.spec` hiddenimports:
```python
hiddenimports=['missing_module']
```

### Large file size
Use UPX compression (already enabled in spec)

### Antivirus warnings
- Use SignPath Foundation (free)
- Or build reputation over time

---

## Summary

**You now have:**
- ✅ Standalone runtime (no Docker for users)
- ✅ Small executable (~100-150MB)
- ✅ PWA for UI (instant updates)
- ✅ Auto-update capability
- ✅ Cross-platform support

**Docker eliminated for distribution. ✨**
