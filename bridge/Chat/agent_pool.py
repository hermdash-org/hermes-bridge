"""
Agent Pool — Warm agent cache, session management, and SSE streaming.

Manages AIAgent instances, session locks, task tracking,
and SSE streaming subscribers.

Seven callbacks give full agent visibility (from core engine run_agent.py):
  1. stream_delta_callback       → live LLM tokens  (run_agent.py:4798)
  2. tool_progress_callback      → tool.started, tool.completed, reasoning.available
  3. thinking_callback           → raw <thinking> blocks / kawaii spinner
  4. reasoning_callback          → real-time reasoning/thinking tokens  (run_agent.py:4809)
  5. status_callback             → lifecycle + context pressure events  (run_agent.py:1695)
  6. step_callback               → turn-by-turn status
  7. background_review_callback  → memory save notifications  (Gap 8)
"""

import logging
import os
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/.hermes/.env"))

# These imports are DEFERRED (lazy) so the bridge can start on machines
# where hermes-agent is not yet installed.  The SetupGate in the UI will
# guide the user through installation.  Importing eagerly would crash the
# entire bridge at import time with "ModuleNotFoundError: No module named
# 'run_agent'" — preventing even /health and /setup/* from working.

_AIAgent = None
_SessionDB = None


def _get_AIAgent():
    """Lazy import of AIAgent from hermes-agent's run_agent module."""
    global _AIAgent
    if _AIAgent is None:
        from run_agent import AIAgent
        _AIAgent = AIAgent
    return _AIAgent


def _get_SessionDB():
    """Lazy import of SessionDB from hermes-agent's hermes_state module."""
    global _SessionDB
    if _SessionDB is None:
        from hermes_state import SessionDB
        _SessionDB = SessionDB
    return _SessionDB

# Gap-fix modules (separation of concerns)
from .agent_config import build_agent_kwargs
from .approval_bridge import wire_approval_for_session
from .interrupt import register_running_agent, unregister_running_agent

logger = logging.getLogger("bridge.pool")


# ── Profile Layer ───────────────────────────────────────────────────
# CRITICAL: Store the ORIGINAL hermes root at module load time.
# This is the SINGLE SOURCE OF TRUTH for path resolution.
#
# Without this, profile switching mutates HERMES_HOME to a profile-specific
# path (e.g. /opt/data/profiles/coder), and the NEXT call to get_profile_home()
# reads that corrupted value and appends /profiles/<name> ON TOP, creating
# infinite recursive paths like:
#   /opt/data/profiles/coder/profiles/kitten/profiles/coder/profiles/...
#
# By capturing the root ONCE at startup, we guarantee stable path resolution
# regardless of how many profile switches happen.
#
# Works for ALL deployment scenarios:
#   - Linux user with ~/.hermes          → root = ~/.hermes
#   - macOS user with ~/.hermes          → root = ~/.hermes
#   - Fresh user (first run of binary)   → root = ~/.hermes (bootstrap creates it)
#   - Windows/WSL user with ~/.hermes    → root = ~/.hermes
#   - Custom HERMES_HOME=/some/path      → root = /some/path

_hermes_root: Path = Path(os.getenv("HERMES_HOME", Path.home() / ".hermes"))
_profile_dbs: dict = {}
_STICKY_FILE: Path = _hermes_root / ".active_profile"  # survives restarts


def _load_sticky_profile() -> str:
    """Read the last active profile from disk. Returns 'default' if not set."""
    try:
        if _STICKY_FILE.exists():
            name = _STICKY_FILE.read_text(encoding="utf-8").strip()
            if name and (name == "default" or (_hermes_root / "profiles" / name).exists()):
                return name
    except Exception:
        pass
    return "default"


_active_profile: str = _load_sticky_profile()  # restored from disk on startup
_profile_dbs_lock = threading.Lock()


def get_hermes_root() -> Path:
    """Return the immutable hermes root directory.

    This NEVER changes after module load. All profile paths are
    computed relative to this root. Safe to call from any thread.
    """
    return _hermes_root


def get_profile_home(profile: str = None) -> Path:
    """Resolve profile name → directory path.

    Always computes relative to _hermes_root (captured at startup).
    NEVER reads HERMES_HOME from env — that would cause recursive
    path growth when profiles are switched.

    Mapping:
      "default"  → /opt/data              (or ~/.hermes)
      "coder"    → /opt/data/profiles/coder (or ~/.hermes/profiles/coder)
    """
    name = profile or _active_profile
    if name == "default":
        return _hermes_root
    return _hermes_root / "profiles" / name


