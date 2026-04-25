"""
Silent Auto-Updater for Hermes Runtime
=======================================
Runs as a background daemon thread. Periodically checks R2 for new versions,
downloads the binary, and swaps it in place on disk.

CRITICAL: The updater NEVER restarts the running process. The new binary
sits on disk until the next natural restart (user closes app, system reboot,
or user clicks "Update Now" in the dashboard). This prevents mid-session
crashes that kill active chats.

Flow:
  1. Background thread wakes every CHECK_INTERVAL seconds
  2. Fetches version.json from R2 (tiny file, ~50 bytes)
  3. Compares with local VERSION
  4. If newer -> downloads binary, verifies checksum, swaps on disk
  5. Sets update_available flag -> dashboard shows "Update ready" banner
  6. On next startup, the new binary loads automatically
"""

import sys
import os
import time
import hashlib
import platform
import subprocess
import threading
import logging
import tempfile
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger("hermes.updater")

# ── Update state (thread-safe: only written by updater thread) ──────────
_update_pending = False
_update_version = None

# ─── Configuration ──────────────────────────────────────────────────────
R2_PUBLIC_URL = "https://dl.hermdash.com"
VERSION_URL = f"{R2_PUBLIC_URL}/version.json"
CHECK_INTERVAL = 3600  # Check every 1 hour (seconds)
DOWNLOAD_TIMEOUT = 180  # 3 min timeout for binary download
VERSION_CHECK_TIMEOUT = 10  # 10s timeout for version check

# Import local version
try:
    from version import VERSION
except ImportError:
    VERSION = "0.0.0"


# ─── Helpers ────────────────────────────────────────────────────────────

def _parse_version(v: str) -> tuple:
    """Parse semver string to comparable tuple. e.g. '1.2.3' → (1, 2, 3)"""
    try:
        parts = v.strip().lstrip("v").split(".")
        return tuple(int(p) for p in parts)
    except (ValueError, AttributeError):
        return (0, 0, 0)


def _get_platform_key() -> str:
    """Return the R2 object key for the current platform's binary."""
    if sys.platform == "win32":
        return "windows.exe"
    elif sys.platform == "darwin":
        return "mac"
    else:
        return "linux"


def _get_current_binary_path() -> Path:
    """Get path to the currently running binary."""
    if getattr(sys, 'frozen', False):
        # PyInstaller frozen executable
        return Path(sys.executable)
    else:
        # Running as script (dev mode) — no update needed
        return None


