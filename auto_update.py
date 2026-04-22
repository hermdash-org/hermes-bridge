"""
Auto-updater for Hermes Runtime
Checks for new version on startup and updates silently
"""

import sys
import os
import requests
from pathlib import Path

VERSION = "1.0.0"
UPDATE_CHECK_URL = "https://hermesdashboard.com/api/version"
DOWNLOAD_BASE_URL = "https://downloads.hermesdashboard.com"


def get_platform_filename():
    """Get the correct filename for current platform"""
    if sys.platform == "win32":
        return "windows.exe"
    elif sys.platform == "darwin":
        return "mac.zip"
    else:
        return "linux"


def check_and_update():
    """
    Check for updates and install if available.
    Runs silently - continues even if update fails.
    """
    try:
        # Check latest version
        response = requests.get(UPDATE_CHECK_URL, timeout=5)
        response.raise_for_status()
        data = response.json()
        latest_version = data.get("version", VERSION)
        
        # Compare versions
        if latest_version <= VERSION:
            return  # Already up to date
        
        print(f"🆕 New version available: {latest_version}")
        print(f"📥 Downloading update...")
        
        # Download new version
        platform_file = get_platform_filename()
        download_url = f"{DOWNLOAD_BASE_URL}/{platform_file}"
        
        download_response = requests.get(download_url, timeout=30)
        download_response.raise_for_status()
        
        # Save to temporary file
        current_exe = Path(sys.executable)
        temp_exe = current_exe.with_suffix(current_exe.suffix + ".new")
        
        with open(temp_exe, "wb") as f:
            f.write(download_response.content)
        
        print(f"✅ Update downloaded")
        print(f"🔄 Restarting with new version...")
        
        # Make executable on Unix
        if sys.platform != "win32":
            os.chmod(temp_exe, 0o755)
        
        # Replace current executable
        os.replace(temp_exe, current_exe)
        
        # Restart with new version
        os.execv(sys.executable, sys.argv)
        
    except requests.RequestException as e:
        # Network error - continue without update
        print(f"⚠️  Update check failed: {e}")
        pass
    except Exception as e:
        # Any other error - continue without update
        print(f"⚠️  Update failed: {e}")
        pass


if __name__ == "__main__":
    # For testing
    print(f"Current version: {VERSION}")
    check_and_update()
