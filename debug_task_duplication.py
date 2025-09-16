#!/usr/bin/env python3
"""
Debug script to analyze task duplication in collect_obsidian_tasks.py
"""

import json
import os
from typing import Dict, Set, List
from collections import defaultdict, Counter

def analyze_task_index(index_path: str):
    """Analyze the task index for duplicates and patterns."""
    
    if not os.path.exists(index_path):
        print(f"Index file not found: {index_path}")
        return
        
    with open(index_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    tasks = data.get('tasks', {})
    print(f"Total tasks in index: {len(tasks)}")
    
    # Analyze duplicates by different keys
    by_fingerprint = defaultdict(list)
    by_source_key = defaultdict(list)
    by_content_key = defaultdict(list)
    by_raw_line = defaultdict(list)
    
    for uid, task in tasks.items():
        # Group by fingerprint
        fingerprint = task.get('fingerprint', '')
        by_fingerprint[fingerprint].append((uid, task))
        
        # Group by source_key  
        source_key = task.get('source_key', '')
        by_source_key[source_key].append((uid, task))
        
        # Group by content key (normalized)
        vault_name = task.get('vault', {}).get('name', '')
        rel_path = task.get('file', {}).get('relative_path', '')
        raw = task.get('raw', '')
        content_key = f"{vault_name}:{rel_path}:{raw.lower().strip()}"
        by_content_key[content_key].append((uid, task))
        
        # Group by raw line
        by_raw_line[raw].append((uid, task))
    
    # Find duplicates
    print("\n=== DUPLICATE ANALYSIS ===")
    
    # Fingerprint duplicates
    fp_dups = {k: v for k, v in by_fingerprint.items() if len(v) > 1}
    print(f"Tasks with duplicate fingerprints: {len(fp_dups)} groups")
    if fp_dups:
        print("Top 5 fingerprint duplicates:")
        for i, (fp, tasks_list) in enumerate(sorted(fp_dups.items(), key=lambda x: len(x[1]), reverse=True)[:5]):
            print(f"  {i+1}. Fingerprint {fp[:16]}...: {len(tasks_list)} tasks")
            for uid, task in tasks_list[:3]:  # Show first 3
                print(f"     - {uid}: {task.get('description', '')[:50]}")
    
    # Source key duplicates
    sk_dups = {k: v for k, v in by_source_key.items() if len(v) > 1}
    print(f"Tasks with duplicate source_keys: {len(sk_dups)} groups")
    if sk_dups:
        print("Top 5 source_key duplicates:")
        for i, (sk, tasks_list) in enumerate(sorted(sk_dups.items(), key=lambda x: len(x[1]), reverse=True)[:5]):
            print(f"  {i+1}. Source key {sk}: {len(tasks_list)} tasks")
            for uid, task in tasks_list[:3]:
                print(f"     - {uid}: {task.get('description', '')[:50]}")
    
    # Content key duplicates
    ck_dups = {k: v for k, v in by_content_key.items() if len(v) > 1}
    print(f"Tasks with duplicate content_keys: {len(ck_dups)} groups")
    if ck_dups:
        print("Top 5 content_key duplicates:")
        for i, (ck, tasks_list) in enumerate(sorted(ck_dups.items(), key=lambda x: len(x[1]), reverse=True)[:5]):
            print(f"  {i+1}. Content key {ck[:80]}...: {len(tasks_list)} tasks")
            for uid, task in tasks_list[:3]:
                print(f"     - {uid}: {task.get('description', '')[:50]}")
    
    # Raw line duplicates  
    raw_dups = {k: v for k, v in by_raw_line.items() if len(v) > 1}
    print(f"Tasks with duplicate raw lines: {len(raw_dups)} groups")
    if raw_dups:
        print("Top 5 raw line duplicates:")
        for i, (raw, tasks_list) in enumerate(sorted(raw_dups.items(), key=lambda x: len(x[1]), reverse=True)[:5]):
            print(f"  {i+1}. Raw line '{raw[:60]}...': {len(tasks_list)} tasks")
            for uid, task in tasks_list[:3]:
                print(f"     - {uid}: {task.get('description', '')[:50]}")
                print(f"       Source key: {task.get('source_key', '')}")
                print(f"       File: {task.get('file', {}).get('relative_path', '')}")
    
    # Analyze UUID patterns
    print(f"\n=== UUID ANALYSIS ===")
    print(f"Total unique UUIDs: {len(set(tasks.keys()))}")
    print(f"Total task records: {len(tasks)}")
    
    if len(set(tasks.keys())) != len(tasks):
        print("ERROR: Duplicate UUIDs found in index!")
        uid_counts = Counter(tasks.keys())
        dups = {k: v for k, v in uid_counts.items() if v > 1}
        print(f"Duplicate UUIDs: {dups}")
    
    # Check for very similar tasks that might be processed twice
    print(f"\n=== SIMILARITY ANALYSIS ===")
    similar_groups = []
    processed = set()
    
    for uid1, task1 in tasks.items():
        if uid1 in processed:
            continue
            
        similar = [uid1]
        desc1 = task1.get('description', '').lower().strip()
        file1 = task1.get('file', {}).get('relative_path', '')
        line1 = task1.get('file', {}).get('line', 0)
        
        for uid2, task2 in tasks.items():
            if uid1 == uid2 or uid2 in processed:
                continue
                
            desc2 = task2.get('description', '').lower().strip()
            file2 = task2.get('file', {}).get('relative_path', '')
            line2 = task2.get('file', {}).get('line', 0)
            
            # Consider similar if same description and file, but different lines
            if desc1 == desc2 and file1 == file2 and abs(line1 - line2) <= 2:
                similar.append(uid2)
        
        if len(similar) > 1:
            similar_groups.append(similar)
            processed.update(similar)
    
    if similar_groups:
        print(f"Found {len(similar_groups)} groups of similar tasks:")
        for i, group in enumerate(similar_groups[:5]):  # Show first 5 groups
            print(f"  Group {i+1} ({len(group)} tasks):")
            for uid in group[:3]:  # Show first 3 from group
                task = tasks[uid]
                print(f"    - {uid}: {task.get('description', '')[:50]}")
                print(f"      File: {task.get('file', {}).get('relative_path', '')}:{task.get('file', {}).get('line', '')}")
                print(f"      Source: {task.get('source_key', '')}")

if __name__ == "__main__":
    import sys
    
    # Default to the main index file
    index_path = "/Users/yannickbowe/.config/obsidian_tasks_index.json"
    
    if len(sys.argv) > 1:
        index_path = sys.argv[1]
        
    print(f"Analyzing task index: {index_path}")
    analyze_task_index(index_path)