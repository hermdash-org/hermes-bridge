"""
Message Queue — Double-send protection.

Prevents messages from being silently dropped when the agent is busy.

Gap 10 fix: Without this, if a user sends a message while the agent
is processing, it is silently ignored. The gateway uses a
_pending_messages dict for this — we replicate that pattern.

When the agent is busy:
  - The message is queued
  - A "busy" event is pushed to SSE so the frontend can show feedback
  - When the current run finishes, the queued message is processed next
"""

import logging
import threading
from collections import deque
from typing import Optional

logger = logging.getLogger("bridge.message_queue")

# Per-session message queue. When the agent is busy, messages go here.
_pending_messages: dict[str, deque] = {}
_pending_lock = threading.Lock()


def enqueue_message(session_id: str, message: str) -> int:
    """Queue a message for a busy session.

    Returns the queue position (1-based).
    """
    with _pending_lock:
        q = _pending_messages.setdefault(session_id, deque())
        q.append(message)
        position = len(q)

    logger.info("Queued message for busy session %s (position %d)",
                session_id, position)
    return position


def dequeue_message(session_id: str) -> Optional[str]:
    """Pop the next pending message for a session.

    Returns None if the queue is empty.
    """
    with _pending_lock:
        q = _pending_messages.get(session_id)
        if q:
            msg = q.popleft()
            if not q:
                del _pending_messages[session_id]
            return msg
    return None


def has_pending(session_id: str) -> bool:
    """Check if a session has queued messages."""
    with _pending_lock:
        q = _pending_messages.get(session_id)
        return bool(q)


def pending_count(session_id: str) -> int:
    """Return the number of pending messages for a session."""
    with _pending_lock:
        q = _pending_messages.get(session_id)
        return len(q) if q else 0


def clear_pending(session_id: str) -> int:
    """Clear all pending messages for a session. Returns count cleared."""
    with _pending_lock:
        q = _pending_messages.pop(session_id, None)
        return len(q) if q else 0
