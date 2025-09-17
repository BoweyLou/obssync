#!/usr/bin/env python3
"""
Priority Migration Utility for ObsSync v2.0

This script handles the migration of reminder priorities from the old mapping
to the new Apple-native priority scheme introduced in v2.0.

BREAKING CHANGE: Priority values inverted in v2.0
- Old mapping: high=9, medium=5, low=1
- New mapping: high=1, medium=5, low=9

This utility will:
1. Scan existing reminders for priority values
2. Identify reminders that need migration
3. Convert priorities to maintain intended priority levels
4. Provide dry-run and apply modes for safe migration
"""

import json
import sys
import os
from typing import Dict, List, Tuple, Optional
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from reminders_gateway import RemindersGateway
    from app_config import get_path
except ImportError as e:
    print(f"Warning: Could not import required modules: {e}")
    print("This migration script requires the ObsSync environment to be properly set up.")


# Priority mapping conversion
OLD_TO_NEW_PRIORITY = {
    9: 1,  # old high → new high
    5: 5,  # medium unchanged
    1: 9,  # old low → new low
    0: 0   # no priority unchanged
}

NEW_TO_OLD_PRIORITY = {v: k for k, v in OLD_TO_NEW_PRIORITY.items()}


def analyze_reminder_priorities() -> Tuple[Dict[str, int], int]:
    """
    Analyze current reminder priorities to identify migration candidates.

    Returns:
        - Dict of reminder_id -> current_priority for items needing migration
        - Total count of reminders analyzed
    """
    print("🔍 Analyzing reminder priorities...")

    try:
        gateway = RemindersGateway()
        store = gateway._get_store()

        # Get all calendars
        calendars = store.calendarsForEntityType_(gateway._EKEntityTypeReminder) or []
        print(f"Found {len(calendars)} reminder lists")

        total_reminders = 0
        migration_candidates = {}
        priority_counts = {0: 0, 1: 0, 5: 0, 9: 0}

        for calendar in calendars:
            # Get reminders from this calendar
            predicate = store.predicateForRemindersInCalendars_([calendar])
            reminders = []

            def completion_handler(found_reminders):
                nonlocal reminders
                reminders = list(found_reminders or [])

            store.fetchRemindersMatchingPredicate_completion_(predicate, completion_handler)

            # Process reminders
            for reminder in reminders:
                total_reminders += 1
                priority = int(reminder.priority())

                # Count priority distribution
                if priority in priority_counts:
                    priority_counts[priority] += 1
                else:
                    priority_counts[priority] = priority_counts.get(priority, 0) + 1

                # Check if this reminder needs migration
                # Reminders with old high (9) or old low (1) priority need conversion
                if priority in [1, 9]:
                    item_id = reminder.calendarItemIdentifier()
                    if item_id:
                        migration_candidates[item_id] = priority

        print(f"\n📊 Priority Distribution Analysis:")
        print(f"  Total reminders analyzed: {total_reminders}")
        print(f"  No priority (0): {priority_counts.get(0, 0)}")
        print(f"  High priority (1): {priority_counts.get(1, 0)}")
        print(f"  Medium priority (5): {priority_counts.get(5, 0)}")
        print(f"  Low priority (9): {priority_counts.get(9, 0)}")

        if migration_candidates:
            print(f"\n⚠️  Migration needed for {len(migration_candidates)} reminders:")
            print(f"  - High priority (1→9): {sum(1 for p in migration_candidates.values() if p == 1)}")
            print(f"  - Low priority (9→1): {sum(1 for p in migration_candidates.values() if p == 9)}")
        else:
            print(f"\n✅ No priority migration needed!")

        return migration_candidates, total_reminders

    except Exception as e:
        print(f"❌ Error analyzing priorities: {e}")
        return {}, 0


