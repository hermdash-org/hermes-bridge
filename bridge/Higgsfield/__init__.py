"""
Higgsfield MCP Integration — Bridge endpoints.

Routes:
  GET  /higgsfield/status   — Check connection status and available tools
  POST /higgsfield/connect  — Trigger OAuth flow, return auth URL
"""

import os
import re
import json
import shutil
import logging
import subprocess
from pathlib import Path
from fastapi import APIRouter, HTTPException

logger = logging.getLogger("bridge.higgsfield")

router = APIRouter(prefix="/higgsfield", tags=["higgsfield"])


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


def _resolve_hermes_cmd() -> list[str]:
    """Return a command that invokes the hermes CLI.

    Prefer the `hermes` binary on PATH; fall back to `python -m hermes_cli`.
    """
    exe = shutil.which("hermes")
    if exe:
        return [exe]
    import sys
    return [sys.executable, "-m", "hermes_cli"]


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
    Trigger Higgsfield OAuth flow.

    Runs `hermes mcp login higgsfield` as a background subprocess. The CLI
    prints the authorization URL to stdout and attempts to open it in the
    user's browser. We capture stdout briefly to extract the URL so the
    frontend can open it directly as a fallback when server-side browser
    launch isn't available (headless VPS, remote access, etc.).

    Returns:
        {
            "message": str,
            "success": bool,
            "auth_url": str | None
        }
    """
    try:
        cmd = _resolve_hermes_cmd() + ["mcp", "login", "higgsfield"]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )

        # Peek at stdout for a few seconds to find the OAuth URL.
        # Don't wait() — the process keeps running to serve the OAuth callback.
        auth_url: str | None = None
        deadline_lines = 40  # bounded read; URL shows up in first handful of lines
        url_re = re.compile(r"https://\S+/oauth2/authorize\?\S+")

        assert proc.stdout is not None
        import selectors
        sel = selectors.DefaultSelector()
        sel.register(proc.stdout, selectors.EVENT_READ)

        read_lines = 0
        while read_lines < deadline_lines:
            events = sel.select(timeout=5.0)
            if not events:
                break
            line = proc.stdout.readline()
            if not line:
                break
            read_lines += 1
            m = url_re.search(line)
            if m:
                auth_url = m.group(0).rstrip(").,;")
                break

        if auth_url is None:
            logger.warning("Higgsfield OAuth: could not extract auth URL from CLI output")

        return {
            "message": "OAuth flow started. Complete authorization in your browser.",
            "success": True,
            "auth_url": auth_url,
        }

    except FileNotFoundError as e:
        logger.error(f"hermes CLI not found: {e}")
        raise HTTPException(
            status_code=500,
            detail="hermes CLI not found on PATH. Install Hermes or ensure `hermes` is executable.",
        )
    except Exception as e:
        logger.error(f"Connect failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
