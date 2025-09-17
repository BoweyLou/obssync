#!/usr/bin/env python3
"""
Debug script to test migration logic step by step
"""

import json
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from obs_tools.commands.collect_reminders_tasks import main as collect_reminders
from reminders_gateway import RemindersGateway
from app_config import get_path

def debug_migration():
    print("🔍 Debug Migration Logic")
    print("=" * 50)

    # Step 1: Load current data
    print("\n1. Loading configuration...")

    # Load vault config
    try:
        with open(get_path("obsidian_vaults"), 'r') as f:
            vault_config = json.load(f)
        print(f"   ✅ Loaded {len(vault_config)} vaults")
        for vault in vault_config:
            print(f"      - {vault['name']}: {vault['path']}")
    except Exception as e:
        print(f"   ❌ Failed to load vaults: {e}")
        return

    # Load reminders config
    try:
        with open(get_path("reminders_lists"), 'r') as f:
            reminders_config = json.load(f)
        print(f"   ✅ Loaded {len(reminders_config)} reminder lists")
        for lst in reminders_config[:5]:  # Show first 5
            print(f"      - {lst['name']}: {lst['identifier']}")
    except Exception as e:
        print(f"   ❌ Failed to load reminders lists: {e}")
        return

    # Step 2: Collect current reminders
    print("\n2. Collecting current reminders...")
    temp_file = "/tmp/debug_reminders.json"

    try:
        collect_result = collect_reminders([
            "--use-config",
            "--config", get_path("reminders_lists"),
            "--output", temp_file
        ])

        if collect_result != 0:
            print("   ❌ Failed to collect reminders")
            return

        with open(temp_file, 'r') as f:
            reminders_data = json.load(f)

        tasks = reminders_data.get('tasks', {})
        print(f"   ✅ Collected {len(tasks)} tasks")

    except Exception as e:
        print(f"   ❌ Failed to collect reminders: {e}")
        return

    # Step 3: Analyze vault-list mappings
    print("\n3. Analyzing vault-list mappings...")

    vault_to_list_id = {}
    list_name_to_id = {lst["name"]: lst["identifier"] for lst in reminders_config}

    print("   Available lists:")
    for name, id in list_name_to_id.items():
        print(f"      - {name}: {id}")

    print("   Vault mappings:")
    for vault in vault_config:
        vault_name = vault["name"]
        if vault_name in list_name_to_id:
            vault_to_list_id[vault_name] = list_name_to_id[vault_name]
            print(f"      ✅ {vault_name} → {vault_name} list ({list_name_to_id[vault_name]})")
        else:
            print(f"      ❌ {vault_name} → NO MATCHING LIST")

    # Step 4: Find tasks that need migration
    print("\n4. Finding tasks to migrate...")

    # Find default lists
    default_list_ids = set()
    default_list_names = ["Reminders", "Tasks"]

    for lst in reminders_config:
        if lst["name"] in default_list_names:
            default_list_ids.add(lst["identifier"])
            print(f"   Default list: {lst['name']} ({lst['identifier']})")

    tasks_to_migrate = []
    tasks_analyzed = 0

    print(f"\n   Analyzing {len(tasks)} tasks...")

    for task_id, task in tasks.items():
        tasks_analyzed += 1
        if tasks_analyzed > 100:  # Limit for debugging
            break

        current_list_id = task.get('list', {}).get('identifier')
        current_list_name = task.get('list', {}).get('name')

        # Check if task is in a default list
        if current_list_id in default_list_ids:
            task_title = task.get('content', {}).get('title', '').lower()

            # Look for vault name mentions
            target_vault = None
            for vault_name in vault_to_list_id.keys():
                if vault_name.lower() in task_title:
                    target_vault = vault_name
                    break

            # If no specific match, use default (Work vault)
            if not target_vault:
                # Find default vault
                for vault in vault_config:
                    if vault.get("is_default"):
                        target_vault = vault["name"]
                        break

            if target_vault and target_vault in vault_to_list_id:
                target_list_id = vault_to_list_id[target_vault]
                if target_list_id != current_list_id:
                    tasks_to_migrate.append({
                        'task_id': task_id,
                        'title': task.get('content', {}).get('title', ''),
                        'from_list': current_list_name,
                        'to_list': target_vault,
                        'to_list_id': target_list_id,
                        'external_ids': task.get('external_ids', {})
                    })

    print(f"   ✅ Found {len(tasks_to_migrate)} tasks to migrate (from {tasks_analyzed} analyzed)")

    # Show first few tasks to migrate
    print("\n5. Tasks to migrate (first 5):")
    for i, migration in enumerate(tasks_to_migrate[:5]):
        print(f"   {i+1}. '{migration['title'][:50]}...'")
        print(f"      From: {migration['from_list']} → To: {migration['to_list']}")
        print(f"      External ID: {migration['external_ids'].get('item', 'None')}")

    # Step 6: Test EventKit access
    print("\n6. Testing EventKit access...")

    try:
        gateway = RemindersGateway()
        lists = gateway.get_reminder_lists()
        print(f"   ✅ EventKit access successful - found {len(lists)} lists")

        # Test finding a specific reminder
        if tasks_to_migrate:
            test_task = tasks_to_migrate[0]
            item_id = test_task['external_ids'].get('item')

            if item_id:
                print(f"   Testing reminder lookup for ID: {item_id}")
                reminder = gateway.find_reminder_by_id(item_id)
                if reminder:
                    print(f"   ✅ Found reminder: {reminder.title()}")
                else:
                    print(f"   ❌ Reminder not found")
            else:
                print(f"   ⚠️  No external ID available for testing")

    except Exception as e:
        print(f"   ❌ EventKit access failed: {e}")
        return

    print(f"\n📊 Summary:")
    print(f"   - Vaults: {len(vault_config)}")
    print(f"   - Reminder lists: {len(reminders_config)}")
    print(f"   - Total tasks: {len(tasks)}")
    print(f"   - Tasks to migrate: {len(tasks_to_migrate)}")
    print(f"   - Default list task count: {sum(1 for t in tasks.values() if t.get('list', {}).get('identifier') in default_list_ids)}")

if __name__ == "__main__":
    debug_migration()