def migrate_priorities(candidates: Dict[str, int], dry_run: bool = True) -> Tuple[int, int]:
    """
    Migrate reminder priorities from old to new mapping.

    Args:
        candidates: Dict of reminder_id -> old_priority
        dry_run: If True, only simulate the migration

    Returns:
        Tuple of (successful_migrations, failed_migrations)
    """
    if not candidates:
        print("✅ No priorities to migrate")
        return 0, 0

    mode_str = "DRY RUN" if dry_run else "LIVE MIGRATION"
    print(f"\n🔄 Starting Priority Migration ({mode_str})")
    print(f"{'='*50}")

    try:
        gateway = RemindersGateway()
        store = gateway._get_store()

        successful = 0
        failed = 0

        for reminder_id, old_priority in candidates.items():
            new_priority = OLD_TO_NEW_PRIORITY.get(old_priority, old_priority)

            try:
                # Find the reminder
                reminder = gateway.find_reminder_by_id(reminder_id)
                if not reminder:
                    print(f"  ❌ Reminder not found: {reminder_id}")
                    failed += 1
                    continue

                title = str(reminder.title() or "Untitled")[:50]

                if dry_run:
                    print(f"  📋 Would migrate: '{title}' priority {old_priority} → {new_priority}")
                    successful += 1
                else:
                    # Actually update the priority
                    reminder.setPriority_(new_priority)
                    success, error = store.saveReminder_commit_error_(reminder, True, None)

                    if success and not error:
                        print(f"  ✅ Migrated: '{title}' priority {old_priority} → {new_priority}")
                        successful += 1
                    else:
                        error_msg = f"Save failed: {error}" if error else "Unknown save error"
                        print(f"  ❌ Failed: '{title}' - {error_msg}")
                        failed += 1

            except Exception as e:
                print(f"  ❌ Error migrating {reminder_id}: {e}")
                failed += 1

        print(f"\n📊 Migration Results:")
        print(f"  ✅ Successful: {successful}")
        print(f"  ❌ Failed: {failed}")
        print(f"  📈 Success rate: {successful/(successful+failed)*100:.1f}%" if (successful+failed) > 0 else "N/A")

        return successful, failed

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return 0, len(candidates)


def main():
    """Main entry point for priority migration."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Migrate reminder priorities from v1.x to v2.0 mapping",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze current priorities (dry run)
  python priority_migration.py --analyze

  # Simulate migration
  python priority_migration.py --migrate --dry-run

  # Perform actual migration
  python priority_migration.py --migrate --apply

  # Full workflow
  python priority_migration.py --analyze --migrate --apply
"""
    )

    parser.add_argument("--analyze", action="store_true",
                       help="Analyze current reminder priorities")
    parser.add_argument("--migrate", action="store_true",
                       help="Perform priority migration")
    parser.add_argument("--dry-run", action="store_true", default=True,
                       help="Simulate migration without making changes (default)")
    parser.add_argument("--apply", action="store_true",
                       help="Actually perform migration (overrides --dry-run)")

    args = parser.parse_args()

    # Determine mode
    dry_run = not args.apply

    print("🔄 ObsSync Priority Migration Utility")
    print("=" * 40)
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE MIGRATION'}")
    print()

    # Default to analyze if no specific action
    if not (args.analyze or args.migrate):
        args.analyze = True

    candidates = {}
    total_analyzed = 0

    # Analysis phase
    if args.analyze:
        candidates, total_analyzed = analyze_reminder_priorities()

        if not candidates:
            print("\n✅ No migration needed. All priorities are already v2.0 compatible!")
            return 0

    # Migration phase
    if args.migrate:
        if not candidates and not args.analyze:
            # Need to analyze first if not already done
            print("Analyzing priorities before migration...")
            candidates, total_analyzed = analyze_reminder_priorities()

        if candidates:
            if not args.apply:
                print(f"\n⚠️  This is a DRY RUN. Use --apply to perform actual migration.")

            successful, failed = migrate_priorities(candidates, dry_run)

            if not dry_run and failed == 0:
                print(f"\n🎉 Priority migration completed successfully!")
                print(f"All {successful} reminders have been updated to v2.0 priority scheme.")
            elif failed > 0:
                print(f"\n⚠️  Migration completed with {failed} failures.")
                print(f"You may need to manually review and fix the failed reminders.")
                return 1
        else:
            print("\n✅ No migration needed!")

    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n❌ Migration cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)