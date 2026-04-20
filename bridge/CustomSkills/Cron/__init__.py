"""
CustomSkills Cron — Profile-aware cron job management for custom skills.

This module wraps the core cron functionality with custom skill awareness:
- Filters jobs to show only those using custom skills from current profile
- Validates custom skill names against current profile's skills-custom/ directory
- Provides custom-skill-specific views of automations and outputs

All operations are profile-scoped via get_profile_home().

Endpoints:
  GET    /custom-skills/cron/jobs                 — List cron jobs using custom skills
  GET    /custom-skills/cron/jobs/{id}            — Get single job details
  GET    /custom-skills/cron/jobs/{id}/runs       — List run output files for job
  GET    /custom-skills/cron/jobs/{id}/output/{ts} — Get raw run output file
  POST   /custom-skills/cron/jobs                 — Create new cron job with custom skill
  PATCH  /custom-skills/cron/jobs/{id}            — Update existing job
  POST   /custom-skills/cron/jobs/{id}/pause      — Pause job
  POST   /custom-skills/cron/jobs/{id}/resume     — Resume paused job
  POST   /custom-skills/cron/jobs/{id}/trigger    — Run job immediately
  DELETE /custom-skills/cron/jobs/{id}            — Delete job
  GET    /custom-skills/cron/inbox                — Get inbox entries for custom skill jobs
  POST   /custom-skills/cron/inbox/{id}/read      — Mark inbox entry as read
"""

import logging
from pathlib import Path
from typing import List, Dict, Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import cron.jobs as _cron_jobs_mod
from cron.jobs import (
    list_jobs,
    get_job,
    create_job,
    update_job,
    pause_job,
    resume_job,
    trigger_job,
    remove_job,
)
from ...Chat.agent_pool import get_session_db, get_active_profile
from ..storage import get_custom_skills_dir, list_custom_skills

router = APIRouter(prefix="/cron", tags=["custom-skills-cron"])
logger = logging.getLogger("bridge.custom_skills.cron")


# ═══════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════


def _get_custom_skill_names() -> set:
    """Get set of custom skill names in current profile."""
    try:
        skills = list_custom_skills()
        return {skill['name'] for skill in skills}
    except Exception:
        return set()


def _job_uses_custom_skills(job: Dict[str, Any]) -> bool:
    """Check if a job uses any custom skills from current profile OR has no skills (base AI).
    
    Jobs with 0 skills are valid - they use base AI without custom skills.
    We only filter OUT jobs that use skills from OTHER profiles.
    """
    job_skills = job.get('skills', [])
    if not job_skills:
        # Check legacy single skill field
        legacy_skill = job.get('skill')
        if legacy_skill:
            job_skills = [legacy_skill]
        else:
            # No skills = uses base AI = valid for this profile
            return True
    
    custom_skill_names = _get_custom_skill_names()
    
    # If job has skills, check if ANY of them are custom skills from this profile
    # This allows jobs with mixed skills (custom + built-in) to show up
    has_custom_skills = any(skill in custom_skill_names for skill in job_skills)
    
    # Also check if job has ONLY built-in skills (not custom skills from other profiles)
    # For now, we'll be permissive and show all jobs that either:
    # 1. Have no skills (base AI)
    # 2. Have at least one custom skill from this profile
    return has_custom_skills or len(job_skills) == 0


def _validate_custom_skills(skill_names: List[str]) -> tuple[bool, str]:
    """Validate that all skill names exist in current profile's custom skills.
    
    Returns:
        (valid, error_message)
    """
    if not skill_names:
        return True, ""
    
    custom_skill_names = _get_custom_skill_names()
    invalid_skills = [s for s in skill_names if s not in custom_skill_names]
    
    if invalid_skills:
        return False, f"Custom skills not found in current profile: {', '.join(invalid_skills)}"
    
    return True, ""


# ═══════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════


@router.get("/jobs")
async def list_custom_skill_jobs(include_disabled: bool = True):
    """List all cron jobs that use custom skills from current profile.
    
    Returns:
    {
        "success": true,
        "profile": "default",
        "count": 5,
        "jobs": [...]
    }
    """
    try:
        all_jobs = list_jobs(include_disabled=include_disabled)
        
        # Filter to only jobs using custom skills
        custom_jobs = [job for job in all_jobs if _job_uses_custom_skills(job)]
        
        return JSONResponse({
            "success": True,
            "profile": get_active_profile(),
            "count": len(custom_jobs),
            "jobs": custom_jobs,
        })
    except Exception as e:
        logger.exception("Failed to list custom skill cron jobs")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.get("/jobs/{job_id}")
