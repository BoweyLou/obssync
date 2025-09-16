#!/usr/bin/env python3
"""
Clean up duplicate tasks in the existing index caused by the indentation bug.
"""

import json
import os
import sys
import shutil
from collections import defaultdict
from datetime import datetime, timezone

# Add the project root to the path for imports
sys.path.insert(0, os.path.dirname(__file__))
from app_config import get_path

def clean_duplicate_tasks(index_path: str, backup: bool = True):
    """Clean up duplicate tasks from the index file."""
    
    if not os.path.exists(index_path):
        print(f"Index file not found: {index_path}")
        return False
        
    print(f"Loading index: {index_path}")
    with open(index_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    tasks = data.get('tasks', {})
    original_count = len(tasks)
    print(f"Original task count: {original_count}")
    
    # Group tasks by source_key to find duplicates
    by_source_key = defaultdict(list)
    for uid, task in tasks.items():
        source_key = task.get('source_key', '')
        by_source_key[source_key].append((uid, task))
    
    # Find duplicates
    duplicates = {k: v for k, v in by_source_key.items() if len(v) > 1}
    print(f"Found {len(duplicates)} duplicate source keys")
    
    if not duplicates:
        print("No duplicates found - index is clean!")
        return True
    
    # Create backup if requested
    if backup:
        backup_path = f"{index_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        print(f"Creating backup: {backup_path}")
        shutil.copy2(index_path, backup_path)
    
    # Clean duplicates - keep the task with the earliest created_at for each source_key
    cleaned_tasks = {}
    removed_count = 0
    
    for source_key, task_list in by_source_key.items():
        if len(task_list) == 1:
            # No duplicates, keep as is
            uid, task = task_list[0]
            cleaned_tasks[uid] = task
        else:
            # Multiple tasks with same source_key - keep the earliest
            print(f"Cleaning {len(task_list)} duplicates for: {source_key[:80]}...")
            
            # Sort by created_at (earliest first)
            sorted_tasks = sorted(task_list, key=lambda x: x[1].get('created_at', '9999-12-31'))
            
            # Keep the first (earliest) task
            keeper_uid, keeper_task = sorted_tasks[0]
            cleaned_tasks[keeper_uid] = keeper_task
            
            # Count removed tasks
            removed_count += len(task_list) - 1
            
            # Show what we're removing
            for uid, task in sorted_tasks[1:]:
                desc = task.get('description', '')[:50] + ('...' if len(task.get('description', '')) > 50 else '')
                print(f"  Removing duplicate: {uid} - {desc}")
    
    print(f"\nCleaning summary:")
    print(f"  Original tasks: {original_count}")
    print(f"  Cleaned tasks: {len(cleaned_tasks)}")
    print(f"  Removed duplicates: {removed_count}")
    
    # Update the data structure
    data['tasks'] = cleaned_tasks
    data['meta']['generated_at'] = datetime.now(timezone.utc).isoformat()
    if 'vault_count' in data['meta']:
        # Add a note about cleaning
        data['meta']['cleaned_duplicates'] = True
        data['meta']['cleaned_at'] = datetime.now(timezone.utc).isoformat()
        data['meta']['removed_count'] = removed_count
    
    # Write the cleaned index
    print(f"Writing cleaned index to {index_path}")
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
    
    print("✅ Index cleaned successfully!")
    return True

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Clean duplicate tasks from the Obsidian task index")
    parser.add_argument("--index", default=None, help="Path to index file (default: from config)")
    parser.add_argument("--no-backup", action="store_true", help="Skip creating backup")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be removed without making changes")
    
    args = parser.parse_args()
    
    index_path = args.index or get_path("obsidian_index")
    
    if args.dry_run:
        print("=== DRY RUN - No changes will be made ===")
        
        with open(index_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        tasks = data.get('tasks', {})
        by_source_key = defaultdict(list)
        for uid, task in tasks.items():
            source_key = task.get('source_key', '')
            by_source_key[source_key].append((uid, task))
        
        duplicates = {k: v for k, v in by_source_key.items() if len(v) > 1}
        
        print(f"Would clean {len(duplicates)} duplicate source keys")
        print(f"Would remove {sum(len(v) - 1 for v in duplicates.values())} duplicate tasks")
        
        # Show top duplicates
        print("\nTop duplicate groups:")
        for i, (source_key, task_list) in enumerate(sorted(duplicates.items(), key=lambda x: len(x[1]), reverse=True)[:10]):
            print(f"  {i+1}. {source_key[:80]}... ({len(task_list)} duplicates)")
            
    else:
        success = clean_duplicate_tasks(index_path, backup=not args.no_backup)
        return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())