"""
CustomSkills validation — validate SKILL.md content and frontmatter.

Validates:
- YAML frontmatter structure
- Required fields (name, description)
- Field length limits
- Platform values
- Version format
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

from agent.skill_utils import parse_frontmatter

logger = logging.getLogger("bridge.custom_skills.validate")


# ═══════════════════════════════════════════════════════════════════
# VALIDATION RESULT
# ═══════════════════════════════════════════════════════════════════


@dataclass
class ValidationResult:
    """Result of skill content validation."""
    
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    frontmatter: Dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════
# VALIDATION RULES
# ═══════════════════════════════════════════════════════════════════


# Valid platform values
VALID_PLATFORMS = {"macos", "linux", "windows"}

# Field length limits
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 500
MAX_VERSION_LENGTH = 20

# Name pattern (alphanumeric, hyphens, underscores)
NAME_PATTERN = re.compile(r'^[a-z0-9][a-z0-9_-]*$')

# Version pattern (semantic versioning)
VERSION_PATTERN = re.compile(r'^\d+\.\d+(\.\d+)?$')


# ═══════════════════════════════════════════════════════════════════
# VALIDATION FUNCTIONS
# ═══════════════════════════════════════════════════════════════════


def validate_skill_content(content: str) -> ValidationResult:
    """Validate skill content including frontmatter and body.
    
    Args:
        content: Full SKILL.md content (including frontmatter)
    
    Returns:
        ValidationResult with validation status and messages
    """
    result = ValidationResult(valid=True)
    
    # Parse frontmatter
    try:
        frontmatter, body = parse_frontmatter(content)
        result.frontmatter = frontmatter
    except Exception as e:
        result.valid = False
        result.errors.append(f"Failed to parse frontmatter: {str(e)}")
        return result
    
    # Validate frontmatter
    fm_result = validate_frontmatter(frontmatter)
    result.errors.extend(fm_result.errors)
    result.warnings.extend(fm_result.warnings)
    result.valid = result.valid and fm_result.valid
    
    # Validate body
    body_result = validate_body(body)
    result.warnings.extend(body_result.warnings)
    
    return result


def validate_frontmatter(frontmatter: Dict[str, Any]) -> ValidationResult:
    """Validate frontmatter structure and required fields.
    
    Args:
        frontmatter: Parsed frontmatter dict
    
    Returns:
        ValidationResult with validation status and messages
    """
    result = ValidationResult(valid=True, frontmatter=frontmatter)
    
    # Required: name
    name = frontmatter.get("name")
    if not name:
        result.valid = False
        result.errors.append("Missing required field: 'name'")
    else:
        name_str = str(name).strip()
        
        # Validate name length
        if len(name_str) > MAX_NAME_LENGTH:
            result.valid = False
            result.errors.append(f"Name too long (max {MAX_NAME_LENGTH} characters)")
        
        # Validate name pattern
        if not NAME_PATTERN.match(name_str):
            result.valid = False
            result.errors.append(
                "Invalid name format. Use lowercase letters, numbers, hyphens, "
                "and underscores only. Must start with letter or number."
            )
    
    # Required: description
    description = frontmatter.get("description")
    if not description:
        result.valid = False
        result.errors.append("Missing required field: 'description'")
    else:
        desc_str = str(description).strip()
        
        # Validate description length
        if len(desc_str) > MAX_DESCRIPTION_LENGTH:
            result.warnings.append(
                f"Description is long ({len(desc_str)} chars). "
                f"Consider keeping it under {MAX_DESCRIPTION_LENGTH} characters."
            )
        
        if len(desc_str) < 10:
            result.warnings.append("Description is very short. Consider adding more detail.")
    
    # Optional: version
    version = frontmatter.get("version")
    if version:
        version_str = str(version).strip()
        
        if len(version_str) > MAX_VERSION_LENGTH:
            result.warnings.append(f"Version string is long (max {MAX_VERSION_LENGTH} characters)")
        
        if not VERSION_PATTERN.match(version_str):
            result.warnings.append(
                "Version should follow semantic versioning (e.g., '1.0.0' or '1.0')"
            )
    
    # Optional: platforms
    platforms = frontmatter.get("platforms")
    if platforms:
        if isinstance(platforms, str):
            platforms = [platforms]
        
        if isinstance(platforms, list):
            for platform in platforms:
                platform_str = str(platform).lower().strip()
                if platform_str not in VALID_PLATFORMS:
                    result.warnings.append(
                        f"Unknown platform '{platform_str}'. "
                        f"Valid platforms: {', '.join(sorted(VALID_PLATFORMS))}"
                    )
        else:
            result.warnings.append("'platforms' should be a list or string")
    
    # Optional: metadata.hermes.config
    metadata = frontmatter.get("metadata")
    if metadata and isinstance(metadata, dict):
        hermes = metadata.get("hermes")
        if hermes and isinstance(hermes, dict):
            config = hermes.get("config")
            if config:
                config_result = validate_config_vars(config)
                result.warnings.extend(config_result.warnings)
    
    return result


def validate_body(body: str) -> ValidationResult:
    """Validate skill body content.
    
    Args:
        body: Skill body content (without frontmatter)
    
    Returns:
        ValidationResult with warnings (body validation is non-blocking)
    """
    result = ValidationResult(valid=True)
    
    body_stripped = body.strip()
    
    # Warn if body is empty
    if not body_stripped:
        result.warnings.append("Skill body is empty. Consider adding usage instructions.")
    
    # Warn if body is very short
    elif len(body_stripped) < 50:
        result.warnings.append("Skill body is very short. Consider adding more detail.")
    
    return result


def validate_config_vars(config: Any) -> ValidationResult:
    """Validate config variable declarations.
    
    Args:
        config: Config vars from metadata.hermes.config
    
    Returns:
        ValidationResult with warnings
    """
    result = ValidationResult(valid=True)
    
    if isinstance(config, dict):
        config = [config]
    
    if not isinstance(config, list):
        result.warnings.append("metadata.hermes.config should be a list or dict")
        return result
    
    for i, item in enumerate(config):
        if not isinstance(item, dict):
            result.warnings.append(f"Config var {i} should be a dict")
            continue
        
        # Check required fields
        if "key" not in item:
            result.warnings.append(f"Config var {i} missing 'key' field")
        
        if "description" not in item:
            result.warnings.append(f"Config var {i} missing 'description' field")
    
    return result
