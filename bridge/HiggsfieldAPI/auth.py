"""
Authentication module for Higgsfield API.

Reads OAuth tokens from ~/.hermes/mcp-tokens/higgsfield.json
and converts them to API credentials for the higgsfield-client SDK.
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("bridge.higgsfield.api.auth")


def _get_hermes_home() -> Path:
    """Get Hermes home directory."""
    return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))


def _get_token_path() -> Path:
    """Get path to CLI credentials file."""
    hermes_home = _get_hermes_home()
    # CLI saves credentials here
    return hermes_home / "higgsfield" / "credentials.json"


def get_credentials() -> Optional[Tuple[str, str]]:
    """
    Get Higgsfield API credentials from CLI credentials file.
    
    The CLI saves credentials in JSON format:
    {
        "api_key": "...",
        "api_secret": "..."
    }
    
    Returns:
        Tuple of (api_key, api_secret) or None if not authenticated
    """
    token_path = _get_token_path()
    
    if not token_path.exists():
        logger.warning(f"No Higgsfield credentials found at {token_path}")
        return None
    
    try:
        with open(token_path, "r") as f:
            creds = json.load(f)
        
        api_key = creds.get("api_key")
        api_secret = creds.get("api_secret")
        
        if not api_key or not api_secret:
            logger.error("Missing api_key or api_secret in credentials file")
            return None
        
        return (api_key, api_secret)
        
    except Exception as e:
        logger.error(f"Failed to read credentials: {e}", exc_info=True)
        return None


def has_credentials() -> bool:
    """Check if Higgsfield credentials are available."""
    return get_credentials() is not None


def set_env_credentials() -> bool:
    """
    Set HF_API_KEY and HF_API_SECRET environment variables.
    
    The higgsfield-client SDK reads from these env vars.
    
    Returns:
        True if credentials were set, False otherwise
    """
    creds = get_credentials()
    if not creds:
        return False
    
    api_key, api_secret = creds
    os.environ["HF_API_KEY"] = api_key
    os.environ["HF_API_SECRET"] = api_secret
    
    logger.info("✓ Higgsfield API credentials loaded from CLI credentials file")
    return True
