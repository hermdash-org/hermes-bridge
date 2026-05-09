"""
Higgsfield Web OAuth Flow — No CLI required.

Implements OAuth 2.0 device flow for Higgsfield authentication.
Uses the Higgsfield CLI to initiate device flow and captures the verification URL/code.
"""

import os
import json
import time
import logging
import subprocess
import threading
from pathlib import Path
from typing import Optional, Dict
from fastapi import APIRouter, HTTPException, BackgroundTasks

logger = logging.getLogger("bridge.higgsfield.oauth")

router = APIRouter(prefix="/higgsfield", tags=["higgsfield-oauth"])


def _get_hermes_home() -> Path:
    """Get Hermes home directory."""
    return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))


def _get_credentials_path() -> Path:
    """Get path to Higgsfield credentials file."""
    return _get_hermes_home() / "higgsfield" / "credentials.json"


def _save_credentials(api_key: str, api_secret: str):
    """Save credentials to file."""
    creds_path = _get_credentials_path()
    creds_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(creds_path, 'w') as f:
        json.dump({
            "api_key": api_key,
            "api_secret": api_secret
        }, f, indent=2)
    
    # Set secure permissions
    os.chmod(creds_path, 0o600)
    logger.info(f"✓ Credentials saved to {creds_path}")


def _load_credentials() -> Optional[Dict[str, str]]:
    """Load credentials from file."""
    creds_path = _get_credentials_path()
    if not creds_path.exists():
        return None
    
    try:
        with open(creds_path, 'r') as f:
            creds = json.load(f)
        
        # Support both formats: CLI format (access_token/refresh_token) and API format (api_key/api_secret)
        if 'access_token' in creds or 'api_key' in creds:
            return creds
        
        return None
    except Exception as e:
        logger.error(f"Failed to load credentials: {e}")
        return None


@router.get("/oauth-status")
async def oauth_status():
    """
    Check if Higgsfield is authenticated.
    
    Returns:
        {
            "authenticated": bool,
            "credentials_exist": bool
        }
    """
    creds = _load_credentials()
    return {
        "authenticated": creds is not None,
        "credentials_exist": _get_credentials_path().exists(),
    }


@router.post("/oauth-start")
async def oauth_start(background_tasks: BackgroundTasks):
    """
    Start OAuth device flow using Higgsfield CLI.
    
    The CLI saves to its default location, we copy to ~/.hermes/higgsfield
    in the background polling function.
    
    Returns:
        {
            "message": str,
            "instructions": str
        }
    """
    try:
        # Check if already authenticated
        if _load_credentials():
            return {
                "message": "Already authenticated",
                "authenticated": True,
            }
        
        # Ensure our credentials directory exists
        our_creds_dir = _get_credentials_path().parent
        our_creds_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("Starting Higgsfield CLI auth in background...")
        
        # Get CLI path - use full path from bundle if available
        import sys
        if hasattr(sys, '_MEIPASS'):
            # Running from PyInstaller bundle - use full path
            from pathlib import Path
            bin_dir = Path(sys._MEIPASS) / "bin"
            if sys.platform == "win32":
                # Windows npm install creates .cmd wrapper, not .exe
                cli_path = str(bin_dir / "higgsfield.cmd")
            else:
                cli_path = str(bin_dir / "higgsfield")
        else:
            # Running from source - use command name
            cli_path = "higgsfield.cmd" if sys.platform == "win32" else "higgsfield"
        
        logger.info(f"Using CLI path: {cli_path}")
        
        # Start CLI auth and capture the verification URL with device code
        # The CLI outputs: "If browser does not open, visit: https://higgsfield.ai/device?code=XXXXX"
        try:
            proc = subprocess.Popen(
                [cli_path, "auth", "login"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=os.environ.copy(),
            )
            
            # Read first few lines to get the verification URL
            verification_url = "https://higgsfield.ai/device"
            user_code = "Check the output"
            
            import threading
            def read_output():
                nonlocal verification_url, user_code
                try:
                    for line in proc.stdout:
                        logger.info(f"CLI output: {line.strip()}")
                        if "visit:" in line.lower() and "higgsfield.ai" in line:
                            # Extract URL from line like: "If browser does not open, visit: https://higgsfield.ai/device?code=XXXXX"
                            parts = line.split("visit:")
                            if len(parts) > 1:
                                url = parts[1].strip()
                                verification_url = url
                                # Extract code from URL
                                if "?code=" in url:
                                    user_code = url.split("?code=")[1].strip()
                                logger.info(f"Captured verification URL: {verification_url}")
                                break
                except Exception as e:
                    logger.error(f"Error reading CLI output: {e}")
            
            # Start thread to read output without blocking
            threading.Thread(target=read_output, daemon=True).start()
            
            # Give it a moment to capture the URL
            import time
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"Failed to start CLI: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to start authentication: {e}")
        
        # Start background polling - will copy credentials when they appear
        background_tasks.add_task(_poll_for_credentials, interval=2, timeout=300)
        
        return {
            "verification_url": verification_url,
            "user_code": user_code,
            "message": "Please open the URL in your browser to complete authentication.",
        }
        
    except FileNotFoundError:
        logger.error("Higgsfield CLI not found in PATH")
        raise HTTPException(status_code=500, detail="Higgsfield CLI not installed")
    except Exception as e:
        logger.error(f"OAuth start failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _poll_for_credentials(interval: int = 3, timeout: int = 300):
    """
    Poll for credentials file to appear after user completes OAuth.
    Checks both CLI default location and our location, copies if needed.
    This runs in background after CLI starts device flow.
    """
    start_time = time.time()
    our_creds_path = _get_credentials_path()
    cli_creds_path = Path.home() / ".config" / "higgsfield" / "credentials.json"
    
    logger.info(f"Polling for credentials...")
    logger.info(f"  - Our location: {our_creds_path}")
    logger.info(f"  - CLI location: {cli_creds_path}")
    
    while time.time() - start_time < timeout:
        # Check our location first
        if our_creds_path.exists():
            logger.info("✓ Credentials found in our location!")
            return
        
        # Check CLI location and copy if found
        if cli_creds_path.exists():
            logger.info(f"✓ Credentials found in CLI location: {cli_creds_path}")
            try:
                # Read from CLI location
                with open(cli_creds_path, 'r') as f:
                    creds = json.load(f)
                
                # Save to our location
                our_creds_path.parent.mkdir(parents=True, exist_ok=True)
                with open(our_creds_path, 'w') as f:
                    json.dump(creds, f, indent=2)
                
                os.chmod(our_creds_path, 0o600)
                logger.info(f"✓ Credentials copied to {our_creds_path}")
                return
            except Exception as e:
                logger.error(f"Failed to copy credentials: {e}")
        
        time.sleep(interval)
    
    logger.warning("Credentials polling timed out")


@router.post("/oauth-clear")
async def oauth_clear():
    """
    Clear stored Higgsfield credentials.
    
    Returns:
        {
            "success": bool,
            "message": str
        }
    """
    try:
        creds_path = _get_credentials_path()
        
        if creds_path.exists():
            creds_path.unlink()
            logger.info(f"✓ Credentials cleared from {creds_path}")
            return {
                "success": True,
                "message": "Credentials cleared successfully"
            }
        else:
            return {
                "success": True,
                "message": "No credentials to clear"
            }
    except Exception as e:
        logger.error(f"Failed to clear credentials: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
