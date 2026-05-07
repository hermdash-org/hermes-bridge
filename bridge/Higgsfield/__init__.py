"""
Higgsfield MCP Integration — Bridge endpoints.

Routes:
  GET  /higgsfield/status   — Check connection status and available tools
  POST /higgsfield/connect  — Start OAuth flow, return authorization URL
  GET  /higgsfield/callback — Handle OAuth callback and save tokens
"""

import os
import json
import logging
import secrets
import hashlib
import base64
import time
import asyncio
from pathlib import Path
from urllib.parse import urlencode
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
import httpx

logger = logging.getLogger("bridge.higgsfield")

router = APIRouter(prefix="/higgsfield", tags=["higgsfield"])

# OAuth flow state (in-memory, per-process)
_oauth_states = {}  # state -> {code_verifier, redirect_uri, timestamp}


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


def _save_tokens(tokens: dict) -> None:
    """Save OAuth tokens to disk in MCP format."""
    token_path = _get_token_path()
    token_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Calculate expires_at for MCP compatibility
    expires_in = tokens.get("expires_in", 3600)
    token_data = {
        "access_token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
        "token_type": tokens.get("token_type", "Bearer"),
        "expires_in": expires_in,
        "expires_at": time.time() + expires_in,
    }
    
    with open(token_path, "w") as f:
        json.dump(token_data, f, indent=2)
    
    os.chmod(token_path, 0o600)
    logger.info(f"✓ Tokens saved to {token_path}")


