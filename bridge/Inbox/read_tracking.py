"""
Read Tracking — Track which inbox items have been read per profile.

Stores read status in ~/.hermes/inbox_read.json (profile-scoped).
Simple JSON file: {"item_id": true, ...}
"""

import json
from pathlib import Path
from typing import Set

from ..Chat.agent_pool import get_profile_home


def _get_read_file() -> Path:
    """Get the read tracking file for the active profile."""
    profile_home = get_profile_home()
    return profile_home / "inbox_read.json"


def get_read_items() -> Set[str]:
    """Get set of read item IDs for active profile."""
    read_file = _get_read_file()
    
    if not read_file.exists():
        return set()
    
    try:
        with open(read_file, 'r') as f:
            data = json.load(f)
            return set(data.keys())
    except Exception:
        return set()


def mark_as_read(item_id: str) -> bool:
    """Mark an item as read. Returns True if successful."""
    read_file = _get_read_file()
    read_file.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # Load existing
        data = {}
        if read_file.exists():
            with open(read_file, 'r') as f:
                data = json.load(f)
        
        # Add item
        data[item_id] = True
        
        # Save
        with open(read_file, 'w') as f:
            json.dump(data, f)
        
        return True
    except Exception:
        return False


def mark_as_unread(item_id: str) -> bool:
    """Mark an item as unread. Returns True if successful."""
    read_file = _get_read_file()
    
    if not read_file.exists():
        return True
    
    try:
        # Load existing
        with open(read_file, 'r') as f:
            data = json.load(f)
        
        # Remove item
        data.pop(item_id, None)
        
        # Save
        with open(read_file, 'w') as f:
            json.dump(data, f)
        
        return True
    except Exception:
        return False


def get_unread_count(all_item_ids: list) -> int:
    """Get count of unread items from a list of item IDs."""
    read_items = get_read_items()
    return sum(1 for item_id in all_item_ids if item_id not in read_items)
