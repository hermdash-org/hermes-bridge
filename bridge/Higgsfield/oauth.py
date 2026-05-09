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
    
    Runs the CLI in a way that captures the verification URL and code,
    then returns them to the frontend for display.
    
    Returns:
        {
            "verification_url": str,
            "user_code": str,
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
        
        # Ensure credentials directory exists
        creds_dir = _get_credentials_path().parent
        creds_dir.mkdir(parents=True, exist_ok=True)
        
        # Set environment for CLI to use our credentials directory
        env = os.environ.copy()
        env["HIGGSFIELD_CONFIG_DIR"] = str(creds_dir)
        
        logger.info("Starting Higgsfield CLI device flow...")
        
        # Run CLI auth login and capture output
        # The CLI will print the verification URL and code
        result = subprocess.run(
            ["higgsfield", "auth", "login"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
        
        # Parse CLI output to extract verification URL and user code
        output = result.stdout + result.stderr
        logger.info(f"CLI output: {output}")
        
        # Extract verification URL and code from output
        # CLI typically outputs something like:
        # "Visit: https://higgsfield.ai/device"
        # "Enter code: ABC-DEF-123"
        
        verification_url = "https://higgsfield.ai/device"  # Default
        user_code = None
        
        for line in output.split('\n'):
            if 'http' in line.lower():
                # Extract URL
                import re
                urls = re.findall(r'https?://[^\s]+', line)
                if urls:
                    verification_url = urls[0].rstrip('.,;')
            
            if 'code' in line.lower():
                # Extract code (usually format: ABC-DEF-123)
                import re
                codes = re.findall(r'\b[A-Z0-9]{3}-[A-Z0-9]{3}-[A-Z0-9]{3}\b', line)
                if codes:
                    user_code = codes[0]
        
        if not user_code:
            # Fallback: try to find any code-like pattern
            import re
            codes = re.findall(r'\b[A-Z0-9-]{8,}\b', output)
            if codes:
                user_code = codes[0]
        
        if user_code:
            # Start background polling for credentials
            background_tasks.add_task(_poll_for_credentials, interval=3, timeout=300)
            
            return {
                "verification_url": verification_url,
                "user_code": user_code,
                "message": f"Visit {verification_url} and enter code: {user_code}",
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to extract verification code from CLI output"
            )
        
    except subprocess.TimeoutExpired:
        logger.error("CLI auth command timed out")
        raise HTTPException(status_code=500, detail="Authentication timed out")
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
