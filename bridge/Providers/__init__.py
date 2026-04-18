"""
Providers — Multi-provider key management for HemUI Bridge.

Serves provider metadata (from hermes_cli/auth.py PROVIDER_REGISTRY)
and handles API key CRUD for any provider. Keys are written to
~/.hermes/.env using the exact env var names from PROVIDER_REGISTRY.

Source of truth for provider configs: hermes_cli/auth.py → PROVIDER_REGISTRY
Source of truth for env loading:     hermes_cli/env_loader.py
Source of truth for paths:           hermes_constants.py → get_hermes_home()

Routes:
  GET  /providers              — list all supported providers + status
  GET  /providers/{id}/status  — single provider status
  POST /providers/{id}/key     — save an API key for a provider
  DELETE /providers/{id}/key   — remove a provider's API key
"""

import os
import re
import logging
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/providers", tags=["providers"])

# ── Constants (mirroring hermes_constants.py) ──────────────────────

try:
    from hermes_constants import get_hermes_home
except ImportError:
    def get_hermes_home() -> Path:
        return Path(os.getenv("HERMES_HOME", Path.home() / ".hermes"))

# ── Provider Registry (from core hermes_cli/auth.py) ──────────────
# We mirror PROVIDER_REGISTRY here. When the bridge runs inside the
# hermes venv, we import directly. Otherwise we hardcode the subset
# needed for HemUI.

try:
    from hermes_cli.auth import PROVIDER_REGISTRY
    _REGISTRY_SOURCE = "core"
except ImportError:
    _REGISTRY_SOURCE = "fallback"
    # Minimal fallback — should not happen in production
    PROVIDER_REGISTRY = {}

# ── Static provider metadata for UI ────────────────────────────────
# Display names, descriptions, key URLs — things the core doesn't
# carry but the UI needs.

_PROVIDER_UI_META = {
    "openrouter": {
        "name": "OpenRouter",
        "description": "Access 200+ models through a single API",
        "url": "https://openrouter.ai/keys",
        "auth_method": "oauth_pkce",
        "has_credits": True,
    },
    "minimax": {
        "name": "MiniMax",
        "description": "MiniMax M1/M2 series — 1M context, agentic",
        "url": "https://www.minimax.io/",
        "auth_method": "api_key",
        "has_credits": False,
        "models": [
            {"id": "minimax-m2.7", "name": "MiniMax M2.7", "context": 1048576},
            {"id": "minimax-m2.5", "name": "MiniMax M2.5", "context": 1048576},
            {"id": "minimax-m1-256k", "name": "MiniMax M1 256K", "context": 1000000},
            {"id": "minimax-m1-128k", "name": "MiniMax M1 128K", "context": 1000000},
            {"id": "minimax-m1-80k", "name": "MiniMax M1 80K", "context": 1000000},
            {"id": "minimax-m1-40k", "name": "MiniMax M1 40K", "context": 1000000},
            {"id": "minimax-m1", "name": "MiniMax M1", "context": 1000000},
        ],
    },
    "kimi-coding": {
        "name": "Kimi / Moonshot",
        "description": "Kimi K2 series — strong coding and reasoning",
        "url": "https://platform.moonshot.ai/",
        "auth_method": "api_key",
        "has_credits": False,
        "models": [
            {"id": "kimi-k2.5", "name": "Kimi K2.5", "context": 262144},
        ],
    },
    "anthropic": {
        "name": "Anthropic",
        "description": "Claude Sonnet, Opus, Haiku — best-in-class reasoning",
        "url": "https://console.anthropic.com/settings/keys",
        "auth_method": "api_key",
        "has_credits": False,
    },
    "gemini": {
        "name": "Google AI Studio",
        "description": "Gemini models — free tier available",
        "url": "https://aistudio.google.com/apikey",
        "auth_method": "api_key",
        "has_credits": False,
    },
    "deepseek": {
        "name": "DeepSeek",
        "description": "DeepSeek V3/R1 — cost-effective coding models",
        "url": "https://platform.deepseek.com/api_keys",
        "auth_method": "api_key",
        "has_credits": False,
    },
    "zai": {
        "name": "Z.AI / GLM",
        "description": "GLM-4/5 series from Zhipu AI",
        "url": "https://open.bigmodel.cn/",
        "auth_method": "api_key",
        "has_credits": False,
    },
    "huggingface": {
        "name": "Hugging Face",
        "description": "Open-source models via HF Inference API",
        "url": "https://huggingface.co/settings/tokens",
        "auth_method": "api_key",
        "has_credits": False,
    },
}

# Ordered list for UI display — OpenRouter first
_PROVIDER_ORDER = [
    "openrouter", "minimax", "kimi-coding", "anthropic",
    "deepseek", "gemini", "zai", "huggingface",
]


# ── .env helpers ───────────────────────────────────────────────────

def _get_env_path() -> Path:
    """Canonical .env path — matches hermes_cli/env_loader.py."""
    return get_hermes_home() / ".env"


def _read_env_value(key_name: str) -> str:
    """Read a specific key from the .env file."""
    env_path = _get_env_path()
    if not env_path.exists():
        return ""

    try:
        content = env_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = env_path.read_text(encoding="latin-1")

    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        if key.strip() == key_name:
            val = value.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                val = val[1:-1]
            return val
    return ""


