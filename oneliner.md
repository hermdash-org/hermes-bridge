**Linux/macOS:**
```bash
curl -fsSL hermesdashboard.com/install | bash
```

**Windows (PowerShell):**
```powershell
irm hermesdashboard.com/install.ps1 | iex
```

These scripts auto-detect the platform and install Docker Engine (CLI only, no GUI):

```bash
# What the script does per platform:
Linux:   curl -fsSL https://get.docker.com | sh    # Docker Engine (free, no GUI)
macOS:   brew install colima docker && colima start  # Lightweight, no GUI
Windows: wsl --install && (install Docker inside WSL) # No Desktop needed
```

Then pulls + runs the container. **No Docker Desktop GUI. CLI only. Lighter. Free.**

Want me to write those install scripts?

Two files in the hermdocker repo:

hermdocker/
└── scripts/
    ├── install.sh      ← Linux/macOS one-liner
    └── install.ps1     ← Windows one-liner
Now commit and push:

Done. Here's your complete setup now:

What	File	One-liner
Linux/macOS install	scripts/install.sh	curl -fsSL hermesdashboard.com/install | bash
Windows install	scripts/install.ps1	irm hermesdashboard.com/install.ps1 | iex
Auto-update	docker-compose.yml	Watchtower checks every 5 min



systemctl --user restart docker-desktop 2>&1