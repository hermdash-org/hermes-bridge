"""
Compression — Pre-turn session hygiene.

Runs a rough token estimate before each agent turn and triggers
context compression if the session is getting too large.

Gap 3 fix: Without this, long sessions blow the context window
and the API returns errors, killing the session.

Maps to gateway/run.py lines 3260-3450 (pre-turn hygiene).
"""

import logging

logger = logging.getLogger("bridge.compression")

# Default context budget — leave room for system prompt + response.
# Most models: 128k-200k tokens. We compress at ~70% to be safe.
DEFAULT_COMPRESSION_THRESHOLD_CHARS = 300_000  # ~75k tokens rough estimate


def estimate_token_count(history: list) -> int:
    """Rough token estimate from conversation history.

    Uses ~4 chars per token heuristic. Not exact, but good enough
    to decide when to trigger compression.
    """
    total_chars = 0
    for msg in history:
        content = msg.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            # Multimodal messages
            for part in content:
                if isinstance(part, dict):
                    total_chars += len(part.get("text", ""))
    return total_chars // 4


def maybe_compress_session(agent, history: list,
                           threshold_chars: int = DEFAULT_COMPRESSION_THRESHOLD_CHARS
                           ) -> bool:
    """Check if session needs compression and trigger it if so.

    Call this BEFORE run_conversation() on each turn.

    Returns True if compression was triggered.
    """
    total_chars = sum(
        len(msg.get("content", "")) if isinstance(msg.get("content"), str)
        else sum(len(p.get("text", "")) for p in (msg.get("content") or []) if isinstance(p, dict))
        for msg in history
    )

    if total_chars < threshold_chars:
        return False

    logger.info(
        "Session %s at %d chars (~%d tokens) — triggering pre-turn compression",
        getattr(agent, "session_id", "?"), total_chars, total_chars // 4,
    )

    try:
        # The agent has a built-in compression method
        if hasattr(agent, "_compress_context"):
            agent._compress_context(history)
            return True
        elif hasattr(agent, "compress_context"):
            agent.compress_context(history)
            return True
        else:
            logger.warning("Agent has no compression method available")
            return False
    except Exception as e:
        logger.error("Pre-turn compression failed: %s", e)
        return False
