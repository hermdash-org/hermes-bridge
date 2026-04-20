"""
CustomSkills templates — default skill templates and scaffolding.

Provides:
- Default SKILL.md template
- Folder scaffolding (references/, templates/, scripts/)
"""

import logging
from pathlib import Path

logger = logging.getLogger("bridge.custom_skills.templates")


# ═══════════════════════════════════════════════════════════════════
# DEFAULT SKILL TEMPLATE
# ═══════════════════════════════════════════════════════════════════


def get_default_skill_template(name: str = "", description: str = "") -> str:
    """Get the default SKILL.md template.
    
    Args:
        name: Skill name (optional, uses placeholder if empty)
        description: Skill description (optional, uses placeholder if empty)
    
    Returns:
        Default SKILL.md content with frontmatter
    """
    # Use placeholders if not provided
    if not name:
        name = "my-skill"
    if not description:
        description = "A brief description of what this skill does"
    
    template = f"""---
name: {name}
description: {description}
version: 1.0.0
platforms: [macos, linux, windows]
---

# {name.replace('-', ' ').title()}

{description}

## Usage

Describe how to use this skill. What tasks does it help with?

## Examples

Provide examples of how to use this skill:

1. Example 1
2. Example 2

## Configuration

If this skill requires configuration, document it here.

You can declare config variables in the frontmatter:

```yaml
metadata:
  hermes:
    config:
      - key: my-skill.api-key
        description: API key for external service
        default: ""
        prompt: Enter your API key
```

## References

Add reference files to the `references/` folder for context the agent should have.

## Templates

Add template files to the `templates/` folder for code or content the agent should generate.

## Scripts

Add executable scripts to the `scripts/` folder for automation tasks.
"""
    
    return template


# ═══════════════════════════════════════════════════════════════════
# FOLDER SCAFFOLDING
# ═══════════════════════════════════════════════════════════════════


def scaffold_skill_folders(skill_dir: Path) -> None:
    """Create default folder structure for a skill.
    
    Creates:
    - references/
    - templates/
    - scripts/
    
    Each folder gets a .gitkeep file to preserve empty folders in git.
    
    Args:
        skill_dir: Path to skill directory
    """
    folders = ["references", "templates", "scripts"]
    
    for folder in folders:
        folder_path = skill_dir / folder
        folder_path.mkdir(exist_ok=True)
        
        # Create .gitkeep to preserve empty folders
        gitkeep = folder_path / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()
    
    logger.info("Scaffolded folders for skill at %s", skill_dir)


# ═══════════════════════════════════════════════════════════════════
# EXAMPLE TEMPLATES
# ═══════════════════════════════════════════════════════════════════


def get_example_reference_template() -> str:
    """Get an example reference file template.
    
    Returns:
        Example reference markdown content
    """
    return """# Reference Document

This is an example reference file. Add context, documentation, or information
that the agent should have when using this skill.

## API Documentation

Document APIs, endpoints, or interfaces here.

## Best Practices

List best practices or guidelines.

## Common Patterns

Show common code patterns or usage examples.
"""


def get_example_template_template() -> str:
    """Get an example template file.
    
    Returns:
        Example template content
    """
    return """# Template File

This is an example template. The agent can use this as a starting point
for generating code or content.

## Variables

You can use placeholders like:
- {{PROJECT_NAME}}
- {{AUTHOR}}
- {{DATE}}

## Example Code

```python
def example_function():
    \"\"\"Example function template.\"\"\"
    pass
```
"""


def get_example_script_template() -> str:
    """Get an example Python script template.
    
    Returns:
        Example Python script content
    """
    return """#!/usr/bin/env python3
\"\"\"
Example script for automation tasks.

This script can be called by the agent to perform specific operations.
\"\"\"

import sys


def main():
    \"\"\"Main entry point.\"\"\"
    print("Running example script...")
    
    # Add your automation logic here
    
    print("Script completed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
"""


# ═══════════════════════════════════════════════════════════════════
# DEFAULT FILES FOR NEW SKILLS
# ═══════════════════════════════════════════════════════════════════


def get_default_skill_files() -> dict:
    """Get default files to create for a new skill.
    
    Returns:
        Dict mapping relative paths to file content
    """
    return {
        "references/example-reference.md": get_example_reference_template(),
        "templates/example-template.md": get_example_template_template(),
        "scripts/example-script.py": get_example_script_template(),
    }