async def get_custom_skill_job(job_id: str):
    """Get details for a single cron job.
    
    Returns:
    {
        "success": true,
        "profile": "default",
        "job": {...}
    }
    """
    try:
        job = get_job(job_id)
        
        if not job:
            return JSONResponse(
                {"success": False, "error": "Job not found"},
                status_code=404,
            )
        
        # Verify job uses custom skills (optional - could allow viewing any job)
        # if not _job_uses_custom_skills(job):
        #     return JSONResponse(
        #         {"success": False, "error": "Job does not use custom skills"},
        #         status_code=403,
        #     )
        
        return JSONResponse({
            "success": True,
            "profile": get_active_profile(),
            "job": job,
        })
    except Exception as e:
        logger.exception("Failed to get custom skill cron job: %s", job_id)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.get("/jobs/{job_id}/runs")
async def list_custom_skill_job_runs(job_id: str, limit: int = 100, offset: int = 0):
    """List run output files for a job.
    
    Returns:
    {
        "success": true,
        "profile": "default",
        "count": 10,
        "runs": [
            {
                "timestamp": "2026-04-14_19-30-00",
                "file": "2026-04-14_19-30-00.md",
                "size": 1234
            }
        ]
    }
    """
    try:
        job = get_job(job_id)
        if not job:
            return JSONResponse(
                {"success": False, "error": "Job not found"},
                status_code=404,
            )
        
        # List output files as run history
        job_output_dir = _cron_jobs_mod.OUTPUT_DIR / job_id
        runs = []
        if job_output_dir.exists():
            files = sorted(job_output_dir.glob("*.md"), reverse=True)
            for f in files[offset:offset + limit]:
                timestamp = f.stem  # e.g. "2026-04-14_19-30-00"
                runs.append({
                    "timestamp": timestamp,
                    "file": f.name,
                    "size": f.stat().st_size,
                })
        
        return JSONResponse({
            "success": True,
            "profile": get_active_profile(),
            "count": len(runs),
            "runs": runs,
        })
    except Exception as e:
        logger.exception("Failed to list runs for job: %s", job_id)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.get("/jobs/{job_id}/output/{timestamp}")
async def get_custom_skill_job_output(job_id: str, timestamp: str):
    """Get raw output from a specific run.
    
    Returns:
    {
        "success": true,
        "profile": "default",
        "content": "Output content...",
        "timestamp": "2026-04-14_19-30-00"
    }
    """
    try:
        output_path = _cron_jobs_mod.OUTPUT_DIR / job_id / f"{timestamp}.md"
        
        if not output_path.exists():
            return JSONResponse(
                {"success": False, "error": "Output not found"},
                status_code=404,
            )
        
        with open(output_path, 'r', encoding='utf-8') as f:
            output = f.read()
        
        return JSONResponse({
            "success": True,
            "profile": get_active_profile(),
            "content": output,
            "timestamp": timestamp,
        })
    except Exception as e:
        logger.exception("Failed to get output for job %s at %s", job_id, timestamp)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.post("/jobs")
async def create_custom_skill_job(request: Request):
    """Create a new cron job with custom skills.
    
    Body:
    {
        "prompt": "Generate daily report",
        "schedule": "every 1h",
        "name": "Daily Report",
        "skills": ["kimbo", "research-assistant"],  // Must be custom skills
        "repeat": null,  // null = forever, 1 = once, N = N times
        "deliver": "origin",  // origin, local, platform:chat_id
        "model": "claude-sonnet-4",
        "script": "scripts/collect-data.py"
    }
    
    Returns:
    {
        "success": true,
        "profile": "default",
        "job": {...}
    }
    """
    try:
        body = await request.json()
        skills = body.get('skills', [])
        
        # Validate that skills are custom skills from current profile
        if skills:
            valid, error = _validate_custom_skills(skills)
            if not valid:
                return JSONResponse(
                    {"success": False, "error": error},
                    status_code=400
                )
        
        job = create_job(
            prompt=body.get('prompt'),
            schedule=body.get('schedule'),
            name=body.get('name'),
            repeat=body.get('repeat'),
            deliver=body.get('deliver'),
            model=body.get('model'),
            skills=skills,
            script=body.get('script')
        )
        
        return JSONResponse({
            "success": True,
            "profile": get_active_profile(),
            "job": job,
        })
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)
    except Exception as e:
        logger.exception("Failed to create custom skill cron job")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.patch("/jobs/{job_id}")
async def update_custom_skill_job(job_id: str, request: Request):
    """Update an existing cron job.
    
    Body: Same fields as create, all optional
    """
    try:
        body = await request.json()
        skills = body.get('skills')
        
        # Validate custom skills if provided
        if skills is not None:
            valid, error = _validate_custom_skills(skills)
            if not valid:
                return JSONResponse(
                    {"success": False, "error": error},
                    status_code=400
                )
        
        job = update_job(job_id, body)
        
        if not job:
            return JSONResponse(
                {"success": False, "error": "Job not found"},
                status_code=404,
            )
        
        return JSONResponse({
            "success": True,
            "profile": get_active_profile(),
            "job": job,
        })
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)
    except Exception as e:
        logger.exception("Failed to update custom skill cron job: %s", job_id)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.post("/jobs/{job_id}/pause")
