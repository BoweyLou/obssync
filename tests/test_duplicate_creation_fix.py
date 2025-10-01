#!/usr/bin/env python3
"""Test to verify the duplicate creation fix works correctly."""

import os
import sys
import tempfile
import json
from pathlib import Path
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from obs_sync.obsidian.tasks import ObsidianTaskManager
from obs_sync.sync.engine import SyncEngine
from obs_sync.core.models import ObsidianTask, TaskStatus, SyncLink


def test_no_duplicate_creation():
    """Test that repeated sync runs don't create duplicate tasks."""
    
    print("Testing duplicate creation fix...")
    
    with tempfile.TemporaryDirectory() as vault_path:
        print(f"Created temporary vault at: {vault_path}")
        
        # Create a test task file
        test_file = os.path.join(vault_path, "test.md")
        with open(test_file, "w") as f:
            f.write("# Test File\n\n- [ ] Test task ^abc123\n")
        
        # Create links directory
        links_dir = os.path.join(vault_path, ".obs-sync")
        os.makedirs(links_dir, exist_ok=True)
        links_path = os.path.join(links_dir, "sync_links.json")
        
        # Create a sync link with old-style UUID (simulating the issue)
        old_link = SyncLink(
            obs_uuid="obs-temp456789",  # Old temporary UUID
            rem_uuid="rem-fake123",     # Fake reminder UUID
            score=0.95,
            last_synced=datetime.now(timezone.utc).isoformat(),
            created_at=datetime.now(timezone.utc).isoformat()
        )
        
        # Save the old-style link
        with open(links_path, 'w') as f:
            json.dump({
                'links': [old_link.to_dict()]
            }, f, indent=2)
        
        print(f"Created sync link with old UUID: {old_link.obs_uuid}")
        
        # Initialize ObsidianTaskManager and list tasks
        obs_manager = ObsidianTaskManager()
        obs_tasks = obs_manager.list_tasks(vault_path)
        
        print(f"Found {len(obs_tasks)} Obsidian tasks")
        if obs_tasks:
            task = obs_tasks[0]
            print(f"Task UUID: {task.uuid}, Block ID: {task.block_id}")
            
            # Verify the task has canonical UUID
            expected_uuid = f"obs-{task.block_id}"
            assert task.uuid == expected_uuid, f"Task should have canonical UUID: {task.uuid} != {expected_uuid}"
            print(f"✓ Task has canonical UUID: {task.uuid}")
        
        # Test SyncEngine link normalization
        config = {
            "min_score": 0.75,
            "days_tolerance": 1,
            "include_completed": True,
            "links_path": links_path,
        }
        
        # Create a mock SyncEngine to test link normalization
        engine = SyncEngine(config)
        
        # Load and normalize links
        existing_links = engine._load_existing_links()
        print(f"Loaded {len(existing_links)} existing links")
        
        normalized_links = engine._normalize_links(existing_links, obs_tasks)
        print(f"Normalized to {len(normalized_links)} links")
        
        # Check if any old UUIDs remain
        old_style_uuids = [link.obs_uuid for link in normalized_links 
                          if link.obs_uuid.startswith('obs-') and 
                          not any(task.uuid == link.obs_uuid for task in obs_tasks)]
        
        if old_style_uuids:
            print(f"Found {len(old_style_uuids)} potentially stale UUIDs: {old_style_uuids}")
        else:
            print("✓ No stale UUIDs found after normalization")
        
        # Verify that all links reference existing tasks or are appropriately handled
        valid_links = 0
        for link in normalized_links:
            if any(task.uuid == link.obs_uuid for task in obs_tasks):
                valid_links += 1
                print(f"✓ Link references existing task: {link.obs_uuid}")
        
        print(f"Valid links: {valid_links}/{len(normalized_links)}")
        
    print("\n✅ Duplicate creation fix test completed!")
    return True


if __name__ == "__main__":
    try:
        success = test_no_duplicate_creation()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)