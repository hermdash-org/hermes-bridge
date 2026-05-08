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
    """Get path to OAuth tokens file."""
    return _get_hermes_home() / "mcp-tokens" / "higgsfield.json"


def get_credentials() -> Optional[Tuple[str, str]]:
    """
    Get Higgsfield API credentials from OAuth tokens.
    
    Returns:
        Tuple of (api_key, api_secret) or None if not authenticated
    """
    token_path = _get_token_path()
    
    if not token_path.exists():
        logger.warning(f"No Higgsfield tokens found at {token_path}")
        return None
    
    try:
        with open(token_path, "r") as f:
            tokens = json.load(f)
        
        access_token = tokens.get("access_token")
        if not access_token:
            logger.error("No access_token in token file")
            return None
        
        # The access token format is typically "key:secret" or just the key
        # We need to check the actual format from Higgsfield OAuth
        # For now, we'll use the access_token as the key
        # and check if there's a separate secret
        
        # Option 1: Token is "key:secret" format
        if ":" in access_token:
            parts = access_token.split(":", 1)
            return (parts[0], parts[1])
        
        # Option 2: Separate key and secret fields
        api_secret = tokens.get("api_secret") or tokens.get("refresh_token")
        if api_secret:
            return (access_token, api_secret)
        
        # Option 3: Just use the access token as both (some APIs work this way)
        logger.info("Using access_token as API key (no separate secret found)")
        return (access_token, access_token)
        
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
    
    logger.info("✓ Higgsfield API credentials loaded from OAuth tokens")
    return True
