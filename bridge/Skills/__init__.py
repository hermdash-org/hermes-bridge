"""
Skills — List, view, toggle installed skills for the active profile.

Profile-aware: uses get_profile_home() from agent_pool — the SAME
global profile resolver used by Sessions, Chat, and Profiles.
NO duplicate profile switching. NO frozen module-level globals.

Pattern:
  Sessions uses → get_session_db()      → reads get_profile_home() / "state.db"
  Skills   uses → _get_skills_dir()     → reads get_profile_home() / "skills"

Both delegate profile resolution to agent_pool.py. Zero spaghetti.

Safe hermes-agent imports (stateless, no frozen globals):
  - parse_frontmatter(content)       → takes string param
  - skill_matches_platform(fm)       → takes dict param
  - iter_skill_index_files(dir, fn)  → takes Path param
  - extract_skill_config_vars(fm)    → takes dict param
  - extract_skill_conditions(fm)     → takes dict param
  - HubLockFile(path=...)            → takes custom path param

Unsafe (frozen at import, DO NOT USE):
  - tools.skills_tool.SKILLS_DIR     → cached at import time
  - tools.skills_tool._find_all_skills() → uses frozen SKILLS_DIR
  - tools.skills_sync.MANIFEST_FILE  → cached at import time
  - hermes_constants.get_skills_dir() → reads HERMES_HOME env once

Endpoints:
  GET    /skills              — List all installed skills
  GET    /skills/{name}       — View skill details (SKILL.md content)
  PUT    /skills/{name}/toggle — Enable/disable a skill
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..Chat.agent_pool import get_active_profile, get_profile_home

router = APIRouter(prefix="/skills", tags=["skills"])
logger = logging.getLogger("bridge.skills")

# ── Stateless imports from hermes-agent (safe — no frozen globals) ──

from agent.skill_utils import (
    parse_frontmatter,
    skill_matches_platform,
    extract_skill_config_vars,
    extract_skill_conditions,
    iter_skill_index_files,
)

# HubLockFile accepts a custom path — safe to use with profile paths
from tools.skills_hub import HubLockFile


# ── Profile-aware path resolution ──────────────────────────────────
# These call get_profile_home() on every request — always current.
# When the user switches profiles via POST /profiles/switch,
# agent_pool updates _active_profile, and these paths change too.

def _get_skills_dir() -> Path:
    """Resolve the active profile's skills directory.

    default  → ~/.hermes/skills
    coder    → ~/.hermes/profiles/coder/skills
    """
    return get_profile_home() / "skills"


def _get_config_path() -> Path:
    """Resolve the active profile's config.yaml."""
    return get_profile_home() / "config.yaml"


def _get_hub_lock_path() -> Path:
    """Resolve the active profile's hub lockfile."""
    return _get_skills_dir() / ".hub" / "lock.json"


def _get_manifest_path() -> Path:
    """Resolve the active profile's bundled manifest."""
    return _get_skills_dir() / ".bundled_manifest"


# ── Config helpers (profile-aware, no frozen globals) ──────────────

def _load_profile_config() -> dict:
    """Load config.yaml from the active profile."""
    config_path = _get_config_path()
    if not config_path.exists():
        return {}
    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _save_profile_config(config: dict) -> None:
    """Save config.yaml to the active profile."""
    config_path = _get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    import yaml
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)


def _get_disabled_skills(config: dict) -> Set[str]:
    """Read disabled skill names from a config dict.

    Mirrors hermes_cli/skills_config.py:get_disabled_skills() but takes
    a config dict (no frozen path).
    """
    skills_cfg = config.get("skills", {})
    if not isinstance(skills_cfg, dict):
        return set()
    disabled = skills_cfg.get("disabled", [])
    if isinstance(disabled, str):
        disabled = [disabled]
    return {str(s).strip() for s in disabled if str(s).strip()}


def _get_hub_installed() -> Dict[str, dict]:
    """Load hub lockfile for the active profile.

    Uses HubLockFile with the profile's path — NOT the frozen module global.
    """
    lock_path = _get_hub_lock_path()
    if not lock_path.exists():
        return {}
    try:
        lock = HubLockFile(path=lock_path)
        return {e["name"]: e for e in lock.list_installed()}
    except Exception:
        return {}


def _read_manifest() -> set:
    """Read the bundled manifest for the active profile.

    Returns set of bundled skill names (the same data as
    tools.skills_sync._read_manifest() but from the profile's path).
    """
    manifest_path = _get_manifest_path()
    if not manifest_path.exists():
        return set()
    try:
        result = set()
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            # v2 format: name:hash — we only need the name
            name = line.split(":", 1)[0].strip()
            if name:
                result.add(name)
        return result
    except Exception:
        return set()


