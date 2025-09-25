#!/usr/bin/env python3
"""Test UUID alignment in ObsidianTaskManager to prevent duplicate task creation."""

import os
import sys
import tempfile
import shutil
from pathlib import Path
from datetime import date

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from obs_sync.obsidian.tasks import ObsidianTaskManager
from obs_sync.core.models import ObsidianTask, TaskStatus


def test_uuid_alignment():
    """Test that UUIDs remain stable across create, update, and list operations."""
    
    print("Testing UUID alignment in ObsidianTaskManager...")
    
    # Create a temporary vault
    with tempfile.TemporaryDirectory() as vault_path:
        print(f"Created temporary vault at: {vault_path}")
        
        # Initialize manager
        manager = ObsidianTaskManager()
        
        # Test 1: Create task and verify UUID alignment
        print("\n1. Testing UUID alignment in create_task...")
        
        # Create a task without block_id (will be generated)
        task1 = ObsidianTask(
            uuid="obs-temp123",  # Temporary UUID
            vault_id="test",
            vault_name="test",
            vault_path=vault_path,
            file_path="test.md",
            line_number=0,
            block_id=None,  # Will be generated
            status=TaskStatus.TODO,
            description="Test task for UUID alignment",
            raw_line="",
        )
        
        created_task = manager.create_task(vault_path, "test.md", task1)
        
        # Verify block_id was generated and UUID was aligned
        assert created_task.block_id is not None, "Block ID should be generated"
        expected_uuid = f"obs-{created_task.block_id}"
        assert created_task.uuid == expected_uuid, f"UUID should be aligned: expected {expected_uuid}, got {created_task.uuid}"
        print(f"✓ Created task with aligned UUID: {created_task.uuid}")
        
        # Test 2: List tasks and verify UUID matches
        print("\n2. Testing UUID consistency in list_tasks...")
        
        listed_tasks = manager.list_tasks(vault_path)
        assert len(listed_tasks) == 1, "Should find exactly one task"
        listed_task = listed_tasks[0]
        
        assert listed_task.uuid == created_task.uuid, f"Listed UUID should match created: {listed_task.uuid} != {created_task.uuid}"
        assert listed_task.block_id == created_task.block_id, "Block IDs should match"
        print(f"✓ Listed task has same UUID: {listed_task.uuid}")
        
        # Test 3: Update task and verify UUID remains aligned
        print("\n3. Testing UUID alignment in update_task...")
        
        # Update the task
        changes = {"description": "Updated test task"}
        updated_task = manager.update_task(listed_task, changes)
        
        assert updated_task.uuid == created_task.uuid, f"UUID should remain stable after update: {updated_task.uuid}"
        assert updated_task.block_id == created_task.block_id, "Block ID should remain stable"
        print(f"✓ Updated task maintains UUID: {updated_task.uuid}")
        
        # Test 4: List again and verify consistency
        print("\n4. Testing UUID consistency after update...")
        
        listed_tasks2 = manager.list_tasks(vault_path)
        assert len(listed_tasks2) == 1, "Should still have exactly one task"
        listed_task2 = listed_tasks2[0]
        
        assert listed_task2.uuid == created_task.uuid, f"UUID should be consistent: {listed_task2.uuid}"
        assert listed_task2.description == "Updated test task", "Description should be updated"
        print(f"✓ Task UUID remains consistent: {listed_task2.uuid}")
        
        # Test 5: Create task with pre-existing block_id
        print("\n5. Testing UUID alignment with pre-existing block_id...")
        
        task2 = ObsidianTask(
            uuid="obs-temp456",  # Temporary UUID
            vault_id="test",
            vault_name="test",
            vault_path=vault_path,
            file_path="test2.md",
            line_number=0,
            block_id="custom123",  # Pre-existing block_id
            status=TaskStatus.TODO,
            description="Task with custom block ID",
            raw_line="",
        )
        
        created_task2 = manager.create_task(vault_path, "test2.md", task2)
        
        assert created_task2.block_id == "custom123", "Should preserve provided block_id"
        assert created_task2.uuid == "obs-custom123", f"UUID should align with block_id: {created_task2.uuid}"
        print(f"✓ Task with custom block_id has aligned UUID: {created_task2.uuid}")
        
        # Test 6: Update task without block_id (migration scenario)
        print("\n6. Testing UUID alignment when adding block_id during update...")
        
        # Create a task file without block_id manually
        test3_path = os.path.join(vault_path, "test3.md")
        with open(test3_path, "w") as f:
            f.write("- [ ] Task without block ID\n")
        
        # List tasks to get the task without block_id
        all_tasks = manager.list_tasks(vault_path)
        task_without_blockid = next(t for t in all_tasks if t.file_path == "test3.md")
        original_uuid = task_without_blockid.uuid
        
        # Update the task (should generate block_id and align UUID)
        changes = {"description": "Task with newly added block ID"}
        updated_task3 = manager.update_task(task_without_blockid, changes)
        
        assert updated_task3.block_id is not None, "Block ID should be generated during update"
        assert updated_task3.uuid == f"obs-{updated_task3.block_id}", f"UUID should be aligned: {updated_task3.uuid}"
        print(f"✓ Task updated with new block_id has aligned UUID: {updated_task3.uuid}")
        
        # Verify the UUID remains stable on subsequent lists
        final_tasks = manager.list_tasks(vault_path)
        final_task3 = next(t for t in final_tasks if t.file_path == "test3.md")
        assert final_task3.uuid == updated_task3.uuid, "UUID should remain stable"
        print(f"✓ Final UUID check passed: {final_task3.uuid}")
        
    print("\n✅ All UUID alignment tests passed!")
    return True


if __name__ == "__main__":
    try:
        success = test_uuid_alignment()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)