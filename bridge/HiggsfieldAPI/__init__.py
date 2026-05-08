"""
Higgsfield API — Direct Python SDK integration (no CLI required)

This module provides a clean wrapper around the official higgsfield-client SDK.
It handles authentication, job submission, polling, and result retrieval.

For non-technical users: Everything works automatically after OAuth.
No CLI installation needed. No manual setup. Just works.
"""

from .client import HiggsfieldAPI
from .auth import get_credentials, has_credentials

__all__ = ["HiggsfieldAPI", "get_credentials", "has_credentials"]
