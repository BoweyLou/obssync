"""
Test that deduplicator properly cleans up sync links when deleting tasks.

This test verifies the fix for the bug where:
1. Sync creates a Reminders task with a link
2. Deduplicator deletes the Reminders task (duplicate)
3. Link remains orphaned (BUG) → now fixed
"""
import os
import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock

from obs_sync.core.models import (
    ObsidianTask,
    RemindersTask,
    TaskStatus,
    SyncLink,
)
from obs_sync.sync.deduplicator import TaskDeduplicator


def test_dedup_cleans_up_links():
    """Test that deduplicator removes links for deleted tasks."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        links_path = os.path.join(tmpdir, "sync_links.json")
        
        # Create initial links file with a link
        obs_uuid = "obs-phd-task-123"
        rem_uuid = "rem-phd-task-456"
        
        initial_links = {
            "links": [
                {
                    "obs_uuid": obs_uuid,
                    "rem_uuid": rem_uuid,
                    "score": 1.0,
                    "vault_id": "test-vault",
                    "last_synced": "2025-09-30T00:00:00Z",
                    "created_at": "2025-09-30T00:00:00Z"
                },
                {
                    "obs_uuid": "obs-other-task",
                    "rem_uuid": "rem-other-task",
                    "score": 1.0,
                    "vault_id": "test-vault",
                    "last_synced": "2025-09-30T00:00:00Z",
                    "created_at": "2025-09-30T00:00:00Z"
                }
            ]
        }
        
        with open(links_path, 'w') as f:
            json.dump(initial_links, f, indent=2)
        
        print(f"✅ Created links file with {len(initial_links['links'])} links")
        
        # Create a Reminders task to delete
        rem_task = RemindersTask(
            uuid=rem_uuid,
            item_id=rem_uuid,
            calendar_id="phd-calendar",
            list_name="PhD",
            status=TaskStatus.TODO,
            title="new write 10 words for your phd",
            due_date=None,
            priority=None,
            notes="",
            tags=["phd"],
            created_at="2025-09-30T00:00:00Z",
            modified_at="2025-09-30T00:00:00Z",
        )
        
        # Mock task managers
        obs_manager = Mock()
        rem_manager = Mock()
        rem_manager.delete_task.return_value = True  # Simulate successful deletion
        
        # Create deduplicator with links_path
        deduplicator = TaskDeduplicator(
            obs_manager=obs_manager,
            rem_manager=rem_manager,
            links_path=links_path
        )
        
        print(f"\n🗑️  Deleting task: {rem_task.title}")
        
        # Delete the task (this should trigger link cleanup)
        results = deduplicator.delete_tasks([rem_task], dry_run=False)
        
        print(f"   Reminders deleted: {results['rem_deleted']}")
        assert results["rem_deleted"] == 1, "Should delete 1 Reminders task"
        
        # Verify link was cleaned up
        with open(links_path, 'r') as f:
            updated_links = json.load(f)
        
        print(f"\n🔍 Checking links after deletion:")
        print(f"   Before: {len(initial_links['links'])} links")
        print(f"   After: {len(updated_links['links'])} links")
        
        # Should have only 1 link remaining (the "other" task)
        assert len(updated_links['links']) == 1, "Should have 1 link remaining"
        assert updated_links['links'][0]['obs_uuid'] == "obs-other-task", "Should keep unrelated link"
        assert updated_links['links'][0]['rem_uuid'] == "rem-other-task", "Should keep unrelated link"
        
        # The deleted task's link should be gone
        deleted_link_exists = any(
            link.get('rem_uuid') == rem_uuid for link in updated_links['links']
        )
        assert not deleted_link_exists, "Deleted task's link should be removed"
        
        print(f"\n✅ Link cleanup verified:")
        print(f"   - Deleted task's link removed")
        print(f"   - Unrelated link preserved")
        print(f"\n🎉 Test passed: Deduplicator properly cleans up orphaned links!")


def test_dedup_cleanup_both_obs_and_rem():
    """Test cleanup works for both Obsidian and Reminders deletions."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        links_path = os.path.join(tmpdir, "sync_links.json")
        
        # Create links
        initial_links = {
            "links": [
                {
                    "obs_uuid": "obs-dup-1",
                    "rem_uuid": "rem-dup-1",
                    "score": 1.0,
                    "vault_id": "test-vault",
                    "last_synced": "2025-09-30T00:00:00Z",
                    "created_at": "2025-09-30T00:00:00Z"
                },
                {
                    "obs_uuid": "obs-dup-2",
                    "rem_uuid": "rem-dup-2",
                    "score": 1.0,
                    "vault_id": "test-vault",
                    "last_synced": "2025-09-30T00:00:00Z",
                    "created_at": "2025-09-30T00:00:00Z"
                }
            ]
        }
        
        with open(links_path, 'w') as f:
            json.dump(initial_links, f, indent=2)
        
        # Create tasks to delete (one of each type)
        obs_task = ObsidianTask(
            uuid="obs-dup-1",
            vault_id="test-vault",
            vault_name="Test",
            vault_path="/tmp/test",
            file_path="test.md",
            line_number=1,
            block_id="abc",
            status=TaskStatus.TODO,
            description="Duplicate Obsidian task",
            raw_line="- [ ] Duplicate Obsidian task",
            due_date=None,
            completion_date=None,
            priority=None,
            tags=[],
            created_at="2025-09-30T00:00:00Z",
            modified_at="2025-09-30T00:00:00Z",
        )
        
        rem_task = RemindersTask(
            uuid="rem-dup-2",
            item_id="rem-dup-2",
            calendar_id="default",
            list_name="Default",
            status=TaskStatus.TODO,
            title="Duplicate Reminders task",
            due_date=None,
            priority=None,
            notes="",
            tags=[],
            created_at="2025-09-30T00:00:00Z",
            modified_at="2025-09-30T00:00:00Z",
        )
        
        # Mock managers
        obs_manager = Mock()
        rem_manager = Mock()
        obs_manager.delete_task.return_value = True
        rem_manager.delete_task.return_value = True
        
        deduplicator = TaskDeduplicator(
            obs_manager=obs_manager,
            rem_manager=rem_manager,
            links_path=links_path
        )
        
        print(f"\n🗑️  Deleting both Obsidian and Reminders tasks...")
        
        # Delete both tasks
        results = deduplicator.delete_tasks([obs_task, rem_task], dry_run=False)
        
        print(f"   Obsidian deleted: {results['obs_deleted']}")
        print(f"   Reminders deleted: {results['rem_deleted']}")
        
        assert results["obs_deleted"] == 1
        assert results["rem_deleted"] == 1
        
        # Verify both links were cleaned up
        with open(links_path, 'r') as f:
            updated_links = json.load(f)
        
        print(f"\n🔍 Links after deletion: {len(updated_links['links'])}")
        assert len(updated_links['links']) == 0, "Both links should be removed"
        
        print(f"\n✅ Both links cleaned up successfully!")
        print(f"\n🎉 Test passed!")


if __name__ == "__main__":
    try:
        print("="*70)
        print("TEST 1: Single Reminders task deletion with link cleanup")
        print("="*70)
        test_dedup_cleans_up_links()
        
        print("\n" + "="*70)
        print("TEST 2: Both Obsidian and Reminders deletion with link cleanup")
        print("="*70)
        test_dedup_cleanup_both_obs_and_rem()
        
        print("\n" + "="*70)
        print("🎉 ALL TESTS PASSED!")
        print("="*70)
        sys.exit(0)
        
    except Exception as e:
        print(f"\n💥 Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)