"""
HemUI Bridge — Entry point.

The PyInstaller binary bundles hermes-agent and the bridge together.
runtime.py is the actual entry point; this module exists for dev-mode
(python -m bridge).
"""

from bridge.server import start_bridge

if __name__ == "__main__":
    start_bridge()
