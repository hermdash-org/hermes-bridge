"""
Interrupt — Agent stop/interrupt support.

Provides the ability to stop a running agent from the frontend.

Gap 2 fix: Without this, once an agent starts running, the user
cannot stop it — even if it's doing something destructive.

Maps to gateway/run.py agent_holder[0].interrupt() pattern.
"""

import logging
import threading

logger = logging.getLogger("bridge.interrupt")

# Session → AIAgent reference for active runs.
# Set before run_conversation(), cleared after.
_running_agents: dict[str, object] = {}
_running_agents_lock = threading.Lock()


def register_running_agent(session_id: str, agent) -> None:
    """Track an agent that is currently executing."""
    with _running_agents_lock:
        _running_agents[session_id] = agent


def unregister_running_agent(session_id: str) -> None:
    """Remove tracking when agent finishes."""
    with _running_agents_lock:
        _running_agents.pop(session_id, None)


def interrupt_agent(session_id: str, reason: str = "User cancelled") -> bool:
    """Interrupt a running agent.

    Calls agent.interrupt() which sets the internal interrupt flag,
    causing the current tool execution or LLM call to abort gracefully.

    Returns True if an agent was found and interrupted.
    """
    with _running_agents_lock:
        agent = _running_agents.get(session_id)

    if agent is None:
        logger.debug("No running agent for session %s", session_id)
        return False

    try:
        if hasattr(agent, "interrupt"):
            agent.interrupt(reason)
            logger.info("Interrupted agent for session %s: %s", session_id, reason)
            return True
        else:
            logger.warning("Agent for %s has no interrupt() method", session_id)
            return False
    except Exception as e:
        logger.error("Failed to interrupt agent %s: %s", session_id, e)
        return False


def is_agent_running(session_id: str) -> bool:
    """Check if an agent is currently running for a session."""
    with _running_agents_lock:
        return session_id in _running_agents
