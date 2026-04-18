"""
Chat package — send messages and stream responses.

Exports a single FastAPI router with:
  POST /chat                     — fire-and-forget message send (+ optional images)
  POST /chat/upload              — upload image file via multipart form
  GET  /chat/stream/{session_id} — SSE real-time token stream
  GET  /chat/status/{task_id}    — poll task completion
  POST /chat/stop/{session_id}   — interrupt a running agent (Gap 2)
  POST /chat/approve             — approve/deny dangerous commands (Gap 1)
"""

import asyncio
import json
import threading
import time
import traceback
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .agent_pool import (
    get_agent,
    get_conversation_history,
    get_session_lock,
    signal_stream_done,
    push_stream_event,
    push_stream_delta,
    running_tasks,
    tasks_lock,
    cleanup_old_tasks,
    trigger_auto_title,
    subscribe_to_stream,
    unsubscribe_from_stream,
    pop_pending_model_note,
)

# Gap-fix modules
from .interrupt import (
    register_running_agent,
    unregister_running_agent,
    interrupt_agent,
    is_agent_running,
)
from .compression import maybe_compress_session
from .message_queue import (
    enqueue_message,
    dequeue_message,
    has_pending,
)
from .approval_bridge import resolve_approval
from .image_upload import (
    save_uploaded_image,
    save_base64_image,
    enrich_message_with_images,
)

router = APIRouter()


# ── POST /chat — Send a message ────────────────────────────────────

@router.post("/chat")
async def chat(request: Request):
    """Start a chat in the background. Returns task_id immediately.

    Frontend flow:
    1. POST /chat → get task_id + session_id
    2. GET /chat/stream/{session_id} → SSE stream
    3. GET /chat/status/{task_id} → poll until done
    """
    body = await request.json()
    message = body.get("message", "")
    session_id = body.get("session_id", None)
    images_b64 = body.get("images", [])  # Optional base64 images array

    if not message and not images_b64:
        return JSONResponse({"error": "message or images required"}, status_code=400)

    if not session_id:
        session_id = str(uuid.uuid4())

    # Gap 10: If agent is busy, queue the message instead of dropping it
    if is_agent_running(session_id):
        position = enqueue_message(session_id, message)
        push_stream_event(session_id, {
            "type": "status",
            "data": {
                "event": "message_queued",
                "message": f"Agent is busy — message queued (position {position})",
                "position": position,
                "ts": time.time(),
            },
        })
        return JSONResponse({
            "status": "queued",
            "session_id": session_id,
            "queue_position": position,
        })

    task_id = str(uuid.uuid4())[:8]

    with tasks_lock:
        running_tasks[task_id] = {
            "status": "running",
            "session_id": session_id,
            "error": None,
            "started_at": time.time(),
        }

    def _run(sid):
        current_sid = sid
        print(f"[{task_id}] START session={current_sid}")
        try:
            session_lock = get_session_lock(current_sid)
            with session_lock:
                agent, approval_ctx = get_agent(current_sid, streaming_session_id=current_sid)

                history = get_conversation_history(current_sid)
                print(f"[{task_id}] Loaded {len(history)} history messages")

                # Gap 3: Pre-turn compression check
                maybe_compress_session(agent, history)

                # Image upload: save base64 images + run vision analysis
                # Matches gateway/run.py:6990-7055 _enrich_message_with_image_analysis
                effective_message = message
                if images_b64:
                    saved_paths = []
                    for img_data in images_b64:
                        try:
                            path = save_base64_image(img_data)
                            saved_paths.append(path)
                        except Exception as e:
                            print(f"[{task_id}] Image save error: {e}")

                    if saved_paths:
                        push_stream_event(current_sid, {
                            "type": "status",
                            "data": {
                                "event": "analyzing_images",
                                "message": f"Analyzing {len(saved_paths)} image(s)...",
                                "ts": time.time(),
                            },
                        })
                        effective_message = enrich_message_with_images(
                            message or "", saved_paths
                        )

                # Prepend pending model switch note so the model knows
                # about the switch (same as gateway/run.py line 6910)
                model_note = pop_pending_model_note(current_sid)
                effective_message = (model_note + "\n\n" + effective_message) if model_note else effective_message

                # Gap 1: Wire approval callbacks around run_conversation
                # Gap 2: Track running agent for interrupt support
                approval_ctx["setup"]()
                register_running_agent(current_sid, agent)
                try:
                    result = agent.run_conversation(effective_message, conversation_history=history)
                finally:
                    approval_ctx["teardown"]()
                    unregister_running_agent(current_sid)

                # Expose graceful generation errors to the UI
                if isinstance(result, dict) and result.get("error"):
                    error_str = result["error"]
                    push_stream_delta(current_sid, f"\n\n**Agent Error:** {error_str}")

                print(f"[{task_id}] COMPLETED")

                # Auto-generate title
                try:
                    response_text = result.get("final_response", "") if result and isinstance(result, dict) else ""
                    if response_text:
                        trigger_auto_title(current_sid, message, response_text, history)
                except Exception as e:
                    print(f"[{task_id}] Auto-title error: {e}")

                # Handle session handoff (compression)
                if agent.session_id and agent.session_id != current_sid:
                    with tasks_lock:
                        running_tasks[task_id]["session_id"] = agent.session_id
                    current_sid = agent.session_id

            signal_stream_done(current_sid)
            with tasks_lock:
                running_tasks[task_id]["status"] = "done"
                running_tasks[task_id]["finished_at"] = time.time()

            # Gap 10: Process any queued messages
            _process_pending_messages(current_sid)

        except Exception as e:
            print(f"[{task_id}] ERROR: {type(e).__name__}: {e}")
            traceback.print_exc()

            # Send the error to the UI before closing the stream
            error_msg = f"\n\n**Provider Error:** {str(e)}"
            push_stream_delta(current_sid, error_msg)

            signal_stream_done(current_sid)
            with tasks_lock:
                running_tasks[task_id]["status"] = "error"
                running_tasks[task_id]["error"] = f"{type(e).__name__}: {str(e)}"
                running_tasks[task_id]["finished_at"] = time.time()

    threading.Thread(target=lambda: _run(session_id), daemon=True).start()
    cleanup_old_tasks()

    return JSONResponse({
        "task_id": task_id,
        "session_id": session_id,
        "status": "running",
    })


