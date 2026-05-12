"""
Trajectories — Read saved conversation trajectories.

The core hermes-agent saves trajectories via agent/trajectory.py:save_trajectory().
By default it writes to the current working directory as trajectory_samples.jsonl.

We patch the save path at bridge startup to write into ~/.hermes/trajectories/
so files are always in a known, profile-aware location.

File format (JSONL — one JSON object per line):
    {
        "conversations": [
            {"from": "system",  "value": "..."},
            {"from": "human",   "value": "user message"},
            {"from": "gpt",     "value": "<think>\\n</think>\\nresponse"},
            {"from": "tool",    "value": "<tool_response>\\n...\\n</tool_response>"}
        ],
        "timestamp": "2026-05-11T14:30:22.123456",
        "model": "openrouter/free",
        "completed": true
    }
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from ..Chat.agent_pool import get_profile_home, get_active_profile

logger = logging.getLogger("bridge.trajectories")

router = APIRouter(prefix="/trajectories", tags=["trajectories"])


# ─── Path Resolution ─────────────────────────────────────────────────────────

def _get_trajectories_dir() -> Path:
    """
    Get the trajectories directory for the active profile.

    default  → ~/.hermes/trajectories/
    coder    → ~/.hermes/profiles/coder/trajectories/
    """
    return get_profile_home() / "trajectories"


def _get_trajectory_file(completed: bool = True) -> Path:
    """
    Get the trajectory JSONL file path.

    Mirrors agent/trajectory.py:save_trajectory() filename logic:
        completed=True  → trajectory_samples.jsonl
        completed=False → failed_trajectories.jsonl
    """
    filename = "trajectory_samples.jsonl" if completed else "failed_trajectories.jsonl"
    return _get_trajectories_dir() / filename


def patch_trajectory_save_path():
    """
    Patch agent/trajectory.py to save into ~/.hermes/trajectories/
    instead of the current working directory.

    Called once at bridge startup from server.py.
    This is the correct approach — we redirect the core's save path
    rather than reimplementing trajectory saving.
    """
    try:
        import agent.trajectory as _traj_mod

        original_save = _traj_mod.save_trajectory

        def _patched_save(trajectory, model, completed, filename=None):
            if filename is None:
                traj_dir = _get_trajectories_dir()
                traj_dir.mkdir(parents=True, exist_ok=True)
                fname = "trajectory_samples.jsonl" if completed else "failed_trajectories.jsonl"
                filename = str(traj_dir / fname)
            original_save(trajectory, model, completed, filename=filename)

        _traj_mod.save_trajectory = _patched_save

        # Also patch the reference in run_agent module if already imported
        try:
            import run_agent as _run_agent_mod
            _run_agent_mod._save_trajectory_to_file = _patched_save
        except (ImportError, AttributeError):
            pass

        logger.info("Trajectory save path patched → %s", _get_trajectories_dir())

    except ImportError:
        logger.debug("agent.trajectory not available — trajectory patching skipped")
    except Exception as e:
        logger.warning("Failed to patch trajectory save path: %s", e)


# ─── JSONL Reader ─────────────────────────────────────────────────────────────

def _read_jsonl(path: Path) -> list:
    """Read all entries from a JSONL file. Returns list of dicts."""
    if not path.exists():
        return []
    entries = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError as e:
                    logger.warning("Skipping malformed line %d in %s: %s", line_num, path, e)
    except Exception as e:
        logger.error("Failed to read %s: %s", path, e)
    return entries


# ─── Routes ──────────────────────────────────────────────────────────────────


@router.get("/status")
async def get_trajectory_status():
    """
    Check trajectory saving status and file info.

    Returns:
        {
            "enabled": bool,
            "profile": str,
            "trajectories_dir": str,
            "completed_file": str,
            "completed_count": int,
            "failed_file": str,
            "failed_count": int
        }
    """
    try:
        # Check if save_trajectories is enabled in config
        enabled = False
        try:
            import yaml
            config_path = get_profile_home() / "config.yaml"
            if config_path.exists():
                with open(config_path) as f:
                    cfg = yaml.safe_load(f) or {}
                enabled = bool(cfg.get("save_trajectories", False))
        except Exception:
            pass

        completed_file = _get_trajectory_file(completed=True)
        failed_file = _get_trajectory_file(completed=False)

        completed_entries = _read_jsonl(completed_file)
        failed_entries = _read_jsonl(failed_file)

        return {
            "enabled": enabled,
            "profile": get_active_profile(),
            "trajectories_dir": str(_get_trajectories_dir()),
            "completed_file": str(completed_file),
            "completed_count": len(completed_entries),
            "failed_file": str(failed_file),
            "failed_count": len(failed_entries),
        }
    except Exception as e:
        logger.exception("Failed to get trajectory status")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
async def list_trajectories(
    completed: Optional[bool] = Query(default=None, description="Filter by completed status. None = all"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """
    List trajectory entries (metadata only — no full conversations).

    Returns entries newest-first.

    Returns:
        {
            "profile": str,
            "total": int,
            "limit": int,
            "offset": int,
            "entries": [
                {
                    "index": int,
                    "timestamp": str,
                    "model": str,
                    "completed": bool,
                    "turn_count": int,
                    "preview": str   ← first human message
                }
            ]
        }
    """
    try:
        all_entries = []

        if completed is None or completed is True:
            for i, e in enumerate(_read_jsonl(_get_trajectory_file(completed=True))):
                all_entries.append((i, True, e))

        if completed is None or completed is False:
            for i, e in enumerate(_read_jsonl(_get_trajectory_file(completed=False))):
                all_entries.append((i, False, e))

        # Sort newest first by timestamp
        all_entries.sort(key=lambda x: x[2].get("timestamp", ""), reverse=True)

        total = len(all_entries)
        page = all_entries[offset: offset + limit]

        entries = []
        for idx, (file_index, is_completed, entry) in enumerate(page):
            conversations = entry.get("conversations", [])
            # Find first human message for preview
            preview = ""
            for turn in conversations:
                if turn.get("from") == "human":
                    preview = turn.get("value", "")[:120]
                    break

            entries.append({
                "index": file_index,
                "source": "completed" if is_completed else "failed",
                "timestamp": entry.get("timestamp", ""),
                "model": entry.get("model", ""),
                "completed": entry.get("completed", is_completed),
                "turn_count": len(conversations),
                "preview": preview,
            })

        return {
            "profile": get_active_profile(),
            "total": total,
            "limit": limit,
            "offset": offset,
            "entries": entries,
        }

    except Exception as e:
        logger.exception("Failed to list trajectories")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{source}/{index}")
async def get_trajectory(source: str, index: int):
    """
    Get a full trajectory by source and index.

    Args:
        source: "completed" or "failed"
        index: 0-based line index in the JSONL file

    Returns:
        {
            "profile": str,
            "source": str,
            "index": int,
            "timestamp": str,
            "model": str,
            "completed": bool,
            "conversations": [
                {"from": "system"|"human"|"gpt"|"tool", "value": str}
            ]
        }
    """
    if source not in ("completed", "failed"):
        raise HTTPException(status_code=400, detail="source must be 'completed' or 'failed'")

    try:
        is_completed = source == "completed"
        entries = _read_jsonl(_get_trajectory_file(completed=is_completed))

        if index < 0 or index >= len(entries):
            raise HTTPException(
                status_code=404,
                detail=f"Index {index} out of range (0-{len(entries) - 1})"
            )

        entry = entries[index]

        return {
            "profile": get_active_profile(),
            "source": source,
            "index": index,
            "timestamp": entry.get("timestamp", ""),
            "model": entry.get("model", ""),
            "completed": entry.get("completed", is_completed),
            "conversations": entry.get("conversations", []),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get trajectory %s/%d", source, index)
        raise HTTPException(status_code=500, detail=str(e))
