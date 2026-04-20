"""
CustomSkills — Create, edit, and manage user-created skills.

Profile-aware: uses get_profile_home() from agent_pool — the SAME
global profile resolver used by Sessions, Chat, Skills, and Profiles.

Storage:
  default  → ~/.hermes/skills-custom/
  coder    → ~/.hermes/profiles/coder/skills-custom/
  work     → ~/.hermes/profiles/work/skills-custom/

Each profile gets isolated custom skills. When the user switches profiles,
all endpoints automatically read/write to the new profile's directory.

Endpoints:
  POST   /custom-skills              — Create new skill
  GET    /custom-skills              — List custom skills
  GET    /custom-skills/{name}       — View custom skill details
  PUT    /custom-skills/{name}       — Edit skill content
  DELETE /custom-skills/{name}       — Delete skill
  POST   /custom-skills/{name}/files — Create file (reference/template/script)
  PUT    /custom-skills/{name}/files/{path} — Edit file
  DELETE /custom-skills/{name}/files/{path} — Delete file
  POST   /custom-skills/validate     — Validate skill content before save
"""

import logging
from pathlib import Path
from typing import List, Dict, Any

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from ..Chat.agent_pool import get_active_profile, get_profile_home
from .storage import (
    get_custom_skills_dir,
    ensure_custom_skills_configured,
    create_skill,
    delete_skill,
    skill_exists,
    list_custom_skills,
    get_skill_details,
    create_skill_file,
    delete_skill_file,
)
from .validate import validate_skill_content, ValidationResult
from .templates import get_default_skill_template
from .Cron import router as cron_router

router = APIRouter(prefix="/custom-skills", tags=["custom-skills"])
logger = logging.getLogger("bridge.custom_skills")

# Include cron sub-router
router.include_router(cron_router)


# ═══════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════


@router.post("/")
async def create_custom_skill(request: Request):
    """Create a new custom skill in the active profile.
    
    Body:
    {
        "name": "my-skill",
        "description": "Brief description",
        "content": "Full markdown content with frontmatter",
        "category": "optional-category"  // Creates skills/{category}/{name}/
    }
    
    Returns:
    {
        "success": true,
        "name": "my-skill",
        "path": "~/.hermes/skills-custom/my-skill",
        "profile": "default"
    }
    """
    try:
        body = await request.json()
        name = body.get("name", "").strip()
        description = body.get("description", "").strip()
        content = body.get("content", "").strip()
        category = body.get("category", "").strip()
        
        if not name:
            return JSONResponse(
                {"success": False, "error": "Skill name is required"},
                status_code=400
            )
        
        # Validate name (alphanumeric, hyphens, underscores only)
        import re
        if not re.match(r'^[a-z0-9][a-z0-9_-]*$', name):
            return JSONResponse(
                {"success": False, "error": "Invalid skill name. Use lowercase letters, numbers, hyphens, and underscores only."},
                status_code=400
            )
        
        # Check if skill already exists
        if skill_exists(name):
            return JSONResponse(
                {"success": False, "error": f"Skill '{name}' already exists"},
                status_code=409
            )
        
        # If no content provided, use template
        if not content:
            content = get_default_skill_template(name, description)
        
        # Validate content
        validation = validate_skill_content(content)
        if not validation.valid:
            return JSONResponse(
                {
                    "success": False,
                    "error": "Invalid skill content",
                    "validation_errors": validation.errors
                },
                status_code=400
            )
        
        # Create the skill
        skill_path = create_skill(name, content, category)
        
        # Ensure external_dirs is configured
        ensure_custom_skills_configured()
        
        return JSONResponse({
            "success": True,
            "name": name,
            "path": str(skill_path),
            "profile": get_active_profile(),
            "message": f"Skill '{name}' created successfully"
        })
        
    except Exception as e:
        logger.exception("Failed to create custom skill")
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500
        )


@router.get("/")
async def list_custom_skills_endpoint():
    """List all custom skills in the active profile.
    
    Returns:
    {
        "success": true,
        "profile": "default",
        "skills_dir": "~/.hermes/skills-custom",
        "count": 5,
        "skills": [
            {
                "name": "my-skill",
                "description": "Brief description",
                "category": "productivity",
                "version": "1.0.0",
                "path": "~/.hermes/skills-custom/productivity/my-skill"
            }
        ]
    }
    """
    try:
        skills = list_custom_skills()
        skills_dir = get_custom_skills_dir()
        
        return JSONResponse({
            "success": True,
            "profile": get_active_profile(),
            "skills_dir": str(skills_dir),
            "count": len(skills),
            "skills": skills
        })
        
    except Exception as e:
        logger.exception("Failed to list custom skills")
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500
        )


