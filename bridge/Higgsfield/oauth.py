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
            return json.load(f)
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
    
    The CLI will handle the OAuth flow and save credentials automatically.
    We just need to tell the user to complete the auth in the browser that opens.
    
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
        
        # Ensure credentials directory exists
        creds_dir = _get_credentials_path().parent
        creds_dir.mkdir(parents=True, exist_ok=True)
        
        # Set environment for CLI to use our credentials directory
        env = os.environ.copy()
        env["HIGGSFIELD_CONFIG_DIR"] = str(creds_dir)
        
        logger.info("Starting Higgsfield CLI auth in background...")
        
        # Start CLI auth in background - it will open browser automatically
        # We don't capture output because that blocks the browser from opening
        subprocess.Popen(
            ["higgsfield", "auth", "login"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        
        # Start background polling for credentials file
        background_tasks.add_task(_poll_for_credentials, interval=2, timeout=300)
        
        # Return generic instructions since we can't capture the exact code
        return {
            "verification_url": "https://higgsfield.ai/device",
            "user_code": "Check the browser window that just opened",
            "message": "Browser opened for authentication. Please complete the login and return here.",
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
    This runs in background after CLI starts device flow.
    """
    start_time = time.time()
    creds_path = _get_credentials_path()
    
    logger.info(f"Polling for credentials at {creds_path}")
    
    while time.time() - start_time < timeout:
        if creds_path.exists():
            logger.info("✓ Credentials file detected!")
            return
        time.sleep(interval)
    
    logger.warning("Credentials polling timed out")
