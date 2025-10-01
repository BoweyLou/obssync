#!/usr/bin/env python3
"""
Test bidirectional tag syncing between Obsidian and Apple Reminders.
"""

import os
import sys
import tempfile
import json
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obs_sync.obsidian.tasks import ObsidianTaskManager
from obs_sync.reminders.tasks import RemindersTaskManager
from obs_sync.reminders.gateway import RemindersGateway, ReminderData
from obs_sync.sync.engine import SyncEngine
from obs_sync.sync.resolver import ConflictResolver
from obs_sync.core.models import ObsidianTask, RemindersTask, TaskStatus, SyncLink
from obs_sync.utils.tags import encode_tags_in_notes, decode_tags_from_notes, merge_tags


def test_tag_encoding_decoding():
    """Test encoding and decoding tags in notes field."""
    print("\n=== Testing Tag Encoding/Decoding ===")
    
    # Test encoding tags with user notes
    user_notes = "This is a user note"
    tags = ["#work", "#important", "#project-x"]
    encoded = encode_tags_in_notes(user_notes, tags)
    print(f"Encoded: {repr(encoded)}")
    
    # Test decoding
    decoded_notes, decoded_tags = decode_tags_from_notes(encoded)
    print(f"Decoded notes: {repr(decoded_notes)}")
    print(f"Decoded tags: {decoded_tags}")
    
    assert decoded_notes == user_notes
    assert decoded_tags == tags
    
    # Test encoding tags without user notes
    encoded_tags_only = encode_tags_in_notes(None, tags)
    print(f"Tags only encoded: {repr(encoded_tags_only)}")
    decoded_notes2, decoded_tags2 = decode_tags_from_notes(encoded_tags_only)
    assert decoded_notes2 is None
    assert decoded_tags2 == tags
    
    # Test with no tags
    encoded_no_tags = encode_tags_in_notes(user_notes, [])
    assert encoded_no_tags == user_notes
    
    print("✅ Tag encoding/decoding tests passed")


def test_tag_merging():
    """Test merging tags from both sources."""
    print("\n=== Testing Tag Merging ===")
    
    obs_tags = ["#work", "#important", "#obsidian-only"]
    rem_tags = ["#work", "#reminders-only", "#priority"]
    
    merged = merge_tags(obs_tags, rem_tags)
    print(f"Obsidian tags: {obs_tags}")
    print(f"Reminders tags: {rem_tags}")
    print(f"Merged tags: {merged}")
    
    # Check all unique tags are present
    assert "#work" in merged
    assert "#important" in merged
    assert "#obsidian-only" in merged
    assert "#reminders-only" in merged
    assert "#priority" in merged
    
    # Check no duplicates
    assert len(merged) == len(set(merged))
    
    # Check order (Obsidian tags should come first)
    assert merged.index("#work") < merged.index("#reminders-only")
    
    print("✅ Tag merging tests passed")


