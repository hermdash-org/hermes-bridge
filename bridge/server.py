"""
Server — Start the bridge HTTP server.

Single responsibility: configure and run uvicorn.
Supervisor handles zombie cleanup, PID files, and signal handling.
"""

import os

import uvicorn

from .app import create_app, VERSION
from .Chat.agent_pool import get_active_profile


def start_bridge(host: str = "127.0.0.1", port: int = 8420):
    """Start the bridge server.

    Before starting uvicorn:
      1. Kills any zombie bridge from a previous run
      2. Frees the port if something is squatting on it
      3. Writes PID file for future zombie detection
      4. Installs SIGTERM/SIGINT handlers for clean shutdown
    """
    # ── Supervisor: zombie cleanup + port guard + PID + signals ──
    from .supervisor import setup as supervisor_setup
    supervisor_setup(port)

    app = create_app()

    print(f"🌉 HemUI Bridge v{VERSION} on http://{host}:{port}")
    print(f"📡 POST /chat  →  GET /chat/stream/{{sid}}  →  GET /chat/status/{{tid}}")
    print(f"🔑 API key: {'set' if os.environ.get('OPENROUTER_API_KEY') else 'MISSING'}")
    print(f"📌 Profile: {get_active_profile()}")

    uvicorn.run(app, host=host, port=port)

