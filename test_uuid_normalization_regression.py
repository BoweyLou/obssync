"""Test for UUID normalization regression fix.

This test verifies that the sync engine correctly normalizes legacy links
with temporary UUIDs to match the new stable hash-based UUIDs for tasks
without block IDs, preventing false orphan detection.
"""

import os
import sys
import tempfile
import json
from pathlib import Path
from datetime import datetime, timezone

# Add the parent directory to the path so we can import obs_sync
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from obs_sync.obsidian.tasks import ObsidianTaskManager
from obs_sync.sync.engine import SyncEngine
from obs_sync.core.models import ObsidianTask, RemindersTask, TaskStatus, SyncLink
from obs_sync.core.paths import get_path_manager


def test_uuid_normalization_no_false_orphans():
    """Test that UUID normalization prevents false orphan detection."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir) / "test_vault"
        vault_path.mkdir()
        
        # Create test markdown file with tasks (no block IDs)
        test_file = vault_path / "tasks.md"
        test_file.write_text("""# Test Tasks

- [ ] Task without block ID 1
- [ ] Task without block ID 2
- [ ] Task without block ID 3
""")
        
        # Initialize managers
        obs_manager = ObsidianTaskManager()
        
        # List tasks - these will have stable hash-based UUIDs
        obs_tasks = obs_manager.list_tasks(str(vault_path))
        
        print(f"Found {len(obs_tasks)} Obsidian tasks:")
        for task in obs_tasks:
            print(f"  - UUID: {task.uuid}, Block ID: {task.block_id}, Desc: {task.description[:30]}")
        
        # Create mock Reminders tasks
        rem_tasks = []
        for i, obs_task in enumerate(obs_tasks):
            rem_task = RemindersTask(
                uuid=f"rem-{i+1}",
                item_id=f"rem-item-{i+1}",
                calendar_id="test-calendar",
                list_name="Test List",
                status=TaskStatus.TODO,
                title=obs_task.description,
                created_at=datetime.now(timezone.utc).isoformat(),
                modified_at=datetime.now(timezone.utc).isoformat()
            )
            rem_tasks.append(rem_task)
        
        print(f"\nCreated {len(rem_tasks)} Reminders tasks")
        
        # Simulate legacy links with temporary UUIDs (pre-normalization)
        legacy_links = []
        for i, (obs_task, rem_task) in enumerate(zip(obs_tasks, rem_tasks)):
            # Create a legacy link with a temporary UUID instead of the stable one
            legacy_link = SyncLink(
                obs_uuid=f"obs-temp-{i+1:08d}",  # Old temporary UUID format
                rem_uuid=rem_task.uuid,
                score=1.0,
                last_synced=datetime.now(timezone.utc).isoformat(),
                created_at=datetime.now(timezone.utc).isoformat()
            )
            legacy_links.append(legacy_link)
        
        print(f"\nCreated {len(legacy_links)} legacy links with temp UUIDs:")
        for link in legacy_links:
            print(f"  - {link.obs_uuid} <-> {link.rem_uuid}")
        
        # Create a mock sync engine to test normalization
        config = {
            "min_score": 0.75,
            "days_tolerance": 1
        }
        
        engine = SyncEngine(config)
        
        # Test normalization
        print("\n=== Testing Link Normalization ===")
        normalized_links = engine._normalize_links(legacy_links, obs_tasks, rem_tasks)
        
        print(f"\nNormalized {len(normalized_links)} links:")
        for link in normalized_links:
            print(f"  - {link.obs_uuid} <-> {link.rem_uuid}")
        
        # Verify that links were normalized to use the stable UUIDs
        normalized_uuids = {link.obs_uuid for link in normalized_links}
        actual_uuids = {task.uuid for task in obs_tasks}
        
        assert normalized_uuids == actual_uuids, \
            f"Normalization failed: normalized UUIDs {normalized_uuids} != actual UUIDs {actual_uuids}"
        
        print("\n✓ All links successfully normalized to stable UUIDs")
        
        # Test orphan detection with normalized links
        print("\n=== Testing Orphan Detection ===")
        orphaned_rem, orphaned_obs = engine._detect_orphaned_tasks(
            normalized_links, obs_tasks, rem_tasks
        )
        
        print(f"Orphaned Reminders: {orphaned_rem}")
        print(f"Orphaned Obsidian: {orphaned_obs}")
        
        assert len(orphaned_rem) == 0, \
            f"False positive: {len(orphaned_rem)} Reminders incorrectly marked as orphaned"
        assert len(orphaned_obs) == 0, \
            f"False positive: {len(orphaned_obs)} Obsidian tasks incorrectly marked as orphaned"
        
        print("\n✓ No false orphans detected after normalization")
        
        # Legacy links that remain stale should be ignored when an active match exists
        print("\n=== Testing legacy link skip with active matches ===")
        stale_link = SyncLink(
            obs_uuid="obs-temp-legacy",
            rem_uuid=rem_tasks[0].uuid,
            score=0.5,
            last_synced=datetime.now(timezone.utc).isoformat(),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        active_links = [
            SyncLink(
                obs_uuid=obs_tasks[0].uuid,
                rem_uuid=rem_tasks[0].uuid,
                score=1.0,
                last_synced=datetime.now(timezone.utc).isoformat(),
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        ]
        orphaned_rem, orphaned_obs = engine._detect_orphaned_tasks(
            [stale_link],
            obs_tasks,
            rem_tasks,
            active_links=active_links,
        )
        assert not orphaned_rem and not orphaned_obs, (
            "Stale link with active replacement should not be marked orphan"
        )
        print("\n✓ Legacy link skipped when active match present")
        
        # Test with one actual deleted task
        print("\n=== Testing with actual orphan ===")
        obs_tasks_with_deletion = obs_tasks[:-1]  # Remove last task
        
        orphaned_rem, orphaned_obs = engine._detect_orphaned_tasks(
            normalized_links, obs_tasks_with_deletion, rem_tasks
        )
        
        assert len(orphaned_rem) == 1, \
            f"Expected 1 orphaned Reminder, got {len(orphaned_rem)}"
        assert rem_tasks[-1].uuid in orphaned_rem, \
            "Wrong Reminder marked as orphaned"
        
        print(f"✓ Correctly detected orphaned Reminder: {orphaned_rem}")
        
        print("\n=== TEST PASSED ===")
        print("UUID normalization correctly prevents false orphan detection")
        print("and still detects real orphans when tasks are deleted.")


if __name__ == "__main__":
    test_uuid_normalization_no_false_orphans()