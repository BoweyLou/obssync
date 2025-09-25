#!/usr/bin/env python3
"""
Clean Slate Migration Script: Remove All Tasks from Apple Reminders List

This script removes ALL tasks from the configured Apple Reminders list to prepare
for a fresh sync with the new deterministic UUID system.

CAUTION: This will permanently delete tasks from Apple Reminders!
Make sure you have backups if needed.
"""

import argparse
import logging
from typing import List, Optional
import sys
import os

# Add the project root to the path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from obs_sync.core.config import SyncConfig
from obs_sync.reminders.gateway import RemindersGateway

def confirm_deletion(list_name: str, task_count: int) -> bool:
    """Get user confirmation before deleting tasks."""
    print(f"\n⚠️  WARNING: This will permanently delete {task_count} tasks from '{list_name}'!")
    print("🔄 This action cannot be undone.")
    print("💾 Make sure you have backups if you need to restore these tasks.")

    while True:
        response = input(f"\nType 'DELETE {task_count} TASKS' to confirm: ").strip()
        expected = f"DELETE {task_count} TASKS"

        if response == expected:
            return True
        elif response.lower() in ['n', 'no', 'cancel', 'quit', 'exit']:
            return False
        else:
            print(f"❌ Please type exactly: {expected}")

def main():
    parser = argparse.ArgumentParser(description='Remove all tasks from Apple Reminders list')
    parser.add_argument('--list-id', help='Specific reminder list ID to clean (optional)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be deleted without deleting')
    parser.add_argument('--force', action='store_true', help='Skip confirmation prompt (use with caution!)')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()

    # Set up logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    print("🧹 Apple Reminders Clean Slate Tool")
    print("=" * 50)

    # Load configuration
    try:
        config = SyncConfig()
    except Exception as e:
        print(f"❌ Failed to load configuration: {e}")
        return 1

    # Determine which list to clean
    if args.list_id:
        list_ids = [args.list_id]
        print(f"🎯 Target: Specific list ID {args.list_id}")
    else:
        list_ids = config.reminder_list_ids or []
        if not list_ids:
            print("❌ No reminder lists configured and no --list-id specified")
            print("💡 Run sync setup first or specify --list-id")
            return 1
        print(f"🎯 Target: Configured reminder lists ({len(list_ids)} lists)")

    # Initialize reminders gateway
    try:
        gateway = RemindersGateway(logger=logger)
    except Exception as e:
        print(f"❌ Failed to initialize Reminders gateway: {e}")
        print("💡 Make sure you have permission to access Apple Reminders")
        return 1

    total_tasks_to_delete = 0
    lists_info = []

    # Collect information about tasks to delete
    for list_id in list_ids:
        try:
            print(f"\n📋 Analyzing list: {list_id}")

            # Get list info
            list_info = gateway.get_list_by_id(list_id)
            if not list_info:
                print(f"⚠️  List not found: {list_id}")
                continue

            list_name = list_info.get('name', 'Unknown')
            print(f"  Name: {list_name}")

            # Get tasks in this list
            tasks = gateway.list_tasks(list_ids=[list_id])
            task_count = len(tasks)
            total_tasks_to_delete += task_count

            lists_info.append({
                'id': list_id,
                'name': list_name,
                'tasks': tasks,
                'count': task_count
            })

            print(f"  Tasks found: {task_count}")

            if args.verbose and task_count > 0:
                print(f"  Sample tasks:")
                for i, task in enumerate(tasks[:3]):  # Show first 3 tasks
                    title = task.get('title', 'No title')[:50]
                    print(f"    {i+1}. {title}")
                if task_count > 3:
                    print(f"    ... and {task_count - 3} more")

        except Exception as e:
            print(f"❌ Error analyzing list {list_id}: {e}")
            continue

    if total_tasks_to_delete == 0:
        print(f"\n✅ No tasks found to delete. Lists are already clean!")
        return 0

    print(f"\n📊 SUMMARY:")
    print(f"  Lists to clean: {len(lists_info)}")
    print(f"  Total tasks to delete: {total_tasks_to_delete}")

    # Dry run mode
    if args.dry_run:
        print(f"\n🔍 DRY RUN MODE - No tasks will be deleted")
        for list_info in lists_info:
            print(f"  Would delete {list_info['count']} tasks from '{list_info['name']}'")
        print(f"\n💡 Remove --dry-run to actually delete tasks")
        return 0

    # Confirmation (unless forced)
    if not args.force:
        confirmed = False
        for list_info in lists_info:
            if list_info['count'] > 0:
                if not confirm_deletion(list_info['name'], list_info['count']):
                    print("❌ Deletion cancelled by user")
                    return 1
                confirmed = True

        if not confirmed:
            print("✅ No tasks to delete")
            return 0

    # Perform deletion
    print(f"\n🗑️  Deleting tasks...")
    total_deleted = 0

    for list_info in lists_info:
        if list_info['count'] == 0:
            continue

        list_name = list_info['name']
        tasks = list_info['tasks']

        print(f"\n📋 Cleaning '{list_name}' ({len(tasks)} tasks)...")

        deleted_count = 0
        for i, task in enumerate(tasks, 1):
            try:
                task_id = task.get('id') or task.get('uuid')
                if not task_id:
                    print(f"  ⚠️  Task {i}: No ID found, skipping")
                    continue

                title = task.get('title', 'No title')[:30]
                success = gateway.delete_task(task_id)

                if success:
                    deleted_count += 1
                    if args.verbose:
                        print(f"  ✅ {i:3d}/{len(tasks)}: {title}")
                    elif i % 10 == 0:  # Progress indicator
                        print(f"    Progress: {i}/{len(tasks)} deleted...")
                else:
                    print(f"  ❌ {i:3d}/{len(tasks)}: Failed to delete '{title}'")

            except Exception as e:
                print(f"  ❌ {i:3d}/{len(tasks)}: Error deleting task: {e}")

        print(f"  ✅ Deleted {deleted_count}/{len(tasks)} tasks from '{list_name}'")
        total_deleted += deleted_count

    print(f"\n📊 FINAL RESULTS:")
    print(f"  Total tasks deleted: {total_deleted}/{total_tasks_to_delete}")

    if total_deleted == total_tasks_to_delete:
        print(f"🎉 Successfully cleaned all Apple Reminders lists!")
        print(f"💡 You can now run a fresh sync to rebuild with deterministic UUIDs")
    else:
        print(f"⚠️  Some tasks could not be deleted. Check the output above for details.")
        return 1

    return 0

if __name__ == '__main__':
    exit(main())