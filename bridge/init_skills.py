"""
Initialize skills directory on first run.
Copies bundled skills from PyInstaller bundle into ~/.hermes/skills
"""

import os
import shutil
import sys
from pathlib import Path


def init_skills_dir():
    """Ensure ~/.hermes/skills exists and is populated with bundled skills."""
    hermes_home = Path(os.getenv("HERMES_HOME", Path.home() / ".hermes"))
    skills_dir = hermes_home / "skills"
    
    # If skills directory already exists and has content, skip
    if skills_dir.exists() and any(skills_dir.iterdir()):
        return
    
    print(f"[INIT] Initializing skills directory at {skills_dir}")
    
    # Create skills directory
    skills_dir.mkdir(parents=True, exist_ok=True)
    
    # Find bundled skills - PyInstaller extracts to sys._MEIPASS
    if hasattr(sys, '_MEIPASS'):
        bundled_skills = Path(sys._MEIPASS) / "skills"
    else:
        # Running from source
        bundled_skills = Path(__file__).parent.parent.parent / "hermes-agent" / "skills"
    
    if bundled_skills.exists() and bundled_skills.is_dir():
        print(f"[COPY] Copying {len(list(bundled_skills.iterdir()))} skill categories...")
        try:
            # Copy all skill categories
            for category_dir in bundled_skills.iterdir():
                if category_dir.is_dir():
                    dest = skills_dir / category_dir.name
                    if not dest.exists():
                        shutil.copytree(category_dir, dest)
                        skill_count = len([d for d in dest.iterdir() if d.is_dir()])
                        print(f"  [OK] {category_dir.name}: {skill_count} skills")
            
            # Copy manifest if exists
            manifest = bundled_skills / ".bundled_manifest"
            if manifest.exists():
                shutil.copy2(manifest, skills_dir / ".bundled_manifest")
            
            print(f"[OK] Skills initialized successfully")
        except Exception as e:
            print(f"[WARN] Error copying skills: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"[WARN] Bundled skills not found at {bundled_skills}")
        print(f"   Skills directory created but empty")
