"""
Higgsfield MCP Integration — Bridge endpoints.

Routes:
  GET  /higgsfield/status   — Check connection status and available tools
  POST /higgsfield/connect  — Trigger OAuth flow
"""

import os
import json
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException

logger = logging.getLogger("bridge.higgsfield")

router = APIRouter(prefix="/higgsfield", tags=["higgsfield"])


def _get_hermes_home() -> Path:
    """Get HERMES_HOME path."""
    return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))


def _get_token_path() -> Path:
    """Get Higgsfield token file path."""
    return _get_hermes_home() / "mcp-tokens" / "higgsfield.json"


def _read_token_file() -> dict | None:
    """Read Higgsfield token file if it exists."""
    token_path = _get_token_path()
    if not token_path.exists():
        return None
    
    try:
        with open(token_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read token file: {e}")
        return None


@router.get("/status")
async def get_status():
    """
    Check Higgsfield MCP connection status.
    
    Returns:
        {
            "connected": bool,
            "tools_count": int,
            "has_tokens": bool
        }
    """
    try:
        # Check if tokens exist
        token_data = _read_token_file()
        has_tokens = token_data is not None
        
        # If tokens exist, check if they're valid (not expired)
        connected = False
        if has_tokens and token_data:
            # Simple check: if access_token exists, consider connected
            # (MCP SDK handles refresh automatically)
            connected = bool(token_data.get("access_token"))
        
        # Get tools count from MCP
        tools_count = 0
        if connected:
            try:
                from tools.mcp_tool import get_mcp_status
                status = get_mcp_status()
                
                for server in status:
                    if server.get("name") == "higgsfield":
                        tools_count = server.get("tools", 0)
                        connected = server.get("connected", False)
                        break
            except Exception as e:
                logger.warning(f"Failed to get MCP status: {e}")
        
        return {
            "connected": connected,
            "tools_count": tools_count,
            "has_tokens": has_tokens
        }
    
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/connect")
async def connect():
    """
    Trigger Higgsfield OAuth flow.
    
    Returns immediately after starting OAuth. User completes in browser,
    then frontend polls status to detect completion.
    
    Returns:
        {
            "message": str,
            "success": bool
        }
    """
    try:
        import subprocess
        import sys
        
        # Start OAuth in background process (non-blocking)
        # This opens the browser and handles the callback
        subprocess.Popen(
            [sys.executable, "-m", "hermes_cli.mcp_config", "login", "higgsfield"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        
        return {
            "message": "OAuth flow started. Complete authorization in your browser.",
            "success": True
        }
    
    except Exception as e:
        logger.error(f"Connect failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
