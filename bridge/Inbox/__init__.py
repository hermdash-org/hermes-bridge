"""
Inbox — Unified view of all automation results across the active profile.

Aggregates cron job outputs with session metadata, costs, and tool usage.
All data is profile-scoped via get_hermes_home() and get_session_db().

Endpoints:
  GET    /inbox                 — List all inbox items (automation results)
  GET    /inbox/{id}            — Get single inbox item with full details
  GET    /inbox/{id}/session    — Get full session conversation
  POST   /inbox/{id}/read       — Mark item as read
  POST   /inbox/{id}/unread     — Mark item as unread
  GET    /inbox/unread/count    — Get unread count
"""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

import cron.jobs as _cron_jobs_mod
from cron.jobs import list_jobs, get_job
from ..Chat.agent_pool import get_session_db
from .read_tracking import get_read_items, mark_as_read, mark_as_unread, get_unread_count

router = APIRouter(prefix="/inbox", tags=["inbox"])


@router.get("/")
async def list_inbox_items(limit: int = 50, offset: int = 0):
    """List all automation results for the active profile.
    
    Returns aggregated data from:
    - Cron output files (~/.hermes/cron/output/{job_id}/*.md)
    - Job metadata (jobs.json)
    - Session data (sessions.db)
    
    Each item includes:
    - Job name, timestamp, status
    - Output preview (first 200 chars)
    - Cost data (tokens, estimated USD)
    - Tool usage summary
    """
    try:
        jobs = list_jobs(include_disabled=True)
        session_db = get_session_db()
        
        # Get read items for this profile
        read_items = get_read_items()
        
        items = []
        
        # Iterate through all jobs and their output files
        for job in jobs:
            job_id = job["id"]
            job_output_dir = _cron_jobs_mod.OUTPUT_DIR / job_id
            
            if not job_output_dir.exists():
                continue
                
            # Get all output files for this job
            output_files = sorted(
                job_output_dir.glob("*.md"),
                key=lambda f: f.stat().st_mtime,
                reverse=True
            )
            
            for output_file in output_files:
                timestamp = output_file.stem  # e.g. "2026-05-04_20-30-00"
                
                # Try to find matching session
                session_id = f"cron_{job_id}_{timestamp.replace('-', '_').replace('_', '', 2)}"
                session = None
                try:
                    session = session_db.get_session(session_id)
                except Exception:
                    pass
                
                # Read output preview
                try:
                    content = output_file.read_text(encoding='utf-8')
                    preview = content[:200].strip()
                    if len(content) > 200:
                        preview += "..."
                except Exception:
                    preview = ""
                
                # Convert timestamp to ISO format for frontend
                # Format: 2026-04-27_19-02-35 → 2026-04-27T19:02:35Z (UTC)
                try:
                    from datetime import datetime
                    dt = datetime.strptime(timestamp, "%Y-%m-%d_%H-%M-%S")
                    iso_timestamp = dt.isoformat() + "Z"  # Assume UTC
                except Exception:
                    iso_timestamp = timestamp
                
                # Build inbox item
                item_id = f"{job_id}_{timestamp}"
                item = {
                    "id": item_id,
                    "job_id": job_id,
                    "job_name": job.get("name", "Unnamed Job"),
                    "timestamp": timestamp,  # Keep original for file lookup
                    "created_at": iso_timestamp,  # ISO format for frontend
                    "status": job.get("last_status", "unknown"),
                    "preview": preview,
                    "size": output_file.stat().st_size,
                    "schedule": job.get("schedule"),  # e.g., "every 60m"
                    "model_used": job.get("model"),  # Model configured for job
                    "is_read": item_id in read_items,  # Read status
                }
                
                # Add session data if available
                if session:
                    item["session_id"] = session_id
                    item["cost_usd"] = session.get("estimated_cost_usd") or session.get("actual_cost_usd")
                    item["input_tokens"] = session.get("input_tokens", 0)
                    item["output_tokens"] = session.get("output_tokens", 0)
                    item["cache_read_tokens"] = session.get("cache_read_tokens", 0)
                    item["cache_write_tokens"] = session.get("cache_write_tokens", 0)
                    item["reasoning_tokens"] = session.get("reasoning_tokens", 0)
                    item["tool_call_count"] = session.get("tool_call_count", 0)
                    item["model"] = session.get("model")
                
                items.append(item)
        
        # Sort by timestamp descending
        items.sort(key=lambda x: x["timestamp"], reverse=True)
        
        # Apply pagination
        paginated = items[offset:offset + limit]
        
        return JSONResponse({
            "success": True,
            "count": len(paginated),
            "total": len(items),
            "items": paginated,
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.get("/{item_id}")
async def get_inbox_item(item_id: str):
    """Get full details for a single inbox item.
    
    Returns:
    - Full output content
    - Complete session metadata
    - Tool calls made
    - Reasoning tokens
    - Cost breakdown
    """
    try:
        # Parse item_id: {job_id}_{timestamp}
        # Timestamp format: YYYY-MM-DD_HH-MM-SS (uses dashes, not underscores)
        # Example: 86141054c301_2026-04-27_19-02-35
        # Split gives: ['86141054c301', '2026-04-27', '19-02-35']
        parts = item_id.split('_')
        if len(parts) < 3:  # job_id + date + time
            return JSONResponse(
                {"success": False, "error": "Invalid item ID format"},
                status_code=400
            )
        
        # Last 2 parts are timestamp (date_time), everything before is job_id
        timestamp = '_'.join(parts[-2:])
        job_id = '_'.join(parts[:-2])
        
        # Get job metadata
        job = get_job(job_id)
        if not job:
            return JSONResponse(
                {"success": False, "error": "Job not found"},
                status_code=404
            )
        
        # Get output file
        output_path = _cron_jobs_mod.OUTPUT_DIR / job_id / f"{timestamp}.md"
        if not output_path.exists():
            return JSONResponse(
                {"success": False, "error": "Output file not found"},
                status_code=404
            )
        
        content = output_path.read_text(encoding='utf-8')
        
        # Convert timestamp to ISO format
        try:
            from datetime import datetime
            dt = datetime.strptime(timestamp, "%Y-%m-%d_%H-%M-%S")
            iso_timestamp = dt.isoformat() + "Z"
        except Exception:
            iso_timestamp = timestamp
        
        # Get session data
        session_id = f"cron_{job_id}_{timestamp.replace('-', '_').replace('_', '', 2)}"
        session_db = get_session_db()
        session = None
        messages = []
        
        try:
            session = session_db.get_session(session_id)
            if session:
                messages = session_db.get_messages(session_id)
        except Exception:
            pass
        
        result = {
            "id": item_id,
            "job_id": job_id,
            "job_name": job.get("name"),
            "timestamp": timestamp,  # Keep original
            "created_at": iso_timestamp,  # ISO format for frontend
            "content": content,
            "status": job.get("last_status"),
            "error": job.get("last_error"),
            "delivery_error": job.get("last_delivery_error"),
            "schedule": job.get("schedule_display") or job.get("schedule"),  # Use display format
            "next_run_at": job.get("next_run_at"),
            "model_configured": job.get("model"),
            "prompt": job.get("prompt"),  # Original prompt for re-run
            "skills": job.get("skills", []),  # Skills used
            "repeat": job.get("repeat"),  # Repeat count
            "enabled": job.get("enabled", True),
            "deliver": job.get("deliver"),  # Delivery targets
            "context_from": job.get("context_from"),  # Job dependencies (optional)
            "is_silent": "[SILENT]" in content,  # Silent run detection
        }
        
        # Add session details if available
        if session:
            started_at = session.get("started_at")
            ended_at = session.get("ended_at")
            duration_seconds = None
            if started_at and ended_at:
                duration_seconds = round(ended_at - started_at, 2)
            
            result["session"] = {
                "id": session_id,
                "model": session.get("model"),
                "started_at": started_at,
                "ended_at": ended_at,
                "duration_seconds": duration_seconds,
                "input_tokens": session.get("input_tokens", 0),
                "output_tokens": session.get("output_tokens", 0),
                "cache_read_tokens": session.get("cache_read_tokens", 0),
                "cache_write_tokens": session.get("cache_write_tokens", 0),
                "reasoning_tokens": session.get("reasoning_tokens", 0),
                "estimated_cost_usd": session.get("estimated_cost_usd"),
                "actual_cost_usd": session.get("actual_cost_usd"),
                "tool_call_count": session.get("tool_call_count", 0),
                "message_count": session.get("message_count", 0),
                "api_call_count": session.get("api_call_count", 0),
            }
            
            # Extract tool names from messages
            tools_used = []
            for msg in messages:
                if msg.get("tool_name"):
                    tools_used.append(msg["tool_name"])
            result["tools_used"] = list(set(tools_used))
        
        return JSONResponse({
            "success": True,
            "item": result,
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.get("/{item_id}/session")
async def get_inbox_item_session(item_id: str):
    """Get full session conversation for an inbox item.
    
    Returns all messages including reasoning and tool calls.
    """
    try:
        # Parse item_id: {job_id}_{timestamp}
        # Timestamp format: YYYY-MM-DD_HH-MM-SS (uses dashes, not underscores)
        # Example: 86141054c301_2026-04-27_19-02-35
        parts = item_id.split('_')
        if len(parts) < 3:  # job_id + date + time
            return JSONResponse(
                {"success": False, "error": "Invalid item ID format"},
                status_code=400
            )
        
        # Last 2 parts are timestamp (date_time), everything before is job_id
        timestamp = '_'.join(parts[-2:])
        job_id = '_'.join(parts[:-2])
        
        # Get session
        session_id = f"cron_{job_id}_{timestamp.replace('-', '_').replace('_', '', 2)}"
        session_db = get_session_db()
        
        session = session_db.get_session(session_id)
        if not session:
            return JSONResponse(
                {"success": False, "error": "Session not found"},
                status_code=404
            )
        
        messages = session_db.get_messages(session_id)
        
        # Format messages for display
        formatted_messages = []
        for msg in messages:
            formatted_messages.append({
                "role": msg["role"],
                "content": msg.get("content", ""),
                "tool_name": msg.get("tool_name"),
                "tool_calls": msg.get("tool_calls"),
                "reasoning": msg.get("reasoning"),
                "reasoning_content": msg.get("reasoning_content"),
                "timestamp": msg.get("timestamp"),
            })
        
        return JSONResponse({
            "success": True,
            "session": {
                "id": session_id,
                "model": session.get("model"),
                "started_at": session.get("started_at"),
                "message_count": len(formatted_messages),
            },
            "messages": formatted_messages,
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.post("/{item_id}/read")
async def mark_item_read(item_id: str):
    """Mark an inbox item as read."""
    try:
        success = mark_as_read(item_id)
        return JSONResponse({
            "success": success,
            "item_id": item_id,
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.post("/{item_id}/unread")
async def mark_item_unread(item_id: str):
    """Mark an inbox item as unread."""
    try:
        success = mark_as_unread(item_id)
        return JSONResponse({
            "success": success,
            "item_id": item_id,
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.get("/unread/count")
async def get_unread_count_endpoint():
    """Get count of unread inbox items."""
    try:
        # Get all item IDs
        jobs = list_jobs(include_disabled=True)
        all_item_ids = []
        
        for job in jobs:
            job_id = job["id"]
            job_output_dir = _cron_jobs_mod.OUTPUT_DIR / job_id
            
            if not job_output_dir.exists():
                continue
            
            output_files = job_output_dir.glob("*.md")
            for output_file in output_files:
                timestamp = output_file.stem
                item_id = f"{job_id}_{timestamp}"
                all_item_ids.append(item_id)
        
        unread = get_unread_count(all_item_ids)
        
        return JSONResponse({
            "success": True,
            "unread_count": unread,
            "total_count": len(all_item_ids),
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)
