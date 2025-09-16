#!/usr/bin/env python3
"""
Comprehensive test of create missing counterparts functionality.
This script validates the core logic without requiring external frameworks.
"""

import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from obs_tools.commands.create_missing_counterparts import (
    MissingCounterpartsCreator,
    CreationPlan,
    CreationResult,
    CreationConfig
)
from lib.date_utils import get_today_string, days_ago

def create_test_data():
    """Create test data for validation."""
    today = get_today_string()
    yesterday = days_ago(1)
    week_ago = days_ago(8)
    
    # Sample Obsidian tasks
    obs_data = {
        "meta": {"schema": 2, "generated_at": f"{today}T10:00:00Z"},
        "tasks": {
            "obs-unlinked-1": {
                "uuid": "obs-unlinked-1",
                "description": "Test Obsidian task 1",
                "status": "todo",
                "due": today,
                "priority": "high",
                "tags": ["#work"],
                "file": {"relative_path": "test.md", "line": 1},
                "vault": {"name": "Test"},
                "block_id": "block123",
                "created_at": f"{yesterday}T09:00:00Z",
                "updated_at": f"{yesterday}T09:00:00Z"
            },
            "obs-unlinked-2": {
                "uuid": "obs-unlinked-2",
                "description": "Old Obsidian task",
                "status": "todo",
                "created_at": f"{week_ago}T09:00:00Z",
                "updated_at": f"{week_ago}T09:00:00Z"
            },
            "obs-done": {
                "uuid": "obs-done",
                "description": "Completed task",
                "status": "done",
                "created_at": f"{yesterday}T09:00:00Z",
                "updated_at": f"{yesterday}T09:00:00Z"
            },
            "obs-linked": {
                "uuid": "obs-linked",
                "description": "Already linked task",
                "status": "todo",
                "created_at": f"{yesterday}T09:00:00Z",
                "updated_at": f"{yesterday}T09:00:00Z"
            }
        }
    }
    
    # Sample Reminders tasks
    rem_data = {
        "meta": {"schema": 2, "generated_at": f"{today}T10:00:00Z"},
        "tasks": {
            "rem-unlinked-1": {
                "uuid": "rem-unlinked-1",
                "description": "Test Reminders task 1",
                "is_completed": False,
                "due_date": today,
                "priority": 5,
                "list": {"name": "Personal"},
                "created_at": f"{yesterday}T08:00:00Z",
                "updated_at": f"{yesterday}T08:00:00Z"
            },
            "rem-unlinked-2": {
                "uuid": "rem-unlinked-2",
                "description": "Old Reminders task",
                "is_completed": False,
                "list": {"name": "Tasks"},
                "created_at": f"{week_ago}T08:00:00Z",
                "updated_at": f"{week_ago}T08:00:00Z"
            },
            "rem-done": {
                "uuid": "rem-done",
                "description": "Completed reminder",
                "is_completed": True,
                "created_at": f"{yesterday}T08:00:00Z",
                "updated_at": f"{yesterday}T08:00:00Z"
            },
            "rem-linked": {
                "uuid": "rem-linked",
                "description": "Already linked reminder",
                "is_completed": False,
                "created_at": f"{yesterday}T08:00:00Z",
                "updated_at": f"{yesterday}T08:00:00Z"
            }
        }
    }
    
    # Sample links data
    links_data = {
        "meta": {"schema": 1, "generated_at": f"{today}T10:00:00Z"},
        "links": [
            {
                "obs_uuid": "obs-linked",
                "rem_uuid": "rem-linked",
                "score": 0.9,
                "created_at": f"{yesterday}T09:00:00Z"
            }
        ]
    }
    
    return obs_data, rem_data, links_data

def test_creator_initialization():
    """Test basic creator initialization."""
    print("Testing creator initialization...")
    
    config = CreationConfig(
        obs_inbox_file="~/test/inbox.md",
        rem_default_calendar_id="test-cal",
        max_creates_per_run=10
    )
    
    creator = MissingCounterpartsCreator(config)
    
    assert creator.config.obs_inbox_file == "~/test/inbox.md"
    assert creator.config.rem_default_calendar_id == "test-cal"
    assert creator.config.max_creates_per_run == 10
    
    print("✓ Creator initialization test passed")

def test_linked_sets_building():
    """Test building linked task sets."""
    print("Testing linked sets building...")
    
    creator = MissingCounterpartsCreator()
    _, _, links_data = create_test_data()
    
    linked_obs, linked_rem = creator.build_linked_sets(links_data)
    
    assert "obs-linked" in linked_obs
    assert "rem-linked" in linked_rem
    assert len(linked_obs) == 1
    assert len(linked_rem) == 1
    
    print("✓ Linked sets building test passed")

