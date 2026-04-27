"""
ENV Management Bridge
Handles environment variable operations for ~/.hermes/.env
ENVs are GLOBAL - not profile-specific
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import os
import re
import tempfile
from pathlib import Path

router = APIRouter()

# ENV file path
def get_env_path():
    """Get the .env file path."""
    hermes_home = os.getenv("HERMES_HOME", str(Path.home() / ".hermes"))
    return Path(hermes_home) / ".env"

# Validation
_ENV_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

def _sanitize_value(value: str) -> str:
    """Remove newlines and carriage returns from value."""
    return value.replace("\n", "").replace("\r", "")

def _redact_value(value: str) -> str:
    """Redact API key for display."""
    if not value or len(value) < 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"

# Provider metadata - matches hermes-agent OPTIONAL_ENV_VARS structure
PROVIDER_GROUPS = {
    "OPENROUTER_": {"name": "OpenRouter", "url": "https://openrouter.ai/keys"},
    "DEEPSEEK_": {"name": "DeepSeek", "url": "https://platform.deepseek.com/api_keys"},
    "GROQ_": {"name": "Groq", "url": "https://console.groq.com/keys"},
    "ANTHROPIC_": {"name": "Anthropic", "url": "https://console.anthropic.com/settings/keys"},
    "GOOGLE_": {"name": "Google AI", "url": "https://aistudio.google.com/app/apikey"},
    "GEMINI_": {"name": "Gemini", "url": "https://aistudio.google.com/app/apikey"},
    "OPENAI_": {"name": "OpenAI", "url": "https://platform.openai.com/api-keys"},
}

def _get_provider_info(key: str):
    """Get provider name and URL for a key."""
    for prefix, info in PROVIDER_GROUPS.items():
        if key.startswith(prefix):
            return info
    return {"name": "Other", "url": None}

def _load_env_file():
    """Load all ENV vars from ~/.hermes/.env"""
    env_path = get_env_path()
    env_vars = {}
    
    if not env_path.exists():
        return env_vars
    
    try:
        with open(env_path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, value = line.partition('=')
                    key = key.strip()
                    value = value.strip()
                    if key:
                        env_vars[key] = value
    except Exception as e:
        print(f"Error loading .env: {e}")
    
    return env_vars

def _save_env_file(env_vars: dict):
    """Save ENV vars to ~/.hermes/.env atomically."""
    env_path = get_env_path()
    
    # Ensure parent directory exists
    env_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write to temp file first
    fd, tmp_path = tempfile.mkstemp(
        dir=str(env_path.parent),
        suffix='.tmp',
        prefix='.env_'
    )
    
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            for key, value in sorted(env_vars.items()):
                f.write(f"{key}={value}\n")
            f.flush()
            os.fsync(f.fileno())
        
        # Atomic replace
        os.replace(tmp_path, env_path)
        
        # Secure permissions (owner only)
        try:
            os.chmod(env_path, 0o600)
        except (OSError, NotImplementedError):
            pass
            
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

# Pydantic models for request/response
class SetEnvRequest(BaseModel):
    key: str
    value: str

class EnvVarResponse(BaseModel):
    is_set: bool
    redacted_value: str | None
    provider: str
    url: str | None
    category: str

@router.get('/env')
async def get_env_vars():
    """
    GET /env
    Returns all ENV vars with metadata
    """
    try:
        env_vars = _load_env_file()
        
        # Build response with metadata
        result = {}
        for key, value in env_vars.items():
            provider_info = _get_provider_info(key)
            result[key] = {
                "is_set": bool(value),
                "redacted_value": _redact_value(value) if value else None,
                "provider": provider_info["name"],
                "url": provider_info["url"],
                "category": "provider" if key.endswith("_API_KEY") or key.endswith("_TOKEN") else "setting"
            }
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put('/env')
async def set_env_var(body: SetEnvRequest):
    """
    PUT /env
    Body: {"key": "OPENROUTER_API_KEY", "value": "sk-..."}
    """
    try:
        key = body.key.strip()
        value = body.value.strip()
        
        # Validate key name
        if not key or not _ENV_VAR_NAME_RE.match(key):
            raise HTTPException(status_code=400, detail="Invalid environment variable name")
        
        # Sanitize value
        value = _sanitize_value(value)
        
        # Load current ENV vars
        env_vars = _load_env_file()
        
        # Update or add
        env_vars[key] = value
        
        # Save atomically
        _save_env_file(env_vars)
        
        # Update process environment
        os.environ[key] = value
        
        return {"ok": True, "key": key}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete('/env/{key}')
async def delete_env_var(key: str):
    """
    DELETE /env/{key}
    """
    try:
        # Validate key name
        if not key or not _ENV_VAR_NAME_RE.match(key):
            raise HTTPException(status_code=400, detail="Invalid environment variable name")
        
        # Load current ENV vars
        env_vars = _load_env_file()
        
        # Check if key exists
        if key not in env_vars:
            raise HTTPException(status_code=404, detail=f"{key} not found in .env")
        
        # Remove key
        del env_vars[key]
        
        # Save atomically
        _save_env_file(env_vars)
        
        # Remove from process environment
        os.environ.pop(key, None)
        
        return {"ok": True, "key": key}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post('/env/{key}/reveal')
async def reveal_env_var(key: str):
    """
    POST /env/{key}/reveal
    Returns the unredacted value
    """
    try:
        # Validate key name
        if not key or not _ENV_VAR_NAME_RE.match(key):
            raise HTTPException(status_code=400, detail="Invalid environment variable name")
        
        # Load ENV vars
        env_vars = _load_env_file()
        
        # Check if key exists
        if key not in env_vars:
            raise HTTPException(status_code=404, detail=f"{key} not found in .env")
        
        return {"key": key, "value": env_vars[key]}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