async def pause_custom_skill_job(job_id: str, request: Request):
    """Pause a running job.
    
    Body (optional):
    {
        "reason": "Maintenance"
    }
    """
    try:
        reason = None
        try:
            body = await request.json()
            reason = body.get('reason')
        except Exception:
            pass  # No body is fine
        
        job = pause_job(job_id, reason=reason)
        
        if not job:
            return JSONResponse(
                {"success": False, "error": "Job not found"},
                status_code=404,
            )
        
        return JSONResponse({
            "success": True,
            "profile": get_active_profile(),
            "job": job,
        })
    except Exception as e:
        logger.exception("Failed to pause custom skill cron job: %s", job_id)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.post("/jobs/{job_id}/resume")
async def resume_custom_skill_job(job_id: str):
    """Resume a paused job."""
    try:
        job = resume_job(job_id)
        
        if not job:
            return JSONResponse(
                {"success": False, "error": "Job not found"},
                status_code=404,
            )
        
        return JSONResponse({
            "success": True,
            "profile": get_active_profile(),
            "job": job,
        })
    except Exception as e:
        logger.exception("Failed to resume custom skill cron job: %s", job_id)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.post("/jobs/{job_id}/trigger")
async def trigger_custom_skill_job(job_id: str):
    """Trigger a job to run immediately."""
    try:
        job = trigger_job(job_id)
        
        if not job:
            return JSONResponse(
                {"success": False, "error": "Job not found"},
                status_code=404,
            )
        
        return JSONResponse({
            "success": True,
            "profile": get_active_profile(),
            "job": job,
        })
    except Exception as e:
        logger.exception("Failed to trigger custom skill cron job: %s", job_id)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.delete("/jobs/{job_id}")
async def delete_custom_skill_job(job_id: str):
    """Delete a cron job permanently."""
    try:
        deleted = remove_job(job_id)
        
        if not deleted:
            return JSONResponse(
                {"success": False, "error": "Job not found"},
                status_code=404,
            )
        
        return JSONResponse({
            "success": True,
            "profile": get_active_profile(),
            "deleted": job_id,
        })
    except Exception as e:
        logger.exception("Failed to delete custom skill cron job: %s", job_id)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.get("/inbox")
async def get_custom_skill_inbox(limit: int = 50, offset: int = 0):
    """Get inbox entries from custom skill cron runs.
    
    Returns:
    {
        "success": true,
        "profile": "default",
        "count": 10,
        "entries": [
            {
                "id": "cron_abc123_20260414_193000",
                "job_id": "abc123",
                "created_at": "2026-04-14 19:30:00",
                "prompt": "...",
                "read": false
            }
        ]
    }
    """
    try:
        session_db = get_session_db()
        
        cursor = session_db._conn.execute("""
            SELECT id, started_at, metadata, system_prompt
            FROM sessions 
            WHERE id LIKE 'cron_%'
            ORDER BY started_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))
        
        entries = []
        for row in cursor.fetchall():
            session_id, created_at, metadata, prompt = row
            job_id = session_id.split('_')[1] if '_' in session_id else None
            
            # Check if this job uses custom skills
            if job_id:
                job = get_job(job_id)
                if job and not _job_uses_custom_skills(job):
                    continue  # Skip non-custom-skill jobs
            
            # metadata may be a JSON string or None
            meta = {}
            if metadata:
                try:
                    import json
                    meta = json.loads(metadata) if isinstance(metadata, str) else metadata
                except Exception:
                    pass
            
            entries.append({
                "id": session_id,
                "job_id": job_id,
                "created_at": created_at,
                "prompt": prompt,
                "read": meta.get('inbox_read', False)
            })
        
        return JSONResponse({
            "success": True,
            "profile": get_active_profile(),
            "count": len(entries),
            "entries": entries
        })
    except Exception as e:
        logger.exception("Failed to get custom skill inbox")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.post("/inbox/{session_id}/read")
async def mark_custom_skill_inbox_read(session_id: str):
    """Mark inbox entry as read."""
    try:
        session_db = get_session_db()
        
        session_db._conn.execute("""
            UPDATE sessions 
            SET metadata = json_set(ifnull(metadata, '{}'), '$.inbox_read', 1)
            WHERE id = ?
        """, (session_id,))
        session_db._conn.commit()
        
        return JSONResponse({
            "success": True,
            "profile": get_active_profile()
        })
    except Exception as e:
        logger.exception("Failed to mark inbox entry as read: %s", session_id)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)
