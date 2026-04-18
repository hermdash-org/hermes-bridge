"""
HemUI Bridge — Entry point.

Docker handles everything: hermes is installed, Python is there,
paths are set, service restarts on crash. This file is now dead simple.
"""

from bridge.server import start_bridge

if __name__ == "__main__":
    start_bridge()
