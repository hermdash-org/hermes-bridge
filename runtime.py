#!/usr/bin/env python3
"""
Hermes Runtime - Standalone executable entry point
This is the main file that PyInstaller will bundle into runtime.exe
"""

import sys
import os

# Ensure bridge module is importable
sys.path.insert(0, os.path.dirname(__file__))

from auto_update import check_and_update
from bridge.server import start_bridge

if __name__ == "__main__":
    # Check for updates on startup
    check_and_update()
    
    # Start the bridge server
    # This will be accessible at http://localhost:8521
    start_bridge(host="127.0.0.1", port=8521)
