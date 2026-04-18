Now the CI/CD workflow and let me verify the final structure:

Edited docker-publish.yml

Now let me verify the final clean structure:

Ran command: `find /home/kennedy/Desktop/hermes-desktop/hermdocker -not -path '*/.git/*' -not -path '*__pycache__*' | sort | head -80`

**Clean.** Here's the before vs after:

### OLD (hemui-nextjs/bridge/) — 30+ files, platform hell:
```
❌ setup/detect.py          (Mac/Win/Linux detection)
❌ setup/install.py          (Python/git/pipx/curl auto-install)
❌ setup/path.py             (Windows %LOCALAPPDATA% vs ~/.hermes)
❌ setup/__init__.py          (setup API endpoints)
❌ service/__init__.py        (systemd/launchctl/VBS)
❌ service/linux.py           (systemd unit files)
❌ service/macos.py           (launchctl plist)  
❌ service/windows.py         (VBS startup scripts)
❌ supervisor/lifecycle.py    (process management)
❌ supervisor/pid.py          (PID files)
❌ supervisor/port.py         (port safety)
❌ bootstrap.py               (platform path injection)
❌ __main__.py                (70 lines of path sniffing)
```

### NEW (hermdocker/) — clean, no BS:
```
✅ Dockerfile                 (1 file replaces ALL of the above)
✅ docker-compose.yml         (one-command launch)
✅ docker/entrypoint.sh       (10 lines)
✅ bridge/app.py              (your API, clean)
✅ bridge/__main__.py          (5 lines)
✅ bridge/Chat/               (your meat — APIs)
✅ bridge/Sessions/           (your meat)
✅ bridge/Models/             (your meat)
✅ + Profiles, Files, Skills, Cron, Voice, Providers, OpenRouterOAuth
```

**13 platform files deleted. Zero platform code remains. Docker handles everything.**

Init the git repo?