def get_session_db(profile: str = None):
    """Get a SessionDB for a profile. Lazy-created, cached forever."""
    name = profile or _active_profile
    with _profile_dbs_lock:
        if name not in _profile_dbs:
            db_path = get_profile_home(name) / "state.db"
            _profile_dbs[name] = _get_SessionDB()(db_path=db_path)
        return _profile_dbs[name]


def get_active_profile() -> str:
    return _active_profile


def set_active_profile(name: str) -> None:
    """Switch active profile — updates env, cron paths, and agent cache.

    Computes the new home from _hermes_root (stable), then sets
    HERMES_HOME for hermes-agent internals that read it from env.
    Persists the choice to disk so restarts restore the correct profile.
    """
    global _active_profile
    old_profile = _active_profile
    _active_profile = name

    # Persist to disk — survives runtime restarts/updates
    try:
        _STICKY_FILE.write_text(name, encoding="utf-8")
    except Exception as e:
        logger.warning("Could not persist active profile to disk: %s", e)

    # Compute from the STABLE root — NOT from os.getenv("HERMES_HOME")
    new_home = get_profile_home(name)
    os.environ["HERMES_HOME"] = str(new_home)

    # Patch cron.jobs frozen module-level paths (computed at import time)
    try:
        import cron.jobs as _cj
        _cj.HERMES_DIR = new_home.resolve()
        _cj.CRON_DIR = _cj.HERMES_DIR / "cron"
        _cj.JOBS_FILE = _cj.CRON_DIR / "jobs.json"
        _cj.OUTPUT_DIR = _cj.CRON_DIR / "output"
    except ImportError:
        pass

    # Patch cron.scheduler's frozen _hermes_home so run_job() reads
    # config.yaml and .env from the correct profile directory.
    try:
        import cron.scheduler as _cs
        _cs._hermes_home = new_home
        _cs._LOCK_DIR = new_home / "cron"
        _cs._LOCK_FILE = _cs._LOCK_DIR / ".tick.lock"
    except ImportError:
        pass

    # Patch hermes_state.DEFAULT_DB_PATH so SessionDB() with no args
    # creates/opens the ACTIVE profile's state.db — not the root one.
    # This is the root cause of cron sessions landing in default.
    try:
        import hermes_state as _hs
        _hs.DEFAULT_DB_PATH = new_home / "state.db"
    except ImportError:
        pass

    # Load root .env first (global API keys), then overlay profile-specific .env.
    # This ensures profiles inherit ALL keys from default and can override specific ones.
    root_env = _hermes_root / ".env"
    if root_env.exists():
        load_dotenv(str(root_env), override=True)
    profile_env = new_home / ".env"
    if profile_env.exists() and new_home != _hermes_root:
        load_dotenv(str(profile_env), override=True)

    # Clear agent cache so agents pick up new profile config
    if old_profile != name:
        with agent_cache_lock:
            agent_cache.clear()
        logger.info("Profile switched: %s → %s (home=%s)", old_profile, name, new_home)


# ── Shared State ────────────────────────────────────────────────────

agent_cache: dict = {}
agent_cache_lock = threading.Lock()

# Model generation counter — bumped by Models module on every config write.
# Agents store the generation they were created with; on mismatch the
# agent is switch_model()'d in-place (matching core gateway/run.py).
_model_generation: int = 0
_model_generation_lock = threading.Lock()

# Pending model-switch notes — prepended to the next user message so
# the model knows it was switched (avoids parroting old identity from history).
# This is the same pattern as gateway/run.py _pending_model_notes.
_pending_model_notes: dict[str, str] = {}
_pending_model_notes_lock = threading.Lock()


def bump_model_generation() -> int:
    """Increment the model generation counter. Called by Models on config write."""
    global _model_generation
    with _model_generation_lock:
        _model_generation += 1
        return _model_generation


def get_model_generation() -> int:
    """Return the current model generation counter."""
    with _model_generation_lock:
        return _model_generation


def pop_pending_model_note(session_id: str) -> str | None:
    """Pop and return any pending model-switch note for this session.

    Called by the chat handler before run_conversation() — if a note
    exists, it is prepended to the user's message so the model adjusts
    its self-identification.
    """
    with _pending_model_notes_lock:
        return _pending_model_notes.pop(session_id, None)

_session_locks: dict[str, threading.Lock] = {}
_session_locks_lock = threading.Lock()