def test_task_filtering():
    """Test task filtering logic."""
    print("Testing task filtering...")
    
    creator = MissingCounterpartsCreator()
    obs_data, _, _ = create_test_data()
    
    tasks = obs_data["tasks"]
    linked_uuids = {"obs-linked"}
    
    # Test without including done tasks
    filtered = creator.filter_tasks(tasks, linked_uuids, include_done=False, since_days=5)
    
    # Should include obs-unlinked-1 (recent, not linked, not done)
    # Should exclude obs-unlinked-2 (old), obs-done (completed), obs-linked (linked)
    assert "obs-unlinked-1" in filtered
    assert "obs-unlinked-2" not in filtered  # too old
    assert "obs-done" not in filtered  # completed
    assert "obs-linked" not in filtered  # linked
    
    # Test with including done tasks
    filtered_with_done = creator.filter_tasks(tasks, linked_uuids, include_done=True, since_days=5)
    
    # Should now also include obs-done
    assert "obs-unlinked-1" in filtered_with_done
    assert "obs-done" in filtered_with_done
    
    print("✓ Task filtering test passed")

def test_field_mapping_obs_to_rem():
    """Test field mapping from Obsidian to Reminders."""
    print("Testing Obsidian to Reminders field mapping...")
    
    creator = MissingCounterpartsCreator()
    
    obs_task = {
        "description": "Buy groceries",
        "due": "2023-12-15",
        "priority": "high",
        "tags": ["#personal", "#shopping"],
        "file": {"relative_path": "daily/2023-12-15.md", "line": 5},
        "vault": {"name": "TestVault"},
        "block_id": "abc123"
    }
    
    mapped = creator.map_obsidian_to_reminders_fields(obs_task)
    
    assert mapped["title"] == "Buy groceries"
    assert mapped["due_date"] == "2023-12-15"
    assert mapped["priority"] == 1  # high -> 1 in EventKit
    assert "Source: daily/2023-12-15.md" in mapped["notes"]
    assert "Line: 5" in mapped["notes"]
    assert "Tags: #personal, #shopping" in mapped["notes"]
    assert mapped["url"] == "obsidian://open?vault=TestVault&file=daily/2023-12-15.md#abc123"
    
    print("✓ Obsidian to Reminders field mapping test passed")

def test_field_mapping_rem_to_obs():
    """Test field mapping from Reminders to Obsidian."""
    print("Testing Reminders to Obsidian field mapping...")
    
    creator = MissingCounterpartsCreator()
    
    rem_task = {
        "description": "Team meeting",
        "is_completed": False,
        "due_date": "2023-12-16",
        "priority": 5,
        "list": {"name": "Work"}
    }
    
    mapped = creator.map_reminders_to_obsidian_fields(rem_task)
    
    assert mapped["description"] == "Team meeting"
    assert mapped["status"] == "todo"
    assert mapped["due"] == "2023-12-16"
    assert mapped["priority"] == "medium"  # 5 -> medium
    assert mapped["tags"] == ["#work"]
    
    print("✓ Reminders to Obsidian field mapping test passed")

def test_creation_plan_generation():
    """Test creation plan generation."""
    print("Testing creation plan generation...")
    
    creator = MissingCounterpartsCreator()
    obs_data, rem_data, links_data = create_test_data()
    
    # Test with recent tasks only
    plan = creator.create_plan(
        obs_data, rem_data, links_data,
        direction="both",
        include_done=False,
        since_days=5
    )
    
    # Should find unlinked recent tasks
    assert len(plan.obs_to_rem) == 1  # obs-unlinked-1
    assert len(plan.rem_to_obs) == 1  # rem-unlinked-1 (rem-done should be excluded now)
    assert plan.total_creates == 2
    assert plan.direction == "both"
    
    # Test direction filtering
    plan_obs_only = creator.create_plan(
        obs_data, rem_data, links_data,
        direction="obs-to-rem",
        include_done=False,
        since_days=5
    )
    
    assert len(plan_obs_only.obs_to_rem) == 1
    assert len(plan_obs_only.rem_to_obs) == 0
    
    print("✓ Creation plan generation test passed")

