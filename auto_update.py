"""
Silent Auto-Updater for Hermes Runtime
=======================================
Runs as a background daemon thread. Periodically checks R2 for new versions,
downloads the binary, and swaps it in place on disk.

CRITICAL: The updater NEVER restarts the running process. The new binary
sits on disk until the next natural restart (user closes app, system reboot,
or user clicks "Update Now" in the dashboard). This prevents mid-session
crashes that kill active chats.

Resilience guarantees:
  - Thread self-heals: if the update loop crashes, it restarts automatically
  - Detection is instant: flags set on version.json comparison, not download
  - Download retries: exponential backoff on failure, never gives up
  - Health-triggered: /health endpoint kicks off a check if the thread is stale
  - Fallback HTTP: uses urllib if requests isn't available (PyInstaller edge case)
  - "Update Now" only restarts when binary is ACTUALLY downloaded on disk

Flow:
  1. Background thread wakes every CHECK_INTERVAL seconds
  2. Fetches version.json from R2 (tiny file, ~50 bytes)
  3. Compares with local VERSION
  4. If newer -> sets update_available flag IMMEDIATELY
  5. Downloads binary, verifies checksum, swaps on disk (best effort)
  6. Dashboard shows "Update ready" banner with "Update Now" button
  7. On next startup (or user click), the new binary loads automatically
"""

import sys
import os
import time
import hashlib
import platform
import subprocess
import threading
import logging
import json
from pathlib import Path

try:
    import requests as _requests_lib
except ImportError:
    _requests_lib = None

logger = logging.getLogger("hermes.updater")

# ── Update state (thread-safe: only written by updater thread) ──────────
_update_pending = False
_update_version = None
_update_downloaded = False       # True once binary is swapped on disk
_last_check_time = 0             # Epoch timestamp of last version check
_check_lock = threading.Lock()   # Prevent concurrent checks
_download_failures = 0           # Consecutive download failure count
_updater_thread = None           # Reference to the updater thread
_updater_thread_lock = threading.Lock()

# ─── Configuration ──────────────────────────────────────────────────────
R2_PUBLIC_URL = "https://dl.hermdash.com"
VERSION_URL = f"{R2_PUBLIC_URL}/version.json"
CHECK_INTERVAL = 300             # Check every 5 minutes (seconds)
DOWNLOAD_TIMEOUT = 180           # 3 min timeout for binary download
VERSION_CHECK_TIMEOUT = 10       # 10s timeout for version check
STALE_CHECK_THRESHOLD = 120      # On-demand re-check if last check > 2 min ago
MAX_DOWNLOAD_RETRIES = 3         # Max retries per update loop iteration
DOWNLOAD_RETRY_BASE_DELAY = 30   # Base delay between download retries (seconds)

# Import local version
try:
    from version import VERSION
except ImportError:
    VERSION = "0.0.0"


# ─── HTTP Helpers (resilient) ───────────────────────────────────────────

def _http_get_json(url, timeout=10, params=None):
    """
    Fetch JSON from a URL. Uses requests if available, falls back to urllib.
    This ensures update checks work even if requests isn't bundled in PyInstaller.
    """
    # Build URL with cache-busting param
    cache_bust = int(time.time())
    if params is None:
        params = {}
    params["t"] = cache_bust

    if _requests_lib is not None:
        resp = _requests_lib.get(
            url, timeout=timeout, params=params,
            headers={"Cache-Control": "no-cache"},
        )
        resp.raise_for_status()
        return resp.json()
    else:
        # Fallback: stdlib urllib (always available)
        import urllib.request
        import urllib.parse
        query = urllib.parse.urlencode(params)
        full_url = f"{url}?{query}"
        req = urllib.request.Request(
            full_url,
            headers={"Cache-Control": "no-cache", "User-Agent": "Hermes-Updater"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))