running_tasks: dict[str, dict] = {}
tasks_lock = threading.Lock()

stream_subscribers: dict[str, list] = {}  # session_id -> [(queue, loop), ...]
stream_sub_lock = threading.Lock()

# Per-session event buffer — events are stored here so late SSE subscribers
# don't miss anything. Cleared when no more subscribers remain.
_stream_buffers: dict[str, list] = {}
_stream_buffer_lock = threading.Lock()


def get_session_lock(session_id: str) -> threading.Lock:
    """Get or create a lock for a specific session."""
    with _session_locks_lock:
        if session_id not in _session_locks:
            _session_locks[session_id] = threading.Lock()
        return _session_locks[session_id]


# ── Stream Helpers ──────────────────────────────────────────────────
# IMPORTANT: These are called from background threads (threading.Thread)
# but push into asyncio.Queues owned by the event loop. asyncio.Queue
# is NOT thread-safe — we must use loop.call_soon_threadsafe() to wake
# the event loop properly.

def _threadsafe_put(q, loop, item):
    """Put into asyncio.Queue from a non-async thread."""
    try:
        loop.call_soon_threadsafe(q.put_nowait, item)
    except Exception:
        pass


def _push_to_subscribers(session_id: str, item):
    """Thread-safe push into async queues + buffer."""
    # Buffer the event so late subscribers don't miss anything
    with _stream_buffer_lock:
        buf = _stream_buffers.setdefault(session_id, [])
        buf.append(item)

    with stream_sub_lock:
        subs = list(stream_subscribers.get(session_id, []))

    for q, loop in subs:
        _threadsafe_put(q, loop, item)


def subscribe_to_stream(session_id, q, loop):
    """Subscribe to events. Replays buffered events on connect."""
    sub = (q, loop)
    with _stream_buffer_lock:
        buffered = list(_stream_buffers.get(session_id, []))
    for item in buffered:
        _threadsafe_put(q, loop, item)

    with stream_sub_lock:
        stream_subscribers.setdefault(session_id, []).append(sub)
    return sub


def unsubscribe_from_stream(session_id, sub):
    """Remove a subscriber and clean up buffer if no subscribers left.

    Buffer is only cleared if the agent has finished (done signal was sent).
    This allows late reconnects to replay all events even after disconnect.
    """
    with stream_sub_lock:
        subs = stream_subscribers.get(session_id, [])
        if sub in subs:
            subs.remove(sub)
        remaining = len(subs)

    # Only clear buffer if no subscribers AND agent is done
    # (done signal = None sentinel is in the buffer)
    if remaining == 0:
        with _stream_buffer_lock:
            buf = _stream_buffers.get(session_id, [])
            # None sentinel means done signal was sent — safe to clear
            agent_done = any(item is None for item in buf)
            if agent_done:
                _stream_buffers.pop(session_id, None)


def push_stream_delta(session_id: str, raw_delta):
    """Push a token delta to all SSE subscribers.

    raw_delta is a plain string from AIAgent._fire_stream_delta (run_agent.py:4798).
    The SSE generator wraps it as JSON: {"delta": raw_delta}.
    """
    if raw_delta is None:
        return
    _push_to_subscribers(session_id, {"type": "delta", "data": raw_delta})


def push_stream_event(session_id: str, event: dict):
    """Push a structured event to SSE subscribers."""
    _push_to_subscribers(session_id, event)


def signal_stream_done(session_id: str):
    """Send None sentinel to all subscribers — signals completion."""
    # Buffer the done signal too so late subscribers see it
    _push_to_subscribers(session_id, None)


# ── Tool Event Helpers (from tui_gateway/server.py) ────────────────

def _tool_ctx(name: str, args: dict) -> str:
    """Build tool context string (preview of primary argument).
    
    Matches tui_gateway/server.py:_tool_ctx (line 973).
    """
    try:
        from agent.display import build_tool_preview
        return build_tool_preview(name, args, max_len=80) or ""
    except Exception:
        return ""


def _fmt_tool_duration(seconds: float | None) -> str:
    """Format duration for display.
    
    Matches tui_gateway/server.py:_fmt_tool_duration (line 978).
    """
    if seconds is None:
        return ""
    if seconds < 10:
        return f"{seconds:.1f}s"
    if seconds < 60:
        return f"{round(seconds)}s"
    mins, secs = divmod(int(round(seconds)), 60)
    return f"{mins}m {secs}s" if secs else f"{mins}m"