@router.post("/reconnect")
async def reconnect():
    """
    Force Higgsfield MCP to connect after OAuth completes.
    
    This triggers MCP registration for Higgsfield, which will now
    succeed because tokens are available.
    """
    try:
        logger.info("Triggering Higgsfield MCP connection...")
        
        # Load config and register Higgsfield MCP server
        async def do_connect():
            try:
                from hermes_cli.config import load_config
                from tools.mcp_tool import register_mcp_servers
                
                config = load_config()
                servers = config.get("mcp_servers", {})
                
                # Only register Higgsfield
                higgsfield_config = {"higgsfield": servers.get("higgsfield", {})}
                
                # This will connect if not already connected
                await asyncio.to_thread(register_mcp_servers, higgsfield_config)
                
                logger.info("✓ Higgsfield MCP connection triggered")
            except Exception as e:
                logger.error(f"MCP connection failed: {e}", exc_info=True)
        
        # Run in background
        asyncio.create_task(do_connect())
        
        return {
            "message": "Connection triggered",
            "success": True,
        }
        
    except Exception as e:
        logger.error(f"Reconnect failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_status():
    """Check Higgsfield MCP connection status."""
    try:
        token_data = _read_token_file()
        has_tokens = token_data is not None and bool(token_data.get("access_token"))

        # Only report connected if MCP server is actually connected
        connected = False
        tools_count = 0
        
        if has_tokens:
            try:
                from tools.mcp_tool import get_mcp_status
                status = get_mcp_status()
                for server in status:
                    if server.get("name") == "higgsfield":
                        tools_count = server.get("tools", 0)
                        connected = server.get("connected", False) and tools_count > 0
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
async def connect(request: Request):
    """
    Start Higgsfield OAuth flow for non-technical users.
    
    Does dynamic client registration with Higgsfield, then generates OAuth URL.
    Uses PKCE for security (no client secret needed).
    
    Returns:
        {
            "message": str,
            "success": bool,
            "auth_url": str  # URL to open in browser
        }
    """
    try:
        # Check if already connected
        token_data = _read_token_file()
        if token_data and token_data.get("access_token"):
            try:
                from tools.mcp_tool import get_mcp_status
                status = get_mcp_status()
                for server in status:
                    if server.get("name") == "higgsfield" and server.get("connected"):
                        logger.info("Higgsfield: Already connected")
                        return {
                            "message": "Already connected",
                            "success": True,
                            "auth_url": None,
                        }
            except Exception:
                pass
        
        # Generate PKCE challenge
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode('utf-8')).digest()
        ).decode('utf-8').rstrip('=')
        
        state = secrets.token_urlsafe(32)
        
        # Determine callback URL based on request
        host = request.headers.get("host", "localhost:8521")
        scheme = "https" if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https" else "http"
        redirect_uri = f"{scheme}://{host}/higgsfield/callback"
        
        # Do dynamic client registration with Higgsfield
        registration_endpoint = "https://mcp.higgsfield.ai/oauth2/register"
        
        logger.info(f"Registering OAuth client with redirect_uri={redirect_uri}")
        
        async with httpx.AsyncClient() as client:
            reg_response = await client.post(
                registration_endpoint,
                json={
                    "client_name": "Hermes Dashboard",
                    "redirect_uris": [redirect_uri],
                    "grant_types": ["authorization_code", "refresh_token"],
                    "response_types": ["code"],
                    "token_endpoint_auth_method": "none",  # Public client (PKCE)
                    "scope": "openid email offline_access",
                },
                timeout=10.0,
            )
            
            if reg_response.status_code != 201:
                error_text = reg_response.text
                logger.error(f"Client registration failed: {reg_response.status_code} {error_text}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to register OAuth client: {reg_response.status_code}"
                )
            
            reg_data = reg_response.json()
            client_id = reg_data.get("client_id")
            logger.info(f"✓ Registered OAuth client: {client_id}")
        
        # Store state for callback validation
        _oauth_states[state] = {
            "code_verifier": code_verifier,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "timestamp": time.time(),
        }
        
        # Clean up old states (older than 10 minutes)
        cutoff = time.time() - 600
        for old_state, data in list(_oauth_states.items()):
            if data["timestamp"] < cutoff:
                _oauth_states.pop(old_state, None)
        
        # Build authorization URL
        auth_endpoint = "https://mcp.higgsfield.ai/oauth2/authorize"
        
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "scope": "openid email offline_access",
            "resource": "https://mcp.higgsfield.ai/",
        }
        
        auth_url = f"{auth_endpoint}?{urlencode(params)}"
        
        logger.info(f"✓ Generated OAuth URL")
        
        return {
            "message": "Open the authorization URL in your browser",
            "success": True,
            "auth_url": auth_url,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Connect failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/callback")
async def oauth_callback(code: str = None, state: str = None, error: str = None):
    """
    Handle OAuth callback from Higgsfield.
    
    Exchanges the authorization code for access/refresh tokens and saves them.
    """
    if error:
        logger.error(f"OAuth error: {error}")
        return HTMLResponse(
            content=f"""
            <html><body style="font-family: sans-serif; padding: 40px; text-align: center;">
                <h2 style="color: #ef4444;">Authorization Failed</h2>
                <p>Error: {error}</p>
                <p>You can close this window and try again.</p>
            </body></html>
            """,
            status_code=400,
        )
    
    if not code or not state:
        logger.error("Missing code or state in callback")
        return HTMLResponse(
            content="""
            <html><body style="font-family: sans-serif; padding: 40px; text-align: center;">
                <h2 style="color: #ef4444;">Invalid Callback</h2>
                <p>Missing required parameters.</p>
            </body></html>
            """,
            status_code=400,
        )
    
    # Validate state
    oauth_state = _oauth_states.get(state)
    if not oauth_state:
        logger.error(f"Invalid state: {state}")
        return HTMLResponse(
            content="""
            <html><body style="font-family: sans-serif; padding: 40px; text-align: center;">
                <h2 style="color: #ef4444;">Invalid State</h2>
                <p>OAuth state mismatch or expired. Please try again.</p>
            </body></html>
            """,
            status_code=400,
        )
    
    code_verifier = oauth_state["code_verifier"]
    redirect_uri = oauth_state["redirect_uri"]
    client_id = oauth_state["client_id"]
    
    # Extract scheme and host from redirect_uri for headers
    from urllib.parse import urlparse
    parsed = urlparse(redirect_uri)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    
    # Clean up state
    _oauth_states.pop(state, None)
    
    logger.info("✓ OAuth callback received, exchanging code for tokens...")
    
    # Exchange code for tokens
    # Use the MCP server's token endpoint, not accounts.higgsfield.ai
    token_endpoint = "https://mcp.higgsfield.ai/oauth2/token"
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": client_id,
                    "code_verifier": code_verifier,
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    "Accept": "application/json",
                    "Origin": origin,
                    "Referer": f"{origin}/settings",
                },
                timeout=30.0,
            )
            
            if resp.status_code != 200:
                error_text = resp.text
                logger.error(f"Token exchange failed: {resp.status_code} {error_text}")
                return HTMLResponse(
                    content=f"""
                    <html><body style="font-family: sans-serif; padding: 40px; text-align: center;">
                        <h2 style="color: #ef4444;">Token Exchange Failed</h2>
                        <p>Status: {resp.status_code}</p>
                        <pre style="text-align: left; background: #f3f4f6; padding: 20px; border-radius: 8px;">{error_text}</pre>
                        <p>Please try connecting again.</p>
                    </body></html>
                    """,
                    status_code=500,
                )
            
            tokens = resp.json()
            logger.info("✓ Tokens received successfully")
            
            # Save tokens in MCP format
            _save_tokens(tokens)
            
            # Trigger MCP connection in background
            async def trigger_mcp_connect():
                try:
                    from hermes_cli.config import load_config
                    from tools.mcp_tool import register_mcp_servers
                    
                    config = load_config()
                    servers = config.get("mcp_servers", {})
                    higgsfield_config = {"higgsfield": servers.get("higgsfield", {})}
                    
                    await asyncio.to_thread(register_mcp_servers, higgsfield_config)
                    logger.info("✓ Higgsfield MCP connected automatically")
                except Exception as e:
                    logger.error(f"Auto-connect failed: {e}", exc_info=True)
            
            asyncio.create_task(trigger_mcp_connect())
            
            return HTMLResponse(
                content="""
                <html><body style="font-family: sans-serif; padding: 40px; text-align: center;">
                    <h2 style="color: #10b981;">✓ Authorization Successful!</h2>
                    <p>Higgsfield is now connected to Hermes.</p>
                    <p style="color: #6b7280;">You can close this window and return to the dashboard.</p>
                    <script>
                        // Auto-close after 3 seconds
                        setTimeout(() => window.close(), 3000);
                    </script>
                </body></html>
                """,
                status_code=200,
            )
            
    except Exception as e:
        logger.error(f"Token exchange error: {e}", exc_info=True)
        return HTMLResponse(
            content=f"""
            <html><body style="font-family: sans-serif; padding: 40px; text-align: center;">
                <h2 style="color: #ef4444;">Connection Error</h2>
                <p>{str(e)}</p>
                <p>Please try again.</p>
            </body></html>
            """,
            status_code=500,
        )
