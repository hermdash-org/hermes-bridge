"""
OpenRouterOAuth — OAuth PKCE flow for OpenRouter API key provisioning.

Lets non-technical users connect their OpenRouter account
with a single browser click. No manual .env editing required.

The key exchange follows OpenRouter's documented PKCE flow:
  1. Frontend generates code_verifier + code_challenge
  2. User authorizes HemUI in browser → gets redirect with `code`
  3. This router exchanges code → API key via OpenRouter API
  4. Key is written to ~/.hermes/.env and set in os.environ

Source of truth for env loading: hermes_cli/env_loader.py
Source of truth for key usage:   agent/credential_pool.py → _seed_from_env()
Source of truth for paths:       hermes_constants.py → get_hermes_home()

Routes:
  GET  /openrouter/status     — is a key configured + credits remaining
  POST /openrouter/exchange    — exchange OAuth code for API key
  POST /openrouter/disconnect  — remove stored key
"""

import os
import re
import logging
from pathlib import Path

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/openrouter", tags=["openrouter"])

# ── Constants (mirroring hermes_constants.py) ──────────────────────
# We import from hermes_constants when available (bridge runs inside
# hermes venv), with a safe fallback.

try:
    from hermes_constants import get_hermes_home, OPENROUTER_BASE_URL
except ImportError:
    OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

    def get_hermes_home() -> Path:
        return Path(os.getenv("HERMES_HOME", Path.home() / ".hermes"))


OPENROUTER_AUTH_KEYS_URL = f"{OPENROUTER_BASE_URL}/auth/keys"
OPENROUTER_CREDITS_URL = f"{OPENROUTER_BASE_URL}/credits"

ENV_KEY_NAME = "OPENROUTER_API_KEY"


# ── .env helpers ───────────────────────────────────────────────────
# Mirrors the env_loader.py pattern from core: the canonical location
# is get_hermes_home() / ".env". We read/write that file directly
# using python-dotenv's set_key when available, else raw string ops.


def _get_env_path() -> Path:
    """Canonical .env path — matches hermes_cli/env_loader.py line 34."""
    return get_hermes_home() / ".env"


def _read_env_key() -> str:
    """Read OPENROUTER_API_KEY from the .env file (not os.environ).

    Returns empty string if not found.
    """
    env_path = _get_env_path()
    if not env_path.exists():
        return ""

    try:
        content = env_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = env_path.read_text(encoding="latin-1")

    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        if key.strip() == ENV_KEY_NAME:
            # Strip surrounding quotes if present
            val = value.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                val = val[1:-1]
            return val
    return ""


def _write_env_key(api_key: str) -> None:
    """Write OPENROUTER_API_KEY to ~/.hermes/.env.

    If the key already exists in the file, replace it in-place.
    If not, append it. Preserves all other content.
    """
    env_path = _get_env_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)

    if env_path.exists():
        try:
            content = env_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = env_path.read_text(encoding="latin-1")
    else:
        content = ""

    new_line = f'{ENV_KEY_NAME}="{api_key}"'
    pattern = re.compile(r"^" + re.escape(ENV_KEY_NAME) + r"\s*=.*$", re.MULTILINE)

    if pattern.search(content):
        content = pattern.sub(new_line, content)
    else:
        if content and not content.endswith("\n"):
            content += "\n"
        content += new_line + "\n"

    env_path.write_text(content, encoding="utf-8")


def _remove_env_key() -> None:
    """Remove OPENROUTER_API_KEY from ~/.hermes/.env."""
    env_path = _get_env_path()
    if not env_path.exists():
        return

    try:
        content = env_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = env_path.read_text(encoding="latin-1")

    pattern = re.compile(
        r"^" + re.escape(ENV_KEY_NAME) + r"\s*=.*\n?", re.MULTILINE
    )
    new_content = pattern.sub("", content)
    env_path.write_text(new_content, encoding="utf-8")


def _sync_env_to_process(api_key: str | None) -> None:
    """Update os.environ so the running bridge picks up the key.

    This matches how credential_pool.py → _seed_from_env() reads
    the key: os.getenv("OPENROUTER_API_KEY").
    """
    if api_key:
        os.environ[ENV_KEY_NAME] = api_key
    elif ENV_KEY_NAME in os.environ:
        del os.environ[ENV_KEY_NAME]