def test_max_creates_limit():
    """Test max creates limit."""
    print("Testing max creates limit...")
    
    creator = MissingCounterpartsCreator()
    obs_data, rem_data, links_data = create_test_data()
    
    # Test with max_creates=1
    plan = creator.create_plan(
        obs_data, rem_data, links_data,
        direction="both",
        include_done=False,
        since_days=5,
        max_creates=1
    )
    
    assert plan.total_creates <= 1
    
    print("✓ Max creates limit test passed")

def test_target_determination():
    """Test target calendar and file determination."""
    print("Testing target determination...")
    
    config = CreationConfig(
        rem_default_calendar_id="default-cal",
        obs_inbox_file="~/inbox.md"
    )
    config.obs_to_rem_rules = [
        {"tag": "#work", "calendar_id": "work-cal"},
        {"tag": "#personal", "calendar_id": "personal-cal"}
    ]
    config.rem_to_obs_rules = [
        {"list_name": "Work", "target_file": "~/work/tasks.md", "heading": "Imported"},
        {"list_name": "Personal", "target_file": "~/personal/tasks.md"}
    ]
    
    creator = MissingCounterpartsCreator(config)
    
    # Test calendar determination
    work_task = {"tags": ["#work", "#project"]}
    personal_task = {"tags": ["#personal"]}
    other_task = {"tags": ["#other"]}
    
    assert creator.determine_target_calendar(work_task) == "work-cal"
    assert creator.determine_target_calendar(personal_task) == "personal-cal"
    assert creator.determine_target_calendar(other_task) == "default-cal"
    
    # Test file determination
    work_reminder = {"list": {"name": "Work"}}
    personal_reminder = {"list": {"name": "Personal"}}
    other_reminder = {"list": {"name": "Other"}}
    
    file_path, heading = creator.determine_target_file(work_reminder)
    assert file_path == "~/work/tasks.md"
    assert heading == "Imported"
    
    file_path, heading = creator.determine_target_file(personal_reminder)
    assert file_path == "~/personal/tasks.md"
    assert heading is None
    
    file_path, heading = creator.determine_target_file(other_reminder)
    assert file_path == "~/inbox.md"
    assert heading is None
    
    print("✓ Target determination test passed")

def test_plan_structure_validation():
    """Test that the plan structure follows Schema v2 requirements."""
    print("Testing plan structure validation...")
    
    creator = MissingCounterpartsCreator()
    obs_data, rem_data, links_data = create_test_data()
    
    plan = creator.create_plan(
        obs_data, rem_data, links_data,
        direction="both",
        include_done=False,
        since_days=5
    )
    
    # Validate plan structure
    assert hasattr(plan, 'obs_to_rem')
    assert hasattr(plan, 'rem_to_obs')
    assert hasattr(plan, 'total_creates')
    assert hasattr(plan, 'direction')
    assert hasattr(plan, 'filters_applied')
    
    # Validate obs_to_rem entries
    for item in plan.obs_to_rem:
        assert 'obs_uuid' in item
        assert 'obs_task' in item
        assert 'target_calendar_id' in item
        assert 'mapped_fields' in item
        
        # Validate obs_task has required schema v2 fields
        obs_task = item['obs_task']
        assert 'uuid' in obs_task
        assert 'description' in obs_task
        assert 'status' in obs_task
        
        # Validate mapped_fields
        mapped = item['mapped_fields']
        assert 'title' in mapped
    
    # Validate rem_to_obs entries
    for item in plan.rem_to_obs:
        assert 'rem_uuid' in item
        assert 'rem_task' in item
        assert 'target_file' in item
        assert 'mapped_fields' in item
        
        # Validate rem_task has required schema v2 fields
        rem_task = item['rem_task']
        assert 'uuid' in rem_task
        assert 'description' in rem_task
        
        # Validate mapped_fields
        mapped = item['mapped_fields']
        assert 'description' in mapped
        assert 'status' in mapped
    
    print("✓ Plan structure validation test passed")

def run_all_tests():
    """Run all validation tests."""
    print("=" * 60)
    print("RUNNING COMPREHENSIVE CREATE MISSING COUNTERPARTS TESTS")
    print("=" * 60)
    
    tests = [
        test_creator_initialization,
        test_linked_sets_building,
        test_task_filtering,
        test_field_mapping_obs_to_rem,
        test_field_mapping_rem_to_obs,
        test_creation_plan_generation,
        test_max_creates_limit,
        test_target_determination,
        test_plan_structure_validation
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} FAILED: {e}")
            failed += 1
    
    print("=" * 60)
    print(f"TEST RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)
    
    if failed == 0:
        print("🎉 ALL TESTS PASSED!")
        return True
    else:
        print(f"❌ {failed} tests failed")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)