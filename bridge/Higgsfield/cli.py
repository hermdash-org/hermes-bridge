"""
Higgsfield CLI Authentication — Bridge endpoints for CLI-based auth.

Routes:
  GET  /higgsfield/cli-status — Check CLI authentication status
  POST /higgsfield/cli-login  — Authenticate Higgsfield CLI (opens browser)
"""

import os
import logging
import subprocess
from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks

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
async def cli_login(background_tasks: BackgroundTasks):
    """
    Authenticate Higgsfield CLI (opens browser automatically).
    
    This runs `higgsfield auth login` which:
    1. Opens browser for device login
    2. Waits for user to authorize
    3. Saves credentials to ~/.config/higgsfield/credentials.json
    
    Returns immediately with status. Frontend should poll /cli-status.
    
    Returns:
        {
            "message": str,
            "success": bool,
            "authenticated": bool,
            "polling_required": bool
        }
    """
    try:
        # CRITICAL: Check if already authenticated FIRST (before starting background task)
        auth_status = _check_cli_auth()
        if auth_status.get("authenticated"):
            logger.info("Higgsfield CLI: Already authenticated, skipping login")
            return {
                "message": "Already authenticated",
                "success": True,
                "authenticated": True,
                "polling_required": False,
            }
        
        # Not authenticated - start login process
        logger.info("Starting Higgsfield CLI authentication flow...")
        
        # Ensure .hermes/higgsfield directory exists
        creds_dir = _get_cli_credentials_path().parent
        creds_dir.mkdir(parents=True, exist_ok=True)
        
        # Run login in background (it opens browser and waits)
        def run_cli_login():
            try:
                logger.info("Executing: higgsfield auth login")
                
                # Set HIGGSFIELD_CONFIG_DIR to use .hermes/higgsfield
                env = os.environ.copy()
                env["HIGGSFIELD_CONFIG_DIR"] = str(creds_dir)
                
                # Run the CLI command
                # Note: On headless servers (VPS), the CLI will print the URL
                # instead of opening a browser automatically
                result = subprocess.run(
                    ["higgsfield", "auth", "login"],
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minute timeout
                    env=env,
                )
                
                if result.returncode == 0:
                    logger.info("✓ Higgsfield CLI authenticated successfully")
                    logger.info(f"✓ Credentials saved to {_get_cli_credentials_path()}")
                else:
                    logger.error(f"CLI login failed (exit {result.returncode})")
                    logger.error(f"stdout: {result.stdout}")
                    logger.error(f"stderr: {result.stderr}")
                    
            except subprocess.TimeoutExpired:
                logger.error("CLI login timed out after 5 minutes")
            except FileNotFoundError:
                logger.error("Higgsfield CLI not found in PATH")
            except Exception as e:
                logger.error(f"CLI login error: {e}", exc_info=True)
        
        # Start login process in background
        background_tasks.add_task(run_cli_login)
        
        return {
            "message": "Browser opened for authentication. Please complete the login.",
            "success": True,
            "authenticated": False,
            "polling_required": True,
        }
        
    except Exception as e:
        logger.error(f"CLI login failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