def _write_env_value(key_name: str, value: str) -> None:
    """Write a key=value to ~/.hermes/.env, preserving other content."""
    env_path = _get_env_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)

    if env_path.exists():
        try:
            content = env_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = env_path.read_text(encoding="latin-1")
    else:
        content = ""

    new_line = f'{key_name}="{value}"'
    pattern = re.compile(r"^" + re.escape(key_name) + r"\s*=.*$", re.MULTILINE)

    if pattern.search(content):
        content = pattern.sub(new_line, content)
    else:
        if content and not content.endswith("\n"):
            content += "\n"
        content += new_line + "\n"

    env_path.write_text(content, encoding="utf-8")


def _remove_env_value(key_name: str) -> None:
    """Remove a key from ~/.hermes/.env."""
    env_path = _get_env_path()
    if not env_path.exists():
        return

    try:
        content = env_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = env_path.read_text(encoding="latin-1")

    pattern = re.compile(
        r"^" + re.escape(key_name) + r"\s*=.*\n?", re.MULTILINE
    )
    new_content = pattern.sub("", content)
    env_path.write_text(new_content, encoding="utf-8")


def _get_provider_env_vars(provider_id: str) -> list:
    """Get the env var names for a provider from PROVIDER_REGISTRY."""
    pconfig = PROVIDER_REGISTRY.get(provider_id)
    if pconfig and hasattr(pconfig, "api_key_env_vars"):
        return list(pconfig.api_key_env_vars)

    # Hardcoded fallback for providers not in registry
    _FALLBACK_ENV_VARS = {
        "openrouter": ["OPENROUTER_API_KEY"],
        "minimax": ["MINIMAX_API_KEY"],
        "kimi-coding": ["KIMI_API_KEY"],
        "anthropic": ["ANTHROPIC_API_KEY"],
        "gemini": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
        "deepseek": ["DEEPSEEK_API_KEY"],
        "zai": ["GLM_API_KEY", "ZAI_API_KEY"],
        "huggingface": ["HF_TOKEN"],
    }
    return _FALLBACK_ENV_VARS.get(provider_id, [])


def _check_provider_key(provider_id: str) -> tuple:
    """Check if a provider has an API key set.

    Returns (has_key: bool, key_preview: str, env_var: str).
    """
    env_vars = _get_provider_env_vars(provider_id)
    for env_var in env_vars:
        # Check os.environ first (runtime), then .env file
        val = os.environ.get(env_var, "") or _read_env_value(env_var)
        if val and len(val) >= 4:
            return True, val[-4:], env_var
    return False, "", env_vars[0] if env_vars else ""


# ── Routes ─────────────────────────────────────────────────────────


@router.get("/")
async def list_providers():
    """List all supported providers with their connection status.

    Returns providers in display order with:
      - id, name, description, url
      - connected: bool (has a valid key)
      - key_preview: last 4 chars
      - auth_method: "api_key" | "oauth_pkce"
      - models: list of available models (for direct providers)
    """
    providers = []
    for pid in _PROVIDER_ORDER:
        meta = _PROVIDER_UI_META.get(pid, {})
        has_key, preview, env_var = _check_provider_key(pid)

        providers.append({
            "id": pid,
            "name": meta.get("name", pid),
            "description": meta.get("description", ""),
            "url": meta.get("url", ""),
            "auth_method": meta.get("auth_method", "api_key"),
            "has_credits": meta.get("has_credits", False),
            "connected": has_key,
            "key_preview": preview if has_key else None,
            "env_var": env_var,
            "models": meta.get("models", []),
        })

    return JSONResponse({"providers": providers})


@router.get("/{provider_id}/status")
async def provider_status(provider_id: str):
    """Check a single provider's connection status."""
    if provider_id not in _PROVIDER_UI_META:
        return JSONResponse(
            {"error": f"Unknown provider: {provider_id}"},
            status_code=404,
        )

    has_key, preview, env_var = _check_provider_key(provider_id)
    meta = _PROVIDER_UI_META.get(provider_id, {})

    return JSONResponse({
        "id": provider_id,
        "connected": has_key,
        "key_preview": preview if has_key else None,
        "env_var": env_var,
        "models": meta.get("models", []),
    })


@router.post("/{provider_id}/key")
async def save_provider_key(provider_id: str, request: dict):
    """Save an API key for a provider.

    Writes to ~/.hermes/.env using the correct env var name from
    PROVIDER_REGISTRY, and sets os.environ so it's immediately available.
    """
    api_key = request.get("api_key", "").strip()

    if not api_key:
        return JSONResponse(
            {"success": False, "error": "API key cannot be empty"},
            status_code=400,
        )

    env_vars = _get_provider_env_vars(provider_id)
    if not env_vars:
        return JSONResponse(
            {"success": False, "error": f"Unknown provider: {provider_id}"},
            status_code=404,
        )

    # Use the primary env var name
    env_var = env_vars[0]

    # Write to .env and os.environ
    _write_env_value(env_var, api_key)
    os.environ[env_var] = api_key

    logger.info(
        "Provider '%s' API key saved (env: %s, key ending ...%s)",
        provider_id, env_var, api_key[-4:],
    )

    return JSONResponse({
        "success": True,
        "key_preview": api_key[-4:],
        "env_var": env_var,
    })


@router.delete("/{provider_id}/key")
async def remove_provider_key(provider_id: str):
    """Remove a provider's API key from .env and os.environ."""
    env_vars = _get_provider_env_vars(provider_id)
    if not env_vars:
        return JSONResponse(
            {"success": False, "error": f"Unknown provider: {provider_id}"},
            status_code=404,
        )

    for env_var in env_vars:
        _remove_env_value(env_var)
        if env_var in os.environ:
            del os.environ[env_var]

    logger.info("Provider '%s' API key removed", provider_id)

    return JSONResponse({"success": True})
