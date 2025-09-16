#!/usr/bin/env python3
"""
Debug script for analyzing specific task sync issue.

This script investigates the SheepShaver task sync problem where:
- Obsidian task UUID: c84d5c8a-4b71-4135-b520-3c106b484eb1 (actual)
- Sync link obs_uuid: t-e2eaba4c2b7c (block_id, not UUID!)
- Apple Reminder UUID: 0bcc4a31-63eb-4d4c-90ec-84ae4fbb6f5d
- Status: Obsidian=done, Reminders=todo
"""

import json
import os
from datetime import datetime
from typing import Dict, Optional

# Import the main sync logic
from obs_tools.commands.sync_links_apply import load_json

def debug_task_sync():
    """Debug the specific task sync issue."""
    
    print("=== DEBUGGING SHEEPSHAVER TASK SYNC ISSUE ===\n")
    
    # Load data files
    try:
        obs_path = os.path.expanduser("~/.config/obsidian_tasks_index.json") 
        rem_path = os.path.expanduser("~/.config/reminders_tasks_index.json")
        links_path = os.path.expanduser("~/.config/sync_links.json")
        
        obs = load_json(obs_path)
        rem = load_json(rem_path)
        links = load_json(links_path)
        
        obs_tasks: Dict[str, dict] = obs.get("tasks", {}) or {}
        rem_tasks: Dict[str, dict] = rem.get("tasks", {}) or {}
        link_list = links.get("links", []) or []
        
        print(f"Loaded {len(obs_tasks)} Obsidian tasks, {len(rem_tasks)} Reminders, {len(link_list)} links\n")
        
    except Exception as e:
        print(f"Error loading data: {e}")
        return
    
    # Find the specific task by UUIDs and block_id
    target_obs_uuid = "c84d5c8a-4b71-4135-b520-3c106b484eb1"
    target_rem_uuid = "0bcc4a31-63eb-4d4c-90ec-84ae4fbb6f5d" 
    target_block_id = "t-e2eaba4c2b7c"
    
    print("1. OBSIDIAN TASK ANALYSIS:")
    print("=" * 40)
    
    obs_task = obs_tasks.get(target_obs_uuid)
    if obs_task:
        print(f"✓ Found Obsidian task by UUID: {target_obs_uuid}")
        print(f"  - Status: {obs_task.get('status')}")
        print(f"  - Block ID: {obs_task.get('block_id')}")
        print(f"  - Description: {obs_task.get('description')}")
        print(f"  - Updated at: {obs_task.get('updated_at')}")
        print(f"  - File modified: {obs_task.get('file', {}).get('modified_at')}")
        print(f"  - Raw: {obs_task.get('raw')}")
    else:
        print(f"✗ Obsidian task not found by UUID: {target_obs_uuid}")
    
    # Check if there's a task by block_id in source_key
    obs_by_block = None
    for uuid, task in obs_tasks.items():
        if task.get('block_id') == target_block_id:
            obs_by_block = task
            print(f"✓ Found Obsidian task by block_id: {target_block_id} -> UUID: {uuid}")
            break
    
    if not obs_by_block and obs_task:
        obs_by_block = obs_task
    
    print(f"\n2. APPLE REMINDER ANALYSIS:")
    print("=" * 40)
    
    rem_task = rem_tasks.get(target_rem_uuid)
    if rem_task:
        print(f"✓ Found Apple Reminder by UUID: {target_rem_uuid}")
        print(f"  - Status: {rem_task.get('status')}")
        print(f"  - Description: {rem_task.get('description')}")  
        print(f"  - Updated at: {rem_task.get('updated_at')}")
        print(f"  - Item modified: {rem_task.get('item_modified_at')}")
        print(f"  - List: {rem_task.get('list', {}).get('name')}")
    else:
        print(f"✗ Apple Reminder not found by UUID: {target_rem_uuid}")
    
    print(f"\n3. SYNC LINK ANALYSIS:")
    print("=" * 40)
    
    target_link = None
    for link in link_list:
        if (link.get('obs_uuid') == target_block_id and 
            link.get('rem_uuid') == target_rem_uuid):
            target_link = link
            break
    
    if target_link:
        print(f"✓ Found sync link:")
        print(f"  - Obs UUID in link: {target_link.get('obs_uuid')} (THIS IS THE PROBLEM!)")
        print(f"  - Rem UUID in link: {target_link.get('rem_uuid')}")
        print(f"  - Score: {target_link.get('score')}")
        print(f"  - Created: {target_link.get('created_at')}")
        print(f"  - Last scored: {target_link.get('last_scored')}")
        print(f"  - Last synced: {target_link.get('last_synced')}")
        print(f"  - Fields: {target_link.get('fields', {})}")
    else:
        print(f"✗ No sync link found matching obs_uuid={target_block_id}, rem_uuid={target_rem_uuid}")
    
    print(f"\n4. ROOT CAUSE ANALYSIS:")
    print("=" * 40)
    
    if target_link and obs_task and rem_task:
        link_obs_id = target_link.get('obs_uuid')  # This is t-e2eaba4c2b7c (block_id)
        actual_obs_uuid = target_obs_uuid  # This is c84d5c8a-4b71-4135-b520-3c106b484eb1 
        
        print(f"PROBLEM IDENTIFIED:")
        print(f"  - Sync link obs_uuid: '{link_obs_id}' (block_id)")
        print(f"  - Actual Obsidian UUID: '{actual_obs_uuid}' (schema v2 UUID)")
        print(f"  - This mismatch causes sync_links_apply.py to skip the task!")
        print()
        
        print(f"WHY SYNC IS SKIPPED:")
        print(f"  1. sync_links_apply.py line 492: ot = obs_tasks.get(ou)")
        print(f"  2. It looks for obs_tasks['{link_obs_id}'] but should look for obs_tasks['{actual_obs_uuid}']")
        print(f"  3. Since obs_tasks['{link_obs_id}'] returns None, the link is skipped (line 494-495)")
        print()
        
        print(f"CURRENT TASK STATES:")
        print(f"  - Obsidian status: '{obs_task.get('status')}' (updated: {obs_task.get('updated_at')})")
        print(f"  - Reminders status: '{rem_task.get('status')}' (updated: {rem_task.get('updated_at')})")
        print(f"  - Sync needed: Obsidian 'done' → Reminders 'todo'")
    
    print(f"\n5. SOLUTION ANALYSIS:")
    print("=" * 40)
    
    if target_link:
        print(f"IMMEDIATE FIX NEEDED:")
        print(f"  - Update sync link obs_uuid from '{target_link.get('obs_uuid')}' to '{target_obs_uuid}'")
        print(f"  - This will allow sync_links_apply.py to find the correct Obsidian task")
        print()
        
        print(f"ROOT CAUSE TO INVESTIGATE:")
        print(f"  - The sync link creation process used block_id instead of schema v2 UUID")
        print(f"  - Check build_sync_links.py or similar linking logic")
        print(f"  - Schema v2 should use deterministic UUIDs, not block_ids for linking")
    
    print(f"\n6. VERIFICATION STEPS:")
    print("=" * 40)
    print(f"  1. Fix the sync link UUID mapping")
    print(f"  2. Run sync_links_apply.py --verbose --apply")
    print(f"  3. Verify Reminders status changes from 'todo' to 'done'")
    print(f"  4. Check that last_synced timestamp gets updated")

if __name__ == "__main__":
    debug_task_sync()