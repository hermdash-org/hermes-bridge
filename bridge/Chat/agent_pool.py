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

    # Load profile-specific .env (fall back to root .env)
    env_path = new_home / ".env"
    if env_path.exists():
        load_dotenv(str(env_path), override=True)
    elif (_hermes_root / ".env").exists():
        load_dotenv(str(_hermes_root / ".env"), override=True)

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
    """Remove a subscriber and clean up buffer if no subscribers left."""
    with stream_sub_lock:
        subs = stream_subscribers.get(session_id, [])
        if sub in subs:
            subs.remove(sub)
        remaining = len(subs)

    # Clean up buffer if no more subscribers
    if remaining == 0:
        with _stream_buffer_lock:
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


# ── Callback Factories ──────────────────────────────────────────────

def _make_tool_progress_callback(session_id: str):
    # Import registry once at callback creation time
    try:
        from tools.registry import registry as _tool_registry
    except ImportError:
        _tool_registry = None

    def callback(event_type, tool_name=None, preview=None, args=None, **kwargs):
        # Enrich with emoji + toolset from the core engine registry
        emoji = "⚡"
        toolset = "unknown"
        if _tool_registry and tool_name:
            emoji = _tool_registry.get_emoji(tool_name, default="⚡")
            toolset = _tool_registry.get_toolset_for_tool(tool_name) or "unknown"

        if event_type == "tool.started":
            push_stream_event(session_id, {
                "type": "tool_started",
                "data": {
                    "tool": tool_name,
                    "emoji": emoji,
                    "toolset": toolset,
                    "preview": preview,
                    "args": args,
                    "ts": time.time(),
                },
            })
        elif event_type == "tool.completed":
            push_stream_event(session_id, {
                "type": "tool_completed",
                "data": {
                    "tool": tool_name,
                    "emoji": emoji,
                    "toolset": toolset,
                    "preview": preview,
                    "duration": round(kwargs.get("duration", 0), 3),
                    "is_error": kwargs.get("is_error", False),
                    "ts": time.time(),
                },
            })
        elif event_type == "reasoning.available":
            push_stream_event(session_id, {
                "type": "reasoning",
                "data": {"text": preview or "", "ts": time.time()},
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

def _get_config_model() -> str:
    """Read model.default from the active profile's config.yaml.

    Uses the same profile resolution as hermes_cli:
      - "default" → ~/.hermes/config.yaml
      - named     → ~/.hermes/profiles/<name>/config.yaml
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
                return model_cfg
            if isinstance(model_cfg, dict):
                return model_cfg.get("default") or model_cfg.get("model") or ""
    except Exception:
        pass
    return os.environ.get("HEMUI_MODEL", "")


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
                new_model = _get_config_model() or "google/gemini-2.5-flash:free"
                old_model = getattr(agent_cache[session_id], 'model', 'unknown')

                # Switch every cached agent in-place
                for sid, cached_agent in list(agent_cache.items()):
                    try:
                        cached_agent.switch_model(
                            new_model=new_model,
                            new_provider=os.environ.get("HEMUI_PROVIDER", "openrouter"),
                            api_key=os.environ.get("OPENROUTER_API_KEY", ""),
                            base_url=os.environ.get("HEMUI_BASE_URL", "https://openrouter.ai/api/v1"),
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
            current_model = _get_config_model() or "google/gemini-2.5-flash:free"

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
                api_key=os.environ.get("OPENROUTER_API_KEY", ""),
                base_url=os.environ.get("HEMUI_BASE_URL", "https://openrouter.ai/api/v1"),
                provider=os.environ.get("HEMUI_PROVIDER", "openrouter"),
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

        agent = agent_cache[session_id]
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
