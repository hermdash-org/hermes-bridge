"""
CustomSkills storage layer — file system operations for custom skills.

Profile-aware: uses get_profile_home() from agent_pool.
All operations automatically target the active profile's skills-custom/ directory.

Storage paths:
  default  → ~/.hermes/skills-custom/
  coder    → ~/.hermes/profiles/coder/skills-custom/
  work     → ~/.hermes/profiles/work/skills-custom/

Skills structure:
  skills-custom/
    {category}/          # Optional category folder
      {skill-name}/
        SKILL.md         # Required
        references/      # Optional
        templates/       # Optional
        scripts/         # Optional
        assets/          # Optional
"""

import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from ..Chat.agent_pool import get_profile_home
from agent.skill_utils import parse_frontmatter, iter_skill_index_files

logger = logging.getLogger("bridge.custom_skills.storage")


# ═══════════════════════════════════════════════════════════════════
# PATH RESOLUTION
# ═══════════════════════════════════════════════════════════════════


def get_custom_skills_dir() -> Path:
    """Get the custom skills directory for the active profile.
    
    Returns:
        default  → ~/.hermes/skills-custom/
        coder    → ~/.hermes/profiles/coder/skills-custom/
    """
    return get_profile_home() / "skills-custom"


def _get_config_path() -> Path:
    """Get config.yaml path for the active profile."""
    return get_profile_home() / "config.yaml"


# ═══════════════════════════════════════════════════════════════════
# CONFIG MANAGEMENT
# ═══════════════════════════════════════════════════════════════════


def ensure_custom_skills_configured() -> None:
    """Ensure skills-custom/ is added to config.yaml external_dirs.
    
    This makes custom skills visible to the agent's skill system.
    Only adds if not already present.
    """
    config_path = _get_config_path()
    custom_dir = get_custom_skills_dir()
    
    # Load existing config
    config = {}
    if config_path.exists():
        try:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning("Failed to read config.yaml: %s", e)
            config = {}
    
    # Ensure skills.external_dirs exists
    if "skills" not in config:
        config["skills"] = {}
    if "external_dirs" not in config["skills"]:
        config["skills"]["external_dirs"] = []
    
    external_dirs = config["skills"]["external_dirs"]
    if isinstance(external_dirs, str):
        external_dirs = [external_dirs]
        config["skills"]["external_dirs"] = external_dirs
    
    # Add custom_dir if not present
    custom_dir_str = str(custom_dir)
    if custom_dir_str not in external_dirs:
        external_dirs.append(custom_dir_str)
        
        # Save config
        config_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            import yaml
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
            logger.info("Added %s to config.yaml external_dirs", custom_dir_str)
        except Exception as e:
            logger.error("Failed to save config.yaml: %s", e)


# ═══════════════════════════════════════════════════════════════════
# SKILL OPERATIONS
# ═══════════════════════════════════════════════════════════════════


def skill_exists(name: str) -> bool:
    """Check if a custom skill exists in the active profile.
    
    Args:
        name: Skill name (checks frontmatter name and directory name)
    
    Returns:
        True if skill exists, False otherwise
    """
    skills_dir = get_custom_skills_dir()
    if not skills_dir.exists():
        return False
    
    # Search for skill by frontmatter name or directory name
    for skill_md in iter_skill_index_files(skills_dir, "SKILL.md"):
        skill_dir = skill_md.parent
        try:
            content = skill_md.read_text(encoding="utf-8")[:2000]
            fm, _ = parse_frontmatter(content)
            skill_name = fm.get("name", skill_dir.name)
            if skill_name == name or skill_dir.name == name:
                return True
        except Exception:
            continue
    
    return False


