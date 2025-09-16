#!/usr/bin/env python3
"""
Debug the actual collection process to see raw vs processed counts
"""

import os
import sys
import json
from collections import defaultdict

# Add the project root to the path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "obs_tools", "commands"))
sys.path.insert(0, os.path.dirname(__file__))

from obs_tools.commands.collect_obsidian_tasks import (
    load_vaults, iter_md_files, parse_tasks_from_file, make_source_key, load_existing
)
from app_config import get_path

def debug_collection():
    """Debug the collection process step by step."""
    
    # Load vaults
    config_path = get_path("obsidian_vaults")
    vaults = load_vaults(config_path)
    print(f"Loaded {len(vaults)} vaults")
    
    ignore = {".git", ".hg", ".svn", ".obsidian", ".recovery_backups", ".trash"}
    
    # Collect raw tasks
    raw_tasks = []
    file_count = 0
    
    print("Collecting raw tasks...")
    for vault in vaults:
        print(f"Processing vault: {vault.name}")
        for path in iter_md_files(vault.path, ignore_dirs=ignore):
            file_count += 1
            rel = os.path.relpath(path, vault.path)
            try:
                tasks = parse_tasks_from_file(path)
                if tasks:
                    print(f"  {rel}: {len(tasks)} tasks")
                raw_tasks.extend([(vault.name, rel, t) for t in tasks])
            except Exception as e:
                print(f"  ERROR parsing {rel}: {e}")
                
    print(f"\nRaw collection results:")
    print(f"  Files processed: {file_count}")
    print(f"  Raw tasks found: {len(raw_tasks)}")
    
    # Analyze source keys for duplicates
    source_keys = []
    source_key_counts = defaultdict(int)
    
    for vault_name, rel_path, task in raw_tasks:
        source_key = make_source_key(vault_name, rel_path, task)
        source_keys.append(source_key)
        source_key_counts[source_key] += 1
    
    print(f"  Unique source keys: {len(set(source_keys))}")
    print(f"  Total source keys: {len(source_keys)}")
    
    # Check for source key duplicates in raw data
    duplicates = {k: v for k, v in source_key_counts.items() if v > 1}
    if duplicates:
        print(f"  Source key duplicates in RAW data: {len(duplicates)}")
        print("  Top duplicates:")
        for i, (key, count) in enumerate(sorted(duplicates.items(), key=lambda x: x[1], reverse=True)[:5]):
            print(f"    {i+1}. {key}: {count} occurrences")
    else:
        print("  No source key duplicates in raw data - good!")
    
    # Load existing index to see what's carried forward
    existing_path = get_path("obsidian_index")
    print(f"\nAnalyzing existing index: {existing_path}")
    
    existing_tasks, source_to_uuid = load_existing(existing_path)
    print(f"  Existing tasks in index: {len(existing_tasks)}")
    print(f"  Source key mappings: {len(source_to_uuid)}")
    
    # Check how many of the raw tasks have existing UUIDs
    new_tasks = 0
    existing_matches = 0
    
    for vault_name, rel_path, task in raw_tasks:
        source_key = make_source_key(vault_name, rel_path, task)
        if source_key in source_to_uuid:
            existing_matches += 1
        else:
            new_tasks += 1
    
    print(f"  Raw tasks with existing UUIDs: {existing_matches}")
    print(f"  Raw tasks that would be new: {new_tasks}")
    
    # Calculate expected final count
    carried_forward_estimate = len(existing_tasks) - existing_matches
    expected_final = len(raw_tasks) + carried_forward_estimate
    
    print(f"\nExpected final count calculation:")
    print(f"  Raw tasks: {len(raw_tasks)}")
    print(f"  Existing tasks not seen: {carried_forward_estimate}")
    print(f"  Expected total: {expected_final}")

if __name__ == "__main__":
    debug_collection()