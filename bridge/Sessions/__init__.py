"""
Sessions — List, get messages, delete, rename sessions.

Reads from the active profile's SessionDB (state.db).
All data is profile-scoped via get_session_db().

Endpoints:
  GET    /sessions              — List sessions (sidebar data)
  GET    /sessions/{id}         — Get session with messages
  DELETE /sessions/{id}         — Delete a session
  PUT    /sessions/{id}/title   — Set/update session title
"""

import io
import sys

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..Chat.agent_pool import get_session_db

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/")
async def list_sessions(limit: int = 50, offset: int = 0):
    """List sessions for the active profile's sidebar.

    Returns id, title, preview, started_at, last_active, message_count.
    Sorted by most recent first.
    """
    try:
        db = get_session_db()
        sessions = db.list_sessions_rich(
            limit=limit,
            offset=offset,
            include_children=False,
        )

        result = []
        for s in sessions:
            result.append({
                "id": s["id"],
                "title": s.get("title") or s.get("preview") or "New Chat",
                "preview": s.get("preview", ""),
                "model": s.get("model"),
                "started_at": s.get("started_at"),
                "last_active": s.get("last_active"),
                "message_count": s.get("message_count", 0),
            })

        return JSONResponse({
            "success": True,
            "count": len(result),
            "sessions": result,
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.get("/{session_id}")
async def get_session(session_id: str):
    """Get a session with all its messages."""
    try:
        db = get_session_db()
        session = db.get_session(session_id)

        if not session:
            return JSONResponse(
                {"success": False, "error": "Session not found"},
                status_code=404,
            )

        messages = db.get_messages(session_id)

        # Filter to user/assistant for display, keep tool calls as metadata
        display_messages = []
        for m in messages:
            display_messages.append({
                "role": m["role"],
                "content": m.get("content", ""),
                "tool_name": m.get("tool_name"),
                "tool_calls": m.get("tool_calls"),
                "reasoning": m.get("reasoning"),
                "timestamp": m.get("timestamp"),
            })

        return JSONResponse({
            "success": True,
            "session": {
                "id": session["id"],
                "title": session.get("title"),
                "model": session.get("model"),
                "started_at": session.get("started_at"),
                "message_count": session.get("message_count", 0),
            },
            "messages": display_messages,
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and its messages."""
    try:
        db = get_session_db()
        session = db.get_session(session_id)

        if not session:
            return JSONResponse(
                {"success": False, "error": "Session not found"},
                status_code=404,
            )

        # Delete all related records to avoid FOREIGN KEY constraint failures:
        # 1. Messages from child sessions (subagent sessions referencing this one)
        # 2. Child sessions themselves
        # 3. Messages from this session
        # 4. The session itself
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
        try:
            conn = db._conn
            with db._lock:
                # Find child sessions (subagent sessions with parent_session_id = this session)
                child_ids = [
                    row[0]
                    for row in conn.execute(
                        "SELECT id FROM sessions WHERE parent_session_id = ?", (session_id,)
                    ).fetchall()
                ]

                # Delete messages from child sessions
                for child_id in child_ids:
                    conn.execute("DELETE FROM messages WHERE session_id = ?", (child_id,))

                # Delete child sessions
                if child_ids:
                    conn.execute(
                        f"DELETE FROM sessions WHERE parent_session_id = ?", (session_id,)
                    )

                # Delete messages from this session
                conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))

                # Delete the session itself
                conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
                conn.commit()
        finally:
            sys.stdout, sys.stderr = old_out, old_err

        return JSONResponse({
            "success": True,
            "deleted": session_id,
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.put("/{session_id}/title")
async def update_title(session_id: str, request=None):
    """Set or update a session title."""
    try:
        from fastapi import Request
        body = await request.json()
        title = body.get("title", "").strip()

        if not title:
            return JSONResponse(
                {"success": False, "error": "title is required"},
                status_code=400,
            )

        db = get_session_db()
        success = db.set_session_title(session_id, title)

        if not success:
            return JSONResponse(
                {"success": False, "error": "Session not found"},
                status_code=404,
            )

        return JSONResponse({
            "success": True,
            "session_id": session_id,
            "title": title,
        })
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)
