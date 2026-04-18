"""
Models — fetch available models and manage active model.

Routes:
  GET  /models         — list models from OpenRouter (public API)
  GET  /models/active   — get model from active profile's config.yaml
  POST /models/active   — set model in active profile's config.yaml + clear cache
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


# ── Profile-aware config ──────────────────────────────────────────

def _read_config_model(profile_dir: Path) -> tuple:
    """Read model/provider from a profile's config.yaml."""
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


def _write_config_model(profile_dir: Path, model_id: str):
    """Write model.default to a profile's config.yaml."""
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


def _set_active_model(model_id: str):
    """Write model to the currently active profile's config.yaml."""
    profile_dir = get_profile_home(get_active_profile())
    _write_config_model(profile_dir, model_id)


# ── GET /models ────────────────────────────────────────────────────

@router.get("/models")
async def list_models():
    """Fetch models from OpenRouter (public, no key needed)."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(OPENROUTER_API)
            resp.raise_for_status()
            data = resp.json()

        models = []
        for m in data.get("data", []):
            pricing = m.get("pricing", {})
            prompt_price = float(pricing.get("prompt", "0") or "0")
            completion_price = float(pricing.get("completion", "0") or "0")

            models.append({
                "id": m.get("id", ""),
                "name": m.get("name", m.get("id", "")),
                "context_length": m.get("context_length", 0),
                "pricing": {"prompt": prompt_price, "completion": completion_price},
                "is_free": prompt_price == 0 and completion_price == 0,
            })

        models.sort(key=lambda x: (not x["is_free"], x["name"].lower()))

        model, provider = _active_model()
        return JSONResponse({
            "models": models,
            "active": {"model": model or "", "provider": provider or "openrouter"},
            "total": len(models),
        })
    except httpx.HTTPError as e:
        return JSONResponse(
            {"error": str(e), "models": []},
            status_code=502,
        )


# ── GET /models/active ─────────────────────────────────────────────

@router.get("/models/active")
async def get_active():
    """Return the currently configured model from active profile's config.yaml."""
    model, provider = _active_model()
    return JSONResponse({
        "model": model or "",
        "provider": provider or "openrouter",
    })


# ── POST /models/active ────────────────────────────────────────────

@router.post("/models/active")
async def set_active(request: Request):
    """Set the active model. Updates active profile's config.yaml + clears agent cache."""
    body = await request.json()
    model_id = body.get("model", "")
    if not model_id:
        return JSONResponse({"error": "model is required"}, status_code=400)

    try:
        _set_active_model(model_id)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    return JSONResponse({"status": "ok", "model": model_id})
