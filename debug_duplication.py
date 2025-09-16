#!/usr/bin/env python3
"""
Debug script to identify the exact source of task duplication.
"""

import json
import sys
import os
from collections import defaultdict

# Add the project root to the path for imports
sys.path.insert(0, os.path.dirname(__file__))

from obs_tools.commands.collect_obsidian_tasks import (
    load_existing, normalize_content_key, make_source_key
)
from app_config import get_path

def analyze_duplication():
    """Analyze the current index to identify duplication patterns."""
    
    # Load current index
    index_path = get_path("obsidian_index")
    if not os.path.exists(index_path):
        print(f"Index file not found: {index_path}")
        return
    
    with open(index_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    tasks = data.get('tasks', {})
    print(f"Total tasks in index: {len(tasks)}")
    
    # Count raw tasks by checking how many have recent created_at
    recent_tasks = [t for t in tasks.values() if t.get('created_at', '').startswith('2025-09-12')]
    total_recent = len(recent_tasks)
    print(f"Tasks created today (likely from recent collection): {total_recent}")
    
    # Group by content key to find duplicates
    content_groups = defaultdict(list)
    source_key_groups = defaultdict(list)
    fingerprint_groups = defaultdict(list)
    
    for uuid, task in tasks.items():
        if task.get('deleted'):
            continue
            
        # Get task identifiers
        vault_name = (task.get('vault') or {}).get('name', '')
        rel_path = (task.get('file') or {}).get('relative_path', '')
        raw = task.get('raw', '')
        source_key = task.get('source_key', '')
        fingerprint = task.get('fingerprint', '')
        description = task.get('description', '')
        
        # Group by different keys
        content_key = normalize_content_key(vault_name, rel_path, raw)
        content_groups[content_key].append((uuid, task))
        
        if source_key:
            source_key_groups[source_key].append((uuid, task))
        
        if fingerprint:
            fingerprint_groups[fingerprint].append((uuid, task))
    
    # Find duplicates by content key
    content_duplicates = {k: v for k, v in content_groups.items() if len(v) > 1}
    source_key_duplicates = {k: v for k, v in source_key_groups.items() if len(v) > 1}
    fingerprint_duplicates = {k: v for k, v in fingerprint_groups.items() if len(v) > 1}
    
    print(f"\nDuplicate analysis:")
    print(f"  Content key duplicates: {len(content_duplicates)} groups")
    print(f"  Source key duplicates: {len(source_key_duplicates)} groups") 
    print(f"  Fingerprint duplicates: {len(fingerprint_duplicates)} groups")
    
    # Show examples of content key duplicates
    if content_duplicates:
        print(f"\nFirst 5 content key duplicate groups:")
        for i, (content_key, group) in enumerate(list(content_duplicates.items())[:5]):
            print(f"\nGroup {i+1}: {content_key}")
            print(f"  Tasks in group: {len(group)}")
            if i == 2:  # Look at Group 3 (the large one) more closely
                print("  Sample raw lines from this group:")
                for j, (uuid, task) in enumerate(group[:5]):
                    raw_line = task.get('raw', 'NO_RAW')
                    print(f"    RAW: {raw_line}")
                print("  Continuing with normal output:")
            for j, (uuid, task) in enumerate(group[:10]):  # Limit to first 10
                source_key = task.get('source_key', 'NO_SOURCE_KEY')
                description = task.get('description', 'NO_DESCRIPTION')[:50]
                created_at = task.get('created_at', 'NO_CREATED_AT')
                print(f"    {uuid[:8]}... | {source_key[:30]}... | {description} | {created_at}")
                if j >= 9:  # Show first 10 only
                    break
    
    # Check for tasks with same source key but different UUIDs
    if source_key_duplicates:
        print(f"\nFirst 5 source key duplicate groups:")
        for i, (source_key, group) in enumerate(list(source_key_duplicates.items())[:5]):
            print(f"\nGroup {i+1}: {source_key}")
            print(f"  Tasks in group: {len(group)}")
            for uuid, task in group:
                description = task.get('description', 'NO_DESCRIPTION')[:50]
                created_at = task.get('created_at', 'NO_CREATED_AT')
                print(f"    {uuid[:8]}... | {description} | {created_at}")

if __name__ == "__main__":
    analyze_duplication()