@router.get("/{name}")
async def get_custom_skill(name: str):
    """Get full details of a custom skill.
    
    Returns:
    {
        "success": true,
        "profile": "default",
        "skill": {
            "name": "my-skill",
            "description": "...",
            "content": "Full SKILL.md content",
            "frontmatter": {...},
            "linked_files": [...],
            "path": "..."
        }
    }
    """
    try:
        if not skill_exists(name):
            return JSONResponse(
                {"success": False, "error": f"Skill '{name}' not found"},
                status_code=404
            )
        
        skill = get_skill_details(name)
        
        return JSONResponse({
            "success": True,
            "profile": get_active_profile(),
            "skill": skill
        })
        
    except Exception as e:
        logger.exception("Failed to get custom skill: %s", name)
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500
        )


@router.put("/{name}")
async def update_custom_skill(name: str, request: Request):
    """Update a custom skill's SKILL.md content.
    
    Body:
    {
        "content": "Updated markdown content with frontmatter"
    }
    """
    try:
        if not skill_exists(name):
            return JSONResponse(
                {"success": False, "error": f"Skill '{name}' not found"},
                status_code=404
            )
        
        body = await request.json()
        content = body.get("content")
        
        if content is None:
            return JSONResponse(
                {"success": False, "error": "'content' field is required"},
                status_code=400
            )
        
        # Validate content
        validation = validate_skill_content(content)
        if not validation.valid:
            return JSONResponse(
                {
                    "success": False,
                    "error": "Invalid skill content",
                    "validation_errors": validation.errors
                },
                status_code=400
            )
        
        # Update the skill
        from .storage import update_skill
        skill_path = update_skill(name, content)
        
        return JSONResponse({
            "success": True,
            "name": name,
            "path": str(skill_path),
            "profile": get_active_profile(),
            "message": f"Skill '{name}' updated successfully"
        })
        
    except Exception as e:
        logger.exception("Failed to update custom skill: %s", name)
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500
        )


@router.delete("/{name}")
async def delete_custom_skill(name: str):
    """Delete a custom skill and all its files.
    
    Returns:
    {
        "success": true,
        "name": "my-skill",
        "profile": "default",
        "message": "Skill deleted successfully"
    }
    """
    try:
        if not skill_exists(name):
            return JSONResponse(
                {"success": False, "error": f"Skill '{name}' not found"},
                status_code=404
            )
        
        delete_skill(name)
        
        return JSONResponse({
            "success": True,
            "name": name,
            "profile": get_active_profile(),
            "message": f"Skill '{name}' deleted successfully"
        })
        
    except Exception as e:
        logger.exception("Failed to delete custom skill: %s", name)
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500
        )


@router.post("/{name}/files")
async def create_custom_skill_file(name: str, request: Request):
    """Create a new file in a skill directory (reference, template, script).
    
    Body:
    {
        "path": "references/api-docs.md",  // Relative path within skill
        "content": "File content"
    }
    """
    try:
        if not skill_exists(name):
            return JSONResponse(
                {"success": False, "error": f"Skill '{name}' not found"},
                status_code=404
            )
        
        body = await request.json()
        file_path = body.get("path", "").strip()
        content = body.get("content", "")
        
        if not file_path:
            return JSONResponse(
                {"success": False, "error": "'path' field is required"},
                status_code=400
            )
        
        # Security: prevent path traversal
        if ".." in file_path or file_path.startswith("/"):
            return JSONResponse(
                {"success": False, "error": "Invalid file path"},
                status_code=400
            )
        
        created_path = create_skill_file(name, file_path, content)
        
        return JSONResponse({
            "success": True,
            "name": name,
            "file_path": file_path,
            "full_path": str(created_path),
            "profile": get_active_profile(),
            "message": f"File '{file_path}' created successfully"
        })
        
    except Exception as e:
        logger.exception("Failed to create skill file: %s in %s", file_path, name)
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500
        )


