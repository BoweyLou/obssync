#!/usr/bin/env python3
"""
Cleanup script to fix bloated sync_links.json files.

This script removes duplicate and orphaned sync links that accumulated
due to a bug in the _persist_links method that never removed stale entries.

Usage:
    python cleanup_sync_links.py [--dry-run]
"""

import json
import os
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# Import PathManager for centralized path management
try:
    from obs_sync.core.paths import get_path_manager
    USE_PATH_MANAGER = True
except ImportError:
    # Fallback if obs_sync is not in path
    USE_PATH_MANAGER = False
    print("⚠️  Warning: PathManager not available, using legacy paths")

def cleanup_sync_links(dry_run=True):
    """Clean up duplicate and orphaned sync links."""
    
    # Find the sync_links.json file using PathManager
    if USE_PATH_MANAGER:
        manager = get_path_manager()
        sync_links_path = manager.get_file_with_fallback("sync_links.json")
        if sync_links_path is None or not sync_links_path.exists():
            # Fall back to default location
            sync_links_path = manager.sync_links_path
    else:
        # Legacy fallback
        sync_links_path = Path.home() / ".obs-sync" / "data" / "sync_links.json"
    
    if not sync_links_path.exists():
        print(f"No sync links file found at {sync_links_path}")
        return
    
    print(f"Processing {sync_links_path}")
    
    # Load existing links
    with open(sync_links_path, 'r') as f:
        data = json.load(f)
    
    original_links = data.get('links', [])
    original_count = len(original_links)
    print(f"Found {original_count} total links")
    
    # Group links by obs_uuid to find duplicates
    obs_uuid_groups = defaultdict(list)
    for link in original_links:
        obs_uuid = link.get('obs_uuid')
        if obs_uuid:
            obs_uuid_groups[obs_uuid].append(link)
    
    # Group links by rem_uuid to find duplicates
    rem_uuid_groups = defaultdict(list)
    for link in original_links:
        rem_uuid = link.get('rem_uuid')
        if rem_uuid:
            rem_uuid_groups[rem_uuid].append(link)
    
    # Find problematic patterns
    duplicate_obs_uuids = {uuid: links for uuid, links in obs_uuid_groups.items() if len(links) > 1}
    duplicate_rem_uuids = {uuid: links for uuid, links in rem_uuid_groups.items() if len(links) > 1}
    
    print(f"\nFound {len(duplicate_obs_uuids)} Obsidian tasks with multiple links")
    print(f"Found {len(duplicate_rem_uuids)} Reminders tasks with multiple links")
    
    # Show some examples
    if duplicate_obs_uuids:
        example_uuid = list(duplicate_obs_uuids.keys())[0]
        example_links = duplicate_obs_uuids[example_uuid]
        print(f"\nExample: Obsidian task {example_uuid} has {len(example_links)} links:")
        for link in example_links[:3]:  # Show first 3
            print(f"  -> Reminders: {link.get('rem_uuid')}")
    
    # Strategy: Keep only the most recent link for each obs_uuid
    cleaned_links = {}
    
    for obs_uuid, links in obs_uuid_groups.items():
        if len(links) == 1:
            # No duplicates, keep as-is
            key = f"{links[0]['obs_uuid']}:{links[0]['rem_uuid']}"
            cleaned_links[key] = links[0]
        else:
            # Multiple links for same Obsidian task
            # Keep the one with the highest score or most recent timestamp
            best_link = links[0]
            for link in links[1:]:
                # Prefer higher score
                if link.get('score', 0) > best_link.get('score', 0):
                    best_link = link
                # Or more recent last_synced
                elif link.get('last_synced', '') > best_link.get('last_synced', ''):
                    best_link = link
            
            key = f"{best_link['obs_uuid']}:{best_link['rem_uuid']}"
            cleaned_links[key] = best_link
    
    # Now check for rem_uuid duplicates in the cleaned set
    final_links = {}
    rem_uuid_seen = {}
    
    for key, link in cleaned_links.items():
        rem_uuid = link.get('rem_uuid')
        
        if rem_uuid not in rem_uuid_seen:
            # First time seeing this rem_uuid, keep it
            final_links[key] = link
            rem_uuid_seen[rem_uuid] = link
        else:
            # Duplicate rem_uuid, keep the one with higher score
            existing = rem_uuid_seen[rem_uuid]
            if link.get('score', 0) > existing.get('score', 0):
                # Remove old, add new
                old_key = f"{existing['obs_uuid']}:{existing['rem_uuid']}"
                if old_key in final_links:
                    del final_links[old_key]
                final_links[key] = link
                rem_uuid_seen[rem_uuid] = link
    
    cleaned_count = len(final_links)
    removed_count = original_count - cleaned_count
    
    print(f"\nCleaning results:")
    print(f"  Original links: {original_count}")
    print(f"  Cleaned links: {cleaned_count}")
    print(f"  Removed: {removed_count} ({removed_count*100/original_count:.1f}%)")
    
    if not dry_run:
        # Backup original
        backup_path = sync_links_path.with_suffix(f'.backup.{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
        with open(backup_path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"\nBacked up original to {backup_path}")
        
        # Write cleaned data
        cleaned_data = {'links': list(final_links.values())}
        with open(sync_links_path, 'w') as f:
            json.dump(cleaned_data, f, indent=2)
        print(f"Wrote cleaned links to {sync_links_path}")
    else:
        print("\nDRY RUN - no changes made")
        print("Run with --apply to actually clean the file")
    
    return {
        'original': original_count,
        'cleaned': cleaned_count,
        'removed': removed_count
    }

if __name__ == "__main__":
    dry_run = "--apply" not in sys.argv
    cleanup_sync_links(dry_run=dry_run)