# No Docker Development Guide

## Setup (One Time)

```bash
cd hermdocker
./dev-setup.sh
```

This installs:
- Virtual environment
- Python dependencies
- hermes-agent
- PyInstaller

---

## Development Workflow

### Start Server:
```bash
./dev-start.sh
```

Server runs on: `http://localhost:8521`

### Stop Server:
`Ctrl+C`

---

## Build for Distribution

```bash
./build-runtime.sh
```

Output: `dist/hermes-runtime` (~100-150MB)

---

## Project Structure

```
hermdocker/
├── venv/              ← Virtual environment (gitignored)
├── bridge/            ← Your bridge code
├── runtime.py         ← Entry point
├── dev-setup.sh       ← One-time setup
├── dev-start.sh       ← Start dev server
├── build-runtime.sh   ← Build executable
└── dist/
    └── hermes-runtime ← Standalone executable
```

---

## For Users (Distribution)

Users download ONE file:
- `hermes-runtime.exe` (Windows)
- `hermes-runtime.app` (Mac)
- `hermes-runtime` (Linux)

Double-click → runs on `localhost:8521`

PWA connects automatically.

---

## Docker Removed ✅

- ❌ No Dockerfile
- ❌ No docker-compose
- ❌ No port conflicts
- ❌ No daemon issues

**Just Python + PyInstaller.**

---

## Quick Commands

| Task | Command |
|------|---------|
| Setup | `./dev-setup.sh` |
| Start dev | `./dev-start.sh` |
| Build runtime | `./build-runtime.sh` |
| Test runtime | `./dist/hermes-runtime` |

---

## Next.js Integration

Update API endpoint:
```javascript
const API_URL = 'http://localhost:8521'
```

PWA checks if runtime is running, shows download button if not.

**Done. No Docker anywhere.** 🎉
