"""
Cron — Job management, run history, and session replay for automations.

All data is profile-scoped via get_hermes_home().
Every operation runs in the active profile context.

Endpoints:
  GET    /cron/jobs                 — List all cron jobs
  GET    /cron/jobs/{id}            — Get single job details
  GET    /cron/jobs/{id}/runs       — List run output files for job
  GET    /cron/jobs/{id}/output/{ts} — Get raw run output file
  POST   /cron/jobs                 — Create new cron job
  PATCH  /cron/jobs/{id}            — Update existing job
  POST   /cron/jobs/{id}/pause      — Pause job
  POST   /cron/jobs/{id}/resume     — Resume paused job
  POST   /cron/jobs/{id}/trigger    — Run job immediately
  DELETE /cron/jobs/{id}            — Delete job
  GET    /cron/inbox                — Get inbox entries
  POST   /cron/inbox/{id}/read      — Mark inbox entry as read
"""

import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse

import cron.jobs as _cron_jobs_mod            # dynamic access to OUTPUT_DIR
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
from ..Chat.agent_pool import get_session_db

router = APIRouter(prefix="/cron", tags=["cron"])


@router.get("/jobs")
async def list_all_jobs(include_disabled: bool = True):
    """List all cron jobs for active profile."""
    try:
        jobs = list_jobs(include_disabled=include_disabled)
        return JSONResponse({
            "success": True,
            "count": len(jobs),
            "jobs": jobs,
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.get("/jobs/{job_id}")
async def get_single_job(job_id: str):
    """Get details for a single cron job."""
    try:
        job = get_job(job_id)

        if not job:
            return JSONResponse(
                {"success": False, "error": "Job not found"},
                status_code=404,
            )

        return JSONResponse({
            "success": True,
            "job": job,
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.get("/jobs/{job_id}/runs")
async def list_runs(job_id: str, limit: int = 100, offset: int = 0):
    """List run output files for a job (derived from output directory)."""
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
            "count": len(runs),
            "runs": runs,
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.get("/jobs/{job_id}/output/{timestamp}")
async def get_run_output(job_id: str, timestamp: str):
    """Get raw stdout output from a specific run."""
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
            "content": output,
            "timestamp": timestamp,
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.post("/jobs")
async def create_new_job(request: Request):
    """Create a new cron job."""
    try:
        body = await request.json()

        job = create_job(
            prompt=body.get('prompt'),
            schedule=body.get('schedule'),
            name=body.get('name'),
            repeat=body.get('repeat'),
            deliver=body.get('deliver'),
            model=body.get('model'),
            skills=body.get('skills'),
            script=body.get('script')
        )

        return JSONResponse({
            "success": True,
            "job": job,
        })
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.patch("/jobs/{job_id}")
async def update_existing_job(job_id: str, request: Request):
    """Update an existing cron job."""
    try:
        body = await request.json()

        job = update_job(job_id, body)

        if not job:
            return JSONResponse(
                {"success": False, "error": "Job not found"},
                status_code=404,
            )

        return JSONResponse({
            "success": True,
            "job": job,
        })
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.post("/jobs/{job_id}/pause")
async def pause_existing_job(job_id: str, request: Request):
    """Pause a running job."""
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
            "job": job,
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.post("/jobs/{job_id}/resume")
async def resume_existing_job(job_id: str):
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
            "job": job,
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.post("/jobs/{job_id}/trigger")
async def trigger_job_immediately(job_id: str):
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
            "job": job,
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.get("/inbox")
async def get_inbox(limit: int = 50, offset: int = 0):
    """Get all inbox entries from cron runs."""
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
            "count": len(entries),
            "entries": entries
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.post("/inbox/{session_id}/read")
async def mark_inbox_read(session_id: str):
    """Mark inbox entry as read."""
    try:
        session_db = get_session_db()

        session_db._conn.execute("""
            UPDATE sessions 
            SET metadata = json_set(ifnull(metadata, '{}'), '$.inbox_read', 1)
            WHERE id = ?
        """, (session_id,))
        session_db._conn.commit()

        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.delete("/jobs/{job_id}")
async def delete_existing_job(job_id: str):
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
            "deleted": job_id,
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)
