"""
Models — fetch available models and manage active model + provider.

Routes:
  GET  /models         — list models from OpenRouter + direct provider models
  GET  /models/active   — get model + provider from active profile's config.yaml
  POST /models/active   — set model + provider in active profile's config.yaml
"""

import os
import yaml
import httpx
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..Chat.agent_pool import get_active_profile, get_profile_home


router = APIRouter()
OPENROUTER_API = "https://openrouter.ai/api/v1/models"

# Direct provider model catalogs — shown in model selector when provider is connected
# Mirror of the upstream hermes-agent hermes_cli/models.py _PROVIDER_MODELS
_DIRECT_PROVIDER_MODELS: dict[str, list[dict]] = {
    "deepseek": [
        {"id": "deepseek-v4-pro", "name": "DeepSeek V4 Pro", "context_length": 1048576,
         "pricing": {"prompt": 0.435, "completion": 0.87}, "is_free": False},
        {"id": "deepseek-v4-flash", "name": "DeepSeek V4 Flash", "context_length": 1048576,
         "pricing": {"prompt": 0.0, "completion": 0.0}, "is_free": True},
        {"id": "deepseek-chat", "name": "DeepSeek Chat (legacy)", "context_length": 65536,
         "pricing": {"prompt": 0.0, "completion": 0.0}, "is_free": True},
        {"id": "deepseek-reasoner", "name": "DeepSeek Reasoner (legacy)", "context_length": 65536,
         "pricing": {"prompt": 0.0, "completion": 0.0}, "is_free": True},
    ],
}


# ── Profile-aware config ──────────────────────────────────────────

def _read_config_model(profile_dir: Path) -> tuple:
    """Read model + provider from a profile's config.yaml.

    Returns (model_id, provider_id). Both may be None.
    """
    config_path = profile_dir / "config.yaml"
    if not config_path.exists():
        return None, None
    try:
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f) or {}
        model_cfg = cfg.get("model", {})
        if isinstance(model_cfg, str):
            return model_cfg, None
        if isinstance(model_cfg, dict):
            return (
                model_cfg.get("default") or model_cfg.get("model"),
                model_cfg.get("provider"),
            )
        return None, None
    except Exception:
        return None, None


def _write_config_model(profile_dir: Path, model_id: str, provider_id: str = ""):
    """Write model.default and optionally model.provider to config.yaml."""
    config_path = profile_dir / "config.yaml"

    user_config = {}
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_config = yaml.safe_load(f) or {}
        except Exception:
            user_config = {}

    if "model" not in user_config or not isinstance(user_config.get("model"), dict):
        user_config["model"] = {}
    user_config["model"]["default"] = model_id
    if provider_id:
        user_config["model"]["provider"] = provider_id

    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(user_config, f, default_flow_style=False, sort_keys=False,
                  allow_unicode=True)

    from bridge.Chat.agent_pool import bump_model_generation
    bump_model_generation()


# ── Convenience wrappers for active profile ────────────────────────

def _active_model() -> tuple:
    """Read (model, provider) for the currently active profile."""
    profile_dir = get_profile_home(get_active_profile())
    return _read_config_model(profile_dir)


def _set_active_model(model_id: str, provider_id: str = ""):
    """Write model + provider to the currently active profile's config.yaml."""
    profile_dir = get_profile_home(get_active_profile())
    _write_config_model(profile_dir, model_id, provider_id)


# ── GET /models ────────────────────────────────────────────────────

@router.get("/models")
async def list_models():
    """Fetch models from OpenRouter + direct providers.

    Returns OpenRouter catalog mixed with any direct provider models
    the user has API keys configured for.
    """
    # 1. Fetch OpenRouter catalog
    openrouter_models = []
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(OPENROUTER_API)
            resp.raise_for_status()
            data = resp.json()

        for m in data.get("data", []):
            pricing = m.get("pricing", {})
            prompt_price = float(pricing.get("prompt", "0") or "0")
            completion_price = float(pricing.get("completion", "0") or "0")

            openrouter_models.append({
                "id": m.get("id", ""),
                "name": m.get("name", m.get("id", "")),
                "context_length": m.get("context_length", 0),
                "pricing": {"prompt": prompt_price, "completion": completion_price},
                "is_free": prompt_price == 0 and completion_price == 0,
                "_provider": "openrouter",  # Tag all OpenRouter models
            })
    except httpx.HTTPError as e:
        # OpenRouter down — fall back to direct providers only
        pass

    # 2. Add direct provider models (ALWAYS show them - API key check happens at runtime)
    all_models = list(openrouter_models)
    for provider_id, model_list in _DIRECT_PROVIDER_MODELS.items():
        for m in model_list:
            # Prefix with provider ID so model selector can identify source
            m_copy = dict(m)
            m_copy["_provider"] = provider_id
            all_models.append(m_copy)

    # 3. Sort: free first, then by name
    all_models.sort(key=lambda x: (not x["is_free"], x["name"].lower()))

    model, provider = _active_model()
    return JSONResponse({
        "models": all_models,
        "active": {
            "model": model or "",
            "provider": provider or "openrouter",
        },
        "total": len(all_models),
    })


def _get_provider_env_var_names(provider_id: str) -> list:
    """Return env var names for a provider (mirror of Providers/_get_provider_env_vars)."""
    _FALLBACK_ENV_VARS = {
        "deepseek": ["DEEPSEEK_API_KEY"],
        "anthropic": ["ANTHROPIC_API_KEY"],
        "gemini": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
        "minimax": ["MINIMAX_API_KEY"],
        "kimi-coding": ["KIMI_API_KEY"],
        "zai": ["GLM_API_KEY", "ZAI_API_KEY"],
        "huggingface": ["HF_TOKEN"],
    }
    return _FALLBACK_ENV_VARS.get(provider_id, [])


# ── GET /models/active ─────────────────────────────────────────────

@router.get("/models/active")
async def get_active():
    """Return the currently configured model + provider from active profile."""
    model, provider = _active_model()
    return JSONResponse({
        "model": model or "",
        "provider": provider or "openrouter",
    })


# ── POST /models/active ────────────────────────────────────────────

@router.post("/models/active")
async def set_active(request: Request):
    """Set the active model and provider.

    Body: { "model": "deepseek-v4-pro", "provider": "deepseek" }
    Provider defaults to "openrouter" for backward compatibility.

    Updates active profile's config.yaml + clears agent cache.
    """
    body = await request.json()
    model_id = body.get("model", "")
    if not model_id:
        return JSONResponse({"error": "model is required"}, status_code=400)

    provider_id = body.get("provider", "openrouter")

    try:
        _set_active_model(model_id, provider_id)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    return JSONResponse({"status": "ok", "model": model_id, "provider": provider_id})
