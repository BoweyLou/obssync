#!/usr/bin/env python3
"""
Test sync apply on just our single task to verify it works end-to-end.
"""

import sys
import os
import json
from datetime import datetime, timezone
sys.path.append(os.path.dirname(__file__))

from obs_tools.commands.sync_links_apply import main

def test_single_task_apply():
    """Test applying sync to our single task."""
    
    # Create minimal test data with just our task
    obs_uuid = "51fdfdc5-00c2-4fd3-b485-cdaf511dfd8d"
    rem_uuid = "11f49767-331d-4492-90a0-22d438218828"
    
    # Load real data
    with open(os.path.expanduser("~/.config/obsidian_tasks_index.json")) as f:
        obs_data = json.load(f)
    
    with open(os.path.expanduser("~/.config/reminders_tasks_index.json")) as f:
        rem_data = json.load(f)
    
    with open(os.path.expanduser("~/.config/sync_links.json")) as f:
        links_data = json.load(f)
    
    # Create test files with just our task
    test_obs = {
        "meta": obs_data["meta"],
        "tasks": {obs_uuid: obs_data["tasks"][obs_uuid]}
    }
    
    test_rem = {
        "meta": rem_data["meta"],
        "tasks": {rem_uuid: rem_data["tasks"][rem_uuid]}
    }
    
    # Find our link
    our_link = None
    for link in links_data["links"]:
        if link["obs_uuid"] == obs_uuid and link["rem_uuid"] == rem_uuid:
            our_link = link
            break
    
    if not our_link:
        print("❌ Could not find link for our task")
        return
    
    test_links = {
        "meta": links_data["meta"],
        "links": [our_link]
    }
    
    # Write test files
    with open("/tmp/test_obs.json", "w") as f:
        json.dump(test_obs, f, indent=2)
    
    with open("/tmp/test_rem.json", "w") as f:
        json.dump(test_rem, f, indent=2)
    
    with open("/tmp/test_links.json", "w") as f:
        json.dump(test_links, f, indent=2)
    
    print("📁 Created test files with single task")
    print(f"Obsidian task: '{test_obs['tasks'][obs_uuid]['description']}'")
    print(f"Reminders task: '{test_rem['tasks'][rem_uuid]['description']}'")
    
    # Run sync apply with verbose output on our test data
    print("\n🔄 Running sync apply...")
    
    try:
        result = main([
            "--obs", "/tmp/test_obs.json",
            "--rem", "/tmp/test_rem.json", 
            "--links", "/tmp/test_links.json",
            "--verbose"
        ])
        
        print(f"\n✅ Sync apply completed with result: {result}")
        
    except Exception as e:
        print(f"❌ Error during sync apply: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_single_task_apply()