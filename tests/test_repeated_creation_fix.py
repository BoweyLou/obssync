#!/usr/bin/env python3
"""
Test that the repeated creation issue is fixed for URL-only tasks.

This directly tests the reported issue where dry-run syncs would repeatedly
log "Creating Reminders/Obsidian task for" the same URL-only tasks.
"""

import os
import sys
import json
from datetime import datetime, timezone

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from obs_sync.core.models import ObsidianTask, RemindersTask, TaskStatus, SyncLink
from obs_sync.sync.matcher import TaskMatcher


def simulate_sync_matching():
    """
    Simulate the sync matching process for URL-only tasks.
    This reproduces the exact scenario that was causing repeated creation logs.
    """
    print("🧪 Testing Fix for Repeated Creation Issue")
    print("=" * 60)
    
    # Create matcher with default config
    matcher = TaskMatcher(min_score=0.75)
    
    # Simulate Obsidian tasks including URL-only ones (common case)
    obs_tasks = [
        ObsidianTask(
            uuid="obs-url-001",
            vault_id="vault1",
            vault_name="Work",
            vault_path="/path/to/vault",
            file_path="daily/2024-01-15.md",
            line_number=10,
            block_id=None,
            status=TaskStatus.TODO,
            description="https://github.com/user/repo/issues/123",
            raw_line="- [ ] https://github.com/user/repo/issues/123",
            due_date=None,
            completion_date=None,
            priority=None,
            tags=[],
            created_at=datetime.now(timezone.utc).isoformat(),
            modified_at=datetime.now(timezone.utc).isoformat()
        ),
        ObsidianTask(
            uuid="obs-hash-002",
            vault_id="vault1",
            vault_name="Work",
            vault_path="/path/to/vault",
            file_path="daily/2024-01-15.md",
            line_number=11,
            block_id=None,
            status=TaskStatus.TODO,
            description="#",
            raw_line="- [ ] #",
            due_date=None,
            completion_date=None,
            priority=None,
            tags=[],
            created_at=datetime.now(timezone.utc).isoformat(),
            modified_at=datetime.now(timezone.utc).isoformat()
        ),
        ObsidianTask(
            uuid="obs-normal-003",
            vault_id="vault1",
            vault_name="Work",
            vault_path="/path/to/vault",
            file_path="daily/2024-01-15.md",
            line_number=12,
            block_id=None,
            status=TaskStatus.TODO,
            description="Review pull request",
            raw_line="- [ ] Review pull request",
            due_date=None,
            completion_date=None,
            priority=None,
            tags=[],
            created_at=datetime.now(timezone.utc).isoformat(),
            modified_at=datetime.now(timezone.utc).isoformat()
        )
    ]
    
    # Simulate matching Reminders tasks (after initial sync)
    rem_tasks = [
        RemindersTask(
            uuid="rem-url-001",
            item_id="item1",
            calendar_id="cal1",
            list_name="Work",
            status=TaskStatus.TODO,
            title="https://github.com/user/repo/issues/123",
            due_date=None,
            priority=None,
            notes="Created from Obsidian",
            created_at=datetime.now(timezone.utc).isoformat(),
            modified_at=datetime.now(timezone.utc).isoformat()
        ),
        RemindersTask(
            uuid="rem-hash-002",
            item_id="item2",
            calendar_id="cal1",
            list_name="Work",
            status=TaskStatus.TODO,
            title="#",
            due_date=None,
            priority=None,
            notes="Created from Obsidian",
            created_at=datetime.now(timezone.utc).isoformat(),
            modified_at=datetime.now(timezone.utc).isoformat()
        ),
        RemindersTask(
            uuid="rem-normal-003",
            item_id="item3",
            calendar_id="cal1",
            list_name="Work",
            status=TaskStatus.TODO,
            title="Review pull request",
            due_date=None,
            priority=None,
            notes="Created from Obsidian",
            created_at=datetime.now(timezone.utc).isoformat(),
            modified_at=datetime.now(timezone.utc).isoformat()
        )
    ]
    
    # Simulate existing links (from previous sync)
    existing_links = []
    
    print("\n📝 Initial State:")
    print(f"  Obsidian tasks: {len(obs_tasks)}")
    print(f"  Reminders tasks: {len(rem_tasks)}")
    print(f"  Existing links: {len(existing_links)}")
    
    # Run matching (this is what happens during sync)
    print("\n🔄 Running Sync Matching...")
    links = matcher.find_matches(obs_tasks, rem_tasks, existing_links)
    
    print(f"\n📊 Matching Results:")
    print(f"  Links found: {len(links)}")
    
    # Track which tasks got matched
    matched_obs = {link.obs_uuid for link in links}
    matched_rem = {link.rem_uuid for link in links}
    
    unmatched_obs = [t for t in obs_tasks if t.uuid not in matched_obs]
    unmatched_rem = [t for t in rem_tasks if t.uuid not in matched_rem]
    
    print(f"  Unmatched Obsidian tasks: {len(unmatched_obs)}")
    print(f"  Unmatched Reminders tasks: {len(unmatched_rem)}")
    
    # Show details of matches
    print("\n🔗 Match Details:")
    for link in links:
        obs = next(t for t in obs_tasks if t.uuid == link.obs_uuid)
        rem = next(t for t in rem_tasks if t.uuid == link.rem_uuid)
        desc = obs.description[:30] + "..." if len(obs.description) > 30 else obs.description
        print(f"  ✅ Matched: '{desc}' (score: {link.score:.3f})")
    
    # Show unmatched (these would trigger creation logs)
    if unmatched_obs:
        print("\n⚠️  Unmatched Obsidian tasks (would create in Reminders):")
        for task in unmatched_obs:
            desc = task.description[:50] + "..." if len(task.description) > 50 else task.description
            print(f"  - '{desc}'")
    
    if unmatched_rem:
        print("\n⚠️  Unmatched Reminders tasks (would create in Obsidian):")
        for task in unmatched_rem:
            title = task.title[:50] + "..." if len(task.title) > 50 else task.title
            print(f"  - '{title}'")
    
    # Verify the fix worked
    print("\n" + "=" * 60)
    
    success = True
    
    # Check URL task matched correctly
    url_matched = any(
        link for link in links 
        if link.obs_uuid == "obs-url-001" and link.rem_uuid == "rem-url-001"
    )
    if url_matched:
        print("✅ URL-only task matched correctly (no repeated creation)")
    else:
        print("❌ URL-only task failed to match (would cause repeated creation)")
        success = False
    
    # Check # task matched correctly
    hash_matched = any(
        link for link in links 
        if link.obs_uuid == "obs-hash-002" and link.rem_uuid == "rem-hash-002"
    )
    if hash_matched:
        print("✅ Single '#' task matched correctly (no repeated creation)")
    else:
        print("❌ Single '#' task failed to match (would cause repeated creation)")
        success = False
    
    # Check normal task matched
    normal_matched = any(
        link for link in links 
        if link.obs_uuid == "obs-normal-003" and link.rem_uuid == "rem-normal-003"
    )
    if normal_matched:
        print("✅ Normal text task matched correctly")
    else:
        print("❌ Normal text task failed to match")
        success = False
    
    # Overall result
    if len(unmatched_obs) == 0 and len(unmatched_rem) == 0:
        print("\n🎉 SUCCESS: No unmatched tasks - repeated creation issue is FIXED!")
    else:
        print(f"\n⚠️  WARNING: {len(unmatched_obs)} Obsidian and {len(unmatched_rem)} Reminders tasks unmatched")
        print("   These would cause repeated 'Creating task' logs on each dry-run")
        success = False
    
    return success


def main():
    """Run the repeated creation fix test."""
    print("=" * 60)
    print("🚀 Testing Fix for Repeated Task Creation Issue")
    print("=" * 60)
    print("\nContext: Testing that URL-only and minimal tasks now match")
    print("correctly to prevent repeated 'Creating task' logs in dry-run mode.")
    
    try:
        success = simulate_sync_matching()
        
        if success:
            print("\n" + "=" * 60)
            print("✅ ALL TESTS PASSED - Repeated creation issue is FIXED!")
            print("=" * 60)
            print("\n📝 Summary:")
            print("  • URL-only tasks now match correctly")
            print("  • Single '#' tasks now match correctly")  
            print("  • No false 'Creating task' logs on repeated dry-runs")
            print("  • Your sync should now be stable!")
            return 0
        else:
            print("\n" + "=" * 60)
            print("❌ TEST FAILED - Issue may persist")
            print("=" * 60)
            return 1
            
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())