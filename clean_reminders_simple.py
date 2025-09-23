#!/usr/bin/env python3
"""
Simple Apple Reminders Cleanup Script

Since the RemindersGateway doesn't have a delete method, this script provides
guidance on manually cleaning Apple Reminders and clearing sync links.
"""

import json
import os
import argparse
from typing import Dict, Any
from pathlib import Path

# Import PathManager for centralized path management
try:
    from obs_sync.core.paths import get_path_manager
    USE_PATH_MANAGER = True
except ImportError:
    # Fallback if obs_sync is not in path
    USE_PATH_MANAGER = False
    print("⚠️  Warning: PathManager not available, using legacy paths")

def get_sync_links_path() -> Path:
    """Get the sync links file path using PathManager or fallback to legacy."""
    if USE_PATH_MANAGER:
        manager = get_path_manager()
        # Try to find existing sync links file with fallback
        existing_file = manager.get_file_with_fallback("sync_links.json")
        if existing_file and existing_file.exists():
            return existing_file
        # Default to new location if no existing file
        return manager.sync_links_path
    else:
        # Legacy fallback
        return Path.home() / ".config" / "sync_links.json"

def read_sync_links() -> Dict[str, Any]:
    """Read the current sync links."""
    sync_links_path = get_sync_links_path()

    if not sync_links_path.exists():
        return {"links": []}

    try:
        with open(sync_links_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Error reading sync links: {e}")
        return {"links": []}

def clear_sync_links(backup: bool = True) -> bool:
    """Clear the sync links file."""
    sync_links_path = get_sync_links_path()

    if not sync_links_path.exists():
        print("✅ No sync links file found - already clean!")
        return True

    try:
        # Backup if requested
        if backup:
            backup_path = sync_links_path.with_suffix(f"{sync_links_path.suffix}.backup")
            with open(sync_links_path, 'r') as src:
                with open(backup_path, 'w') as dst:
                    dst.write(src.read())
            print(f"💾 Backed up sync links to: {backup_path}")

        # Clear the file
        with open(sync_links_path, 'w') as f:
            json.dump({"links": []}, f, indent=2)

        print(f"✅ Cleared sync links file: {sync_links_path}")
        
        # If using PathManager, note if this was a legacy location
        if USE_PATH_MANAGER:
            manager = get_path_manager()
            if sync_links_path.parent == Path.home() / ".config":
                print(f"📝 Note: Cleared legacy location. New syncs will use: {manager.sync_links_path}")
        
        return True

    except Exception as e:
        print(f"❌ Error clearing sync links: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Clean slate migration helper')
    parser.add_argument('--clear-sync-links', action='store_true',
                       help='Clear the sync links file')
    parser.add_argument('--no-backup', action='store_true',
                       help='Don\'t backup sync links when clearing')
    parser.add_argument('--show-links', action='store_true',
                       help='Show current sync links')
    parser.add_argument('--show-path', action='store_true',
                       help='Show the path to sync links file')

    args = parser.parse_args()

    print("🧹 Clean Slate Migration Helper")
    print("=" * 50)

    # Show sync links path if requested
    if args.show_path:
        sync_links_path = get_sync_links_path()
        print(f"📁 Sync links location: {sync_links_path}")
        if USE_PATH_MANAGER:
            manager = get_path_manager()
            print(f"📂 Working directory: {manager.working_dir}")
            # Check for legacy files
            has_legacy, legacy_files = manager.get_legacy_files()
            if has_legacy:
                print(f"📋 Legacy files found:")
                for name, path in legacy_files.items():
                    print(f"   - {name}: {path}")
        print()

    # Show current sync links
    if args.show_links or not any([args.clear_sync_links, args.show_path]):
        sync_data = read_sync_links()
        links = sync_data.get("links", [])

        print(f"📊 Current sync links: {len(links)}")
        print(f"📁 Location: {get_sync_links_path()}")

        if links:
            print("\n🔗 Sync Links:")
            for i, link in enumerate(links, 1):
                obs_uuid = link.get("obs_uuid", "unknown")
                rem_uuid = link.get("rem_uuid", "unknown")
                score = link.get("score", 0)
                print(f"  {i:2d}. {obs_uuid} ↔ {rem_uuid[:8]}... (score: {score:.3f})")
        else:
            print("✅ No sync links found")

    # Clear sync links if requested
    if args.clear_sync_links:
        print(f"\n🗑️  Clearing sync links...")
        success = clear_sync_links(backup=not args.no_backup)
        if not success:
            return 1

    # Provide manual cleanup instructions
    if not args.show_path:
        print(f"\n📋 Manual Cleanup Instructions:")
        print(f"=" * 50)

        print(f"📱 Apple Reminders:")
        print(f"  1. Open Apple Reminders app")
        print(f"  2. Navigate to the 'Vault' list")
        print(f"  3. Select all tasks (Cmd+A)")
        print(f"  4. Delete them (Delete key or right-click > Delete)")
        print(f"  5. Empty the trash if needed")

        print(f"\n📝 Obsidian Vault:")
        print(f"  Option 1 - Use the strip script:")
        print(f"    python3 strip_block_ids.py '/path/to/vault' --apply")
        print(f"  Option 2 - Manual cleanup:")
        print(f"    • Find all tasks with ^block-id patterns")
        print(f"    • Remove the ^block-id portion from each task line")
        print(f"    • Leave the rest of the task intact")

        print(f"\n🔄 After cleanup:")
        print(f"  1. Run: python3 obs_tools.py sync")
        print(f"  2. This will create fresh sync links with deterministic UUIDs")
        print(f"  3. Future syncs should be stable without orphan deletions")

    return 0

if __name__ == '__main__':
    exit(main())