def _http_download_file(url, dest_path, timeout=180, params=None):
    """
    Download a file from URL to dest_path. Uses requests if available,
    falls back to urllib. Returns SHA256 hex digest of downloaded content.
    """
    cache_bust = int(time.time())
    if params is None:
        params = {}
    params["t"] = cache_bust

    sha256 = hashlib.sha256()

    if _requests_lib is not None:
        resp = _requests_lib.get(
            url, timeout=timeout, stream=True, params=params,
            headers={"Cache-Control": "no-cache"},
        )
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
                sha256.update(chunk)
    else:
        import urllib.request
        import urllib.parse
        query = urllib.parse.urlencode(params)
        full_url = f"{url}?{query}"
        req = urllib.request.Request(
            full_url,
            headers={"Cache-Control": "no-cache", "User-Agent": "Hermes-Updater"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            with open(dest_path, "wb") as f:
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
                    sha256.update(chunk)

    return sha256.hexdigest()


# ─── Helpers ────────────────────────────────────────────────────────────

def _parse_version(v: str) -> tuple:
    """Parse semver string to comparable tuple. e.g. '1.2.3' -> (1, 2, 3)"""
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
    Restart the Hermes runtime to load the new binary.

    Strategy (in order):
      1. Try platform service manager (systemctl/launchctl) — checks exit code
      2. If service manager fails (not installed as service), use os.execv
         to replace the current process in-place with the updated binary

    os.execv is the ultimate fallback — it replaces the running process
    with the new binary at the same path. Works regardless of how the
    runtime was started (service, terminal, cron, etc.)
    """
    binary = _get_current_binary_path()
    service_restarted = False

    try:
        if sys.platform == "darwin":
            result = subprocess.run(
                ["launchctl", "kickstart", "-k",
                 "gui/{}/com.hermes.runtime".format(os.getuid())],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=5
            )
            service_restarted = (result.returncode == 0)

        elif sys.platform == "win32":
            if binary:
                # Windows: detach a new process, then exit current
                subprocess.Popen(
                    f'ping 127.0.0.1 -n 3 > nul && "{binary}"',
                    shell=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                # Give the ping delay time to start, then exit this process
                os._exit(0)

        else:
            # Linux: try systemctl first, CHECK if it actually works
            result = subprocess.run(
                ["systemctl", "--user", "restart", "hermes-runtime.service"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=10
            )
            service_restarted = (result.returncode == 0)

    except Exception as e:
        logger.warning(f"Service manager restart failed: {e}")

    if service_restarted:
        logger.info("Service manager restarted successfully")
        return

    # Fallback: os.execv replaces current process with new binary
    # This works regardless of how the runtime was started
    logger.info("Service manager unavailable, using os.execv to restart")
    try:
        if binary and binary.exists():
            logger.info(f"Restarting via os.execv: {binary}")
            os.execv(str(binary), [str(binary)])
        else:
            logger.error(f"Cannot restart: binary not found at {binary}")
    except Exception as e:
        logger.error(f"os.execv restart failed: {e}")


# ─── Core Update Logic ─────────────────────────────────────────────────

def _check_for_update() -> dict | None:
    """
    Check R2 for the latest version.
    Returns version info dict if update available, None otherwise.
    Uses _http_get_json which falls back to urllib if requests isn't available.
    """
    try:
        data = _http_get_json(VERSION_URL, timeout=VERSION_CHECK_TIMEOUT)

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
        logger.warning(f"Version check failed (will retry): {e}")
        return None


def _download_and_apply(update_info: dict) -> bool:
    """
    Download new binary, verify checksum, swap in place.
    Returns True if update was applied successfully.
    NEVER restarts — just swaps the binary on disk.
    """
    global _update_downloaded, _download_failures

    binary_path = _get_current_binary_path()
    if binary_path is None:
        logger.debug("Not a frozen binary, skipping download (update still flagged)")
        return False

    install_dir = _get_install_dir()
    install_dir.mkdir(parents=True, exist_ok=True)

    # Download to temp file in same directory (for atomic rename)
    tmp_path = binary_path.with_suffix(binary_path.suffix + ".update")

    try:
        logger.info(f"Downloading v{update_info['version']}...")

        actual_hash = _http_download_file(
            update_info["url"], tmp_path, timeout=DOWNLOAD_TIMEOUT
        )

        # Verify checksum if provided
        if update_info.get("sha256"):
            if actual_hash != update_info["sha256"]:
                logger.error(
                    f"Checksum mismatch: expected {update_info['sha256']}, "
                    f"got {actual_hash}"
                )
                tmp_path.unlink(missing_ok=True)
                _download_failures += 1
                return False

        # Verify the downloaded file looks like a valid binary
        if not _verify_binary(tmp_path):
            logger.error("Downloaded file failed validation")
            tmp_path.unlink(missing_ok=True)
            _download_failures += 1
            return False

        # Make executable on Unix
        if sys.platform != "win32":
            os.chmod(tmp_path, 0o755)

        # Atomic swap: rename new binary over old one
        if sys.platform == "win32":
            # Windows can't overwrite a running exe directly
            # Rename current -> .old, then new -> current
            old_path = binary_path.with_suffix(binary_path.suffix + ".old")
            old_path.unlink(missing_ok=True)
            try:
                os.rename(binary_path, old_path)
            except PermissionError:
                # Binary is locked, schedule update for next restart
                logger.warning("Binary locked, update will apply on next restart")
                # Leave .update file — on next startup we check for it
                _download_failures += 1
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

        # Mark binary as downloaded and ready to apply
        _update_downloaded = True
        _download_failures = 0  # Reset failure counter on success

        return True

    except Exception as e:
        logger.error(f"Download failed: {e}")
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        _download_failures += 1
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

def _do_version_check():
    """
    Perform a single version check and update flags.
    Called by both the background loop and on-demand from health endpoint.
    Returns update_info dict if update found, None otherwise.
    """
    global _update_pending, _update_version, _last_check_time

    with _check_lock:
        try:
            update_info = _check_for_update()
            _last_check_time = time.time()

            if update_info:
                # Set the flag IMMEDIATELY when detected -- before download
                _update_pending = True
                _update_version = update_info['version']
                logger.info(
                    f"Update detected: {VERSION} -> {update_info['version']}"
                )
                return update_info
            return None
        except Exception as e:
            logger.error(f"Version check error: {e}")
            return None


def _update_loop():
    """
    Main update loop -- runs forever in background thread.
    Self-healing: any exception is caught and logged, loop continues.
    Download failures use exponential backoff but never stop trying.
    """
    # Short delay to let server stabilize
    time.sleep(5)

    while True:
        try:
            update_info = _do_version_check()
            if update_info and not _update_downloaded:
                # Retry download with exponential backoff
                for attempt in range(MAX_DOWNLOAD_RETRIES):
                    success = _download_and_apply(update_info)
                    if success:
                        break
                    # Exponential backoff: 30s, 60s, 120s
                    delay = DOWNLOAD_RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        f"Download attempt {attempt + 1}/{MAX_DOWNLOAD_RETRIES} "
                        f"failed, retrying in {delay}s"
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        f"All {MAX_DOWNLOAD_RETRIES} download attempts failed. "
                        f"Will retry next check cycle. "
                        f"Total consecutive failures: {_download_failures}"
                    )
        except Exception as e:
            # Catch EVERYTHING -- this thread must never die
            logger.error(f"Update loop error (recovering): {e}")

        time.sleep(CHECK_INTERVAL)


def _ensure_updater_alive():
    """
    Check if the updater thread is alive. If it crashed, restart it.
    Called from is_update_available() to guarantee self-healing.
    """
    global _updater_thread

    with _updater_thread_lock:
        if _updater_thread is not None and not _updater_thread.is_alive():
            logger.warning("Updater thread died, restarting...")
            _updater_thread = threading.Thread(
                target=_update_loop,
                daemon=True,
                name="auto-updater-revived"
            )
            _updater_thread.start()
            logger.info("Updater thread restarted successfully")


def start_auto_updater():
    """
    Start the silent auto-updater as a daemon thread.
    Call this once from runtime.py after the server starts.
    """
    global _updater_thread

    # First, apply any pending update from a previous failed swap
    _apply_pending_update()

    # Don't run updater in dev mode
    if not getattr(sys, 'frozen', False):
        logger.debug("Dev mode detected, auto-updater disabled")
        return

    with _updater_thread_lock:
        _updater_thread = threading.Thread(
            target=_update_loop,
            daemon=True,
            name="auto-updater"
        )
        _updater_thread.start()

    logger.info(f"Auto-updater started (checking every {CHECK_INTERVAL}s, restart-free)")


def is_update_available() -> dict | None:
    """
    Check if a newer version exists.
    Called by the bridge's /health endpoint to inform the dashboard.
    Returns {"version": "x.y.z", "downloaded": bool} if update found, None otherwise.

    Self-healing: also checks if the updater thread is alive and restarts it
    if it crashed. Triggers a background version check if data is stale.
    """
    global _last_check_time

    # Self-heal: restart updater thread if it crashed
    if getattr(sys, 'frozen', False):
        _ensure_updater_alive()

    # If we already know about an update, return it immediately
    if _update_pending and _update_version:
        return {"version": _update_version, "downloaded": _update_downloaded}

    # Otherwise, if it's been a while since we checked, kick off a
    # non-blocking check so the NEXT health poll has fresh data
    now = time.time()
    if now - _last_check_time > STALE_CHECK_THRESHOLD:
        _last_check_time = now  # Prevent stampede
        threading.Thread(
            target=_do_version_check, daemon=True, name="update-check-ondemand"
        ).start()

    return None


def apply_update_now() -> dict:
    """
    User clicked 'Update Now' in dashboard. Restart the service.
    Only call this when the user explicitly requests it.

    Returns status dict so the endpoint can inform the user:
      - {"status": "restarting"} if binary downloaded and restarting
      - {"status": "downloading"} if update detected but not yet downloaded
      - {"status": "no_update"} if no update available
    """
    if not _update_pending:
        return {"status": "no_update"}

    if not _update_downloaded:
        # Update detected but binary not yet on disk -- don't restart
        # into the same old version! Kick off a download attempt instead.
        logger.warning(
            "User clicked Update Now but binary not downloaded yet. "
            "Triggering download..."
        )
        if _update_version:
            threading.Thread(
                target=_download_and_apply,
                args=({"version": _update_version, "sha256": "",
                       "url": f"{R2_PUBLIC_URL}/{_get_platform_key()}"},),
                daemon=True,
                name="update-download-ondemand"
            ).start()
        return {"status": "downloading"}

    logger.info("User requested immediate update restart")
    _restart_service()
    return {"status": "restarting"}


# Legacy function name for backward compatibility
def check_and_update():
    """Legacy entry point -- now just starts the background updater."""
    start_auto_updater()
