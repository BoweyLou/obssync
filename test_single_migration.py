#!/usr/bin/env python3
"""
Test script to migrate a single task and capture any errors
"""

import json
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from obs_tools.commands.collect_reminders_tasks import main as collect_reminders
from reminders_gateway import RemindersGateway
from app_config import get_path

def test_single_migration():
    print("🧪 Test Single Task Migration")
    print("=" * 50)

    # Get the migration candidates from our debug script logic
    temp_file = "/tmp/debug_reminders.json"

    # Load reminders data
    with open(temp_file, 'r') as f:
        reminders_data = json.load(f)

    tasks = reminders_data.get('tasks', {})

    # Load configs
    with open(get_path("obsidian_vaults"), 'r') as f:
        vault_config_raw = json.load(f)
    with open(get_path("reminders_lists"), 'r') as f:
        reminders_config_raw = json.load(f)

    vault_entries = vault_config_raw.get("vaults", []) if isinstance(vault_config_raw, dict) else vault_config_raw
    reminders_config = reminders_config_raw.get("lists", []) if isinstance(reminders_config_raw, dict) else reminders_config_raw

    # Create mappings
    vault_to_list_id = {}
    list_name_to_id = {lst.get("name"): lst.get("identifier") for lst in reminders_config if isinstance(lst, dict)}
    for vault in vault_entries or []:
        if not isinstance(vault, dict):
            continue
        vault_name = vault.get("name")
        if vault_name in list_name_to_id and list_name_to_id[vault_name]:
            vault_to_list_id[vault_name] = list_name_to_id[vault_name]

    # Find default lists
    default_list_ids = set()
    for lst in reminders_config:
        if not isinstance(lst, dict):
            continue
        if lst.get("name") in ["Reminders", "Tasks"] and lst.get("identifier"):
            default_list_ids.add(lst["identifier"])

    # Find one task to migrate
    test_task = None
    for task_id, task in tasks.items():
        current_list_id = task.get('list', {}).get('identifier')
        current_list_name = task.get('list', {}).get('name')

        if current_list_id in default_list_ids:
            # Use default vault (Work)
            target_vault = "Work"  # Hardcode for testing

            if target_vault in vault_to_list_id:
                target_list_id = vault_to_list_id[target_vault]
                if target_list_id != current_list_id:
                    test_task = {
                        'task': task,
                        'task_id': task_id,
                        'title': task.get('description') or task.get('content', {}).get('title', ''),
                        'from_list': current_list_name,
                        'to_list': target_vault,
                        'to_list_id': target_list_id,
                        'external_ids': task.get('external_ids', {})
                    }
                    break

    if not test_task:
        print("❌ No test task found")
        return

    print(f"🎯 Test task selected:")
    print(f"   Title: {test_task['title']}")
    print(f"   From: {test_task['from_list']} ({test_task['task']['list']['identifier']})")
    print(f"   To: {test_task['to_list']} ({test_task['to_list_id']})")
    print(f"   External ID: {test_task['external_ids'].get('item')}")

    # Now attempt the migration
    try:
        print(f"\n🔄 Attempting migration...")

        # Initialize gateway
        gateway = RemindersGateway()

        # Get external IDs
        external_ids = test_task['external_ids']
        item_id = external_ids.get('item')

        if not item_id:
            print("❌ No external item ID")
            return

        print(f"   Step 1: Finding reminder {item_id}...")
        reminder = gateway.find_reminder_by_id(item_id)
        if not reminder:
            print("❌ Reminder not found")
            return
        print(f"   ✅ Found reminder: {reminder.title()}")

        print(f"   Step 2: Getting EventKit store...")
        store = gateway._get_store()
        print(f"   ✅ Got store")

        print(f"   Step 3: Finding target calendar {test_task['to_list_id']}...")
        calendars = store.calendarsForEntityType_(gateway._EKEntityTypeReminder) or []
        target_calendar = None

        for cal in calendars:
            if str(cal.calendarIdentifier()) == test_task['to_list_id']:
                target_calendar = cal
                break

        if not target_calendar:
            print(f"❌ Target calendar not found: {test_task['to_list_id']}")
            print("   Available calendars:")
            for cal in calendars:
                print(f"      - {cal.title()}: {cal.calendarIdentifier()}")
            return

        print(f"   ✅ Found target calendar: {target_calendar.title()}")

        print(f"   Step 4: Checking current calendar...")
        current_calendar = reminder.calendar()
        print(f"   Current calendar: {current_calendar.title()} ({current_calendar.calendarIdentifier()})")

        if str(current_calendar.calendarIdentifier()) == test_task['to_list_id']:
            print("   ⚠️  Task is already in target calendar!")
            return

        print(f"   Step 5: Moving reminder to target calendar...")
        reminder.setCalendar_(target_calendar)
        print(f"   ✅ setCalendar_() called successfully")

        print(f"   Step 6: Saving changes...")
        error = None
        success = store.saveReminder_commit_error_(reminder, True, error)

        if success:
            print(f"   ✅ Save successful!")
        else:
            print(f"   ❌ Save failed. Error: {error}")
            return

        print(f"   Step 7: Verifying migration...")
        # Re-fetch the reminder to verify
        updated_reminder = gateway.find_reminder_by_id(item_id)
        if updated_reminder:
            updated_calendar = updated_reminder.calendar()
            print(f"   New calendar: {updated_calendar.title()} ({updated_calendar.calendarIdentifier()})")

            if str(updated_calendar.calendarIdentifier()) == test_task['to_list_id']:
                print(f"   ✅ MIGRATION SUCCESSFUL!")
            else:
                print(f"   ❌ Migration failed - task is still in wrong calendar")
        else:
            print(f"   ❌ Could not re-fetch reminder for verification")

    except Exception as e:
        import traceback
        print(f"❌ Migration failed with error: {e}")
        print(f"Traceback:")
        traceback.print_exc()

if __name__ == "__main__":
    test_single_migration()