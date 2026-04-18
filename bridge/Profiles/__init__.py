"""
Profiles — List, switch, create, rename, delete profiles.

Uses hermes_cli.profiles directly — zero reimplementation.
Each profile gets its own sessions, memory, skills, config, and DB.

Endpoints:
  GET    /profiles          — List all profiles
  GET    /profiles/active   — Get current active profile
  POST   /profiles/switch   — Switch active profile
  POST   /profiles          — Create a new profile
  PUT    /profiles/{name}   — Rename a profile
  DELETE /profiles/{name}   — Delete a profile
"""

import io
import sys

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..Chat.agent_pool import (
    get_active_profile,
    get_profile_home,
    get_session_db,
    set_active_profile,
)

router = APIRouter(prefix="/profiles", tags=["profiles"])


# ── GET /profiles — List all profiles ───────────────────────────────

@router.get("/")
async def list_all_profiles():
    """List all profiles with metadata.

    Returns name, model, provider, gateway status, skill count,
    and which one is currently active in HemUI.
    """
    try:
        from hermes_cli.profiles import list_profiles

        profiles = list_profiles()
        active = get_active_profile()

        result = []
        for p in profiles:
            result.append({
                "name": p.name,
                "path": str(p.path),
                "is_default": p.is_default,
                "is_active": p.name == active,
                "gateway_running": p.gateway_running,
                "model": p.model,
                "provider": p.provider,
                "has_env": p.has_env,
                "skill_count": p.skill_count,
                "alias": str(p.alias_path) if p.alias_path else None,
            })

        return JSONResponse({
            "success": True,
            "active": active,
            "count": len(result),
            "profiles": result,
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── GET /profiles/active — Current active profile ──────────────────

@router.get("/active")
async def get_active():
    """Get the current active profile. Instant — reads from memory."""
    active = get_active_profile()
    home = get_profile_home(active)

    return JSONResponse({
        "success": True,
        "profile": active,
        "home": str(home),
        "exists": home.is_dir(),
    })


# ── POST /profiles/switch — Switch profile ─────────────────────────

@router.post("/switch")
async def switch_profile(request: Request):
    """Switch to a different profile.

    Body: { "profile": "coder" }

    Sub-microsecond operation. In-flight requests are NOT affected.
    Frontend should reload sessions/memories after switch.
    """
    try:
        body = await request.json()
        profile_name = body.get("profile", "").strip()

        if not profile_name:
            return JSONResponse(
                {"success": False, "error": "profile name is required"},
                status_code=400,
            )

        from hermes_cli.profiles import profile_exists, validate_profile_name

        try:
            validate_profile_name(profile_name)
        except ValueError as e:
            return JSONResponse(
                {"success": False, "error": str(e)},
                status_code=400,
            )

        if not profile_exists(profile_name):
            return JSONResponse(
                {"success": False, "error": f"Profile '{profile_name}' does not exist"},
                status_code=404,
            )

        old_profile = get_active_profile()
        set_active_profile(profile_name)

        # Pre-warm DB connection for the new profile
        get_session_db(profile_name)

        home = get_profile_home(profile_name)

        return JSONResponse({
            "success": True,
            "previous": old_profile,
            "active": profile_name,
            "home": str(home),
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── POST /profiles — Create profile ────────────────────────────────

@router.post("/")
async def create_profile(request: Request):
    """Create a new profile.

    Body: {
        "name": "coder",
        "clone": true,       (optional — clone config from active)
        "clone_all": false   (optional — full copy)
    }
    """
    try:
        body = await request.json()
        name = body.get("name", "").strip()
        clone = body.get("clone", False)
        clone_all = body.get("clone_all", False)

        if not name:
            return JSONResponse(
                {"success": False, "error": "name is required"},
                status_code=400,
            )

        from hermes_cli.profiles import (
            create_profile as _create,
            seed_profile_skills,
            validate_profile_name,
        )

        try:
            validate_profile_name(name)
        except ValueError as e:
            return JSONResponse(
                {"success": False, "error": str(e)},
                status_code=400,
            )

        # Suppress print() from hermes_cli in headless mode
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
        try:
            profile_dir = _create(
                name=name,
                clone_config=clone,
                clone_all=clone_all,
            )
            seed_profile_skills(profile_dir, quiet=True)
        finally:
            sys.stdout, sys.stderr = old_out, old_err

        return JSONResponse({
            "success": True,
            "name": name,
            "path": str(profile_dir),
        })
    except FileExistsError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=409)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── PUT /profiles/{name} — Rename profile ──────────────────────────

@router.put("/{name}")
async def rename_profile_endpoint(name: str, request: Request):
    """Rename a profile.

    Body: { "new_name": "assistant" }
    """
    try:
        body = await request.json()
        new_name = body.get("new_name", "").strip()

        if not new_name:
            return JSONResponse(
                {"success": False, "error": "new_name is required"},
                status_code=400,
            )

        from hermes_cli.profiles import rename_profile as _rename

        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
        try:
            new_dir = _rename(name, new_name)
        finally:
            sys.stdout, sys.stderr = old_out, old_err

        if get_active_profile() == name:
            set_active_profile(new_name)

        return JSONResponse({
            "success": True,
            "old_name": name,
            "new_name": new_name,
            "path": str(new_dir),
        })
    except FileNotFoundError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=404)
    except FileExistsError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=409)
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── DELETE /profiles/{name} — Delete profile ───────────────────────

@router.delete("/{name}")
async def delete_profile_endpoint(name: str):
    """Delete a profile.

    Suppresses print() from hermes_cli (no terminal in headless mode).
    Falls back to default if deleted profile was active.
    """
    try:
        from hermes_cli.profiles import delete_profile as _delete

        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        try:
            _delete(name, yes=True)
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr

        if get_active_profile() == name:
            set_active_profile("default")

        return JSONResponse({
            "success": True,
            "deleted": name,
            "active": get_active_profile(),
        })
    except FileNotFoundError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=404)
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)
