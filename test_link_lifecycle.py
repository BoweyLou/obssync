#!/usr/bin/env python3
"""
Test bidirectional link establishment and lifecycle state management
for create missing counterparts functionality.
"""

import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from obs_tools.commands.create_missing_counterparts import (
    MissingCounterpartsCreator,
    CreationPlan,
    CreationResult,
    CreationConfig
)
from lib.date_utils import get_today_string, days_ago, now_iso

def test_link_entry_creation():
    """Test link entry creation with proper structure."""
    print("Testing link entry creation...")
    
    creator = MissingCounterpartsCreator()
    
    obs_task = {
        "uuid": "obs-123",
        "description": "Test Obsidian task",
        "due": "2023-12-15",
        "status": "todo"
    }
    
    rem_task = {
        "uuid": "rem-456", 
        "description": "Test Reminders task",
        "due_date": "2023-12-15",
        "is_completed": False
    }
    
    link = creator._create_link_entry(
        obs_uuid="obs-123",
        rem_uuid="rem-456",
        score=1.0,
        obs_task=obs_task,
        rem_task=rem_task
    )
    
    # Validate link structure
    assert link["obs_uuid"] == "obs-123"
    assert link["rem_uuid"] == "rem-456"
    assert link["score"] == 1.0
    assert link["title_similarity"] == 1.0  # Perfect for created counterparts
    assert link["date_distance_days"] == 0
    assert link["due_equal"] is True
    assert "created_at" in link
    assert "last_scored" in link
    assert link["last_synced"] is None
    
    # Validate fields sub-structure
    assert link["fields"]["obs_title"] == "Test Obsidian task"
    assert link["fields"]["rem_title"] == "Test Reminders task"
    assert link["fields"]["obs_due"] == "2023-12-15"
    assert link["fields"]["rem_due"] == "2023-12-15"
    
    print("✓ Link entry creation test passed")

def test_link_entry_with_missing_fields():
    """Test link entry creation when some fields are missing."""
    print("Testing link entry creation with missing fields...")
    
    creator = MissingCounterpartsCreator()
    
    obs_task = {
        "uuid": "obs-123",
        "description": "Test task",
        # No due date
    }
    
    rem_task = {
        "uuid": "rem-456",
        # No description, no due date
        "is_completed": False
    }
    
    link = creator._create_link_entry(
        obs_uuid="obs-123",
        rem_uuid="rem-456", 
        score=0.8,
        obs_task=obs_task,
        rem_task=rem_task
    )
    
    # Should handle missing fields gracefully
    assert link["fields"]["obs_title"] == "Test task"
    assert link["fields"]["rem_title"] == ""  # Empty string for missing description
    assert link["fields"]["obs_due"] is None
    assert link["fields"]["rem_due"] is None
    
    print("✓ Link entry with missing fields test passed")

def test_lifecycle_timestamps():
    """Test that lifecycle timestamps are properly set."""
    print("Testing lifecycle timestamps...")
    
    creator = MissingCounterpartsCreator()
    
    obs_task = {"uuid": "obs-123", "description": "Test"}
    rem_task = {"uuid": "rem-456", "description": "Test"}
    
    # Create link and check timestamps
    link = creator._create_link_entry("obs-123", "rem-456", 1.0, obs_task, rem_task)
    
    # Timestamps should be ISO format
    created_at = link["created_at"]
    last_scored = link["last_scored"]
    
    assert created_at.endswith("Z") or "+" in created_at  # Valid ISO format
    assert last_scored.endswith("Z") or "+" in last_scored  # Valid ISO format
    
    # Created and last_scored should be very close in time (within 1 second)
    from datetime import datetime
    created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    scored_dt = datetime.fromisoformat(last_scored.replace("Z", "+00:00"))
    
    time_diff = abs((created_dt - scored_dt).total_seconds())
    assert time_diff < 1.0  # Should be within 1 second
    
    # last_synced should be None for new links
    assert link["last_synced"] is None
    
    print("✓ Lifecycle timestamps test passed")