def _count_list(obj: object, *path: str) -> int | None:
    """Navigate nested dict and count list length.
    
    Matches tui_gateway/server.py:_count_list (line 988).
    """
    cur = obj
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return len(cur) if isinstance(cur, list) else None


def _tool_summary(name: str, result: str, duration_s: float | None) -> str | None:
    """Generate human-readable summary of tool execution.
    
    Matches tui_gateway/server.py:_tool_summary (line 996).
    """
    import json
    try:
        data = json.loads(result)
    except Exception:
        data = None

    dur = _fmt_tool_duration(duration_s)
    suffix = f" in {dur}" if dur else ""
    text = None

    if name == "web_search" and isinstance(data, dict):
        n = _count_list(data, "data", "web")
        if n is not None:
            text = f"Did {n} {'search' if n == 1 else 'searches'}"

    elif name == "web_extract" and isinstance(data, dict):
        n = _count_list(data, "results") or _count_list(data, "data", "results")
        if n is not None:
            text = f"Extracted {n} {'page' if n == 1 else 'pages'}"

    return f"{text or 'Completed'}{suffix}" if (text or dur) else None


# ── Per-session tool state (for edit snapshots and timing) ────────
# Shared between tool_start_callback and tool_complete_callback
_tool_session_state: dict[str, dict] = {}
_tool_session_state_lock = threading.Lock()


def _get_tool_state(session_id: str) -> dict:
    """Get or create tool state dict for a session."""
    with _tool_session_state_lock:
        if session_id not in _tool_session_state:
            _tool_session_state[session_id] = {
                "edit_snapshots": {},
                "tool_started_at": {},
            }
        return _tool_session_state[session_id]


# ── Callback Factories ──────────────────────────────────────────────

def _make_tool_progress_callback(session_id: str):
    """Tool lifecycle callback matching tui_gateway/server.py architecture.
    
    Handles:
    - reasoning.available events
    - subagent.* events (start, complete, thinking, progress, tool)
    
    Matches tui_gateway/server.py:_on_tool_progress (line 1087+)
    """
    def callback(event_type, tool_name=None, preview=None, args=None, **kwargs):
        # DEBUG: Print to console
        print(f"[TOOL_PROGRESS] event_type={event_type}, tool_name={tool_name}, session={session_id}")
        
        # Handle reasoning events
        if event_type == "reasoning.available":
            push_stream_event(session_id, {
                "type": "reasoning",
                "data": {"text": preview or "", "ts": time.time()},
            })
            return

        # Handle subagent events (matches tui_gateway/server.py line 1087)
        if event_type.startswith("subagent."):
            print(f"[SUBAGENT EVENT] {event_type} - goal: {kwargs.get('goal', 'N/A')}")
            print(f"[SUBAGENT PUSH] Pushing {event_type} to session {session_id}")
            payload = {
                "goal": str(kwargs.get("goal") or ""),
                "task_count": int(kwargs.get("task_count") or 1),
                "task_index": int(kwargs.get("task_index") or 0),
                "ts": time.time(),
            }
            
            # Identity fields for subagent tree (all optional)
            if kwargs.get("subagent_id"):
                payload["subagent_id"] = str(kwargs["subagent_id"])
            if kwargs.get("parent_id"):
                payload["parent_id"] = str(kwargs["parent_id"])
            if kwargs.get("depth") is not None:
                payload["depth"] = int(kwargs["depth"])
            if kwargs.get("model"):
                payload["model"] = str(kwargs["model"])
            if kwargs.get("tool_count") is not None:
                payload["tool_count"] = int(kwargs["tool_count"])
            if kwargs.get("toolsets"):
                payload["toolsets"] = [str(t) for t in kwargs["toolsets"]]
                
            # Status and summary fields
            if kwargs.get("status"):
                payload["status"] = str(kwargs["status"])
            if kwargs.get("summary"):
                payload["summary"] = str(kwargs["summary"])
            if kwargs.get("duration_seconds") is not None:
                payload["duration_seconds"] = float(kwargs["duration_seconds"])
                
            # Tool-specific fields
            if tool_name:
                payload["tool_name"] = str(tool_name)
            if preview:
                payload["text"] = str(preview)
                if event_type == "subagent.tool":
                    payload["tool_preview"] = str(preview)
                    
            # Cost and usage tracking
            for int_key in ("input_tokens", "output_tokens", "reasoning_tokens", "api_calls"):
                val = kwargs.get(int_key)
                if val is not None:
                    try:
                        payload[int_key] = int(val)
                    except (TypeError, ValueError):
                        pass
                        
            if kwargs.get("cost_usd") is not None:
                try:
                    payload["cost_usd"] = float(kwargs["cost_usd"])
                except (TypeError, ValueError):
                    pass
                    
            # File operations tracking
            if kwargs.get("files_read"):
                payload["files_read"] = [str(p) for p in kwargs["files_read"]]
            if kwargs.get("files_written"):
                payload["files_written"] = [str(p) for p in kwargs["files_written"]]
            if kwargs.get("output_tail"):
                payload["output_tail"] = list(kwargs["output_tail"])

            # Send the subagent event
            push_stream_event(session_id, {
                "type": event_type,  # subagent.start, subagent.complete, etc.
                "data": payload,
            })
            print(f"[SUBAGENT PUSHED] Event {event_type} pushed to SSE for session {session_id}")

    return callback