# ── Routes ─────────────────────────────────────────────────────────


@router.get("/status")
async def openrouter_status():
    """Check if an OpenRouter API key is configured and fetch credits.

    Returns:
      - connected: bool
      - has_key: bool
      - credits: { total_credits, total_usage, remaining } or null
      - key_preview: last 4 chars for user verification
    """
    api_key = os.environ.get(ENV_KEY_NAME, "") or _read_env_key()

    if not api_key:
        return JSONResponse({
            "connected": False,
            "has_key": False,
            "credits": None,
            "key_preview": None,
        })

    # Fetch credits to verify key is valid + show balance
    credits_data = None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                OPENROUTER_CREDITS_URL,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if resp.status_code == 200:
                data = resp.json().get("data", resp.json())
                credits_data = {
                    "total_credits": data.get("total_credits", 0),
                    "total_usage": data.get("total_usage", 0),
                    "remaining": round(
                        data.get("total_credits", 0) - data.get("total_usage", 0),
                        4,
                    ),
                }
            elif resp.status_code in (401, 403):
                # Key is invalid/revoked
                return JSONResponse({
                    "connected": False,
                    "has_key": True,
                    "credits": None,
                    "key_preview": api_key[-4:],
                    "error": "API key is invalid or revoked",
                })
    except Exception as exc:
        logger.warning("Failed to fetch OpenRouter credits: %s", exc)

    return JSONResponse({
        "connected": True,
        "has_key": True,
        "credits": credits_data,
        "key_preview": api_key[-4:],
    })


@router.post("/exchange")
async def openrouter_exchange(request: dict):
    """Exchange an OAuth PKCE authorization code for an API key.

    Follows OpenRouter's documented flow:
      POST https://openrouter.ai/api/v1/auth/keys
      { code, code_verifier, code_challenge_method }

    On success, writes the key to ~/.hermes/.env and sets os.environ.
    """
    code = request.get("code", "").strip()
    code_verifier = request.get("code_verifier", "").strip()

    if not code:
        return JSONResponse(
            {"success": False, "error": "Missing authorization code"},
            status_code=400,
        )

    if not code_verifier:
        return JSONResponse(
            {"success": False, "error": "Missing code_verifier for PKCE"},
            status_code=400,
        )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                OPENROUTER_AUTH_KEYS_URL,
                json={
                    "code": code,
                    "code_verifier": code_verifier,
                    "code_challenge_method": "S256",
                },
            )

            if resp.status_code != 200:
                error_body = resp.json() if resp.headers.get(
                    "content-type", ""
                ).startswith("application/json") else {}
                return JSONResponse(
                    {
                        "success": False,
                        "error": error_body.get(
                            "error",
                            f"OpenRouter returned {resp.status_code}",
                        ),
                    },
                    status_code=resp.status_code,
                )

            data = resp.json()
            api_key = data.get("key", "")

            if not api_key:
                return JSONResponse(
                    {"success": False, "error": "No key returned from OpenRouter"},
                    status_code=502,
                )

    except httpx.TimeoutException:
        return JSONResponse(
            {"success": False, "error": "OpenRouter request timed out"},
            status_code=504,
        )
    except Exception as exc:
        logger.error("OpenRouter key exchange failed: %s", exc)
        return JSONResponse(
            {"success": False, "error": str(exc)},
            status_code=500,
        )

    # Persist to .env and os.environ
    _write_env_key(api_key)
    _sync_env_to_process(api_key)

    logger.info("OpenRouter API key provisioned via OAuth (key ending ...%s)", api_key[-4:])

    return JSONResponse({
        "success": True,
        "key_preview": api_key[-4:],
    })


@router.post("/disconnect")
async def openrouter_disconnect():
    """Remove the stored OpenRouter API key.

    Clears from:
      1. os.environ (so running agents stop using it)
      2. ~/.hermes/.env (so it doesn't reload on restart)
    """
    _remove_env_key()
    _sync_env_to_process(None)

    logger.info("OpenRouter API key disconnected")

    return JSONResponse({"success": True})