# ── Skill discovery (profile-aware reimplementation) ───────────────

def _discover_skills(skills_dir: Path, disabled: Set[str]) -> List[dict]:
    """Walk the active profile's skills directory and parse all SKILL.md files.

    Returns skill metadata dicts. Includes ALL skills (disabled ones
    get enabled=False so the UI can show toggles).

    Uses stateless hermes-agent functions (parse_frontmatter, etc.)
    with the profile's path — never touches frozen module globals.
    """
    if not skills_dir.is_dir():
        return []

    skills = []
    seen_names: set = set()
    hub_installed = _get_hub_installed()
    builtin_names = _read_manifest()

    for skill_md in iter_skill_index_files(skills_dir, "SKILL.md"):
        skill_dir = skill_md.parent

        try:
            content = skill_md.read_text(encoding="utf-8")[:4000]
            frontmatter, body = parse_frontmatter(content)
        except Exception:
            continue

        if not skill_matches_platform(frontmatter):
            continue

        name = str(frontmatter.get("name", skill_dir.name))[:64]
        if name in seen_names:
            continue
        seen_names.add(name)

        # Description — from frontmatter or first non-heading line
        description = str(frontmatter.get("description", ""))
        if not description:
            for line in body.strip().split("\n"):
                line = line.strip()
                if line and not line.startswith("#"):
                    description = line[:200]
                    break

        # Category from directory structure (skills/{category}/{name})
        try:
            rel = skill_dir.relative_to(skills_dir)
            parts = rel.parts
            category = parts[0] if len(parts) > 1 else ""
        except ValueError:
            category = ""

        # Source classification
        hub_entry = hub_installed.get(name)
        if hub_entry:
            source = hub_entry.get("source", "hub")
            trust_level = hub_entry.get("trust_level", "community")
        elif name in builtin_names:
            source = "builtin"
            trust_level = "builtin"
        else:
            source = "local"
            trust_level = "local"

        skills.append({
            "name": name,
            "description": description[:200],
            "category": category,
            "enabled": name not in disabled,
            "source": source,
            "trust_level": trust_level,
            "version": str(frontmatter.get("version", "")),
            "platforms": frontmatter.get("platforms", []),
            "path": str(skill_dir),
        })

    return skills


def _find_skill_path(skills_dir: Path, name: str) -> Optional[Path]:
    """Find a skill directory by name within the active profile's skills dir.

    Checks frontmatter name first, then directory name as fallback.
    """
    if not skills_dir.is_dir():
        return None

    for skill_md in iter_skill_index_files(skills_dir, "SKILL.md"):
        skill_dir = skill_md.parent
        try:
            content = skill_md.read_text(encoding="utf-8")[:2000]
            fm, _ = parse_frontmatter(content)
            skill_name = fm.get("name", skill_dir.name)
            if skill_name == name:
                return skill_dir
        except Exception:
            continue

        # Directory name fallback
        if skill_dir.name == name:
            return skill_dir

    return None


# ═══════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════


# ── GET /skills — List all installed skills ─────────────────────────

@router.get("/")
async def list_skills():
    """List all installed skills for the active profile.

    Profile-aware: reads from get_profile_home() / "skills".
    Includes enabled/disabled state from profile's config.yaml.
    Returns ALL skills so the UI can render toggles.
    """
    try:
        skills_dir = _get_skills_dir()
        config = _load_profile_config()
        disabled = _get_disabled_skills(config)

        skills = _discover_skills(skills_dir, disabled)

        # Sort: enabled first, then by category, then alphabetical
        skills.sort(key=lambda s: (not s["enabled"], s.get("category", ""), s["name"]))

        return JSONResponse({
            "success": True,
            "profile": get_active_profile(),
            "skills_dir": str(skills_dir),
            "count": len(skills),
            "enabled_count": sum(1 for s in skills if s["enabled"]),
            "disabled_count": sum(1 for s in skills if not s["enabled"]),
            "skills": skills,
        })
    except Exception as e:
        logger.exception("Failed to list skills")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── GET /skills/{name} — View skill details ────────────────────────