def _make_tool_start_callback(session_id: str):
    """Tool start callback matching tui_gateway/server.py:_on_tool_start (line 1020).
    
    Captures edit snapshots for diff generation and tracks start time.
    Called by run_agent.py:8391 with (tool_call_id, name, args).
    """
    # Import registry once at callback creation time
    try:
        from tools.registry import registry as _tool_registry
    except ImportError:
        _tool_registry = None

    def callback(tool_call_id: str, name: str, args: dict):
        state = _get_tool_state(session_id)
        
        # Capture edit snapshot for diff generation
        try:
            from agent.display import capture_local_edit_snapshot
            snapshot = capture_local_edit_snapshot(name, args)
            if snapshot is not None:
                state["edit_snapshots"][tool_call_id] = snapshot
        except Exception:
            pass
        
        state["tool_started_at"][tool_call_id] = time.time()

        # Enrich with emoji + toolset from the core engine registry
        emoji = "⚡"
        toolset = "unknown"
        if _tool_registry and name:
            emoji = _tool_registry.get_emoji(name, default="⚡")
            toolset = _tool_registry.get_toolset_for_tool(name) or "unknown"

        # Send tool_started event (matches tui_gateway/server.py line 1032)
        push_stream_event(session_id, {
            "type": "tool_started",
            "data": {
                "tool_id": tool_call_id,
                "tool": name,
                "emoji": emoji,
                "toolset": toolset,
                "context": _tool_ctx(name, args or {}),
                "ts": time.time(),
            },
        })

    return callback


def _make_tool_complete_callback(session_id: str):
    """Tool complete callback matching tui_gateway/server.py:_on_tool_complete (line 1038).
    
    Generates summary and inline_diff, then sends tool_completed event.
    Called by run_agent.py:8568 with (tool_call_id, name, args, result).
    """
    # Import registry once at callback creation time
    try:
        from tools.registry import registry as _tool_registry
    except ImportError:
        _tool_registry = None

    def callback(tool_call_id: str, name: str, args: dict, result: str):
        state = _get_tool_state(session_id)
        
        # Retrieve snapshot and start time
        snapshot = state["edit_snapshots"].pop(tool_call_id, None)
        started_at = state["tool_started_at"].pop(tool_call_id, None)
        duration_s = time.time() - started_at if started_at else None

        # Enrich with emoji + toolset from the core engine registry
        emoji = "⚡"
        toolset = "unknown"
        if _tool_registry and name:
            emoji = _tool_registry.get_emoji(name, default="⚡")
            toolset = _tool_registry.get_toolset_for_tool(name) or "unknown"

        # Build payload (matches tui_gateway/server.py line 1040)
        payload = {
            "tool_id": tool_call_id,
            "tool": name,
            "emoji": emoji,
            "toolset": toolset,
            "duration": round(duration_s, 3) if duration_s else 0,
            "ts": time.time(),
        }

        # Add summary (matches tui_gateway/server.py line 1050)
        summary = _tool_summary(name, result, duration_s)
        if summary:
            payload["summary"] = summary

        # Add inline_diff for file edits (matches tui_gateway/server.py line 1056)
        try:
            from agent.display import render_edit_diff_with_delta
            import re
            
            rendered: list[str] = []
            if render_edit_diff_with_delta(
                name,
                result,
                function_args=args,
                snapshot=snapshot,
                print_fn=rendered.append,
            ):
                # Strip ANSI color codes for web display
                diff_text = "\n".join(rendered)
                # Remove ANSI escape sequences (color codes)
                ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
                clean_diff = ansi_escape.sub('', diff_text)
                payload["inline_diff"] = clean_diff
        except Exception:
            pass

        push_stream_event(session_id, {
            "type": "tool_completed",
            "data": payload,
        })

    return callback


