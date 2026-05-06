"""
Higgsfield MCP Integration — Bridge endpoints.

Routes:
  GET  /higgsfield/status   — Check connection status and available tools
  POST /higgsfield/connect  — Trigger OAuth flow, return auth URL
"""

import os
import json
import logging
import asyncio
from pathlib import Path
from fastapi import APIRouter, HTTPException

logger = logging.getLogger("bridge.higgsfield")

router = APIRouter(prefix="/higgsfield", tags=["higgsfield"])

# OAuth flow state
_oauth_task = None
_oauth_auth_url = None


def _get_hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))


def _get_token_path() -> Path:
    return _get_hermes_home() / "mcp-tokens" / "higgsfield.json"


def _read_token_file() -> dict | None:
    token_path = _get_token_path()
    if not token_path.exists():
        return None
    try:
        with open(token_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read token file: {e}")
        return None


@router.get("/status")
async def get_status():
    """Check Higgsfield MCP connection status."""
    try:
        token_data = _read_token_file()
        has_tokens = token_data is not None

        connected = False
        if has_tokens and token_data:
            connected = bool(token_data.get("access_token"))

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
            "has_tokens": has_tokens,
        }

    except Exception as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/connect")
async def connect():
    """
    Trigger Higgsfield OAuth flow using MCP OAuth library directly.

    Starts the OAuth flow in a background task and returns the authorization
    URL immediately. The frontend opens this URL in the user's browser, and
    the OAuth callback server (running on the VPS) handles the redirect.

    Returns:
        {
            "message": str,
            "success": bool,
            "auth_url": str | None
        }
    """
    global _oauth_task, _oauth_auth_url

    try:
        # Import MCP OAuth
        try:
            from tools.mcp_oauth import build_oauth_auth, _redirect_handler
        except ImportError:
            raise HTTPException(
                status_code=500,
                detail="MCP OAuth not available. Install with: pip install 'mcp>=1.26.0'"
            )

        # Get Higgsfield MCP config
        try:
            from hermes_cli.config import load_config
            config = load_config()
            mcp_servers = config.get("mcp_servers", {})
            higgsfield_cfg = mcp_servers.get("higgsfield")
            if not higgsfield_cfg:
                raise HTTPException(
                    status_code=500,
                    detail="Higgsfield not configured in config.yaml"
                )
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            raise HTTPException(status_code=500, detail=f"Config error: {e}")

        server_url = higgsfield_cfg.get("url", "https://mcp.higgsfield.ai/mcp")
        oauth_config = higgsfield_cfg.get("oauth", {})

        # Custom redirect handler that captures the URL
        auth_url_captured = None

        async def capture_redirect_handler(authorization_url: str) -> None:
            nonlocal auth_url_captured
            auth_url_captured = authorization_url
            logger.info(f"Higgsfield OAuth URL: {authorization_url}")

        # Build OAuth provider with custom redirect handler
        from tools.mcp_oauth import (
            HermesTokenStorage,
            _configure_callback_port,
            _build_client_metadata,
            _maybe_preregister_client,
            _wait_for_callback,
            OAuthClientProvider,
        )

        cfg = dict(oauth_config)
        storage = HermesTokenStorage("higgsfield")

        _configure_callback_port(cfg)
        client_metadata = _build_client_metadata(cfg)
        _maybe_preregister_client(storage, cfg, client_metadata)

        provider = OAuthClientProvider(
            server_url=server_url,
            client_metadata=client_metadata,
            storage=storage,
            redirect_handler=capture_redirect_handler,
            callback_handler=_wait_for_callback,
            timeout=float(cfg.get("timeout", 300)),
        )

        # Start OAuth flow in background
        async def run_oauth():
            try:
                # Initialize the provider (triggers OAuth flow)
                await provider._initialize()
                logger.info("Higgsfield OAuth completed successfully")
            except Exception as e:
                logger.error(f"Higgsfield OAuth failed: {e}")

        _oauth_task = asyncio.create_task(run_oauth())

        # Wait briefly for the auth URL to be captured
        for _ in range(20):  # 2 seconds max
            if auth_url_captured:
                break
            await asyncio.sleep(0.1)

        if not auth_url_captured:
            logger.warning("Could not capture Higgsfield OAuth URL")

        return {
            "message": "OAuth flow started. Complete authorization in your browser.",
            "success": True,
            "auth_url": auth_url_captured,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Connect failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