@router.get("/{name}")
async def get_skill(name: str):
    """Get full details of a specific skill.

    Returns SKILL.md content, parsed frontmatter, config vars,
    conditions, linked files, and enabled state.
    """
    try:
        skills_dir = _get_skills_dir()
        config = _load_profile_config()
        disabled = _get_disabled_skills(config)

        # Find the skill
        skill_path = _find_skill_path(skills_dir, name)
        if not skill_path:
            return JSONResponse(
                {"success": False, "error": f"Skill '{name}' not found"},
                status_code=404,
            )

        skill_md = skill_path / "SKILL.md"
        content = skill_md.read_text(encoding="utf-8")
        frontmatter, body = parse_frontmatter(content)

        # Config variable declarations
        config_vars = extract_skill_config_vars(frontmatter)

        # Conditional activation fields
        conditions = extract_skill_conditions(frontmatter)

        # Scan the entire file tree (no guessing folder names)
        linked_files = []
        for f in sorted(skill_path.rglob("*")):
            if f.is_file():
                try:
                    rel = f.relative_to(skill_path)
                    # Skip hidden files or directories (.git, .DS_Store, etc)
                    if any(part.startswith('.') for part in rel.parts):
                        continue
                    
                    linked_files.append({
                        "name": f.name,
                        "path": str(rel),
                        "type": "file"
                    })
                except ValueError:
                    continue

        # Category from directory structure
        try:
            rel = skill_path.relative_to(skills_dir)
            parts = rel.parts
            category = parts[0] if len(parts) > 1 else ""
        except ValueError:
            category = ""

        # Source classification
        hub_installed = _get_hub_installed()
        builtin_names = _read_manifest()
        hub_entry = hub_installed.get(name)

        if hub_entry:
            source = hub_entry.get("source", "hub")
            trust_level = hub_entry.get("trust_level", "community")
        elif name in builtin_names:
            source = "builtin"
            trust_level = "builtin"
        else:
            source = "local"
            trust_level = "local"

        return JSONResponse({
            "success": True,
            "profile": get_active_profile(),
            "skill": {
                "name": str(frontmatter.get("name", name)),
                "description": str(frontmatter.get("description", "")),
                "category": category,
                "version": str(frontmatter.get("version", "")),
                "platforms": frontmatter.get("platforms", []),
                "enabled": name not in disabled,
                "source": source,
                "trust_level": trust_level,
                "content": body,
                "frontmatter": _sanitize_frontmatter(frontmatter),
                "config_vars": config_vars,
                "conditions": conditions,
                "linked_files": linked_files,
                "path": str(skill_path),
            },
        })
    except Exception as e:
        logger.exception("Failed to get skill: %s", name)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── PUT /skills/{name} — Edit skill content ────────────────────────

@router.put("/{name}")
async def edit_skill(name: str, request: Request):
    """Edit the SKILL.md content of an existing skill.

    Body: { "content": "..." } -> Raw markdown string including frontmatter.
    """
    try:
        body = await request.json()
        content = body.get("content")

        if content is None:
            return JSONResponse(
                {"success": False, "error": "'content' field is required"},
                status_code=400,
            )

        # Verify skill exists
        skills_dir = _get_skills_dir()
        skill_path = _find_skill_path(skills_dir, name)
        if not skill_path:
            return JSONResponse(
                {"success": False, "error": f"Skill '{name}' not found"},
                status_code=404,
            )

        skill_md = skill_path / "SKILL.md"
        
        # We don't parse the frontmatter to validate here, we just save the 
        # raw string from the user's editor directly, trusting it's valid markdown.
        skill_md.write_text(content, encoding="utf-8")

        return JSONResponse({
            "success": True,
            "name": name,
            "profile": get_active_profile(),
            "message": "Skill updated successfully"
        })
    except Exception as e:
        logger.exception("Failed to edit skill: %s", name)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── GET /skills/{name}/files/{filepath:path} — Read any file ────────

@router.get("/{name}/files/{filepath:path}")
async def get_skill_file(name: str, filepath: str):
    """Read the content of any file within a skill directory."""
    try:
        skills_dir = _get_skills_dir()
        skill_path = _find_skill_path(skills_dir, name)
        if not skill_path:
            return JSONResponse({"success": False, "error": f"Skill '{name}' not found"}, status_code=404)

        # Secure path resolution
        target_path = (skill_path / filepath).resolve()
        if not str(target_path).startswith(str(skill_path.resolve())):
            return JSONResponse({"success": False, "error": "Path traversal denied"}, status_code=403)

        if not target_path.is_file():
            return JSONResponse({"success": False, "error": f"File '{filepath}' not found"}, status_code=404)

        content = target_path.read_text(encoding="utf-8")
        return {"success": True, "content": content}
    except UnicodeDecodeError:
        return JSONResponse({"success": False, "error": "Cannot read binary files via this endpoint"}, status_code=400)
    except Exception as e:
        logger.exception("Failed to read file: %s in skill: %s", filepath, name)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── PUT /skills/{name}/files/{filepath:path} — Write any file ───────