def _make_thinking_callback(session_id: str):
    def callback(text):
        if text:
            push_stream_event(session_id, {
                "type": "thinking",
                "data": {"text": text, "ts": time.time()},
            })
    return callback


def _make_reasoning_callback(session_id: str):
    """Real-time reasoning/thinking token stream (run_agent.py:4809).

    Fires for every reasoning delta as the model thinks — gives the UI
    live thinking text instead of waiting for the full response.
    """
    def callback(text):
        if text:
            push_stream_event(session_id, {
                "type": "reasoning_delta",
                "data": {"text": text, "ts": time.time()},
            })
    return callback


def _make_status_callback(session_id: str):
    """Lifecycle + context pressure events (run_agent.py:1695).

    Gives the UI visibility into agent state: retries, compression,
    context pressure warnings, etc.
    """
    def callback(event_type, message):
        push_stream_event(session_id, {
            "type": "status",
            "data": {
                "event": event_type,
                "message": message,
                "ts": time.time(),
            },
        })
    return callback


def _make_background_review_callback(session_id: str):
    """Background review notifications ("💾 Memory updated", etc.).

    Maps to gateway/run.py line 7934: agent.background_review_callback.
    Gap 8 fix: Without this, users never see memory save confirmations.
    """
    def callback(message: str):
        if message:
            push_stream_event(session_id, {
                "type": "status",
                "data": {
                    "event": "background_review",
                    "message": message,
                    "ts": time.time(),
                },
            })
    return callback


# ── Agent Access ────────────────────────────────────────────────────

_DEFAULT_MODEL = "google/gemini-2.5-flash:free"


def _read_config_model_and_provider() -> tuple[str, str]:
    """Read (model, provider) from the active profile's config.yaml.

    Returns (model_str, provider_str). Either may be empty string.
    """
    try:
        import yaml
        profile_dir = get_profile_home(_active_profile)
        config_path = profile_dir / "config.yaml"
        if config_path.exists():
            with open(config_path) as f:
                cfg = yaml.safe_load(f) or {}
            model_cfg = cfg.get("model", {})
            if isinstance(model_cfg, str):
                return model_cfg, ""
            if isinstance(model_cfg, dict):
                return (
                    model_cfg.get("default") or model_cfg.get("model") or "",
                    model_cfg.get("provider") or "",
                )
    except Exception:
        pass
    return os.environ.get("HEMUI_MODEL", ""), os.environ.get("HEMUI_PROVIDER", "")


def _get_config_model() -> str:
    """Read model from active profile's config.yaml. Returns empty string if not set."""
    model, _ = _read_config_model_and_provider()
    return model


def _get_config_provider() -> str:
    """Read provider from active profile's config.yaml."""
    _, provider = _read_config_model_and_provider()
    return provider


def _resolve_provider_info(provider_id: str) -> dict:
    """Resolve provider ID → credentials for AIAgent creation.

    Uses the upstream PROVIDER_REGISTRY when available (bridge runs
    inside hermes venv). Falls back to sensible OpenRouter defaults
    for unknown/empty providers.

    Returns a dict with keys:
      - provider: str (canonical provider ID)
      - api_key: str
      - base_url: str
    """
    if not provider_id:
        provider_id = "openrouter"

    try:
        from hermes_cli.auth import PROVIDER_REGISTRY

        pconf = PROVIDER_REGISTRY.get(provider_id)
        if pconf is not None:
            # Resolve API key: try each env var name in order
            api_key = ""
            for env_name in pconf.api_key_env_vars:
                val = os.environ.get(env_name, "")
                if val:
                    api_key = val
                    break

            # Resolve base URL: env var override or fallback to default
            base_url = pconf.inference_base_url or ""
            if pconf.base_url_env_var:
                env_url = os.environ.get(pconf.base_url_env_var, "")
                if env_url:
                    base_url = env_url

            return {
                "provider": provider_id,
                "api_key": api_key,
                "base_url": base_url,
            }
    except ImportError:
        pass
    except Exception:
        pass

    # Fallback: Provider-specific defaults
    if provider_id == "deepseek":
        return {
            "provider": "deepseek",
            "api_key": os.environ.get("DEEPSEEK_API_KEY", ""),
            "base_url": "https://api.deepseek.com/v1",
        }
    elif provider_id == "anthropic":
        return {
            "provider": "anthropic", 
            "api_key": os.environ.get("ANTHROPIC_API_KEY", ""),
            "base_url": "https://api.anthropic.com",
        }
    elif provider_id == "gemini":
        return {
            "provider": "gemini",
            "api_key": os.environ.get("GOOGLE_API_KEY", "") or os.environ.get("GEMINI_API_KEY", ""),
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
        }
    
    # Fallback: OpenRouter defaults
    return {
        "provider": "openrouter",
        "api_key": os.environ.get("OPENROUTER_API_KEY", ""),
        "base_url": os.environ.get(
            "HEMUI_BASE_URL", "https://openrouter.ai/api/v1"
        ),
    }


