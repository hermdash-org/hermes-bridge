"""
Server — Start the bridge HTTP server.
"""

import os
import sys
import threading
import time
import logging

import uvicorn

from .app import create_app, VERSION
from .Chat.agent_pool import get_active_profile

logger = logging.getLogger("bridge.cron")


def _start_cron_ticker():
    """Start background cron ticker thread.
    
    This runs AFTER profile initialization, so it uses the correct
    profile-specific cron paths. The file lock prevents conflicts
    if the user also has the gateway service running.
    """
    def cron_loop():
        try:
            # Import here so we get the profile-patched paths
            sys.path.insert(0, '/opt/hermes')
            from cron.scheduler import tick
            
            logger.info('Cron ticker started (profile-aware)')
            print("🔄 Cron ticker loop starting...")
            
            while True:
                try:
                    logger.debug('Checking for due jobs...')
                    executed = tick(verbose=True)  # Enable verbose for debugging
                    if executed > 0:
                        logger.info(f'Executed {executed} job(s)')
                        print(f"✅ Executed {executed} job(s)")
                    else:
                        logger.debug('No jobs due')
                except Exception as e:
                    logger.error(f'Cron tick error: {e}', exc_info=True)
                    print(f"❌ Cron tick error: {e}")
                time.sleep(60)
        except Exception as e:
            logger.error(f'Cron ticker initialization failed: {e}', exc_info=True)
            print(f"❌ Cron ticker initialization failed: {e}")
    
    try:
        ticker = threading.Thread(target=cron_loop, daemon=True, name='cron-ticker')
        ticker.start()
        logger.info('Cron ticker thread started')
    except Exception as e:
        logger.error(f'Failed to start cron ticker: {e}', exc_info=True)


def start_bridge(host: str = "0.0.0.0", port: int = 8420):
    """Start the bridge server."""
    app = create_app()

    print(f"🌉 HemUI Bridge v{VERSION} on http://{host}:{port}")
    print(f"📡 POST /chat  →  GET /chat/stream/{{sid}}  →  GET /chat/status/{{tid}}")
    print(f"🔑 API key: {'set' if os.environ.get('OPENROUTER_API_KEY') else 'MISSING'}")
    print(f"📌 Profile: {get_active_profile()}")
    
    # Start cron ticker with error handling
    try:
        print("🔄 Starting cron ticker...")
        _start_cron_ticker()
        print("✅ Cron ticker started successfully")
    except Exception as e:
        logger.error(f"Failed to start cron ticker: {e}", exc_info=True)
        print(f"⚠️  Cron ticker disabled due to error: {e}")

    uvicorn.run(app, host=host, port=port)