def _process_pending_messages(session_id: str):
    """Process queued messages after the current run finishes (Gap 10)."""
    next_msg = dequeue_message(session_id)
    if not next_msg:
        return

    # Recursively trigger a new run for the pending message
    print(f"[QUEUE] Processing pending message for {session_id}")
    task_id = str(uuid.uuid4())[:8]

    with tasks_lock:
        running_tasks[task_id] = {
            "status": "running",
            "session_id": session_id,
            "error": None,
            "started_at": time.time(),
        }

    def _run_pending(sid, msg, tid):
        try:
            session_lock = get_session_lock(sid)
            with session_lock:
                agent, approval_ctx = get_agent(sid, streaming_session_id=sid)
                history = get_conversation_history(sid)
                maybe_compress_session(agent, history)

                approval_ctx["setup"]()
                register_running_agent(sid, agent)
                try:
                    result = agent.run_conversation(msg, conversation_history=history)
                finally:
                    approval_ctx["teardown"]()
                    unregister_running_agent(sid)

                if isinstance(result, dict) and result.get("error"):
                    push_stream_delta(sid, f"\n\n**Agent Error:** {result['error']}")

            signal_stream_done(sid)
            with tasks_lock:
                running_tasks[tid]["status"] = "done"
                running_tasks[tid]["finished_at"] = time.time()

            # Chain: process any further pending messages
            _process_pending_messages(sid)

        except Exception as e:
            print(f"[QUEUE] ERROR: {e}")
            traceback.print_exc()
            push_stream_delta(sid, f"\n\n**Provider Error:** {str(e)}")
            signal_stream_done(sid)
            with tasks_lock:
                running_tasks[tid]["status"] = "error"
                running_tasks[tid]["error"] = str(e)
                running_tasks[tid]["finished_at"] = time.time()

    threading.Thread(
        target=lambda: _run_pending(session_id, next_msg, task_id),
        daemon=True,
    ).start()


# ── GET /chat/stream/{session_id} — SSE stream ─────────────────────