def get_agent(session_id: str, streaming_session_id: str = None):
    """Get or create a warm AIAgent for a session."""
    db = get_session_db()
    current_gen = get_model_generation()

    with agent_cache_lock:
        # If model generation changed, switch_model() in-place
        # (same pattern as gateway/run.py _handle_model_command)
        if session_id in agent_cache:
            cached_gen = getattr(agent_cache[session_id], '_hemui_model_gen', -1)
            if cached_gen != current_gen:
                new_model = _get_config_model() or _DEFAULT_MODEL
                old_model = getattr(agent_cache[session_id], 'model', 'unknown')

                # Switch every cached agent in-place
                for sid, cached_agent in list(agent_cache.items()):
                    try:
                        provider_id = _get_config_provider() or "openrouter"
                        provider_info = _resolve_provider_info(provider_id)
                        api_key = provider_info["api_key"]
                        base_url = provider_info["base_url"]
                        provider_name = provider_info["provider"]
                        
                        cached_agent.switch_model(
                            new_model=new_model,
                            new_provider=provider_name,
                            api_key=api_key,
                            base_url=base_url,
                        )
                        cached_agent._hemui_model_gen = current_gen
                    except Exception:
                        # If switch_model fails, evict this agent
                        del agent_cache[sid]

                # Store pending note for EVERY active session
                with _pending_model_notes_lock:
                    for sid in list(agent_cache.keys()):
                        _pending_model_notes[sid] = (
                            f"[Note: model was just switched from {old_model} to {new_model}. "
                            f"You are now {new_model}. "
                            f"Adjust your self-identification accordingly.]"
                        )

        # Create new agent if needed
        if session_id not in agent_cache:
            current_model = _get_config_model() or _DEFAULT_MODEL
            current_provider = _get_config_provider() or "openrouter"
            provider_info = _resolve_provider_info(current_provider)

            # Gap 4,5,6,7,9: Read full config from config.yaml
            profile_home = get_profile_home(_active_profile)
            extra_kwargs = build_agent_kwargs(profile_home)

            # Load ephemeral_system_prompt from config.yaml — same as
            # gateway/run.py:1107-1125 (_load_ephemeral_system_prompt)
            _user_ephemeral = ""
            try:
                import yaml as _y
                _cfg_path = profile_home / "config.yaml"
                if _cfg_path.exists():
                    with open(_cfg_path, encoding="utf-8") as _f:
                        _cfg = _y.safe_load(_f) or {}
                    _user_ephemeral = (_cfg.get("agent", {}).get("system_prompt", "") or "").strip()
            except Exception:
                pass
            # Env var overrides (same precedence as gateway)
            _user_ephemeral = os.environ.get("HERMES_EPHEMERAL_SYSTEM_PROMPT", "") or _user_ephemeral

            # Platform note — matches gateway/session.py:265-283 pattern
            # (platform-specific behavioral notes injected into context)
            _platform_note = (
                "**Platform notes:** You are running inside a desktop chat interface. "
                "You can display images and files inline by including MEDIA:<filepath> "
                "in your response. The interface renders these as visible images."
            )
            # Combine: platform note + user's configured system prompt
            _combined_ephemeral = _platform_note
            if _user_ephemeral:
                _combined_ephemeral = (_combined_ephemeral + "\n\n" + _user_ephemeral).strip()

            # Toolsets: prefer config.yaml resolution from build_agent_kwargs
            # (matches the official TUI gateway's _load_enabled_toolsets).
            # Env var override preserved for backward compat, but config.yaml
            # is now the primary source — no more hardcoded "hermes-cli" gate.
            resolved_toolsets = extra_kwargs.pop("enabled_toolsets", None)
            env_toolsets = os.environ.get("HEMUI_TOOLSETS")
            if env_toolsets:
                resolved_toolsets = [t.strip() for t in env_toolsets.split(",") if t.strip()]

            agent = _get_AIAgent()(
                model=current_model,
                api_key=provider_info["api_key"],
                base_url=provider_info["base_url"],
                provider=provider_info["provider"],
                platform="hemui",
                session_id=session_id,
                session_db=db,
                quiet_mode=True,
                enabled_toolsets=resolved_toolsets,
                ephemeral_system_prompt=_combined_ephemeral or None,
                **extra_kwargs,
            )
            agent._hemui_model_gen = current_gen
            agent_cache[session_id] = agent
            logger.debug("Created new agent for session %s", session_id)
        else:
            # Reuse cached agent (matches gateway/run.py:9800-9815)
            agent = agent_cache[session_id]
            logger.debug("Reusing cached agent for session %s", session_id)
        
        # Per-message state — callbacks change every turn and must not be
        # baked into the cached agent constructor (gateway/run.py:9850-9860)
        agent._hemui_model_gen = current_gen
        agent.session_id = session_id
        agent._last_flushed_db_idx = 0

        # ── Wire ALL core engine callbacks for this session ──
        # These match the constructor params in run_agent.py:544-554
        if streaming_session_id:
            # 1. Live token stream (run_agent.py:4798 → _fire_stream_delta)
            agent.stream_delta_callback = lambda delta, _sid=streaming_session_id: (
                push_stream_delta(_sid, delta)
            )
            # 2. Tool lifecycle (started/completed/reasoning.available)
            agent.tool_progress_callback = _make_tool_progress_callback(
                streaming_session_id
            )
            # 2a. Tool start callback (for edit snapshots + timing)
            # Matches tui_gateway/server.py:_on_tool_start (line 1020)
            agent.tool_start_callback = _make_tool_start_callback(
                streaming_session_id
            )
            # 2b. Tool complete callback (for summary + inline_diff)
            # Matches tui_gateway/server.py:_on_tool_complete (line 1038)
            agent.tool_complete_callback = _make_tool_complete_callback(
                streaming_session_id
            )
            # 3. Kawaii thinking spinner
            agent.thinking_callback = _make_thinking_callback(
                streaming_session_id
            )
            # 4. Real-time reasoning tokens (run_agent.py:4809)
            agent.reasoning_callback = _make_reasoning_callback(
                streaming_session_id
            )
            # 5. Lifecycle status (retries, compression, context pressure)
            agent.status_callback = _make_status_callback(
                streaming_session_id
            )
            # 6. Gap 8: Background review callback ("💾 Memory updated")
            agent.background_review_callback = _make_background_review_callback(
                streaming_session_id
            )

        # Gap 1: Build approval context for this session
        approval_ctx = wire_approval_for_session(
            session_id, push_stream_event
        )

        # Resolve provider info dynamically
        provider_id = _get_config_provider() or "openrouter"
        provider_info = _resolve_provider_info(provider_id)
        
        return agent, approval_ctx





