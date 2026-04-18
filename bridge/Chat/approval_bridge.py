"""
Approval Bridge — Wire dangerous command approvals through SSE.

Replicates gateway/run.py lines 8007-8093:
  - Sets HERMES_GATEWAY_SESSION so the approval system knows to block
  - Registers a per-session gateway_notify callback
  - Pushes approval_required events through SSE
  - Provides resolve_approval() for the frontend to approve/deny

This module is the ONLY place approval wiring lives.
The agent thread blocks until the user responds via POST /chat/approve.

Gap 1 fix: Without this, ALL dangerous commands auto-approve silently.
"""

import logging
import os
import threading
import time

logger = logging.getLogger("bridge.approval")

# Ensure the agent knows we're in a gateway-like context.
# This is the ONE line that turns on dangerous command protection.
# Without it, approval.py:714-716 returns {"approved": True} for everything.
os.environ.setdefault("HERMES_GATEWAY_SESSION", "1")


def wire_approval_for_session(session_id: str, push_event_fn) -> dict:
    """Wire approval callbacks for a session before run_conversation().

    Args:
        session_id: The chat session ID (used as approval session_key).
        push_event_fn: Callable(session_id, event_dict) to push SSE events.

    Returns:
        A context dict with:
          - "setup": callable to call BEFORE run_conversation()
          - "teardown": callable to call AFTER run_conversation() (in finally)

    Usage:
        ctx = wire_approval_for_session(sid, push_stream_event)
        ctx["setup"]()
        try:
            agent.run_conversation(...)
        finally:
            ctx["teardown"]()
    """
    from tools.approval import (
        register_gateway_notify,
        reset_current_session_key,
        set_current_session_key,
        unregister_gateway_notify,
    )

    _token_holder = [None]

    def setup():
        """Bind approval session key and register the SSE notify callback."""
        _token_holder[0] = set_current_session_key(session_id)
        register_gateway_notify(session_id, _make_notify_callback(
            session_id, push_event_fn
        ))

    def teardown():
        """Unregister callbacks so blocked threads don't hang forever."""
        unregister_gateway_notify(session_id)
        if _token_holder[0] is not None:
            reset_current_session_key(_token_holder[0])

    return {"setup": setup, "teardown": teardown}


def _make_notify_callback(session_id: str, push_event_fn):
    """Create a sync callback that pushes approval requests to SSE.

    This bridges the sync agent thread → async SSE stream,
    matching gateway/run.py lines 8018-8078.
    """
    def notify(approval_data: dict):
        cmd = approval_data.get("command", "")
        desc = approval_data.get("description", "dangerous command")
        pattern_key = approval_data.get("pattern_key", "")

        push_event_fn(session_id, {
            "type": "approval_required",
            "data": {
                "command": cmd[:500],  # truncate for safety
                "description": desc,
                "pattern_key": pattern_key,
                "session_id": session_id,
                "ts": time.time(),
            },
        })

    return notify


def resolve_approval(session_id: str, choice: str) -> bool:
    """Resolve a pending approval from the frontend.

    Args:
        session_id: The session that has a pending approval.
        choice: One of "once", "session", "always", "deny".

    Returns:
        True if an approval was resolved, False if no pending approval.
    """
    from tools.approval import resolve_gateway_approval
    try:
        resolved = resolve_gateway_approval(session_id, choice)
        logger.info("Approval resolved for %s: %s (resolved=%s)",
                     session_id, choice, resolved)
        return resolved
    except Exception as e:
        logger.error("Failed to resolve approval: %s", e)
        return False
