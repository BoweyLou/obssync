#!/usr/bin/env python3
"""
Edge case testing for create missing counterparts functionality.
Tests various edge cases, data integrity, and schema compliance.
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

def test_empty_indices():
    """Test behavior with empty task indices."""
    print("Testing empty indices...")
    
    creator = MissingCounterpartsCreator()
    
    # Empty indices
    obs_data = {"meta": {"schema": 2}, "tasks": {}}
    rem_data = {"meta": {"schema": 2}, "tasks": {}}
    links_data = {"meta": {"schema": 1}, "links": []}
    
    plan = creator.create_plan(obs_data, rem_data, links_data)
    
    assert plan.total_creates == 0
    assert len(plan.obs_to_rem) == 0
    assert len(plan.rem_to_obs) == 0
    
    print("✓ Empty indices test passed")

def test_all_tasks_linked():
    """Test behavior when all tasks are already linked."""
    print("Testing all tasks linked...")
    
    creator = MissingCounterpartsCreator()
    today = get_today_string()
    
    obs_data = {
        "meta": {"schema": 2},
        "tasks": {
            "obs-1": {
                "uuid": "obs-1",
                "description": "Linked task 1",
                "status": "todo",
                "updated_at": f"{today}T09:00:00Z"
            },
            "obs-2": {
                "uuid": "obs-2", 
                "description": "Linked task 2",
                "status": "todo",
                "updated_at": f"{today}T09:00:00Z"
            }
        }
    }
    
    rem_data = {
        "meta": {"schema": 2},
        "tasks": {
            "rem-1": {
                "uuid": "rem-1",
                "description": "Linked reminder 1",
                "is_completed": False,
                "updated_at": f"{today}T09:00:00Z"
            },
            "rem-2": {
                "uuid": "rem-2",
                "description": "Linked reminder 2", 
                "is_completed": False,
                "updated_at": f"{today}T09:00:00Z"
            }
        }
    }
    
    links_data = {
        "meta": {"schema": 1},
        "links": [
            {"obs_uuid": "obs-1", "rem_uuid": "rem-1"},
            {"obs_uuid": "obs-2", "rem_uuid": "rem-2"}
        ]
    }
    
    plan = creator.create_plan(obs_data, rem_data, links_data)
    
    assert plan.total_creates == 0
    assert len(plan.obs_to_rem) == 0
    assert len(plan.rem_to_obs) == 0
    
    print("✓ All tasks linked test passed")

def test_tasks_with_special_characters():
    """Test tasks with special characters and edge cases."""
    print("Testing tasks with special characters...")
    
    creator = MissingCounterpartsCreator()
    today = get_today_string()
    
    obs_data = {
        "meta": {"schema": 2},
        "tasks": {
            "obs-special": {
                "uuid": "obs-special",
                "description": "Task with émojis 🎉 and special chars: @#$%^&*()",
                "status": "todo",
                "updated_at": f"{today}T09:00:00Z",
                "tags": ["#émojis", "#special-chars"],
                "file": {"relative_path": "special/file with spaces.md", "line": 1},
                "vault": {"name": "Test Vault"},
                "block_id": "special-123"
            }
        }
    }
    
    rem_data = {
        "meta": {"schema": 2},
        "tasks": {
            "rem-unicode": {
                "uuid": "rem-unicode",
                "description": "Unicode test: 你好世界 🌍 café naïve résumé",
                "is_completed": False,
                "updated_at": f"{today}T09:00:00Z",
                "list": {"name": "Special List"}
            }
        }
    }
    
    links_data = {"meta": {"schema": 1}, "links": []}
    
    plan = creator.create_plan(obs_data, rem_data, links_data)
    
    assert plan.total_creates == 2
    assert len(plan.obs_to_rem) == 1
    assert len(plan.rem_to_obs) == 1
    
    # Validate field mapping handles special characters
    obs_item = plan.obs_to_rem[0]
    assert "émojis" in obs_item["mapped_fields"]["title"]
    assert "special chars" in obs_item["mapped_fields"]["title"]
    
    rem_item = plan.rem_to_obs[0]
    assert "你好世界" in rem_item["mapped_fields"]["description"]
    assert "🌍" in rem_item["mapped_fields"]["description"]
    
    print("✓ Special characters test passed")

def test_very_long_descriptions():
    """Test tasks with very long descriptions."""
    print("Testing very long descriptions...")
    
    creator = MissingCounterpartsCreator()
    today = get_today_string()
    
    # Create a very long description (over 1000 characters)
    long_description = "This is a very long task description. " * 50
    
    obs_data = {
        "meta": {"schema": 2},
        "tasks": {
            "obs-long": {
                "uuid": "obs-long",
                "description": long_description,
                "status": "todo",
                "updated_at": f"{today}T09:00:00Z"
            }
        }
    }
    
    rem_data = {"meta": {"schema": 2}, "tasks": {}}
    links_data = {"meta": {"schema": 1}, "links": []}
    
    plan = creator.create_plan(obs_data, rem_data, links_data)
    
    assert plan.total_creates == 1
    
    # Validate that long description is preserved (may be stripped of whitespace)
    obs_item = plan.obs_to_rem[0]
    assert len(obs_item["mapped_fields"]["title"]) > 1000
    assert obs_item["mapped_fields"]["title"] == long_description.strip()
    
    print("✓ Very long descriptions test passed")

def test_missing_required_fields():
    """Test tasks with missing required fields."""
    print("Testing missing required fields...")
    
    creator = MissingCounterpartsCreator()
    today = get_today_string()
    
    # Task with missing description
    obs_data = {
        "meta": {"schema": 2},
        "tasks": {
            "obs-no-desc": {
                "uuid": "obs-no-desc",
                # "description": missing
                "status": "todo",
                "updated_at": f"{today}T09:00:00Z"
            }
        }
    }
    
    rem_data = {
        "meta": {"schema": 2},
        "tasks": {
            "rem-no-desc": {
                "uuid": "rem-no-desc",
                # "description": missing
                "is_completed": False,
                "updated_at": f"{today}T09:00:00Z"
            }
        }
    }
    
    links_data = {"meta": {"schema": 1}, "links": []}
    
    plan = creator.create_plan(obs_data, rem_data, links_data)
    
    assert plan.total_creates == 2
    
    # Validate that default descriptions are provided
    obs_item = plan.obs_to_rem[0]
    assert obs_item["mapped_fields"]["title"] == "Untitled Task"
    
    rem_item = plan.rem_to_obs[0]
    assert rem_item["mapped_fields"]["description"] == "Untitled Task"
    
    print("✓ Missing required fields test passed")

def test_invalid_date_formats():
    """Test handling of invalid date formats."""
    print("Testing invalid date formats...")
    
    creator = MissingCounterpartsCreator()
    today = get_today_string()
    
    obs_data = {
        "meta": {"schema": 2},
        "tasks": {
            "obs-bad-date": {
                "uuid": "obs-bad-date",
                "description": "Task with bad date",
                "status": "todo",
                "due": "not-a-date",
                "updated_at": f"{today}T09:00:00Z"
            }
        }
    }
    
    rem_data = {
        "meta": {"schema": 2},
        "tasks": {
            "rem-bad-date": {
                "uuid": "rem-bad-date",
                "description": "Reminder with bad date",
                "is_completed": False,
                "due_date": "invalid-date-format",
                "updated_at": f"{today}T09:00:00Z"
            }
        }
    }
    
    links_data = {"meta": {"schema": 1}, "links": []}
    
    plan = creator.create_plan(obs_data, rem_data, links_data)
    
    assert plan.total_creates == 2
    
    # Validate that invalid dates are handled gracefully
    obs_item = plan.obs_to_rem[0]
    # Should not have due_date in mapped_fields if original was invalid
    assert "due_date" not in obs_item["mapped_fields"]
    
    rem_item = plan.rem_to_obs[0]
    # Should not have due in mapped_fields if original was invalid
    assert "due" not in rem_item["mapped_fields"]
    
    print("✓ Invalid date formats test passed")

def test_schema_v2_compliance():
    """Test that generated plans comply with Schema v2."""
    print("Testing Schema v2 compliance...")
    
    creator = MissingCounterpartsCreator()
    today = get_today_string()
    
    obs_data = {
        "meta": {"schema": 2, "generated_at": f"{today}T10:00:00Z"},
        "tasks": {
            "obs-compliant": {
                "uuid": "obs-compliant",
                "source_key": "block:Vault:file.md:t-abc123",
                "aliases": ["block:Vault:file.md:t-abc123"],
                "vault": {"name": "Vault", "path": "/path/to/vault"},
                "file": {
                    "relative_path": "file.md",
                    "absolute_path": "/path/to/vault/file.md",
                    "line": 10,
                    "heading": None,
                    "created_at": f"{today}T08:00:00Z",
                    "modified_at": f"{today}T09:00:00Z"
                },
                "status": "todo",
                "description": "Schema v2 compliant task",
                "raw": "- [ ] Schema v2 compliant task ^t-abc123",
                "tags": ["#test"],
                "due": today,
                "priority": "high",
                "block_id": "t-abc123",
                "external_ids": {"block_id": "t-abc123"},
                "fingerprint": "abc123def456",
                "created_at": f"{today}T08:00:00Z",
                "updated_at": f"{today}T09:00:00Z",
                "last_seen": f"{today}T09:00:00Z",
                "cached_tokens": ["schema", "v2", "compliant", "task"],
                "title_hash": "12345678"
            }
        }
    }
    
    rem_data = {
        "meta": {"schema": 2, "generated_at": f"{today}T10:00:00Z"},
        "tasks": {
            "rem-compliant": {
                "uuid": "rem-compliant",
                "source_key": "rem:abc-123-def-456",
                "aliases": ["rem:abc-123-def-456", "reminder:list-id:abc-123-def-456"],
                "list": {
                    "name": "Test List",
                    "identifier": "list-id",
                    "source": {"name": "iCloud", "type": "2"},
                    "color": "#FF0000"
                },
                "status": "todo",
                "description": "Schema v2 compliant reminder",
                "notes": "Additional notes",
                "url": None,
                "priority": 5,
                "due": today,
                "alarms": [],
                "item_created_at": f"{today}T08:00:00Z",
                "item_modified_at": f"{today}T09:00:00Z",
                "external_ids": {
                    "external": "abc-123-def-456",
                    "item": "abc-123-def-456",
                    "calendar": "list-id"
                },
                "fingerprint": "def456ghi789",
                "created_at": f"{today}T08:00:00Z",
                "updated_at": f"{today}T09:00:00Z",
                "last_seen": f"{today}T09:00:00Z",
                "cached_tokens": ["schema", "v2", "compliant", "reminder"],
                "title_hash": "87654321"
            }
        }
    }
    
    links_data = {"meta": {"schema": 1}, "links": []}
    
    plan = creator.create_plan(obs_data, rem_data, links_data)
    
    assert plan.total_creates == 2
    
    # Validate Schema v2 compliance
    obs_item = plan.obs_to_rem[0]
    obs_task = obs_item["obs_task"]
    
    # Check required Schema v2 fields
    required_fields = ["uuid", "source_key", "vault", "file", "status", "description"]
    for field in required_fields:
        assert field in obs_task, f"Missing required field: {field}"
    
    # Check vault structure
    assert "name" in obs_task["vault"]
    assert "path" in obs_task["vault"]
    
    # Check file structure
    assert "relative_path" in obs_task["file"]
    assert "absolute_path" in obs_task["file"]
    assert "line" in obs_task["file"]
    
    rem_item = plan.rem_to_obs[0]
    rem_task = rem_item["rem_task"]
    
    # Check required Schema v2 fields for reminders
    required_rem_fields = ["uuid", "source_key", "list", "status", "description"]
    for field in required_rem_fields:
        assert field in rem_task, f"Missing required field: {field}"
    
    # Check list structure
    assert "name" in rem_task["list"]
    assert "identifier" in rem_task["list"]
    
    print("✓ Schema v2 compliance test passed")

def test_priority_mapping_edge_cases():
    """Test edge cases in priority mapping."""
    print("Testing priority mapping edge cases...")
    
    creator = MissingCounterpartsCreator()
    today = get_today_string()
    
    # Test various priority values
    test_cases = [
        # (input_priority, expected_obs_to_rem, expected_rem_to_obs)
        ("high", 1, "high"),
        ("medium", 5, "medium"),
        ("low", 9, "low"),
        ("", None, None),
        ("invalid", None, None),
        (None, None, None),
        (0, None, "high"),    # For reminders: 0 -> high priority
        (1, None, "high"),    # For reminders: 1 -> high priority  
        (2, None, "medium"),  # For reminders: 2 -> medium priority
        (5, None, "medium"),  # For reminders: 5 -> medium priority
        (9, None, "low"),     # For reminders: 9 -> low priority
        (10, None, "low"),    # For reminders: 10 -> low priority (>=9)
    ]
    
    for i, (priority, expected_rem, expected_obs) in enumerate(test_cases[:6]):  # Test Obsidian priorities first
        obs_data = {
            "meta": {"schema": 2},
            "tasks": {
                f"obs-{i}": {
                    "uuid": f"obs-{i}",
                    "description": f"Priority test {i}",
                    "status": "todo",
                    "priority": priority,
                    "updated_at": f"{today}T09:00:00Z"
                }
            }
        }
        
        rem_data = {"meta": {"schema": 2}, "tasks": {}}
        links_data = {"meta": {"schema": 1}, "links": []}
        
        plan = creator.create_plan(obs_data, rem_data, links_data)
        
        if plan.obs_to_rem:
            mapped_priority = plan.obs_to_rem[0]["mapped_fields"].get("priority")
            if expected_rem is None:
                assert "priority" not in plan.obs_to_rem[0]["mapped_fields"]
            else:
                assert mapped_priority == expected_rem
    
    # Test Reminders priorities
    for i, (priority, expected_rem, expected_obs) in enumerate(test_cases[6:], start=6):
        rem_data = {
            "meta": {"schema": 2},
            "tasks": {
                f"rem-{i}": {
                    "uuid": f"rem-{i}",
                    "description": f"Priority test {i}",
                    "is_completed": False,
                    "priority": priority,
                    "updated_at": f"{today}T09:00:00Z"
                }
            }
        }
        
        obs_data = {"meta": {"schema": 2}, "tasks": {}}
        links_data = {"meta": {"schema": 1}, "links": []}
        
        plan = creator.create_plan(obs_data, rem_data, links_data)
        
        if plan.rem_to_obs:
            mapped_priority = plan.rem_to_obs[0]["mapped_fields"].get("priority")
            if expected_obs is None:
                assert "priority" not in plan.rem_to_obs[0]["mapped_fields"]
            else:
                assert mapped_priority == expected_obs
    
    print("✓ Priority mapping edge cases test passed")

def run_all_edge_case_tests():
    """Run all edge case tests."""
    print("=" * 60)
    print("RUNNING EDGE CASE TESTS FOR CREATE MISSING COUNTERPARTS")
    print("=" * 60)
    
    tests = [
        test_empty_indices,
        test_all_tasks_linked,
        test_tasks_with_special_characters,
        test_very_long_descriptions,
        test_missing_required_fields,
        test_invalid_date_formats,
        test_schema_v2_compliance,
        test_priority_mapping_edge_cases
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
    print(f"EDGE CASE TEST RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)
    
    if failed == 0:
        print("🎉 ALL EDGE CASE TESTS PASSED!")
        return True
    else:
        print(f"❌ {failed} edge case tests failed")
        return False

if __name__ == "__main__":
    success = run_all_edge_case_tests()
    sys.exit(0 if success else 1)