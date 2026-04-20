"""
App — FastAPI application factory.

In Docker, hermes-agent is ALWAYS installed. No detection needed.
No setup endpoints. No platform sniffing. Just the API.
"""

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

VERSION = "1.0.0"

logger = logging.getLogger("bridge.app")


def create_app() -> FastAPI:
    """Build the FastAPI app with all routers."""

    app = FastAPI(
        title="HemUI Bridge",
        description="HTTP bridge between HemUI and Hermes Agent",
        version=VERSION,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Health check ────────────────────────────────────────────────
    @app.get("/health")
    async def health():
        active_tasks = 0
        active_profile = "default"
        try:
            from .Chat.agent_pool import get_active_profile, running_tasks
            active_tasks = sum(1 for t in running_tasks.values() if t["status"] == "running")
            active_profile = get_active_profile()
        except Exception:
            pass

        return {
            "status": "ok",
            "bridge": "hemui",
            "version": VERSION,
            "hermes_installed": True,  # Always true in Docker
            "api_key_set": bool(os.environ.get("OPENROUTER_API_KEY")) or _has_api_key(),
            "active_tasks": active_tasks,
            "active_profile": active_profile,
        }

    # ── API key setup (user still needs to enter their key) ─────────
    @app.post("/setup/apikey")
    async def set_api_key(payload: dict):
        """Save API key to ~/.hermes/.env"""
        from pathlib import Path
        key = payload.get("key", "").strip()
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
            if line.startswith("OPENROUTER_API_KEY="):
                lines[i] = f"OPENROUTER_API_KEY={key}"
                found = True
                break
        if not found:
            lines.append(f"OPENROUTER_API_KEY={key}")

        env_file.write_text("\n".join(lines) + "\n")
        os.environ["OPENROUTER_API_KEY"] = key

        return {"status": "ok"}

    # ── Mount all routers (hermes is guaranteed in Docker) ──────────
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

    # Sync active profile from hermes config
    try:
        from .Chat.agent_pool import set_active_profile
        from hermes_cli.profiles import get_active_profile as get_sticky_profile
        sticky = get_sticky_profile()
        if sticky and sticky != "default":
            set_active_profile(sticky)
    except Exception:
        pass

    logger.info("✅ Bridge ready — all routers mounted")
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