def get_conversation_history(session_id: str) -> list:
    """Load conversation history from DB."""
    try:
        db = get_session_db()
        return db.get_messages_as_conversation(session_id)
    except Exception as e:
        print(f"[POOL] Failed to load history: {e}")
        return []


def cleanup_old_tasks():
    """Remove completed tasks older than 5 minutes."""
    cutoff = time.time() - 300
    with tasks_lock:
        to_remove = [
            tid for tid, t in running_tasks.items()
            if t["status"] != "running" and t.get("finished_at", 0) < cutoff
        ]
        for tid in to_remove:
            del running_tasks[tid]


def trigger_auto_title(session_id: str, message: str, response: str, history: list):
    """Generate title in background after first exchange."""
    if not response:
        return

    def _generate():
        try:
            db = get_session_db()
            user_msg_count = sum(1 for m in (history or []) if m.get("role") == "user")
            if user_msg_count > 2:
                return

            existing = db.get_session_title(session_id)
            if existing:
                return

            from agent.title_generator import generate_title
            title = generate_title(message, response)
            if not title:
                return

            db.set_session_title(session_id, title)
            print(f"[POOL] Auto-title: {title}")

            push_stream_event(session_id, {
                "type": "title_updated",
                "data": {"title": title, "session_id": session_id},
            })
        except Exception as e:
            print(f"[POOL] Auto-title failed: {e}")

    threading.Thread(target=_generate, daemon=True, name="auto-title").start()