def create_skill(name: str, content: str, category: str = "") -> Path:
    """Create a new custom skill.
    
    Args:
        name: Skill name (used for directory name)
        content: Full SKILL.md content (including frontmatter)
        category: Optional category (creates skills-custom/{category}/{name}/)
    
    Returns:
        Path to created skill directory
    
    Raises:
        ValueError: If skill already exists
        OSError: If file operations fail
    """
    from .templates import get_default_skill_files
    
    skills_dir = get_custom_skills_dir()
    
    # Determine skill path
    if category:
        skill_path = skills_dir / category / name
    else:
        skill_path = skills_dir / name
    
    # Check if already exists
    if skill_path.exists():
        raise ValueError(f"Skill directory already exists: {skill_path}")
    
    # Create directory structure
    skill_path.mkdir(parents=True, exist_ok=True)
    
    # Create SKILL.md
    skill_md = skill_path / "SKILL.md"
    skill_md.write_text(content, encoding="utf-8")
    
    # Create default folders with example files
    default_files = get_default_skill_files()
    for file_path, file_content in default_files.items():
        target_path = skill_path / file_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(file_content, encoding="utf-8")
    
    logger.info("Created custom skill: %s at %s with %d default files", 
                name, skill_path, len(default_files))
    return skill_path


def update_skill(name: str, content: str) -> Path:
    """Update an existing skill's SKILL.md content.
    
    Args:
        name: Skill name
        content: Updated SKILL.md content
    
    Returns:
        Path to skill directory
    
    Raises:
        ValueError: If skill not found
        OSError: If file operations fail
    """
    skill_path = _find_skill_path(name)
    if not skill_path:
        raise ValueError(f"Skill '{name}' not found")
    
    skill_md = skill_path / "SKILL.md"
    skill_md.write_text(content, encoding="utf-8")
    
    logger.info("Updated custom skill: %s", name)
    return skill_path


def delete_skill(name: str) -> None:
    """Delete a custom skill and all its files.
    
    Args:
        name: Skill name
    
    Raises:
        ValueError: If skill not found
        OSError: If deletion fails
    """
    skill_path = _find_skill_path(name)
    if not skill_path:
        raise ValueError(f"Skill '{name}' not found")
    
    shutil.rmtree(skill_path)
    logger.info("Deleted custom skill: %s at %s", name, skill_path)


def list_custom_skills() -> List[Dict]:
    """List all custom skills in the active profile.
    
    Returns:
        List of skill metadata dicts with keys:
        - name: Skill name
        - description: Brief description
        - category: Category (if in subfolder)
        - version: Version string
        - path: Full path to skill directory
    """
    skills_dir = get_custom_skills_dir()
    if not skills_dir.exists():
        return []
    
    skills = []
    seen_names = set()
    
    for skill_md in iter_skill_index_files(skills_dir, "SKILL.md"):
        skill_dir = skill_md.parent
        
        try:
            content = skill_md.read_text(encoding="utf-8")[:4000]
            frontmatter, body = parse_frontmatter(content)
        except Exception:
            continue
        
        name = str(frontmatter.get("name", skill_dir.name))[:64]
        if name in seen_names:
            continue
        seen_names.add(name)
        
        # Description from frontmatter or first non-heading line
        description = str(frontmatter.get("description", ""))
        if not description:
            for line in body.strip().split("\n"):
                line = line.strip()
                if line and not line.startswith("#"):
                    description = line[:200]
                    break
        
        # Category from directory structure
        try:
            rel = skill_dir.relative_to(skills_dir)
            parts = rel.parts
            category = parts[0] if len(parts) > 1 else ""
        except ValueError:
            category = ""
        
        skills.append({
            "name": name,
            "description": description[:200],
            "category": category,
            "version": str(frontmatter.get("version", "")),
            "path": str(skill_dir),
        })
    
    return skills


def get_skill_details(name: str) -> Dict:
    """Get full details of a custom skill.
    
    Args:
        name: Skill name
    
    Returns:
        Dict with keys:
        - name: Skill name
        - description: Description
        - content: Full SKILL.md content (body only, no frontmatter)
        - frontmatter: Parsed frontmatter dict
        - linked_files: List of files in skill directory
        - path: Full path to skill directory
    
    Raises:
        ValueError: If skill not found
    """
    skill_path = _find_skill_path(name)
    if not skill_path:
        raise ValueError(f"Skill '{name}' not found")
    
    skill_md = skill_path / "SKILL.md"
    content = skill_md.read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter(content)
    
    # Scan all files in skill directory
    linked_files = []
    for f in sorted(skill_path.rglob("*")):
        if f.is_file():
            try:
                rel = f.relative_to(skill_path)
                # Skip hidden files (starting with .) including .gitkeep
                if any(part.startswith('.') for part in rel.parts):
                    continue
                
                linked_files.append({
                    "name": f.name,
                    "path": str(rel),
                    "type": "file"
                })
            except ValueError:
                continue
    
    return {
        "name": str(frontmatter.get("name", name)),
        "description": str(frontmatter.get("description", "")),
        "content": body,
        "frontmatter": frontmatter,
        "linked_files": linked_files,
        "path": str(skill_path),
    }


