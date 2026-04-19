"""
Server — Start the bridge HTTP server.
"""

import os

import uvicorn

from .app import create_app, VERSION
from .Chat.agent_pool import get_active_profile


def start_bridge(host: str = "0.0.0.0", port: int = 8420):
    """Start the bridge server."""
    app = create_app()

    print(f"🌉 HemUI Bridge v{VERSION} on http://{host}:{port}")
    print(f"📡 POST /chat  →  GET /chat/stream/{{sid}}  →  GET /chat/status/{{tid}}")
    print(f"🔑 API key: {'set' if os.environ.get('OPENROUTER_API_KEY') else 'MISSING'}")
    print(f"📌 Profile: {get_active_profile()}")

    uvicorn.run(app, host=host, port=port)