def _get_install_dir() -> Path:
    """Get the platform-specific install directory."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Hermes"
    elif sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Hermes"
    else:
        return Path.home() / ".local" / "share" / "hermes"


def _verify_binary(path: Path) -> bool:
    """Basic verification that the downloaded file is a valid binary."""
    if not path.exists():
        return False
    size = path.stat().st_size
    # Binary should be at least 1MB and less than 200MB
    if size < 1_000_000 or size > 200_000_000:
        return False
    return True


def _restart_service():
    """
    Restart the Hermes service using the platform's service manager.
    The service manager handles stopping the old process and starting
    the new binary atomically — no manual pkill needed.
    """
    try:
        if sys.platform == "darwin":
            # macOS: launchctl kickstart -k sends SIGTERM then restarts
            subprocess.Popen(
                ["launchctl", "kickstart", "-k",
                 "gui/{}/com.hermes.runtime".format(os.getuid())],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        elif sys.platform == "win32":
            # Windows: schedule restart after short delay
            binary = _get_current_binary_path()
            if binary:
                subprocess.Popen(
                    f'taskkill /F /IM hermes-runtime.exe >nul 2>&1 & '
                    f'ping 127.0.0.1 -n 3 > nul && "{binary}"',
                    shell=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
        else:
            # Linux: systemctl restart sends SIGTERM then starts new binary
            subprocess.Popen(
                ["systemctl", "--user", "restart", "hermes-runtime.service"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
    except Exception as e:
        logger.error(f"Service restart failed: {e}")
        # Fallback: try os.execv to replace current process with new binary
        try:
            binary = _get_current_binary_path()
            if binary and binary.exists():
                os.execv(str(binary), sys.argv)
        except Exception as e2:
            logger.error(f"Fallback restart also failed: {e2}")


# ─── Core Update Logic ─────────────────────────────────────────────────

def _check_for_update() -> dict | None:
    """
    Check R2 for the latest version.
    Returns version info dict if update available, None otherwise.
    """
    if requests is None:
        logger.warning("requests library not available, skipping update check")
        return None

    try:
        # Cache-busting: timestamp param forces CDN cache miss,
        # no-cache header tells proxies to revalidate with origin.
        # Without this, Cloudflare could serve stale version.json for hours.
        import time as _t
        resp = requests.get(
            VERSION_URL,
            timeout=VERSION_CHECK_TIMEOUT,
            params={"t": int(_t.time())},
            headers={"Cache-Control": "no-cache"},
        )
        resp.raise_for_status()
        data = resp.json()

        latest = data.get("version", "0.0.0")
        sha256 = data.get("checksums", {}).get(_get_platform_key(), "")

        if _parse_version(latest) > _parse_version(VERSION):
            return {
                "version": latest,
                "sha256": sha256,
                "url": f"{R2_PUBLIC_URL}/{_get_platform_key()}"
            }
        return None

    except Exception as e:
        logger.debug(f"Version check failed (will retry): {e}")
        return None


def _download_and_apply(update_info: dict) -> bool:
    """
    Download new binary, verify checksum, swap in place, restart.
    Returns True if update was applied successfully.
    """
    binary_path = _get_current_binary_path()
    if binary_path is None:
        logger.debug("Not a frozen binary, skipping update")
        return False

    install_dir = _get_install_dir()
    install_dir.mkdir(parents=True, exist_ok=True)

    # Download to temp file in same directory (for atomic rename)
    tmp_path = binary_path.with_suffix(binary_path.suffix + ".update")

    try:
        logger.info(f"Downloading v{update_info['version']}...")

        # Cache-busting on binary download too — CDN could serve stale binary
        import time as _t
        resp = requests.get(
            update_info["url"],
            timeout=DOWNLOAD_TIMEOUT,
            stream=True,
            params={"t": int(_t.time())},
            headers={"Cache-Control": "no-cache"},
        )
        resp.raise_for_status()

        sha256 = hashlib.sha256()
        with open(tmp_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
                sha256.update(chunk)

        # Verify checksum if provided
        if update_info.get("sha256"):
            actual_hash = sha256.hexdigest()
            if actual_hash != update_info["sha256"]:
                logger.error(
                    f"Checksum mismatch: expected {update_info['sha256']}, "
                    f"got {actual_hash}"
                )
                tmp_path.unlink(missing_ok=True)
                return False

        # Verify the downloaded file looks like a valid binary
        if not _verify_binary(tmp_path):
            logger.error("Downloaded file failed validation")
            tmp_path.unlink(missing_ok=True)
            return False

        # Make executable on Unix
        if sys.platform != "win32":
            os.chmod(tmp_path, 0o755)

        # Atomic swap: rename new binary over old one
        if sys.platform == "win32":
            # Windows can't overwrite a running exe directly
            # Rename current → .old, then new → current
            old_path = binary_path.with_suffix(binary_path.suffix + ".old")
            old_path.unlink(missing_ok=True)
            try:
                os.rename(binary_path, old_path)
            except PermissionError:
                # Binary is locked, schedule update for next restart
                logger.warning("Binary locked, update will apply on next restart")
                # Leave .update file — on next startup we check for it
                return False
            os.rename(tmp_path, binary_path)
            # Clean up old binary after a delay (best effort)
            try:
                old_path.unlink(missing_ok=True)
            except Exception:
                pass
        else:
            # Unix: atomic replace
            os.replace(tmp_path, binary_path)

        logger.info(f"Updated binary on disk to v{update_info['version']}")
        logger.info("Update will take effect on next restart (NOT restarting now)")

        # Set the pending flag — dashboard can read this via /health
        global _update_pending, _update_version
        _update_pending = True
        _update_version = update_info['version']

        return True

    except Exception as e:
        logger.error(f"Update failed: {e}")
        tmp_path.unlink(missing_ok=True)
        return False


def _apply_pending_update():
    """
    Check if a .update file was left from a failed swap (Windows).
    Apply it before the server starts.
    """
    binary_path = _get_current_binary_path()
    if binary_path is None:
        return

    update_file = binary_path.with_suffix(binary_path.suffix + ".update")
    if update_file.exists() and _verify_binary(update_file):
        try:
            if sys.platform != "win32":
                os.chmod(update_file, 0o755)
            os.replace(update_file, binary_path)
            logger.info("Applied pending update from previous session")
            os.execv(str(binary_path), sys.argv)
        except Exception as e:
            logger.error(f"Failed to apply pending update: {e}")
            update_file.unlink(missing_ok=True)


# ─── Background Daemon ─────────────────────────────────────────────────

def _update_loop():
    """Main update loop — runs forever in background thread."""
    # Wait a bit after startup before first check (let server stabilize)
    time.sleep(30)

    while True:
        try:
            update_info = _check_for_update()
            if update_info:
                logger.info(
                    f"Update available: {VERSION} → {update_info['version']}"
                )
                _download_and_apply(update_info)
        except Exception as e:
            logger.error(f"Update loop error: {e}")

        time.sleep(CHECK_INTERVAL)


def start_auto_updater():
    """
    Start the silent auto-updater as a daemon thread.
    Call this once from runtime.py after the server starts.
    """
    # First, apply any pending update from a previous failed swap
    _apply_pending_update()

    # Don't run updater in dev mode
    if not getattr(sys, 'frozen', False):
        logger.debug("Dev mode detected, auto-updater disabled")
        return

    thread = threading.Thread(
        target=_update_loop,
        daemon=True,
        name="auto-updater"
    )
    thread.start()
    logger.info(f"Auto-updater started (checking every {CHECK_INTERVAL}s, restart-free)")


def is_update_available() -> dict | None:
    """
    Check if an update has been downloaded and is waiting to be applied.
    Called by the bridge's /health endpoint to inform the dashboard.
    Returns {"version": "x.y.z"} if update pending, None otherwise.
    """
    if _update_pending and _update_version:
        return {"version": _update_version}
    return None


def apply_update_now():
    """
    User clicked 'Update Now' in dashboard. Restart the service.
    Only call this when the user explicitly requests it.
    """
    if _update_pending:
        logger.info("User requested immediate update restart")
        _restart_service()


# Legacy function name for backward compatibility
def check_and_update():
    """Legacy entry point -- now just starts the background updater."""
    start_auto_updater()