# ═══════════════════════════════════════════════════════════════════
# FILE OPERATIONS
# ═══════════════════════════════════════════════════════════════════


def get_skill_file_content(name: str, file_path: str) -> str:
    """Get content of a specific file in a skill directory.
    
    Args:
        name: Skill name
        file_path: Relative path within skill
    
    Returns:
        File content as string
    
    Raises:
        ValueError: If skill or file not found
        OSError: If file operations fail
    """
    skill_path = _find_skill_path(name)
    if not skill_path:
        raise ValueError(f"Skill '{name}' not found")
    
    target_path = skill_path / file_path
    
    if not target_path.exists():
        raise ValueError(f"File not found: {file_path}")
    
    if not target_path.is_file():
        raise ValueError(f"Path is not a file: {file_path}")
    
    try:
        content = target_path.read_text(encoding="utf-8")
        logger.info("Read file %s from skill %s (%d chars)", file_path, name, len(content))
        return content
    except Exception as e:
        logger.error("Failed to read file %s from skill %s: %s", file_path, name, e)
        raise


def create_skill_file(name: str, file_path: str, content: str) -> Path:
    """Create a new file in a skill directory.
    
    Args:
        name: Skill name
        file_path: Relative path within skill (e.g., "references/api.md")
        content: File content
    
    Returns:
        Path to created file
    
    Raises:
        ValueError: If skill not found or file already exists
        OSError: If file operations fail
    """
    skill_path = _find_skill_path(name)
    if not skill_path:
        raise ValueError(f"Skill '{name}' not found")
    
    target_path = skill_path / file_path
    
    if target_path.exists():
        raise ValueError(f"File already exists: {file_path}")
    
    # Create parent directories
    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write file
    target_path.write_text(content, encoding="utf-8")
    
    logger.info("Created file %s in skill %s", file_path, name)
    return target_path


def update_skill_file(name: str, file_path: str, content: str) -> Path:
    """Update an existing file in a skill directory.
    
    Args:
        name: Skill name
        file_path: Relative path within skill
        content: Updated file content
    
    Returns:
        Path to updated file
    
    Raises:
        ValueError: If skill or file not found
        OSError: If file operations fail
    """
    skill_path = _find_skill_path(name)
    if not skill_path:
        raise ValueError(f"Skill '{name}' not found")
    
    target_path = skill_path / file_path
    
    if not target_path.exists():
        raise ValueError(f"File not found: {file_path}")
    
    target_path.write_text(content, encoding="utf-8")
    
    logger.info("Updated file %s in skill %s", file_path, name)
    return target_path


def delete_skill_file(name: str, file_path: str) -> None:
    """Delete a file from a skill directory.
    
    Args:
        name: Skill name
        file_path: Relative path within skill
    
    Raises:
        ValueError: If skill or file not found
        OSError: If deletion fails
    """
    skill_path = _find_skill_path(name)
    if not skill_path:
        raise ValueError(f"Skill '{name}' not found")
    
    target_path = skill_path / file_path
    
    if not target_path.exists():
        raise ValueError(f"File not found: {file_path}")
    
    target_path.unlink()
    logger.info("Deleted file %s from skill %s", file_path, name)


# ═══════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════


def _find_skill_path(name: str) -> Optional[Path]:
    """Find a skill directory by name.
    
    Searches by frontmatter name first, then directory name.
    
    Args:
        name: Skill name
    
    Returns:
        Path to skill directory, or None if not found
    """
    skills_dir = get_custom_skills_dir()
    if not skills_dir.exists():
        return None
    
    for skill_md in iter_skill_index_files(skills_dir, "SKILL.md"):
        skill_dir = skill_md.parent
        try:
            content = skill_md.read_text(encoding="utf-8")[:2000]
            fm, _ = parse_frontmatter(content)
            skill_name = fm.get("name", skill_dir.name)
            if skill_name == name or skill_dir.name == name:
                return skill_dir
        except Exception:
            continue
    
    return None
