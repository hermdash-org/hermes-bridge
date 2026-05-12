"""
Initialize trajectory saving for all profiles.

Single responsibility: ensure save_trajectories: true is set
in every profile's config.yaml on bridge startup.

Called once from server.py — separate from skills, separate from routes.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger("bridge.trajectories.init")


def _get_hermes_home() -> Path:
    return Path(os.getenv("HERMES_HOME", Path.home() / ".hermes"))


def _get_all_profile_paths() -> list[Path]:
    """Return all profile directories including default."""
    hermes_home = _get_hermes_home()
    profiles = [hermes_home]  # default profile
    profiles_dir = hermes_home / "profiles"
    if profiles_dir.exists():
        for p in profiles_dir.iterdir():
            if p.is_dir():
                profiles.append(p)
    return profiles


def _enable_trajectories_for_profile(profile_path: Path) -> None:
    """Set save_trajectories: true in a profile's config.yaml."""
    config_path = profile_path / "config.yaml"
    try:
        import yaml
        cfg = {}
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        if cfg.get("save_trajectories") is True:
            return  # Already enabled
        cfg["save_trajectories"] = True
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)
        profile_name = profile_path.name if profile_path != _get_hermes_home() else "default"
        logger.info("Enabled save_trajectories for profile: %s", profile_name)
    except Exception as e:
        logger.warning("Could not enable trajectories for %s: %s", profile_path, e)


def init_trajectories():
    """Enable trajectory saving for all profiles on startup."""
    for profile_path in _get_all_profile_paths():
        _enable_trajectories_for_profile(profile_path)
