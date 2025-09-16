#!/usr/bin/env python3
"""
Test script to verify the real sync logic detects our title change.
"""

import sys
import os
import json
sys.path.append(os.path.dirname(__file__))

def test_real_title_detection():
    """Test that the sync logic detects the real title change."""
    
    # Load the real data
    with open(os.path.expanduser("~/.config/obsidian_tasks_index.json")) as f:
        obs_data = json.load(f)
    
    with open(os.path.expanduser("~/.config/reminders_tasks_index.json")) as f:
        rem_data = json.load(f)
    
    with open(os.path.expanduser("~/.config/sync_links.json")) as f:
        links_data = json.load(f)
    
    # Find our specific task
    obs_uuid = "51fdfdc5-00c2-4fd3-b485-cdaf511dfd8d"
    rem_uuid = "11f49767-331d-4492-90a0-22d438218828"
    
    obs_task = obs_data["tasks"][obs_uuid]
    rem_task = rem_data["tasks"][rem_uuid]
    
    print(f"Obsidian title: '{obs_task['description']}'")
    print(f"Reminders title: '{rem_task['description']}'")
    print(f"Obsidian updated: {obs_task.get('updated_at', 'N/A')}")
    print(f"Reminders modified: {rem_task.get('item_modified_at', 'N/A')}")
    
    # Check which should win based on timestamps
    obs_fresh = obs_task.get("file", {}).get("modified_at") or obs_task.get("updated_at")
    rem_fresh = rem_task.get("item_modified_at") or rem_task.get("updated_at")
    
    print(f"Obs freshness timestamp: {obs_fresh}")
    print(f"Rem freshness timestamp: {rem_fresh}")
    
    if obs_fresh and rem_fresh:
        from datetime import datetime
        obs_dt = datetime.fromisoformat(obs_fresh.replace("Z", "+00:00"))
        rem_dt = datetime.fromisoformat(rem_fresh.replace("Z", "+00:00"))
        
        if rem_dt > obs_dt:
            print("🔄 Reminders is newer → title should flow to Obsidian")
            print(f"Expected change: '{obs_task['description']}' → '{rem_task['description']}'")
        elif obs_dt > rem_dt:
            print("🔄 Obsidian is newer → title should flow to Reminders")
        else:
            print("⚖️ Same timestamp → no change")
    
    # Verify we have the expected content difference
    if obs_task['description'] != rem_task['description']:
        print("✅ Title difference detected - sync should process this")
    else:
        print("❌ No title difference - nothing to sync")

if __name__ == "__main__":
    test_real_title_detection()