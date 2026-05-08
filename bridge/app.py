"""
App — FastAPI application factory.

hermes-agent is bundled inside the PyInstaller binary. No detection needed.
No setup endpoints. No platform sniffing. Just the API.
"""

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import runtime version
try:
    from version import VERSION as RUNTIME_VERSION
except ImportError:
    RUNTIME_VERSION = "dev"

VERSION = "1.0.0"  # Bridge API version

logger = logging.getLogger("bridge.app")


def _reload_env():
    """Re-read ~/.hermes/.env so new API keys are picked up without restart."""
    from pathlib import Path
    from dotenv import load_dotenv
    env_file = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / ".env"
    if env_file.exists():
        load_dotenv(str(env_file), override=True)


def _has_api_key():
    """Check if any known LLM provider API key is set."""
    keys = ["OPENROUTER_API_KEY", "GROQ_API_KEY", "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY", "GOOGLE_API_KEY", "TOGETHER_API_KEY"]
    return any(os.environ.get(k) for k in keys)


def create_app() -> FastAPI:
    """Build the FastAPI app with all routers."""

    app = FastAPI(
        title="HemUI Bridge",
        description="HTTP bridge between HemUI and Hermes Agent",
        version=VERSION,
    )

    # Private Network Access (PNA) support — Chrome requires this header
    # for requests from public origins (hermdash.com) to localhost.
    # FastAPI's CORSMiddleware doesn't support PNA yet.
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import Response

    class PrivateNetworkAccessMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            # Handle preflight OPTIONS with PNA header
            if request.method == "OPTIONS":
                response = Response(status_code=204)
                response.headers["Access-Control-Allow-Origin"] = request.headers.get("Origin", "*")
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
                response.headers["Access-Control-Allow-Headers"] = "*"
                response.headers["Access-Control-Allow-Private-Network"] = "true"
                return response
            response = await call_next(request)
            response.headers["Access-Control-Allow-Private-Network"] = "true"
            return response

    app.add_middleware(PrivateNetworkAccessMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Health check ────────────────────────────────────────────────
    @app.get("/health")
    async def health():
        # Hot-reload .env so new API keys are picked up without restart
        _reload_env()

        active_tasks = 0
        active_profile = "default"
        try:
            from .Chat.agent_pool import get_active_profile, running_tasks
            active_tasks = sum(1 for t in running_tasks.values() if t["status"] == "running")
            active_profile = get_active_profile()
        except Exception:
            pass

        # Check if an update has been downloaded and is waiting
        update_info = None
        try:
            from auto_update import is_update_available
            update_info = is_update_available()
        except Exception:
            pass

        return {
            "status": "ok",
            "bridge": "hemui",
            "version": VERSION,
            "runtime_version": RUNTIME_VERSION,
            "hermes_installed": True,  # Always true -- bundled in binary
            "api_key_set": bool(os.environ.get("OPENROUTER_API_KEY")) or _has_api_key(),
            "active_tasks": active_tasks,
            "active_profile": active_profile,
            "update_available": update_info,  # None or {"version": "x.y.z"}
        }

    # ── API key setup (user still needs to enter their key) ─────────
    @app.post("/setup/apikey")
    async def set_api_key(payload: dict):
        """Save API key to ~/.hermes/.env
        
        Accepts:
          {"key": "sk-..."}  → saves as OPENROUTER_API_KEY (default)
          {"key": "sk-...", "name": "GROQ_API_KEY"}  → saves as GROQ_API_KEY
        """
        from pathlib import Path
        key = payload.get("key", "").strip()
        key_name = payload.get("name", "OPENROUTER_API_KEY").strip()
        if not key:
            return {"error": "No key provided"}

        env_file = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / ".env"
        env_file.parent.mkdir(parents=True, exist_ok=True)

        # Read existing, update or append
        lines = []
        if env_file.exists():
            lines = env_file.read_text().splitlines()

        found = False
        for i, line in enumerate(lines):
            if line.startswith(f"{key_name}="):
                lines[i] = f"{key_name}={key}"
                found = True
                break
        if not found:
            lines.append(f"{key_name}={key}")

        env_file.write_text("\n".join(lines) + "\n")
        os.environ[key_name] = key

        return {"status": "ok"}

    # ── Manual update trigger (user clicks "Update Now") ─────────────
    @app.post("/update/apply")
    async def apply_update():
        """User clicked 'Update Now' in dashboard. Restart to apply."""
        try:
            from auto_update import apply_update_now, is_update_available
            info = is_update_available()
            if not info:
                return {"status": "no_update"}

            result = apply_update_now()
            result["version"] = info["version"]
            # result["status"] is "restarting", "downloading", or "no_update"
            return result
        except Exception as e:
            return {"error": str(e)}

    # ── Mount all routers (hermes-agent is bundled in the binary) ───
    from .Chat import router as chat_router
    from .Profiles import router as profiles_router
    from .Sessions import router as sessions_router
    from .Models import router as models_router
    from .OpenRouterOAuth import router as openrouter_oauth_router
    from .Providers import router as providers_router
    from .Skills import router as skills_router
    from .CustomSkills import router as custom_skills_router
    from .Files import router as files_router
    from .Cron import router as cron_router
    from .Voice import router as voice_router
    from .Env import router as env_router
    from .Inbox import router as inbox_router
    from .Higgsfield import router as higgsfield_router
    from .Higgsfield.cli import router as higgsfield_cli_router

    app.include_router(chat_router)
    app.include_router(profiles_router)
    app.include_router(sessions_router)
    app.include_router(models_router)
    app.include_router(openrouter_oauth_router)
    app.include_router(providers_router)
    app.include_router(skills_router)
    app.include_router(custom_skills_router)
    app.include_router(files_router)
    app.include_router(cron_router)
    app.include_router(voice_router)
    app.include_router(env_router)
    app.include_router(inbox_router)
    app.include_router(higgsfield_router)
    app.include_router(higgsfield_cli_router)

    # Sync active profile from hermes config
    try:
        from .Chat.agent_pool import set_active_profile
        from hermes_cli.profiles import get_active_profile as get_sticky_profile
        sticky = get_sticky_profile()
        if sticky and sticky != "default":
            set_active_profile(sticky)
    except Exception:
        pass

    logger.info("Bridge ready -- all routers mounted")
    return app


def _has_api_key() -> bool:
    """Check if API key exists in ~/.hermes/.env"""
    from pathlib import Path
    env_file = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.strip().startswith("OPENROUTER_API_KEY=") and len(line.strip()) > 25:
                return True
    return False