def test_obsidian_task_with_tags():
    """Test creating and parsing Obsidian tasks with tags."""
    print("\n=== Testing Obsidian Tasks with Tags ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = tmpdir
        test_file = Path(tmpdir) / "test.md"
        
        # Create a task with tags
        test_file.write_text("""# Test File
- [ ] Task with tags #work #important #project-x
- [ ] Another task #personal
""")
        
        # Parse tasks
        manager = ObsidianTaskManager()
        tasks = manager.list_tasks(vault_path)
        
        assert len(tasks) == 2
        
        # Check first task tags
        task1 = tasks[0]
        print(f"Task 1 description: {task1.description}")
        print(f"Task 1 tags: {task1.tags}")
        assert "#work" in task1.tags
        assert "#important" in task1.tags
        assert "#project-x" in task1.tags
        
        # Check second task tags
        task2 = tasks[1]
        print(f"Task 2 description: {task2.description}")
        print(f"Task 2 tags: {task2.tags}")
        assert "#personal" in task2.tags
        
        # Update task with new tags
        updated_task = manager.update_task(task1, {
            "tags": ["#work", "#updated", "#high-priority"]
        })
        
        # Read file to verify tags were written
        updated_content = test_file.read_text()
        print(f"Updated file content:\n{updated_content}")
        assert "#updated" in updated_content
        assert "#high-priority" in updated_content
        
        print("✅ Obsidian task tag tests passed")


def test_reminders_gateway_with_tags():
    """Test RemindersGateway handling of tags in notes field."""
    print("\n=== Testing RemindersGateway with Tags ===")
    
    # Test the tag encoding/decoding functionality directly
    from obs_sync.utils.tags import encode_tags_in_notes
    
    # Test encoding tags for Reminders
    user_notes = "User note"
    tags = ['#work', '#important']
    encoded = encode_tags_in_notes(user_notes, tags)
    
    print(f"Encoded notes for Reminders: {repr(encoded)}")
    assert "---tags---" in encoded
    assert "#work" in encoded
    assert "#important" in encoded
    assert "User note" in encoded
    
    # Test that RemindersData includes tags field
    from obs_sync.reminders.gateway import ReminderData
    
    reminder_data = ReminderData(
        uuid="test-uuid",
        title="Test task",
        completed=False,
        notes="User note",
        tags=['#work', '#important']
    )
    
    assert reminder_data.tags == ['#work', '#important']
    print(f"ReminderData with tags: uuid={reminder_data.uuid}, tags={reminder_data.tags}")
    
    print("✅ RemindersGateway tag tests passed")


def test_sync_engine_tag_round_trip():
    """Test full round-trip of tags through sync engine."""
    print("\n=== Testing Sync Engine Tag Round Trip ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = tmpdir
        test_file = Path(tmpdir) / "test.md"
        inbox_file = Path(tmpdir) / "inbox.md"
        
        # Create initial files
        test_file.write_text("# Test File\n- [ ] Obsidian task with tags #work #important\n")
        inbox_file.write_text("# Inbox\n")
        
        # Mock configuration
        config = {
            'vault_path': vault_path,
            'inbox_path': 'inbox.md',
            'default_calendar_id': 'test-calendar',
            'min_score': 0.75,
            'days_tolerance': 1
        }
        
        # Create sync engine
        engine = SyncEngine(config)
        
        # Mock the RemindersTaskManager
        mock_rem_manager = Mock(spec=RemindersTaskManager)
        
        # Create a mock Reminders task with different tags
        rem_task = RemindersTask(
            uuid="rem-123",
            item_id="item-123",
            calendar_id="test-calendar",
            list_name="Test List",
            status=TaskStatus.TODO,
            title="Reminders task",
            tags=["#reminders", "#sync-test"],
            notes="Reminders note"
        )
        
        mock_rem_manager.list_tasks.return_value = [rem_task]
        mock_rem_manager.create_task.return_value = rem_task
        mock_rem_manager.update_task.return_value = rem_task
        
        engine.rem_manager = mock_rem_manager
        
        # Run sync (dry run first)
        print("\n--- Dry Run ---")
        result = engine.sync(vault_path, dry_run=True)
        print(f"Sync result: {json.dumps(result, indent=2)}")
        
        # The result contains counts, not the actual tasks
        # Let's verify the sync would handle tags correctly
        print(f"Would create {result['changes']['rem_created']} Reminders task(s)")
        print(f"Would create {result['changes']['obs_created']} Obsidian task(s)")
        
        # Test conflict resolution with tags
        resolver = ConflictResolver()
        
        obs_task = ObsidianTask(
            uuid="obs-456",
            vault_id="test",
            vault_name="test",
            vault_path=vault_path,
            file_path="test.md",
            line_number=2,
            block_id="test-block-id",
            status=TaskStatus.TODO,
            description="Task with obs tags",
            tags=["#work", "#obsidian"],
            raw_line="- [ ] Task with obs tags #work #obsidian"
        )
        
        rem_task2 = RemindersTask(
            uuid="rem-789",
            item_id="item-789",
            calendar_id="test-calendar",
            list_name="Test List",
            status=TaskStatus.TODO,
            title="Task with rem tags",
            tags=["#reminders", "#apple"],
            notes="Note"
        )
        
        conflicts = resolver.resolve_conflicts(obs_task, rem_task2)
        print(f"\nTag conflict resolution: {conflicts.get('tags_winner', 'none')}")
        
        # Test that tags differ is detected
        assert resolver._tags_differ(obs_task.tags, rem_task2.tags)
        assert conflicts.get('tags_winner') == 'merge'
        
        print("✅ Sync engine tag round-trip tests passed")


def test_tag_preservation_on_sync():
    """Test that tags are preserved during sync operations."""
    print("\n=== Testing Tag Preservation on Sync ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = tmpdir
        test_file = Path(tmpdir) / "test.md"
        
        # Create task with multiple tags
        test_file.write_text("""# Test
- [ ] Task one #work #urgent #project-alpha
- [ ] Task two #personal #low-priority
""")
        
        # Parse tasks
        obs_manager = ObsidianTaskManager()
        tasks = obs_manager.list_tasks(vault_path)
        
        task1 = tasks[0]
        original_tags = task1.tags.copy()
        
        # Simulate updating task (without changing tags)
        updated = obs_manager.update_task(task1, {
            "description": "Updated task one"
        })
        
        # Verify tags are preserved
        print(f"Original tags: {original_tags}")
        print(f"Tags after update: {updated.tags}")
        assert updated.tags == original_tags
        
        # Read file to verify tags are still in markdown
        content = test_file.read_text()
        for tag in original_tags:
            assert tag in content
        
        print("✅ Tag preservation tests passed")


if __name__ == "__main__":
    try:
        test_tag_encoding_decoding()
        test_tag_merging()
        test_obsidian_task_with_tags()
        test_reminders_gateway_with_tags()
        test_sync_engine_tag_round_trip()
        test_tag_preservation_on_sync()
        
        print("\n" + "="*50)
        print("🎉 All tag sync tests passed successfully!")
        print("="*50)
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)