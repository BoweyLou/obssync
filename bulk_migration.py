#!/usr/bin/env python3
"""
Bulk migration script to move all tasks from default lists to vault-specific lists
"""

import json
import sys
import os
import tempfile

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from obs_tools.commands.collect_reminders_tasks import main as collect_reminders
from reminders_gateway import RemindersGateway
from app_config import get_path, load_app_config
from lib.vault_organization import generate_stable_vault_id

def bulk_migrate_tasks(batch_size=50, dry_run=True, force=False):
    print(f"📦 Bulk Task Migration ({'DRY RUN' if dry_run else 'LIVE MIGRATION'})")
    print("=" * 60)

    # Load configuration
    app_prefs, paths = load_app_config()

    print(f"🔧 Configuration:")
    print(f"   Vault organization: {app_prefs.vault_organization_enabled}")
    print(f"   Default vault: {app_prefs.default_vault_id}")

    if not app_prefs.vault_organization_enabled:
        print("❌ Vault organization not enabled")
        return

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

    # Create mappings
    vault_to_list_id = {}
    list_name_to_id = {
        lst.get("name"): lst.get("identifier")
        for lst in reminders_config
        if isinstance(lst, dict) and lst.get("identifier")
    }

    print(f"\n🗂️  Vault-List Mappings:")
    for vault in vault_entries or []:
        if not isinstance(vault, dict):
            continue
        vault_name = vault.get("name")
        vault_path = vault.get("path", "")
        vault_id = vault.get("vault_id") or generate_stable_vault_id(str(vault_path))
        mapped_list_id = vault.get("associated_list_id")

        if not mapped_list_id and vault_name in list_name_to_id:
            mapped_list_id = list_name_to_id[vault_name]

        if mapped_list_id:
            vault_to_list_id[vault_id] = {
                "list_id": mapped_list_id,
                "vault_name": vault_name or vault_id,
            }
            print(f"   ✅ {vault_name or vault_id} → {mapped_list_id}")
        else:
            print(f"   ❌ {vault_name or vault_id} → NO MATCHING LIST")

    # Collect current reminders
    print(f"\n📥 Collecting current reminders...")

    # Create platform-independent temporary file
    temp_fd, temp_file = tempfile.mkstemp(suffix='.json', prefix='bulk_migration_reminders_')

    try:
        # Close the file descriptor on Windows before other processes access it
        os.close(temp_fd)

        collect_result = collect_reminders([
            "--use-config",
            "--config", get_path("reminders_lists"),
            "--output", temp_file
        ])

        if collect_result != 0:
            print("❌ Failed to collect reminders")
            return

        with open(temp_file, 'r') as f:
            reminders_data = json.load(f)

        tasks = reminders_data.get('tasks', {})
        print(f"   ✅ Collected {len(tasks)} tasks")

    except Exception as e:
        print(f"❌ Failed to collect reminders: {e}")
        return
    finally:
        # Ensure temp file is always cleaned up
        try:
            if os.path.exists(temp_file):
                os.unlink(temp_file)
        except OSError:
            pass  # Ignore cleanup errors

    # Find default lists
    default_list_ids = set()
    default_list_names = ["Reminders", "Tasks"]

    print(f"\n🎯 Default Lists (for migration):")
    for lst in reminders_config:
        if not isinstance(lst, dict):
            continue
        name = lst.get("name")
        identifier = lst.get("identifier")
        if name in default_list_names and identifier:
            default_list_ids.add(identifier)
            print(f"   - {name}: {identifier}")

    # Count tasks in default lists
    default_task_count = sum(1 for task in tasks.values()
                           if task.get('list', {}).get('identifier') in default_list_ids)

    print(f"\n📊 Tasks in default lists: {default_task_count}")

    # Determine target vault
    target_vault_id = app_prefs.default_vault_id or default_vault_id
    if not target_vault_id or target_vault_id not in vault_to_list_id:
        print(f"❌ Default vault '{target_vault_id}' not found in mappings")
        return

    target_entry = vault_to_list_id[target_vault_id]
    target_list_id = target_entry["list_id"]
    target_vault_name = target_entry.get("vault_name", target_vault_id)
    print(f"🎯 Target: All default tasks → {target_vault_name} list ({target_list_id})")

    # Find all tasks to migrate
    tasks_to_migrate = []
    for task_id, task in tasks.items():
        current_list_id = task.get('list', {}).get('identifier')
        current_list_name = task.get('list', {}).get('name')

        # Check if task is in a default list
        if current_list_id in default_list_ids and current_list_id != target_list_id:
            tasks_to_migrate.append({
                'task_id': task_id,
                'title': task.get('description') or task.get('content', {}).get('title', ''),
                'from_list': current_list_name,
                'to_list': target_vault_name,
                'to_list_id': target_list_id,
                'external_ids': task.get('external_ids', {}),
                'task': task
            })

    print(f"\n🔄 Tasks to migrate: {len(tasks_to_migrate)}")

    if not tasks_to_migrate:
        print("✅ No tasks need migration")
        return

    # Show sample tasks
    print(f"\n📋 Sample tasks (first 5):")
    for i, migration in enumerate(tasks_to_migrate[:5]):
        title = migration['title'][:50] + "..." if len(migration['title']) > 50 else migration['title']
        print(f"   {i+1}. '{title}'")
        print(f"      {migration['from_list']} → {migration['to_list']}")

    if dry_run:
        print(f"\n🏁 DRY RUN COMPLETE")
        print(f"   Would migrate {len(tasks_to_migrate)} tasks to {target_vault_name}")
        print(f"   Run with --apply to execute migration")
        return

    # Confirm migration
    print(f"\n⚠️  LIVE MIGRATION: This will move {len(tasks_to_migrate)} tasks!")

    if force:
        print("🚀 Force mode enabled, proceeding without confirmation...")
    else:
        # Try to get input, but continue if stdin is not available (non-interactive mode)
        try:
            response = input(f"Continue? (yes/no): ").strip().lower()
            if response != 'yes':
                print("❌ Migration cancelled")
                return
        except EOFError:
            print("📡 Non-interactive mode detected, proceeding with migration...")
            response = 'yes'

    # Perform migration in batches
    print(f"\n🚀 Starting migration (batch size: {batch_size})...")

    try:
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
            return

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
                    item_id = migration['external_ids'].get('item')
                    if not item_id:
                        print(f"   ⚠️  No external ID: {migration['title'][:30]}...")
                        batch_errors += 1
                        continue

                    # Find and migrate reminder
                    reminder = gateway.find_reminder_by_id(item_id)
                    if not reminder:
                        print(f"   ⚠️  Not found: {migration['title'][:30]}...")
                        batch_errors += 1
                        continue

                    # Move to target calendar
                    reminder.setCalendar_(target_calendar)
                    success = store.saveReminder_commit_error_(reminder, True, None)

                    if success:
                        batch_migrated += 1
                        if batch_migrated % 10 == 0:  # Progress indicator
                            print(f"   ✅ Migrated {batch_migrated}/{len(batch)} tasks...")
                    else:
                        print(f"   ❌ Save failed: {migration['title'][:30]}...")
                        batch_errors += 1

                except Exception as e:
                    print(f"   ❌ Error: {migration['title'][:30]}... - {e}")
                    batch_errors += 1

            total_migrated += batch_migrated
            total_errors += batch_errors

            print(f"   📊 Batch complete: {batch_migrated} migrated, {batch_errors} errors")

            # Pause between batches to avoid overwhelming EventKit
            if batch_end < len(tasks_to_migrate):
                import time
                print(f"   ⏱️  Pausing 2 seconds...")
                time.sleep(2)

        print(f"\n🏁 MIGRATION COMPLETE!")
        print(f"   ✅ Successfully migrated: {total_migrated}")
        print(f"   ❌ Errors: {total_errors}")
        print(f"   📊 Success rate: {total_migrated/(total_migrated+total_errors)*100:.1f}%")

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Bulk migrate tasks from default lists to vault-specific lists")
    parser.add_argument("--apply", action="store_true", help="Actually perform migration (default: dry run)")
    parser.add_argument("--batch-size", type=int, default=50, help="Number of tasks per batch (default: 50)")
    parser.add_argument("--force", action="store_true", help="Skip confirmation prompt")

    args = parser.parse_args()

    bulk_migrate_tasks(
        batch_size=args.batch_size,
        dry_run=not args.apply,
        force=args.force
    )
