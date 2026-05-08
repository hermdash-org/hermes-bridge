"""
Higgsfield Web OAuth Flow — No CLI required.

Implements OAuth 2.0 device flow for Higgsfield authentication.
Users click a button, get a URL, authenticate in browser, credentials saved automatically.
"""

import os
import json
import time
import logging
import requests
from pathlib import Path
from typing import Optional, Dict
from fastapi import APIRouter, HTTPException, BackgroundTasks

logger = logging.getLogger("bridge.higgsfield.oauth")

router = APIRouter(prefix="/higgsfield", tags=["higgsfield-oauth"])

# Higgsfield OAuth endpoints
OAUTH_BASE = "https://api.higgsfield.ai/oauth"
DEVICE_CODE_URL = f"{OAUTH_BASE}/device/code"
TOKEN_URL = f"{OAUTH_BASE}/device/token"
CLIENT_ID = "hermes-dashboard"  # Public client ID for Hermes


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


def _poll_for_token(device_code: str, interval: int = 5, timeout: int = 300):
    """
    Poll for OAuth token after user completes authentication.
    Runs in background and saves credentials when ready.
    """
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            response = requests.post(TOKEN_URL, json={
                "client_id": CLIENT_ID,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code"
            })
            
            if response.status_code == 200:
                data = response.json()
                api_key = data.get("api_key")
                api_secret = data.get("api_secret")
                
                if api_key and api_secret:
                    _save_credentials(api_key, api_secret)
                    logger.info("✓ OAuth completed successfully")
                    return
            
            elif response.status_code == 400:
                error = response.json().get("error")
                if error == "authorization_pending":
                    # User hasn't completed auth yet, keep polling
                    time.sleep(interval)
                    continue
                elif error == "slow_down":
                    # Increase polling interval
                    interval += 5
                    time.sleep(interval)
                    continue
                else:
                    logger.error(f"OAuth error: {error}")
                    return
            
            else:
                logger.error(f"Token request failed: {response.status_code}")
                return
                
        except Exception as e:
            logger.error(f"Polling error: {e}")
            time.sleep(interval)
    
    logger.warning("OAuth polling timed out")


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
    Start OAuth device flow.
    
    Returns a URL for the user to visit and a user code to enter.
    Starts background polling for token.
    
    Returns:
        {
            "verification_url": str,
            "user_code": str,
            "device_code": str,
            "expires_in": int,
            "interval": int,
            "message": str
        }
    """
    try:
        # Check if already authenticated
        if _load_credentials():
            return {
                "message": "Already authenticated",
                "authenticated": True,
            }
        
        # Request device code
        response = requests.post(DEVICE_CODE_URL, json={
            "client_id": CLIENT_ID,
            "scope": "generate upload"
        })
        
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to start OAuth flow")
        
        data = response.json()
        
        # Start background polling
        background_tasks.add_task(
            _poll_for_token,
            device_code=data["device_code"],
            interval=data.get("interval", 5)
        )
        
        return {
            "verification_url": data["verification_uri"],
            "user_code": data["user_code"],
            "device_code": data["device_code"],
            "expires_in": data.get("expires_in", 300),
            "interval": data.get("interval", 5),
            "message": f"Visit {data['verification_uri']} and enter code: {data['user_code']}",
        }
        
    except Exception as e:
        logger.error(f"OAuth start failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
