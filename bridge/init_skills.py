"""
Initialize skills directory on first run.
Copies bundled skills from PyInstaller bundle into ~/.hermes/skills
"""

import os
import shutil
import sys
from pathlib import Path

# Our custom skill categories bundled in hermes/skills/
CUSTOM_SKILL_CATEGORIES = ["higgsfield", "fal"]


def init_skills_dir():
    """
    Ensure custom skills exist in ALL profiles.

    Syncs each category in CUSTOM_SKILL_CATEGORIES independently.
    Adding a new category = add it to the list above. Nothing else.
    """
    hermes_home = Path(os.getenv("HERMES_HOME", Path.home() / ".hermes"))

    # Find bundled skills — PyInstaller extracts to sys._MEIPASS
    if hasattr(sys, '_MEIPASS'):
        bundled_skills = Path(sys._MEIPASS) / "skills"
    else:
        # Running from source
        bundled_skills = Path(__file__).parent.parent.parent / "hermes-agent" / "skills"

    if not bundled_skills.exists() or not bundled_skills.is_dir():
        print(f"[WARN] Bundled skills not found at {bundled_skills}")
        return

    # Collect all profiles + default
    profiles_to_sync = [hermes_home]
    profiles_dir = hermes_home / "profiles"
    if profiles_dir.exists():
        for profile_dir in profiles_dir.iterdir():
            if profile_dir.is_dir():
                profiles_to_sync.append(profile_dir)

    # Sync each custom category to each profile independently
    for profile_path in profiles_to_sync:
        skills_dir = profile_path / "skills"
        profile_name = profile_path.name if profile_path != hermes_home else "default"
        skills_dir.mkdir(parents=True, exist_ok=True)

        for category in CUSTOM_SKILL_CATEGORIES:
            source = bundled_skills / category
            dest = skills_dir / category

            if not source.exists():
                print(f"[WARN] Bundled category not found: {category}")
                continue

            if dest.exists() and any(dest.iterdir()):
                print(f"[SKIP] {category} already exists in {profile_name}")
                continue

            try:
                shutil.copytree(source, dest)
                skill_count = len([d for d in dest.iterdir() if d.is_dir()])
                print(f"[OK] {category}: {skill_count} skills → {profile_name}")
            except Exception as e:
                print(f"[WARN] Error syncing {category} to {profile_name}: {e}")
