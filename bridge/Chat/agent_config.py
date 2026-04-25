"""
Agent Config — Read agent configuration from config.yaml.

Extracts all runtime parameters the gateway uses (gateway/run.py:7878-7901)
that the bridge was previously missing:
  - Provider routing (only, ignore, order, sort, require_parameters, data_collection)
  - Reasoning config (extended thinking budgets)
  - Service tier
  - Fallback model
  - Max iterations
  - Request overrides

Single responsibility: config.yaml → dict of AIAgent kwargs.
"""

import logging
import os
from pathlib import Path

import yaml

logger = logging.getLogger("bridge.agent_config")


def _load_profile_config(profile_home: Path) -> dict:
    """Load config.yaml from a profile directory."""
    config_path = profile_home / "config.yaml"
    if not config_path.exists():
        return {}
    try:
        with open(config_path) as f:
            cfg = yaml.safe_load(f) or {}
        # Expand env vars if hermes_cli is available
        try:
            from hermes_cli.config import _expand_env_vars
            cfg = _expand_env_vars(cfg)
        except ImportError:
            pass
        return cfg
    except Exception as e:
        logger.warning("Failed to load config.yaml: %s", e)
        return {}


def get_provider_routing(cfg: dict) -> dict:
    """Extract provider routing from config.yaml → AIAgent kwargs.

    Maps to gateway/run.py lines 7890-7896:
      providers_allowed, providers_ignored, providers_order,
      provider_sort, provider_require_parameters, provider_data_collection
    """
    pr = cfg.get("providers", {})
    if not isinstance(pr, dict):
        return {}

    result = {}

    if pr.get("only"):
        result["providers_allowed"] = pr["only"]
    if pr.get("ignore"):
        result["providers_ignored"] = pr["ignore"]
    if pr.get("order"):
        result["providers_order"] = pr["order"]
    if pr.get("sort"):
        result["provider_sort"] = pr["sort"]
    if pr.get("require_parameters") is not None:
        result["provider_require_parameters"] = bool(pr["require_parameters"])
    if pr.get("data_collection") is not None:
        result["provider_data_collection"] = pr["data_collection"]

    return result


def get_reasoning_config(cfg: dict) -> dict | None:
    """Extract reasoning/thinking config from config.yaml.

    Maps to gateway/run.py _load_reasoning_config().
    """
    reasoning = cfg.get("reasoning", {})
    if not isinstance(reasoning, dict) or not reasoning:
        return None
    return reasoning


def get_service_tier(cfg: dict) -> str | None:
    """Extract service tier from config.yaml.

    Maps to gateway/run.py _load_service_tier().
    """
    tier = cfg.get("service_tier")
    if tier and isinstance(tier, str):
        return tier.strip() or None
    return None


def get_fallback_model(cfg: dict) -> str | None:
    """Extract fallback model from config.yaml.

    Maps to gateway/run.py self._fallback_model.
    """
    model_cfg = cfg.get("model", {})
    if isinstance(model_cfg, dict):
        fb = model_cfg.get("fallback", "")
        return fb.strip() if isinstance(fb, str) and fb.strip() else None
    return None


def get_max_iterations(cfg: dict) -> int:
    """Extract max_iterations from config or env.

    Maps to gateway/run.py line 5344:
      max_iterations = int(os.getenv("HERMES_MAX_ITERATIONS", "90"))
    """
    # Env var takes priority (set by env_setup.py from config.yaml)
    env_val = os.environ.get("HERMES_MAX_ITERATIONS")
    if env_val:
        try:
            return int(env_val)
        except ValueError:
            pass

    # Direct config.yaml fallback
    agent_cfg = cfg.get("agent", {})
    if isinstance(agent_cfg, dict):
        max_turns = agent_cfg.get("max_turns")
        if max_turns is not None:
            try:
                return int(max_turns)
            except (ValueError, TypeError):
                pass

    return 90  # hermes default


def get_request_overrides(cfg: dict) -> dict | None:
    """Extract request-level overrides (temperature, top_p, etc.)."""
    overrides = cfg.get("request_overrides", {})
    if isinstance(overrides, dict) and overrides:
        return overrides
    return None


def get_enabled_toolsets(cfg: dict) -> list[str] | None:
    """Resolve enabled toolsets from config.yaml.

    Uses the SAME resolution function as the official TUI gateway
    (tui_gateway/server.py:633 _load_enabled_toolsets) and gateway/run.py:6548.

    This ensures every toolset the upstream project adds — including
    MCP servers, new tool categories, and platform-specific tools —
    is automatically available through the bridge without any code change.

    Falls back to None (= all tools enabled) if the import fails,
    which is the most open/permissive default.
    """
    try:
        from hermes_cli.config import load_config
        from hermes_cli.tools_config import _get_platform_tools

        # Use the config we already loaded (profile-aware) merged with
        # whatever load_config() returns for global defaults.
        # "cli" platform key matches the TUI gateway's behaviour.
        # include_default_mcp_servers=True ensures MCP tools are available
        # at runtime (see tui_gateway/server.py PR #3252 comment).
        effective_cfg = cfg or load_config()
        try:
            # Current hermes-agent (with MCP server support)
            enabled = sorted(
                _get_platform_tools(effective_cfg, "cli", include_default_mcp_servers=True)
            )
        except TypeError:
            # Older hermes-agent versions without include_default_mcp_servers param
            enabled = sorted(
                _get_platform_tools(effective_cfg, "cli")
            )
        return enabled or None
    except ImportError:
        # hermes_cli.tools_config not available (very old version or
        # running outside hermes venv) — return None = all tools enabled.
        return None
    except Exception:
        # Any other error — return None (most open/permissive default).
        return None


def build_agent_kwargs(profile_home: Path) -> dict:
    """Build the full dict of extra AIAgent constructor kwargs from config.

    Returns a dict that can be **unpacked into the AIAgent() call.
    """
    cfg = _load_profile_config(profile_home)
    kwargs = {}

    # Gap 4: Provider routing
    kwargs.update(get_provider_routing(cfg))

    # Gap 5: Reasoning config
    reasoning = get_reasoning_config(cfg)
    if reasoning:
        kwargs["reasoning_config"] = reasoning

    # Gap 5: Service tier
    tier = get_service_tier(cfg)
    if tier:
        kwargs["service_tier"] = tier

    # Gap 6: Fallback model
    fallback = get_fallback_model(cfg)
    if fallback:
        kwargs["fallback_model"] = fallback

    # Gap 7: Max iterations
    kwargs["max_iterations"] = get_max_iterations(cfg)

    # Gap 9: Request overrides
    overrides = get_request_overrides(cfg)
    if overrides:
        kwargs["request_overrides"] = overrides

    # Toolsets: read from config.yaml (same as official TUI/gateway)
    toolsets = get_enabled_toolsets(cfg)
    if toolsets is not None:
        kwargs["enabled_toolsets"] = toolsets

    return kwargs