def test_schema_v2_link_compliance():
    """Test that created links comply with expected schema."""
    print("Testing Schema v2 link compliance...")
    
    creator = MissingCounterpartsCreator()
    
    # Create comprehensive tasks with Schema v2 fields
    obs_task = {
        "uuid": "obs-schema-test",
        "source_key": "block:Vault:file.md:t-abc123",
        "description": "Schema v2 test task",
        "status": "todo",
        "due": "2023-12-15",
        "priority": "high",
        "tags": ["#test"],
        "file": {"relative_path": "test.md", "line": 10},
        "vault": {"name": "TestVault"},
        "block_id": "t-abc123",
        "created_at": "2023-12-15T08:00:00Z",
        "updated_at": "2023-12-15T09:00:00Z"
    }
    
    rem_task = {
        "uuid": "rem-schema-test",
        "source_key": "rem:abc-123-def-456",
        "description": "Schema v2 test reminder",
        "is_completed": False,
        "due_date": "2023-12-15",
        "priority": 5,
        "list": {"name": "Test List", "identifier": "list-123"},
        "created_at": "2023-12-15T08:00:00Z",
        "updated_at": "2023-12-15T09:00:00Z"
    }
    
    link = creator._create_link_entry(
        obs_uuid="obs-schema-test",
        rem_uuid="rem-schema-test",
        score=1.0,
        obs_task=obs_task,
        rem_task=rem_task
    )
    
    # Validate required link fields
    required_fields = [
        "obs_uuid", "rem_uuid", "score", "title_similarity", 
        "date_distance_days", "due_equal", "created_at", 
        "last_scored", "last_synced", "fields"
    ]
    
    for field in required_fields:
        assert field in link, f"Missing required link field: {field}"
    
    # Validate fields sub-structure
    assert "obs_title" in link["fields"]
    assert "rem_title" in link["fields"]
    assert "obs_due" in link["fields"]
    assert "rem_due" in link["fields"]
    
    # Validate data types
    assert isinstance(link["score"], (int, float))
    assert isinstance(link["title_similarity"], (int, float))
    assert isinstance(link["date_distance_days"], int)
    assert isinstance(link["due_equal"], bool)
    
    print("✓ Schema v2 link compliance test passed")

def test_link_score_calculations():
    """Test that link scores are correctly calculated for created counterparts."""
    print("Testing link score calculations...")
    
    creator = MissingCounterpartsCreator()
    
    # Perfect match scenario
    obs_task = {
        "uuid": "obs-perfect",
        "description": "Perfect match task",
        "due": "2023-12-15"
    }
    
    rem_task = {
        "uuid": "rem-perfect",
        "description": "Perfect match task",
        "due_date": "2023-12-15"
    }
    
    link = creator._create_link_entry("obs-perfect", "rem-perfect", 1.0, obs_task, rem_task)
    
    # Created counterparts should have perfect scores
    assert link["score"] == 1.0
    assert link["title_similarity"] == 1.0
    assert link["date_distance_days"] == 0
    assert link["due_equal"] is True
    
    # Test with different content but still created counterpart
    obs_task2 = {
        "uuid": "obs-different",
        "description": "Original task",
        "due": "2023-12-15"
    }
    
    rem_task2 = {
        "uuid": "rem-different", 
        "description": "Mapped task description",
        "due_date": "2023-12-16"  # Different date
    }
    
    link2 = creator._create_link_entry("obs-different", "rem-different", 1.0, obs_task2, rem_task2)
    
    # Should still have perfect scores because it's a created counterpart
    assert link2["score"] == 1.0
    assert link2["title_similarity"] == 1.0  # Perfect for created counterparts
    assert link2["date_distance_days"] == 0  # Reset for created counterparts
    assert link2["due_equal"] is True  # Assumed true for created counterparts
    
    print("✓ Link score calculations test passed")

def test_link_data_integrity():
    """Test data integrity constraints for links."""
    print("Testing link data integrity...")
    
    creator = MissingCounterpartsCreator()
    
    # Test with various edge cases
    edge_cases = [
        # Case 1: Empty descriptions
        ({
            "uuid": "obs-empty",
            "description": "",
        }, {
            "uuid": "rem-empty", 
            "description": "",
        }),
        
        # Case 2: Very long descriptions
        ({
            "uuid": "obs-long",
            "description": "A" * 1000,
        }, {
            "uuid": "rem-long",
            "description": "B" * 1000,
        }),
        
        # Case 3: Special characters
        ({
            "uuid": "obs-special",
            "description": "Task with émojis 🎉 and chars: @#$%",
        }, {
            "uuid": "rem-special",
            "description": "Unicode: 你好世界 🌍",
        }),
        
        # Case 4: None values
        ({
            "uuid": "obs-none",
            "description": "Valid description",
            "due": None,
        }, {
            "uuid": "rem-none",
            "description": "Valid description", 
            "due_date": None,
        }),
    ]
    
    for i, (obs_task, rem_task) in enumerate(edge_cases):
        link = creator._create_link_entry(
            obs_uuid=obs_task["uuid"],
            rem_uuid=rem_task["uuid"],
            score=1.0,
            obs_task=obs_task,
            rem_task=rem_task
        )
        
        # Basic structure should always be maintained
        assert "obs_uuid" in link
        assert "rem_uuid" in link
        assert "fields" in link
        assert "obs_title" in link["fields"]
        assert "rem_title" in link["fields"]
        
        # UUIDs should match
        assert link["obs_uuid"] == obs_task["uuid"]
        assert link["rem_uuid"] == rem_task["uuid"]
        
        # Fields should be strings or None
        assert isinstance(link["fields"]["obs_title"], str)
        assert isinstance(link["fields"]["rem_title"], str)
        assert link["fields"]["obs_due"] is None or isinstance(link["fields"]["obs_due"], str)
        assert link["fields"]["rem_due"] is None or isinstance(link["fields"]["rem_due"], str)
    
    print("✓ Link data integrity test passed")

