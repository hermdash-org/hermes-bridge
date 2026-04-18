"""
Skill Execution — format a skill's SKILL.md into a run-ready message.

This module replicates the EXACT proven pattern from hermes-agent core:
  agent/skill_commands.py → build_skill_invocation_message()
  agent/skill_commands.py → _build_skill_message()
  agent/skill_commands.py → _inject_skill_config()

The formatted message is returned as a plain string. The frontend sends
that string through the existing POST /chat pipeline — zero duplication
of agent logic, clean separation of concerns.

Architecture reference:
  cli.py:5617-5625  — CLI builds the message and queues it as user input
  cli.py:86         — agent.run_conversation(message) processes it
  skill_commands.py:82-118 — config var injection into message
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("bridge.skills.run")


# ── Config injection (proven pattern from skill_commands.py:82-118) ──────

def _inject_skill_config(
    raw_content: str,
    parts: list[str],
) -> None:
    """Resolve and inject skill-declared config values into the message parts.

    Replicates the exact mechanism from:
      agent/skill_commands.py → _inject_skill_config() (lines 82-118)

    If the SKILL.md frontmatter declares ``metadata.hermes.config`` entries,
    their current values (from config.yaml or defaults) are appended as a
    ``[Skill config: ...]`` block so the agent knows the configured values
    without needing to read config.yaml itself.
    """
    try:
        from agent.skill_utils import (
            extract_skill_config_vars,
            parse_frontmatter,
            resolve_skill_config_values,
        )

        if not raw_content:
            return

        frontmatter, _ = parse_frontmatter(raw_content)
        config_vars = extract_skill_config_vars(frontmatter)
        if not config_vars:
            return

        resolved = resolve_skill_config_values(config_vars)
        if not resolved:
            return

        lines = ["", "[Skill config (from ~/.hermes/config.yaml):"]
        for key, value in resolved.items():
            display_val = str(value) if value else "(not set)"
            lines.append(f"  {key} = {display_val}")
        lines.append("]")
        parts.extend(lines)
    except ImportError:
        logger.debug("agent.skill_utils not available — skipping config injection")
    except Exception:
        pass  # Non-critical — skill still loads without config injection


def format_skill_run_message(
    skill_name: str,
    skill_content: str,
    skill_path: Path,
    linked_files: list[dict],
    raw_content: str = "",
    user_instruction: str = "",
    autonomous: bool = True,
) -> str:
    """Format a skill into a run-ready user message.

    Follows the exact pattern from hermes-agent core:
      agent/skill_commands.py → _build_skill_message()

    The returned string is sent as-is to POST /chat → agent.run_conversation().

    Args:
        skill_name:       Display name of the skill (e.g. "dogfood")
        skill_content:    Raw body text of SKILL.md (after frontmatter)
        skill_path:       Absolute path to the skill directory
        linked_files:     List of {"name": ..., "path": ...} dicts from skill discovery
        raw_content:      Full raw SKILL.md content (with frontmatter) for config injection
        user_instruction: Optional text the user typed (e.g. "check my website")
        autonomous:       If True, add runtime note for unattended execution

    Returns:
        The formatted message string ready for agent consumption.
    """
    # ── Activation header (proven pattern from skill_commands.py:316-319) ──
    activation_note = (
        f'[SYSTEM: The user has invoked the "{skill_name}" skill, indicating they want '
        "you to follow its instructions. The full skill content is loaded below.]"
    )

    parts = [activation_note, "", skill_content.strip()]

    # ── Config injection (proven pattern from skill_commands.py:136) ──
    _inject_skill_config(raw_content, parts)

    # ── Supporting files reference (proven pattern from skill_commands.py:160-187) ──
    supporting = [f["path"] for f in linked_files if f.get("path")]

    # Exclude the main SKILL.md from the supporting files list
    supporting = [p for p in supporting if p.upper() != "SKILL.MD"]

    if supporting:
        parts.append("")
        parts.append("[This skill has supporting files you can load with the skill_view tool:]")
        for sf in supporting:
            parts.append(f"- {sf}")
        parts.append(
            f'\nTo view any of these, use: skill_view(name="{skill_name}", file_path="<path>")'
        )

    # ── User instruction (proven pattern from skill_commands.py:189-191) ──
    if user_instruction:
        parts.append("")
        parts.append(
            f"The user has provided the following instruction alongside the skill invocation: {user_instruction}"
        )

    # ── Runtime note (proven pattern from skill_commands.py:193-195) ──
    if autonomous:
        parts.append("")
        parts.append(
            "[Runtime note: This is an autonomous execution triggered from the HermDash UI. "
            "Execute the skill's full workflow end-to-end without asking the user for "
            "confirmation, clarification or choices. Make reasonable default decisions "
            "and proceed. Deliver the final output directly.]"
        )

    return "\n".join(parts)