@router.get("/{name}/files/{file_path:path}")
async def get_custom_skill_file(name: str, file_path: str):
    """Get content of a specific file in a skill directory.
    
    Returns:
    {
        "success": true,
        "name": "my-skill",
        "file_path": "references/api-docs.md",
        "content": "File content here...",
        "profile": "default"
    }
    """
    try:
        if not skill_exists(name):
            return JSONResponse(
                {"success": False, "error": f"Skill '{name}' not found"},
                status_code=404
            )
        
        # Security: prevent path traversal
        if ".." in file_path or file_path.startswith("/"):
            return JSONResponse(
                {"success": False, "error": "Invalid file path"},
                status_code=400
            )
        
        from .storage import get_skill_file_content
        content = get_skill_file_content(name, file_path)
        
        return JSONResponse({
            "success": True,
            "name": name,
            "file_path": file_path,
            "content": content,
            "profile": get_active_profile()
        })
        
    except ValueError as e:
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=404
        )
    except Exception as e:
        logger.exception("Failed to get skill file: %s in %s", file_path, name)
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500
        )


@router.put("/{name}/files/{file_path:path}")
async def update_custom_skill_file(name: str, file_path: str, request: Request):
    """Update a file in a skill directory.
    
    Body:
    {
        "content": "Updated file content"
    }
    """
    try:
        if not skill_exists(name):
            return JSONResponse(
                {"success": False, "error": f"Skill '{name}' not found"},
                status_code=404
            )
        
        body = await request.json()
        content = body.get("content")
        
        if content is None:
            return JSONResponse(
                {"success": False, "error": "'content' field is required"},
                status_code=400
            )
        
        # Security: prevent path traversal
        if ".." in file_path or file_path.startswith("/"):
            return JSONResponse(
                {"success": False, "error": "Invalid file path"},
                status_code=400
            )
        
        from .storage import update_skill_file
        updated_path = update_skill_file(name, file_path, content)
        
        return JSONResponse({
            "success": True,
            "name": name,
            "file_path": file_path,
            "full_path": str(updated_path),
            "profile": get_active_profile(),
            "message": f"File '{file_path}' updated successfully"
        })
        
    except Exception as e:
        logger.exception("Failed to update skill file: %s in %s", file_path, name)
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500
        )


@router.delete("/{name}/files/{file_path:path}")
async def delete_custom_skill_file(name: str, file_path: str):
    """Delete a file from a skill directory.
    
    Returns:
    {
        "success": true,
        "name": "my-skill",
        "file_path": "references/api-docs.md",
        "message": "File deleted successfully"
    }
    """
    try:
        if not skill_exists(name):
            return JSONResponse(
                {"success": False, "error": f"Skill '{name}' not found"},
                status_code=404
            )
        
        # Security: prevent path traversal
        if ".." in file_path or file_path.startswith("/"):
            return JSONResponse(
                {"success": False, "error": "Invalid file path"},
                status_code=400
            )
        
        delete_skill_file(name, file_path)
        
        return JSONResponse({
            "success": True,
            "name": name,
            "file_path": file_path,
            "profile": get_active_profile(),
            "message": f"File '{file_path}' deleted successfully"
        })
        
    except Exception as e:
        logger.exception("Failed to delete skill file: %s in %s", file_path, name)
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500
        )


@router.post("/validate")
async def validate_skill(request: Request):
    """Validate skill content before saving.
    
    Body:
    {
        "content": "Skill markdown content with frontmatter"
    }
    
    Returns:
    {
        "valid": true,
        "errors": [],
        "warnings": [],
        "frontmatter": {...}
    }
    """
    try:
        body = await request.json()
        content = body.get("content", "")
        
        validation = validate_skill_content(content)
        
        return JSONResponse({
            "valid": validation.valid,
            "errors": validation.errors,
            "warnings": validation.warnings,
            "frontmatter": validation.frontmatter
        })
        
    except Exception as e:
        logger.exception("Failed to validate skill content")
        return JSONResponse(
            {"valid": False, "errors": [str(e)], "warnings": []},
            status_code=500
        )


@router.get("/template/default")
async def get_skill_template():
    """Get the default skill template.
    
    Returns:
    {
        "success": true,
        "template": "---\nname: ...\n---\n..."
    }
    """
    try:
        template = get_default_skill_template()
        
        return JSONResponse({
            "success": True,
            "template": template
        })
        
    except Exception as e:
        logger.exception("Failed to get skill template")
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500
        )
