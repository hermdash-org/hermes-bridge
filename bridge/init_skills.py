"""
Initialize skills directory on first run.
Copies bundled skills from PyInstaller bundle into ~/.hermes/skills
"""

import os
import shutil
import sys
from pathlib import Path


def init_skills_dir():
    """
    Ensure skills exist in ALL profiles (not just default).
    
    This is the SENIOR-LEVEL solution that matches hermes-agent's architecture:
    - Syncs bundled skills to each profile's skills/ directory
    - Respects profile isolation (each profile gets its own copy)
    - Works when users create new profiles
    - Uses the same logic as `hermes profile create`
    """
    hermes_home = Path(os.getenv("HERMES_HOME", Path.home() / ".hermes"))
    
    # Find bundled skills - PyInstaller extracts to sys._MEIPASS
    if hasattr(sys, '_MEIPASS'):
        bundled_skills = Path(sys._MEIPASS) / "skills"
    else:
        # Running from source
        bundled_skills = Path(__file__).parent.parent.parent / "hermes-agent" / "skills"
    
    if not bundled_skills.exists() or not bundled_skills.is_dir():
        print(f"[WARN] Bundled skills not found at {bundled_skills}")
        return
    
    # Get all profile directories + default
    profiles_to_sync = [hermes_home]  # Default profile
    
    profiles_dir = hermes_home / "profiles"
    if profiles_dir.exists():
        for profile_dir in profiles_dir.iterdir():
            if profile_dir.is_dir():
                profiles_to_sync.append(profile_dir)
    
    # Sync skills to each profile
    for profile_path in profiles_to_sync:
        skills_dir = profile_path / "skills"
        profile_name = profile_path.name if profile_path != hermes_home else "default"
        
        # Check if Higgsfield skills specifically exist (not just any skills)
        higgsfield_dir = skills_dir / "higgsfield"
        if higgsfield_dir.exists() and any(higgsfield_dir.iterdir()):
            print(f"[SKIP] Higgsfield skills already exist in {profile_name}")
            continue
        
        print(f"[INIT] Syncing Higgsfield skills to profile: {profile_name}")
        
        # Create skills directory
        skills_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Copy Higgsfield skills specifically
            higgsfield_source = bundled_skills / "higgsfield"
            if higgsfield_source.exists() and higgsfield_source.is_dir():
                dest = skills_dir / "higgsfield"
                if not dest.exists():
                    shutil.copytree(higgsfield_source, dest)
                    skill_count = len([d for d in dest.iterdir() if d.is_dir()])
                    print(f"  [OK] higgsfield: {skill_count} skills")
                else:
                    print(f"  [SKIP] higgsfield already exists")
            
            # Also copy other skill categories if skills dir is empty
            if not any(skills_dir.iterdir()):
                for category_dir in bundled_skills.iterdir():
                    if category_dir.is_dir() and category_dir.name != "higgsfield":
                        dest = skills_dir / category_dir.name
                        if not dest.exists():
                            shutil.copytree(category_dir, dest)
                
                # Copy manifest if exists
                manifest = bundled_skills / ".bundled_manifest"
                if manifest.exists():
                    shutil.copy2(manifest, skills_dir / ".bundled_manifest")
            
            print(f"[OK] Skills synced to {profile_name}")
        except Exception as e:
            print(f"[WARN] Error syncing skills to {profile_name}: {e}")
            import traceback
            traceback.print_exc()
