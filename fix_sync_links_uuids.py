#!/usr/bin/env python3
"""
Fix sync links that use block_ids instead of proper schema v2 UUIDs.

This script repairs the data integrity issue where sync links have obs_uuid
values that are block_ids instead of the actual UUID keys used in the 
Obsidian tasks index.
"""

import json
import os
from datetime import datetime, timezone

def fix_sync_links_uuids(dry_run=True):
    """
    Fix sync links to use proper UUIDs instead of block_ids.
    
    Args:
        dry_run: If True, only show what would be changed without making changes
    """
    
    print("=== FIXING SYNC LINKS UUID INCONSISTENCIES ===\n")
    
    # Load data files
    obs_path = os.path.expanduser("~/.config/obsidian_tasks_index.json")
    links_path = os.path.expanduser("~/.config/sync_links.json")
    
    with open(obs_path, 'r') as f:
        obs = json.load(f)
    with open(links_path, 'r') as f:
        links = json.load(f)
    
    obs_tasks = obs.get('tasks', {})
    link_list = links.get('links', [])
    
    print(f"Loaded {len(obs_tasks)} Obsidian tasks and {len(link_list)} sync links")
    
    # Build reverse lookup: block_id -> UUID
    block_id_to_uuid = {}
    for uuid, task in obs_tasks.items():
        block_id = task.get('block_id')
        if block_id:
            block_id_to_uuid[block_id] = uuid
    
    print(f"Built reverse lookup with {len(block_id_to_uuid)} block_id -> UUID mappings")
    
    # Find and fix broken links
    fixed_count = 0
    broken_links = []
    
    for i, link in enumerate(link_list):
        obs_uuid = link.get('obs_uuid')
        
        # Check if obs_uuid exists as a key in obs_tasks
        if obs_uuid not in obs_tasks:
            # Check if it's a block_id that can be mapped to a real UUID
            if obs_uuid in block_id_to_uuid:
                real_uuid = block_id_to_uuid[obs_uuid]
                broken_links.append({
                    'index': i,
                    'old_obs_uuid': obs_uuid,
                    'new_obs_uuid': real_uuid,
                    'rem_uuid': link.get('rem_uuid'),
                    'score': link.get('score'),
                    'created_at': link.get('created_at')
                })
    
    print(f"\nFound {len(broken_links)} sync links that need UUID fixes")
    
    if not broken_links:
        print("No broken links found - all sync links already have correct UUIDs!")
        return
    
    # Show some examples
    print("\nExamples of broken links:")
    for i, broken in enumerate(broken_links[:5]):  # Show first 5
        print(f"  {i+1}. obs_uuid: '{broken['old_obs_uuid']}' -> '{broken['new_obs_uuid']}'")
        print(f"     rem_uuid: {broken['rem_uuid']}")
        print(f"     score: {broken['score']}, created: {broken['created_at']}")
        if broken['old_obs_uuid'] == 't-e2eaba4c2b7c':
            print(f"     ^^^ THIS IS THE PROBLEM TASK!")
    
    if dry_run:
        print(f"\nDRY RUN MODE - Would fix {len(broken_links)} sync links")
        print("Run with dry_run=False to apply fixes")
        return
    
    # Apply fixes
    print(f"\nApplying fixes to {len(broken_links)} sync links...")
    
    for broken in broken_links:
        link_index = broken['index']
        link_list[link_index]['obs_uuid'] = broken['new_obs_uuid']
        fixed_count += 1
    
    # Update metadata
    links['meta']['generated_at'] = datetime.now(timezone.utc).isoformat()
    if 'schema' not in links['meta']:
        links['meta']['schema'] = 1
    
    # Write back to file
    backup_path = links_path + '.backup.' + datetime.now().strftime('%Y%m%d_%H%M%S')
    print(f"Creating backup at: {backup_path}")
    
    # Create backup
    with open(backup_path, 'w') as f:
        json.dump(links, f, indent=2, ensure_ascii=False)
    
    # Write fixed version
    with open(links_path, 'w') as f:
        json.dump(links, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Fixed {fixed_count} sync links")
    print(f"✓ Backup created at {backup_path}")
    print(f"✓ Updated sync links written to {links_path}")

if __name__ == "__main__":
    # First run in dry-run mode
    fix_sync_links_uuids(dry_run=True)
    
    # Apply fixes:
    print("\n" + "="*50)
    print("APPLYING FIXES...")
    print("="*50)
    fix_sync_links_uuids(dry_run=False)