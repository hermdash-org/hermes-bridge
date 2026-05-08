"""
Higgsfield CLI Authentication — Bridge endpoints for CLI-based auth.

Routes:
  GET  /higgsfield/cli-status — Check CLI authentication status
  POST /higgsfield/cli-login  — Get OAuth URL for authentication
"""

import os
import logging
import subprocess
from pathlib import Path
from fastapi import APIRouter, HTTPException

logger = logging.getLogger("bridge.higgsfield.cli")

router = APIRouter(prefix="/higgsfield", tags=["higgsfield-cli"])


def _get_hermes_home() -> Path:
    """Get Hermes home directory."""
    return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))


def _get_cli_credentials_path() -> Path:
    """Get path to Higgsfield CLI credentials file (inside .hermes)."""
    return _get_hermes_home() / "higgsfield" / "credentials.json"


def _check_cli_auth() -> dict:
    """Check if Higgsfield CLI is authenticated."""
    try:
        # Set HIGGSFIELD_CONFIG_DIR to use .hermes/higgsfield
        creds_dir = _get_cli_credentials_path().parent
        env = os.environ.copy()
        env["HIGGSFIELD_CONFIG_DIR"] = str(creds_dir)
        
        result = subprocess.run(
            ["higgsfield", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
            env=env,
        )
        if result.returncode == 0 and result.stdout.strip():
            return {
                "authenticated": True,
                "token": result.stdout.strip()[:20] + "...",  # Truncated for security
            }
        return {"authenticated": False}
    except Exception as e:
        logger.error(f"Failed to check CLI auth: {e}")
        return {"authenticated": False, "error": str(e)}


@router.get("/cli-status")
async def cli_status():
    """
    Check Higgsfield CLI authentication status.
    
    Returns:
        {
            "authenticated": bool,
            "token": str (truncated) or null,
            "credentials_file": str (path),
            "credentials_exist": bool
        }
    """
    try:
        auth_status = _check_cli_auth()
        creds_path = _get_cli_credentials_path()
        
        return {
            **auth_status,
            "credentials_file": str(creds_path),
            "credentials_exist": creds_path.exists(),
        }
    except Exception as e:
        logger.error(f"CLI status check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cli-login")
async def cli_login():
    """
    Get Higgsfield OAuth URL for authentication.
    
    Returns the OAuth URL that the user should open in their browser.
    After completing OAuth, credentials are saved automatically.
    
    Returns:
        {
            "oauth_url": str,
            "message": str,
            "success": bool,
            "authenticated": bool,
            "polling_required": bool
        }
    """
    try:
        # Check if already authenticated
        auth_status = _check_cli_auth()
        if auth_status.get("authenticated"):
            logger.info("Higgsfield CLI: Already authenticated, skipping login")
            return {
                "message": "Already authenticated",
                "success": True,
                "authenticated": True,
                "polling_required": False,
            }
        
        # Generate OAuth URL
        logger.info("Generating Higgsfield OAuth URL...")
        
        # Higgsfield OAuth endpoint (device flow)
        # The CLI uses this URL for authentication
        oauth_url = "https://higgsfield.ai/auth/cli"
        
        logger.info(f"OAuth URL generated: {oauth_url}")
        
        return {
            "oauth_url": oauth_url,
            "message": "Please open the URL in your browser to authenticate",
            "success": True,
            "authenticated": False,
            "polling_required": True,
        }
        
    except Exception as e:
        logger.error(f"Failed to generate OAuth URL: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
