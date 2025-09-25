#!/usr/bin/env python3
"""
Multi-Vault Clean Slate Migration Script

Discovers all Obsidian vaults and runs clean slate migration across all of them.
"""

import os
import sys
import subprocess
import argparse
from typing import List, Dict, Tuple
from pathlib import Path

def discover_vaults(search_path: str) -> List[Dict[str, str]]:
    """Discover all Obsidian vaults in a directory tree."""
    vaults = []

    for root, dirs, files in os.walk(search_path):
        if '.obsidian' in dirs:
            vault_path = root
            vault_name = os.path.basename(vault_path)

            # Skip if this is a nested vault inside another vault
            parent_path = os.path.dirname(vault_path)
            is_nested = False
            while parent_path != search_path and parent_path != '/':
                if os.path.exists(os.path.join(parent_path, '.obsidian')):
                    is_nested = True
                    break
                parent_path = os.path.dirname(parent_path)

            if not is_nested:
                vaults.append({
                    'name': vault_name,
                    'path': vault_path,
                    'relative_path': os.path.relpath(vault_path, search_path)
                })

    return sorted(vaults, key=lambda x: x['name'])

def analyze_vault_block_ids(vault_path: str) -> Tuple[int, int, int]:
    """Analyze block IDs in a vault."""
    total_tasks = 0
    old_format_tasks = 0
    new_format_tasks = 0

    try:
        result = subprocess.run([
            'python3', 'strip_block_ids.py', vault_path, '--verbose'
        ], capture_output=True, text=True, timeout=60)

        # Parse the output to extract statistics
        lines = result.stdout.split('\n')
        for line in lines:
            if 'Total tasks found:' in line:
                total_tasks = int(line.split(':')[1].strip())
            elif 'WOULD STRIP:' in line and '^t-' in line:
                old_format_tasks += 1
            elif 'WOULD STRIP:' in line and '^' in line and '^t-' not in line:
                new_format_tasks += 1

    except Exception as e:
        print(f"  ❌ Error analyzing vault: {e}")

    return total_tasks, old_format_tasks, new_format_tasks

def run_vault_migration(vault_path: str, dry_run: bool = True) -> bool:
    """Run block ID stripping for a single vault."""
    try:
        cmd = ['python3', 'strip_block_ids.py', vault_path]
        if not dry_run:
            cmd.append('--apply')

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        if result.returncode == 0:
            return True
        else:
            print(f"    ❌ Migration failed: {result.stderr}")
            return False

    except Exception as e:
        print(f"    ❌ Error running migration: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Multi-vault clean slate migration')
    parser.add_argument('--search-path',
                       default='/Users/yannickbowe/Library/Mobile Documents/iCloud~md~obsidian/Documents',
                       help='Path to search for Obsidian vaults')
    parser.add_argument('--apply', action='store_true',
                       help='Apply changes (default is dry-run)')
    parser.add_argument('--vault-filter',
                       help='Only process vaults containing this string in their name')

    args = parser.parse_args()

    if not os.path.exists(args.search_path):
        print(f"❌ Search path does not exist: {args.search_path}")
        return 1

    dry_run = not args.apply

    print("🔍 Multi-Vault Clean Slate Migration")
    print("=" * 60)
    print(f"📁 Search path: {args.search_path}")
    print(f"🔄 Mode: {'DRY RUN' if dry_run else 'APPLY CHANGES'}")
    if args.vault_filter:
        print(f"🔍 Filter: {args.vault_filter}")
    print()

    # Discover vaults
    print("🔍 Discovering Obsidian vaults...")
    vaults = discover_vaults(args.search_path)

    if not vaults:
        print("❌ No Obsidian vaults found!")
        return 1

    # Filter vaults if requested
    if args.vault_filter:
        vaults = [v for v in vaults if args.vault_filter.lower() in v['name'].lower()]
        if not vaults:
            print(f"❌ No vaults found matching filter: {args.vault_filter}")
            return 1

    print(f"📊 Found {len(vaults)} vault(s):")
    for vault in vaults:
        print(f"  • {vault['name']} ({vault['relative_path']})")
    print()

    # Analyze each vault
    print("📊 Analyzing vaults for block IDs...")
    vault_stats = []

    for vault in vaults:
        print(f"📝 Analyzing: {vault['name']}")
        total, old_format, new_format = analyze_vault_block_ids(vault['path'])

        vault_stats.append({
            'vault': vault,
            'total_tasks': total,
            'old_format': old_format,
            'new_format': new_format,
            'needs_cleaning': (old_format + new_format) > 0
        })

        print(f"  📈 Tasks: {total} total, {old_format + new_format} with block IDs")
        if old_format > 0:
            print(f"    🔴 Old format (^t-...): {old_format}")
        if new_format > 0:
            print(f"    🟡 New format (^...): {new_format}")
        if total == 0:
            print(f"    ✅ No tasks found")
        elif old_format + new_format == 0:
            print(f"    ✅ No block IDs to clean")

    print()

    # Summary
    vaults_needing_cleaning = [v for v in vault_stats if v['needs_cleaning']]
    total_tasks_with_blocks = sum(v['old_format'] + v['new_format'] for v in vault_stats)

    print("📊 MIGRATION SUMMARY:")
    print(f"  Total vaults: {len(vaults)}")
    print(f"  Vaults needing cleaning: {len(vaults_needing_cleaning)}")
    print(f"  Total block IDs to remove: {total_tasks_with_blocks}")

    if total_tasks_with_blocks == 0:
        print("✅ All vaults are already clean - no migration needed!")
        return 0

    print()

    # Run migration
    if dry_run:
        print("🔍 DRY RUN RESULTS:")
        for stat in vault_stats:
            if stat['needs_cleaning']:
                vault_name = stat['vault']['name']
                block_count = stat['old_format'] + stat['new_format']
                print(f"  📝 {vault_name}: Would clean {block_count} block IDs")

        print(f"\n💡 Run with --apply to execute the migration")
        print(f"💡 Use --vault-filter 'name' to process specific vaults only")

    else:
        print("🧹 EXECUTING MIGRATION:")

        success_count = 0
        for stat in vault_stats:
            if not stat['needs_cleaning']:
                continue

            vault = stat['vault']
            vault_name = vault['name']
            block_count = stat['old_format'] + stat['new_format']

            print(f"\n📝 Migrating: {vault_name} ({block_count} block IDs)")
            success = run_vault_migration(vault['path'], dry_run=False)

            if success:
                print(f"    ✅ Successfully cleaned {vault_name}")
                success_count += 1
            else:
                print(f"    ❌ Failed to clean {vault_name}")

        print(f"\n📊 MIGRATION RESULTS:")
        print(f"  Successful: {success_count}/{len(vaults_needing_cleaning)}")

        if success_count == len(vaults_needing_cleaning):
            print(f"🎉 All vaults successfully migrated!")
            print(f"\n🔄 Next steps:")
            print(f"  1. Clear sync links: python3 clean_reminders_simple.py --clear-sync-links")
            print(f"  2. Clean Apple Reminders lists manually")
            print(f"  3. Run fresh sync: python3 obs_tools.py sync --apply")
        else:
            print(f"⚠️  Some vaults failed migration. Check errors above.")
            return 1

    return 0

if __name__ == '__main__':
    exit(main())