@router.get("/chat/stream/{session_id}")
async def stream_session(session_id: str):
    """SSE endpoint — receive real-time agent events.

    Uses buffered subscription: even if the agent started producing
    tokens before this SSE connection was established, all buffered
    events are replayed immediately on connect.

    Event types emitted:
      delta              — token text ({"delta": "..."})
      thinking           — kawaii spinner text
      reasoning_delta    — real-time reasoning/thinking tokens
      reasoning          — full reasoning text (post-response)
      tool_started       — tool execution began
      tool_completed     — tool execution finished
      status             — lifecycle events (retries, compression, etc.)
      approval_required  — dangerous command needs user approval (Gap 1)
      title_updated      — auto-generated session title
      done               — stream complete
      error              — stream error
    """
    q = asyncio.Queue()
    loop = asyncio.get_running_loop()

    # Subscribe — replays any buffered events from before we connected
    sub = subscribe_to_stream(session_id, q, loop)

    async def event_generator():
        try:
            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue

                if item is None:
                    yield f"event: done\ndata: {{}}\n\n"
                    break

                if isinstance(item, dict):
                    event_type = item.get("type", "delta")
                    data = item.get("data", "")

                    if event_type == "delta":
                        # data is a raw string from push_stream_delta
                        if isinstance(data, str) and data:
                            yield f"event: delta\ndata: {json.dumps({'delta': data})}\n\n"
                        elif isinstance(data, dict):
                            # Fallback: extract from dict if ever sent as dict
                            content = data.get("delta", data.get("content", ""))
                            if content:
                                yield f"event: delta\ndata: {json.dumps({'delta': content})}\n\n"
                    elif event_type == "title_updated":
                        yield f"event: title_updated\ndata: {json.dumps(data)}\n\n"
                    else:
                        # All other events: thinking, reasoning_delta, reasoning,
                        # tool_started, tool_completed, status, approval_required
                        yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

                elif isinstance(item, str) and item:
                    yield f"event: delta\ndata: {json.dumps({'delta': item})}\n\n"

        finally:
            unsubscribe_from_stream(session_id, sub)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── GET /chat/status/{task_id} — Poll status ───────────────────────

@router.get("/chat/status/{task_id}")
async def chat_status(task_id: str):
    """Check if a background chat task is still running."""
    with tasks_lock:
        task = running_tasks.get(task_id)

    if not task:
        return JSONResponse({"error": "task not found"}, status_code=404)

    return JSONResponse({
        "task_id": task_id,
        "status": task["status"],
        "session_id": task["session_id"],
        "error": task.get("error"),
    })


# ── POST /chat/stop/{session_id} — Interrupt agent (Gap 2) ─────────

@router.post("/chat/stop/{session_id}")
async def stop_agent(session_id: str):
    """Interrupt a running agent for a session.

    Calls agent.interrupt() which gracefully aborts the current
    tool execution or LLM call.
    """
    success = interrupt_agent(session_id, reason="User cancelled from UI")

    if success:
        push_stream_event(session_id, {
            "type": "status",
            "data": {
                "event": "interrupted",
                "message": "Agent interrupted by user",
                "ts": time.time(),
            },
        })
        return JSONResponse({"status": "interrupted", "session_id": session_id})
    else:
        return JSONResponse(
            {"status": "not_running", "session_id": session_id},
            status_code=404,
        )


# ── POST /chat/approve — Approve/deny dangerous commands (Gap 1) ──

@router.post("/chat/approve")
async def approve_command(request: Request):
    """Approve or deny a dangerous command.

    Frontend receives an 'approval_required' SSE event with the command
    details, then calls this endpoint with the user's decision.

    Body:
      session_id: str — the session with a pending approval
      choice: str    — "once", "session", "always", or "deny"
    """
    body = await request.json()
    session_id = body.get("session_id", "")
    choice = body.get("choice", "deny")

    if not session_id:
        return JSONResponse({"error": "session_id required"}, status_code=400)

    if choice not in ("once", "session", "always", "deny"):
        return JSONResponse(
            {"error": f"invalid choice: {choice}"},
            status_code=400,
        )

    resolved = resolve_approval(session_id, choice)

    return JSONResponse({
        "resolved": resolved,
        "session_id": session_id,
        "choice": choice,
    })