def test_bidirectional_link_consistency():
    """Test that bidirectional links maintain consistency."""
    print("Testing bidirectional link consistency...")
    
    creator = MissingCounterpartsCreator()
    today = get_today_string()
    
    # Create test plan with both directions
    obs_data = {
        "meta": {"schema": 2},
        "tasks": {
            "obs-unlinked": {
                "uuid": "obs-unlinked",
                "description": "Unlinked Obsidian task",
                "status": "todo",
                "due": today,
                "updated_at": f"{today}T09:00:00Z"
            }
        }
    }
    
    rem_data = {
        "meta": {"schema": 2},
        "tasks": {
            "rem-unlinked": {
                "uuid": "rem-unlinked",
                "description": "Unlinked Reminders task",
                "is_completed": False,
                "due_date": today,
                "updated_at": f"{today}T09:00:00Z"
            }
        }
    }
    
    links_data = {"meta": {"schema": 1}, "links": []}
    
    plan = creator.create_plan(obs_data, rem_data, links_data, direction="both")
    
    # Should have one creation in each direction
    assert len(plan.obs_to_rem) == 1
    assert len(plan.rem_to_obs) == 1
    
    # Simulate what would happen during execution
    obs_item = plan.obs_to_rem[0]
    rem_item = plan.rem_to_obs[0]
    
    # Create mock results for what _create_reminder_counterpart and _create_obsidian_counterpart would return
    mock_rem_result = {
        "rem_uuid": "new-rem-uuid",
        "rem_task": {
            "uuid": "new-rem-uuid",
            "description": obs_item["mapped_fields"]["title"],
            "created_at": now_iso()
        }
    }
    
    mock_obs_result = {
        "obs_uuid": "new-obs-uuid",
        "obs_task": {
            "uuid": "new-obs-uuid", 
            "description": rem_item["mapped_fields"]["description"],
            "created_at": now_iso()
        }
    }
    
    # Create links for both directions
    link1 = creator._create_link_entry(
        obs_uuid=obs_item["obs_uuid"],
        rem_uuid=mock_rem_result["rem_uuid"],
        score=1.0,
        obs_task=obs_item["obs_task"],
        rem_task=mock_rem_result["rem_task"]
    )
    
    link2 = creator._create_link_entry(
        obs_uuid=mock_obs_result["obs_uuid"],
        rem_uuid=rem_item["rem_uuid"],
        score=1.0,
        obs_task=mock_obs_result["obs_task"],
        rem_task=rem_item["rem_task"]
    )
    
    # Validate that both links have proper structure
    for link in [link1, link2]:
        assert link["score"] == 1.0
        assert link["title_similarity"] == 1.0
        assert link["due_equal"] is True
        assert "created_at" in link
        assert "obs_uuid" in link
        assert "rem_uuid" in link
    
    # Links should reference different UUIDs (one original, one created)
    assert link1["obs_uuid"] != link2["obs_uuid"]  # Different Obsidian tasks
    assert link1["rem_uuid"] != link2["rem_uuid"]  # Different Reminders tasks
    
    print("✓ Bidirectional link consistency test passed")

def run_all_link_lifecycle_tests():
    """Run all link and lifecycle tests."""
    print("=" * 60)
    print("RUNNING LINK ESTABLISHMENT & LIFECYCLE TESTS")
    print("=" * 60)
    
    tests = [
        test_link_entry_creation,
        test_link_entry_with_missing_fields,
        test_lifecycle_timestamps,
        test_schema_v2_link_compliance,
        test_link_score_calculations,
        test_link_data_integrity,
        test_bidirectional_link_consistency
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("=" * 60)
    print(f"LINK & LIFECYCLE TEST RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)
    
    if failed == 0:
        print("🎉 ALL LINK & LIFECYCLE TESTS PASSED!")
        return True
    else:
        print(f"❌ {failed} link & lifecycle tests failed")
        return False

if __name__ == "__main__":
    success = run_all_link_lifecycle_tests()
    sys.exit(0 if success else 1)