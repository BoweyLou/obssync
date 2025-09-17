#!/usr/bin/env python3
"""
Simple bulk migration script without interactive prompts
"""

import json
import sys
import os
import time
import tempfile
import subprocess

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from reminders_gateway import RemindersGateway
from app_config import get_path, load_app_config
from lib.vault_organization import generate_stable_vault_id

def simple_bulk_migrate(batch_size=50, max_tasks=None):
    """Simple migration without confirmation prompts."""

    print(f"📦 Simple Bulk Task Migration")
    print("=" * 50)

    # Load configuration
    app_prefs, paths = load_app_config()

    if not app_prefs.vault_organization_enabled:
        print("❌ Vault organization not enabled")
        return False

    # Load configs
    with open(get_path("obsidian_vaults"), 'r') as f:
        vault_config_raw = json.load(f)
    with open(get_path("reminders_lists"), 'r') as f:
        reminders_config_raw = json.load(f)

    if isinstance(vault_config_raw, dict):
        vault_entries = vault_config_raw.get("vaults", [])
        default_vault_id = vault_config_raw.get("default_vault_id")
    else:
        vault_entries = vault_config_raw
        default_vault_id = None

    if isinstance(reminders_config_raw, dict):
        reminders_config = reminders_config_raw.get("lists", [])
    else:
        reminders_config = reminders_config_raw

    # Find target vault info
    target_vault_id = app_prefs.default_vault_id or default_vault_id
    target_list_id = None
    target_vault_name = None

    for vault in vault_entries or []:
        if isinstance(vault, dict) and vault.get("vault_id") == target_vault_id:
            target_list_id = vault.get("associated_list_id")
            target_vault_name = vault.get("name", target_vault_id)
            break

    if not target_list_id:
        print(f"❌ Target vault not found or not mapped: {target_vault_id}")
        return False

    print(f"🎯 Target: {target_vault_name} ({target_list_id})")

    # Collect current reminders
    print(f"📥 Collecting reminders...")

    # Create secure temporary file with context manager for automatic cleanup
    with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', prefix='simple_migration_reminders_', delete=False) as temp_file:
        temp_file_path = temp_file.name

    try:
        # Build command as a list to avoid shell injection
        python_path = os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3")
        collect_cmd = [
            python_path,
            "obs_tools.py",
            "reminders",
            "collect",
            "--use-config",
            "--output",
            temp_file_path
        ]

        # Use subprocess.run for security (no shell=True)
        result = subprocess.run(collect_cmd, check=True, capture_output=True, text=True)

        with open(temp_file_path, 'r') as f:
            reminders_data = json.load(f)

        tasks = reminders_data.get('tasks', {})
        print(f"✅ Collected {len(tasks)} tasks")

    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to collect reminders: {e}")
        print(f"Command output: {e.stdout}")
        print(f"Command error: {e.stderr}")
        return False
    except Exception as e:
        print(f"❌ Error during reminder collection: {e}")
        return False
    finally:
        # Ensure temp file is always cleaned up
        try:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
        except OSError:
            pass  # Ignore cleanup errors

    # Find default lists
    default_list_ids = set()
    for lst in reminders_config:
        if not isinstance(lst, dict):
            continue
        name = lst.get("name")
        identifier = lst.get("identifier")
        if name in ["Reminders", "Tasks"] and identifier:
            default_list_ids.add(identifier)
            print(f"📋 Default list: {name} ({identifier})")

    # Find tasks to migrate
    tasks_to_migrate = []
    for task_id, task in tasks.items():
        current_list_id = task.get('list', {}).get('identifier')

        if current_list_id in default_list_ids and current_list_id != target_list_id:
            external_ids = task.get('external_ids', {})
            item_id = external_ids.get('item')

            if item_id:  # Only migrate tasks with external IDs
                tasks_to_migrate.append({
                    'task_id': task_id,
                    'title': task.get('description') or task.get('content', {}).get('title', ''),
                    'item_id': item_id,
                    'from_list': task.get('list', {}).get('name', ''),
                    'task': task
                })

    print(f"🔄 Tasks to migrate: {len(tasks_to_migrate)}")

    if not tasks_to_migrate:
        print("✅ No tasks to migrate!")
        return True

    # Limit tasks if specified
    if max_tasks and len(tasks_to_migrate) > max_tasks:
        tasks_to_migrate = tasks_to_migrate[:max_tasks]
        print(f"📝 Limited to {max_tasks} tasks for this run")

    # Initialize gateway and migrate
    try:
        print(f"🚀 Starting migration...")
        gateway = RemindersGateway()
        store = gateway._get_store()

        # Find target calendar
        calendars = store.calendarsForEntityType_(gateway._EKEntityTypeReminder) or []
        target_calendar = None
        for cal in calendars:
            if str(cal.calendarIdentifier()) == target_list_id:
                target_calendar = cal
                break

        if not target_calendar:
            print(f"❌ Target calendar not found: {target_list_id}")
            return False

        print(f"✅ Target calendar: {target_calendar.title()}")

        # Migrate in batches
        total_migrated = 0
        total_errors = 0

        for batch_start in range(0, len(tasks_to_migrate), batch_size):
            batch_end = min(batch_start + batch_size, len(tasks_to_migrate))
            batch = tasks_to_migrate[batch_start:batch_end]

            print(f"\n📦 Batch {batch_start//batch_size + 1}: Tasks {batch_start+1}-{batch_end}")

            batch_migrated = 0
            batch_errors = 0

            for migration in batch:
                try:
                    item_id = migration['item_id']

                    # Find reminder
                    reminder = gateway.find_reminder_by_id(item_id)
                    if not reminder:
                        print(f"   ⚠️  Not found: {migration['title'][:30]}...")
                        batch_errors += 1
                        continue

                    # Check current calendar
                    current_calendar = reminder.calendar()
                    if str(current_calendar.calendarIdentifier()) == target_list_id:
                        # Already migrated
                        batch_migrated += 1
                        continue

                    # Move to target calendar
                    reminder.setCalendar_(target_calendar)
                    success = store.saveReminder_commit_error_(reminder, True, None)

                    if success:
                        batch_migrated += 1
                        if batch_migrated % 10 == 0:
                            print(f"   ✅ {batch_migrated}/{len(batch)} migrated...")
                    else:
                        print(f"   ❌ Save failed: {migration['title'][:30]}...")
                        batch_errors += 1

                except Exception as e:
                    print(f"   ❌ Error: {migration['title'][:30]}... - {e}")
                    batch_errors += 1

            total_migrated += batch_migrated
            total_errors += batch_errors

            print(f"   📊 Batch: {batch_migrated} migrated, {batch_errors} errors")

            # Pause between batches
            if batch_end < len(tasks_to_migrate):
                print(f"   ⏱️  Pausing 2 seconds...")
                time.sleep(2)

        print(f"\n🏁 MIGRATION COMPLETE!")
        print(f"   ✅ Successfully migrated: {total_migrated}")
        print(f"   ❌ Errors: {total_errors}")
        if total_migrated + total_errors > 0:
            print(f"   📊 Success rate: {total_migrated/(total_migrated+total_errors)*100:.1f}%")

        return True

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Simple bulk migration without prompts")
    parser.add_argument("--batch-size", type=int, default=50, help="Batch size (default: 50)")
    parser.add_argument("--max-tasks", type=int, help="Limit number of tasks to migrate")

    args = parser.parse_args()

    success = simple_bulk_migrate(
        batch_size=args.batch_size,
        max_tasks=args.max_tasks
    )

    sys.exit(0 if success else 1)