@router.put("/{name}/files/{filepath:path}")
async def write_skill_file(name: str, filepath: str, request: Request):
    """Edit the content of any file within a skill directory."""
    try:
        body = await request.json()
        content = body.get("content")

        if content is None:
            return JSONResponse({"success": False, "error": "'content' field is required"}, status_code=400)

        skills_dir = _get_skills_dir()
        skill_path = _find_skill_path(skills_dir, name)
        if not skill_path:
            return JSONResponse({"success": False, "error": f"Skill '{name}' not found"}, status_code=404)

        # Secure path resolution
        target_path = (skill_path / filepath).resolve()
        if not str(target_path).startswith(str(skill_path.resolve())):
            return JSONResponse({"success": False, "error": "Path traversal denied"}, status_code=403)

        # Create subdirectories if they don't exist
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")

        return {"success": True, "message": f"File {filepath} updated successfully"}
    except Exception as e:
        logger.exception("Failed to write to file: %s in skill: %s", filepath, name)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── POST /skills/{name}/run — Execute a skill in chat ──────────────

@router.post("/{name}/run")
async def run_skill(name: str, request: Request):
    """Format a skill into a run-ready message for the chat pipeline.

    Follows the EXACT proven pattern from hermes-agent core:
      agent/skill_commands.py → build_skill_invocation_message()

    Returns the formatted message string. The frontend sends this
    through POST /chat to create a skill-locked chat session.

    Body: { "instruction": "optional user instruction" }
    Returns: { "success": true, "message": "...", "skill_name": "..." }
    """
    try:
        body = await request.json()
        user_instruction = body.get("instruction", "")

        skills_dir = _get_skills_dir()
        skill_path = _find_skill_path(skills_dir, name)
        if not skill_path:
            return JSONResponse(
                {"success": False, "error": f"Skill '{name}' not found"},
                status_code=404,
            )

        # Read SKILL.md and parse
        skill_md = skill_path / "SKILL.md"
        if not skill_md.exists():
            return JSONResponse(
                {"success": False, "error": f"SKILL.md not found for '{name}'"},
                status_code=404,
            )

        content = skill_md.read_text(encoding="utf-8")
        frontmatter, body_text = parse_frontmatter(content)

        skill_display_name = str(frontmatter.get("name", name))

        # Discover linked files (same logic as get_skill)
        linked_files = []
        for f in sorted(skill_path.rglob("*")):
            if f.is_file():
                try:
                    rel = f.relative_to(skill_path)
                    if any(part.startswith('.') for part in rel.parts):
                        continue
                    linked_files.append({
                        "name": f.name,
                        "path": str(rel),
                    })
                except ValueError:
                    continue

        # Format using proven pattern from hermes-agent core
        from .run import format_skill_run_message

        formatted_message = format_skill_run_message(
            skill_name=skill_display_name,
            skill_content=body_text,
            skill_path=skill_path,
            linked_files=linked_files,
            raw_content=content,
            user_instruction=user_instruction,
        )

        return JSONResponse({
            "success": True,
            "message": formatted_message,
            "skill_name": skill_display_name,
            "profile": get_active_profile(),
        })
    except Exception as e:
        logger.exception("Failed to run skill: %s", name)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── PUT /skills/{name}/toggle — Enable/disable ─────────────────────

@router.put("/{name}/toggle")
async def toggle_skill(name: str, request: Request):
    """Enable or disable a skill.

    Body: { "enabled": true } or { "enabled": false }

    Writes to the active profile's config.yaml under skills.disabled[].
    Follows the same config structure as hermes_cli/skills_config.py.
    """
    try:
        body = await request.json()
        enabled = body.get("enabled")

        if enabled is None:
            return JSONResponse(
                {"success": False, "error": "'enabled' field is required"},
                status_code=400,
            )

        # Verify skill exists
        skills_dir = _get_skills_dir()
        skill_path = _find_skill_path(skills_dir, name)
        if not skill_path:
            return JSONResponse(
                {"success": False, "error": f"Skill '{name}' not found"},
                status_code=404,
            )

        # Update config
        config = _load_profile_config()
        disabled = _get_disabled_skills(config)

        if enabled:
            disabled.discard(name)
        else:
            disabled.add(name)

        # Write back
        config.setdefault("skills", {})
        config["skills"]["disabled"] = sorted(disabled)
        _save_profile_config(config)

        return JSONResponse({
            "success": True,
            "name": name,
            "enabled": bool(enabled),
            "profile": get_active_profile(),
        })
    except Exception as e:
        logger.exception("Failed to toggle skill: %s", name)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── Helpers ─────────────────────────────────────────────────────────

def _sanitize_frontmatter(fm: dict) -> dict:
    """Ensure frontmatter is JSON-serializable."""
    result = {}
    for k, v in fm.items():
        if isinstance(v, (str, int, float, bool, type(None))):
            result[k] = v
        elif isinstance(v, list):
            result[k] = [str(i) if not isinstance(i, (str, int, float, bool, type(None))) else i for i in v]
        elif isinstance(v, dict):
            result[k] = _sanitize_frontmatter(v)
        else:
            result[k] = str(v)
    return result
