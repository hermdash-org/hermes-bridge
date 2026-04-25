"""
Environment Setup — Bridge config.yaml → env var bridging.

Replicates the EXACT setup from:
  gateway/run.py  lines 89-239  (config.yaml → TERMINAL_* env vars)
  cli.py          lines 390-455 (terminal config → env mappings)

Without this, the agent's file tools and terminal tool have no idea what
working directory to use, causing files to be written to wrong locations
or the terminal to start in the bridge's own directory.

This module is imported ONCE at bridge startup, before any agent is created.
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("bridge.env_setup")


def setup_agent_environment() -> None:
    """Bridge config.yaml values into environment variables.

    This is the EXACT equivalent of gateway/run.py lines 89-239.
    Must be called before any AIAgent is created.
    """
    # ── Load .env from HERMES_HOME/.env ──────────────────────────────
    # Capture HERMES_HOME ONCE — before any profile switching can corrupt it
    from dotenv import load_dotenv
    hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    logger.info("HERMES_HOME resolved to: %s", hermes_home)
    env_path = hermes_home / ".env"
    if env_path.exists():
        load_dotenv(str(env_path), override=False)

    # ── Quiet mode (gateway/run.py:228) ─────────────────────────────
    os.environ.setdefault("HERMES_QUIET", "1")

    # ── Load config.yaml (gateway/run.py:91-96) ─────────────────────
    config_path = hermes_home / "config.yaml"
    cfg = {}
    if config_path.exists():
        try:
            import yaml
            with open(config_path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}

            # Expand ${ENV_VAR} references (gateway/run.py:98-99)
            try:
                from hermes_cli.config import _expand_env_vars
                cfg = _expand_env_vars(cfg)
            except ImportError:
                pass

            # Top-level simple values — fallback only (gateway/run.py:101-103)
            for key, val in cfg.items():
                if isinstance(val, (str, int, float, bool)) and key not in os.environ:
                    os.environ[key] = str(val)
        except Exception as e:
            logger.debug("Could not load config.yaml: %s", e)

    # ── Terminal config → TERMINAL_* env vars (gateway/run.py:106-136) ──
    terminal_cfg = cfg.get("terminal", {})
    if terminal_cfg and isinstance(terminal_cfg, dict):
        terminal_env_map = {
            "backend": "TERMINAL_ENV",
            "env_type": "TERMINAL_ENV",
            "cwd": "TERMINAL_CWD",
            "timeout": "TERMINAL_TIMEOUT",
            "lifetime_seconds": "TERMINAL_LIFETIME_SECONDS",
            "docker_image": "TERMINAL_DOCKER_IMAGE",
            "docker_forward_env": "TERMINAL_DOCKER_FORWARD_ENV",
            "singularity_image": "TERMINAL_SINGULARITY_IMAGE",
            "modal_image": "TERMINAL_MODAL_IMAGE",
            "daytona_image": "TERMINAL_DAYTONA_IMAGE",
            "ssh_host": "TERMINAL_SSH_HOST",
            "ssh_user": "TERMINAL_SSH_USER",
            "ssh_port": "TERMINAL_SSH_PORT",
            "ssh_key": "TERMINAL_SSH_KEY",
            "container_cpu": "TERMINAL_CONTAINER_CPU",
            "container_memory": "TERMINAL_CONTAINER_MEMORY",
            "container_disk": "TERMINAL_CONTAINER_DISK",
            "container_persistent": "TERMINAL_CONTAINER_PERSISTENT",
            "docker_volumes": "TERMINAL_DOCKER_VOLUMES",
            "sandbox_dir": "TERMINAL_SANDBOX_DIR",
            "persistent_shell": "TERMINAL_PERSISTENT_SHELL",
        }
        for cfg_key, env_var in terminal_env_map.items():
            if cfg_key in terminal_cfg:
                val = terminal_cfg[cfg_key]
                if isinstance(val, list):
                    os.environ[env_var] = json.dumps(val)
                else:
                    os.environ[env_var] = str(val)

    # ── TERMINAL_CWD fallback (gateway/run.py:236-239) ──────────────
    # Critical: if no CWD was set from config.yaml, default to ~
    # NOT the bridge's own directory (hemui-nextjs/)
    configured_cwd = os.environ.get("TERMINAL_CWD", "")
    if not configured_cwd or configured_cwd in (".", "auto", "cwd"):
        os.environ["TERMINAL_CWD"] = str(Path.home())
        logger.info("TERMINAL_CWD set to %s", os.environ["TERMINAL_CWD"])

    # ── Auxiliary model overrides (gateway/run.py:141-178) ──────────
    auxiliary_cfg = cfg.get("auxiliary", {})
    if auxiliary_cfg and isinstance(auxiliary_cfg, dict):
        aux_task_env = {
            "vision": {
                "provider": "AUXILIARY_VISION_PROVIDER",
                "model": "AUXILIARY_VISION_MODEL",
                "base_url": "AUXILIARY_VISION_BASE_URL",
                "api_key": "AUXILIARY_VISION_API_KEY",
            },
            "web_extract": {
                "provider": "AUXILIARY_WEB_EXTRACT_PROVIDER",
                "model": "AUXILIARY_WEB_EXTRACT_MODEL",
                "base_url": "AUXILIARY_WEB_EXTRACT_BASE_URL",
                "api_key": "AUXILIARY_WEB_EXTRACT_API_KEY",
            },
            "approval": {
                "provider": "AUXILIARY_APPROVAL_PROVIDER",
                "model": "AUXILIARY_APPROVAL_MODEL",
                "base_url": "AUXILIARY_APPROVAL_BASE_URL",
                "api_key": "AUXILIARY_APPROVAL_API_KEY",
            },
        }
        for task_key, env_map in aux_task_env.items():
            task_cfg = auxiliary_cfg.get(task_key, {})
            if not isinstance(task_cfg, dict):
                continue
            prov = str(task_cfg.get("provider", "")).strip()
            model = str(task_cfg.get("model", "")).strip()
            base_url = str(task_cfg.get("base_url", "")).strip()
            api_key = str(task_cfg.get("api_key", "")).strip()
            if prov and prov != "auto":
                os.environ[env_map["provider"]] = prov
            if model:
                os.environ[env_map["model"]] = model
            if base_url:
                os.environ[env_map["base_url"]] = base_url
            if api_key:
                os.environ[env_map["api_key"]] = api_key

    # ── Agent config (gateway/run.py:179-192) ───────────────────────
    agent_cfg = cfg.get("agent", {})
    if agent_cfg and isinstance(agent_cfg, dict):
        if "max_turns" in agent_cfg:
            os.environ["HERMES_MAX_ITERATIONS"] = str(agent_cfg["max_turns"])

    # ── Security settings (gateway/run.py:202-207) ──────────────────
    security_cfg = cfg.get("security", {})
    if isinstance(security_cfg, dict):
        redact = security_cfg.get("redact_secrets")
        if redact is not None:
            os.environ["HERMES_REDACT_SECRETS"] = str(redact).lower()

    # ── Timezone (gateway/run.py:199-201) ───────────────────────────
    tz_cfg = cfg.get("timezone", "")
    if tz_cfg and isinstance(tz_cfg, str) and "HERMES_TIMEZONE" not in os.environ:
        os.environ["HERMES_TIMEZONE"] = tz_cfg.strip()

    # ── Toolsets ────────────────────────────────────────────────────
    # The official hermes-agent config schema is:
    #   platform_toolsets:
    #     cli: [hermes-cli, web, ...]
    # We also support the legacy flat key for backward compat:
    #   toolsets: [hermes-cli, web]
    # The authoritative resolver lives in agent_config.get_enabled_toolsets()
    # which calls hermes_cli.tools_config._get_platform_tools() directly.
    # This env var is only a fallback hint — the resolver is the source of truth.
    if "HEMUI_TOOLSETS" not in os.environ:
        # Try official schema first: platform_toolsets.cli
        pt = cfg.get("platform_toolsets")
        if isinstance(pt, dict):
            cli_toolsets = pt.get("cli")
            if isinstance(cli_toolsets, list) and cli_toolsets:
                os.environ["HEMUI_TOOLSETS"] = ",".join(str(t) for t in cli_toolsets)
        # Fallback: legacy flat toolsets key
        if "HEMUI_TOOLSETS" not in os.environ:
            toolsets = cfg.get("toolsets")
            if isinstance(toolsets, list) and toolsets:
                os.environ["HEMUI_TOOLSETS"] = ",".join(str(t) for t in toolsets)

    logger.info(
        "Agent environment configured: TERMINAL_CWD=%s, TERMINAL_ENV=%s, TOOLSETS=%s",
        os.environ.get("TERMINAL_CWD", "(not set)"),
        os.environ.get("TERMINAL_ENV", "local"),
        os.environ.get("HEMUI_TOOLSETS", "(auto-resolved)")
    )
