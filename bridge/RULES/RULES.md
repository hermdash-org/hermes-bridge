# Bridge Development Rules

## Rule #1: Follow the Core Architecture

**The core `hermes-agent` codebase (`/hermes-agent/`) has already solved every problem.**

Before implementing ANY feature in the bridge:

1. **Find the equivalent in core first.** Check `gateway/run.py`, `run_agent.py`, `hermes_cli/` — the answer is already there.
2. **Mirror the pattern exactly.** Don't reinvent. Don't guess. Copy the approach.
3. **Never hardcode paths.** Use `hermes_constants.get_hermes_home()` and profile-aware resolution from `hermes_cli/profiles.py`.

### Key Reference Files

| Feature | Core File | What to Look For |
|---------|-----------|-----------------|
| Model switching | `gateway/run.py` → `_handle_model_command()` | `switch_model()` in-place + `_pending_model_notes` |
| Agent creation | `gateway/run.py` → `_get_or_create_agent()` | How agents are cached and configured |
| Config read/write | `hermes_cli/config.py` | `get_config_path()`, `set_config_value()` |
| Profile resolution | `hermes_cli/profiles.py` | `get_profile_dir()`, `get_active_profile()` |
| Session management | `gateway/run.py` → `SessionStore` | How sessions are created, reset, managed |
| Path resolution | `hermes_constants.py` | `get_hermes_home()` — never hardcode `~/.hermes` |

### Lessons Learned

- **Model switch note:** When switching models mid-session, the new model reads conversation history and parrots the OLD model's identity. The core solves this by prepending `"[Note: model was just switched from X to Y. Adjust your self-identification accordingly.]"` to the next user message. Without this note, the model will always identify as the previous model.

- **`switch_model()` over cache eviction:** The core uses `AIAgent.switch_model()` to swap the client in-place. Don't destroy and recreate agents — switch them.

- **Config is the single source of truth:** `~/.hermes/config.yaml` (per-profile) is where model configuration lives. Not env vars. Not module-level globals. The bridge reads from config, the bridge writes to config.

## Rule #2: No Spaghetti

- No hardcoded paths (`Path.home() / ".hermes"` → use helper functions)
- No env var dependencies for model selection (read from `config.yaml`)
- No `try/except: pass` silencing real errors
- No `.pyc` files in git (`.gitignore` covers this)

## Rule #3: Check Before You Build

If you're about to write more than 20 lines of new logic, **stop and grep the core first.** The pattern already exists.
