#!/usr/bin/env python3
"""
Tests for create_missing_counterparts module.

This module tests the functionality for creating missing counterpart tasks
between Obsidian and Apple Reminders, including:
- Task filtering and identification
- Field mapping between systems
- Creation plan generation
- Dry-run mode
- Configuration system integration
- Error handling
"""

import json
import os
import pytest
import sys
import tempfile
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any
from unittest.mock import Mock, patch, MagicMock

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obs_tools.commands.create_missing_counterparts import (
    MissingCounterpartsCreator,
    CreationPlan,
    CreationResult,
    CreationConfig,
    main
)
from app_config import CreationDefaults, ObsToRemRule, RemToObsRule
from lib.date_utils import get_today_string, days_ago


class TestCreationConfig:
    """Test CreationConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = CreationConfig()
        assert config.obs_inbox_file == "~/Documents/Obsidian/Default/Tasks.md"
        assert config.rem_default_calendar_id is None
        assert config.max_creates_per_run == 50
        assert config.since_days == 30
        assert config.include_done is False
        assert isinstance(config.obs_to_rem_rules, list)
        assert isinstance(config.rem_to_obs_rules, list)
        assert config.vault_path_to_list == {}
        assert config.vault_name_to_list == {}
        assert config.default_vault_path is None
        assert config.default_vault_name is None
        assert config.default_vault_list_id is None
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = CreationConfig(
            obs_inbox_file="~/custom/inbox.md",
            rem_default_calendar_id="cal-123",
            max_creates_per_run=25,
            since_days=14,
            include_done=True
        )
        assert config.obs_inbox_file == "~/custom/inbox.md"
        assert config.rem_default_calendar_id == "cal-123"
        assert config.max_creates_per_run == 25
        assert config.since_days == 14
        assert config.include_done is True
        assert config.vault_path_to_list == {}
        assert config.vault_name_to_list == {}


class TestCreationPlan:
    """Test CreationPlan dataclass."""
    
    def test_empty_plan(self):
        """Test empty creation plan."""
        plan = CreationPlan()
        assert plan.obs_to_rem == []
        assert plan.rem_to_obs == []
        assert plan.total_creates == 0
        assert plan.direction == "both"
        assert isinstance(plan.filters_applied, dict)
    
    def test_plan_with_data(self):
        """Test creation plan with data."""
        plan = CreationPlan(
            obs_to_rem=[{"uuid": "obs-1"}],
            rem_to_obs=[{"uuid": "rem-1"}, {"uuid": "rem-2"}],
            direction="both"
        )
        assert len(plan.obs_to_rem) == 1
        assert len(plan.rem_to_obs) == 2
        assert plan.total_creates == 3


class TestMissingCounterpartsCreator:
    """Test MissingCounterpartsCreator class."""
    
    @pytest.fixture
    def creator(self):
        """Create a MissingCounterpartsCreator instance for testing."""
        config = CreationConfig(
            obs_inbox_file="~/test/inbox.md",
            rem_default_calendar_id="test-cal-id",
            max_creates_per_run=10,
            since_days=7
        )
        return MissingCounterpartsCreator(config, logger=Mock())
    
    @pytest.fixture
    def sample_obs_index(self):
        """Sample Obsidian tasks index."""
        return {
            "meta": {"schema": 2, "generated_at": "2023-12-15T10:00:00Z"},
            "tasks": {
                "obs-1": {
                    "uuid": "obs-1",
                    "description": "Buy groceries",
                    "status": "todo",
                    "due": "2023-12-15",
                    "priority": "high",
                    "tags": ["#personal"],
                    "file": {"relative_path": "daily/2023-12-15.md", "line": 5},
                    "vault": {"name": "TestVault"},
                    "block_id": "abc123",
                    "created_at": "2023-12-15T09:00:00Z",
                    "updated_at": "2023-12-15T09:00:00Z"
                },
                "obs-2": {
                    "uuid": "obs-2",
                    "description": "Project meeting",
                    "status": "todo",
                    "due": "2023-12-16",
                    "tags": ["#work"],
                    "file": {"relative_path": "projects/alpha.md", "line": 10},
                    "vault": {"name": "TestVault"},
                    "block_id": "def456",
                    "created_at": "2023-12-14T09:00:00Z",
                    "updated_at": "2023-12-14T09:00:00Z"
                },
                "obs-3": {
                    "uuid": "obs-3",
                    "description": "Completed task",
                    "status": "done",
                    "created_at": "2023-12-10T09:00:00Z",
                    "updated_at": "2023-12-10T09:00:00Z"
                }
            }
        }
    
    @pytest.fixture
    def sample_rem_index(self):
        """Sample Reminders tasks index."""
        return {
            "meta": {"schema": 2, "generated_at": "2023-12-15T10:00:00Z"},
            "tasks": {
                "rem-1": {
                    "uuid": "rem-1",
                    "description": "Buy milk",
                    "is_completed": False,
                    "due_date": "2023-12-15",
                    "priority": 5,
                    "list": {"name": "Personal", "identifier": "list-personal"},
                    "created_at": "2023-12-15T08:00:00Z",
                    "updated_at": "2023-12-15T08:00:00Z"
                },
                "rem-2": {
                    "uuid": "rem-2",
                    "description": "Team standup",
                    "is_completed": False,
                    "due_date": "2023-12-16",
                    "priority": 9,
                    "list": {"name": "Work", "identifier": "list-work"},
                    "created_at": "2023-12-14T08:00:00Z",
                    "updated_at": "2023-12-14T08:00:00Z"
                },
                "rem-3": {
                    "uuid": "rem-3",
                    "description": "Old completed task",
                    "is_completed": True,
                    "created_at": "2023-12-01T08:00:00Z",
                    "updated_at": "2023-12-01T08:00:00Z"
                }
            }
        }
    
    @pytest.fixture
    def sample_links_data(self):
        """Sample sync links data."""
        return {
            "meta": {"schema": 1, "generated_at": "2023-12-15T10:00:00Z"},
            "links": [
                {
                    "obs_uuid": "obs-linked",
                    "rem_uuid": "rem-linked",
                    "score": 0.9,
                    "created_at": "2023-12-15T09:00:00Z"
                }
            ]
        }
    
    def test_load_indices_and_links(self, creator, temp_dir):
        """Test loading indices and links files."""
        # Create test files
        obs_path = os.path.join(temp_dir, "obs.json")
        rem_path = os.path.join(temp_dir, "rem.json")
        links_path = os.path.join(temp_dir, "links.json")
        
        obs_data = {"meta": {}, "tasks": {"obs-1": {"uuid": "obs-1"}}}
        rem_data = {"meta": {}, "tasks": {"rem-1": {"uuid": "rem-1"}}}
        links_data = {"meta": {}, "links": []}
        
        with open(obs_path, 'w') as f:
            json.dump(obs_data, f)
        with open(rem_path, 'w') as f:
            json.dump(rem_data, f)
        with open(links_path, 'w') as f:
            json.dump(links_data, f)
        
        obs_index, rem_index, links = creator.load_indices_and_links(obs_path, rem_path, links_path)
        
        assert obs_index == obs_data
        assert rem_index == rem_data
        assert links == links_data
    
    def test_build_linked_sets(self, creator, sample_links_data):
        """Test building sets of linked task UUIDs."""
        linked_obs, linked_rem = creator.build_linked_sets(sample_links_data)
        
        assert "obs-linked" in linked_obs
        assert "rem-linked" in linked_rem
        assert len(linked_obs) == 1
        assert len(linked_rem) == 1
    
    def test_filter_tasks_basic(self, creator):
        """Test basic task filtering."""
        tasks = {
            "task-1": {"uuid": "task-1", "status": "todo", "updated_at": "2023-12-15T09:00:00Z"},
            "task-2": {"uuid": "task-2", "status": "done", "updated_at": "2023-12-15T09:00:00Z"},
            "task-3": {"uuid": "task-3", "status": "todo", "deleted": True},
            "task-4": {"uuid": "task-4", "status": "todo", "missing_since": "2023-12-14T09:00:00Z"}
        }
        linked_uuids = {"task-1"}
        
        filtered = creator.filter_tasks(tasks, linked_uuids, include_done=False)
        
        # Should only include task-2 (not linked, not done, not deleted/missing)
        # Wait, task-2 is done, so it should be excluded unless include_done=True
        # Actually only unlinked, non-done, non-deleted/missing tasks should remain
        # That's none in this case since task-1 is linked, task-2 is done, task-3 is deleted, task-4 is missing
        assert len(filtered) == 0
        
        # Test with include_done=True
        filtered_with_done = creator.filter_tasks(tasks, linked_uuids, include_done=True)
        assert "task-2" in filtered_with_done  # Now includes done tasks
        assert len(filtered_with_done) == 1
    
    def test_filter_tasks_by_date(self, creator):
        """Test task filtering by date."""
        old_date = days_ago(10)
        recent_date = days_ago(3)
        
        tasks = {
            "old-task": {"uuid": "old-task", "status": "todo", "updated_at": f"{old_date}T09:00:00Z"},
            "recent-task": {"uuid": "recent-task", "status": "todo", "updated_at": f"{recent_date}T09:00:00Z"}
        }
        
        filtered = creator.filter_tasks(tasks, set(), since_days=5)
        
        assert "recent-task" in filtered
        assert "old-task" not in filtered
    
    def test_map_obsidian_to_reminders_fields(self, creator):
        """Test mapping Obsidian task fields to Reminders format."""
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
        assert mapped["priority"] == 9  # high -> 9
        assert "Source: daily/2023-12-15.md" in mapped["notes"]
        assert "Line: 5" in mapped["notes"]
        assert "Tags: #personal, #shopping" in mapped["notes"]
        assert mapped["url"] == "obsidian://open?vault=TestVault&file=daily/2023-12-15.md#abc123"
    
    def test_map_reminders_to_obsidian_fields(self, creator):
        """Test mapping Reminders task fields to Obsidian format."""
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
    
    def test_determine_target_calendar(self, creator):
        """Test determining target calendar for Obsidian tasks."""
        # Set up mapping rules
        creator.config.obs_to_rem_rules = [
            {"tag": "#work", "calendar_id": "work-cal"},
            {"tag": "#personal", "calendar_id": "personal-cal"}
        ]
        creator.config.rem_default_calendar_id = "default-cal"

        # Task with matching rule
        work_task = {"tags": ["#work", "#project"]}
        assert creator.determine_target_calendar(work_task) == "work-cal"
        
        # Task without matching rule
        other_task = {"tags": ["#other"]}
        assert creator.determine_target_calendar(other_task) == "default-cal"
        
        # Task with no tags
        no_tags_task = {"tags": []}
        assert creator.determine_target_calendar(no_tags_task) == "default-cal"

    def test_determine_target_calendar_uses_vault_mapping(self, creator):
        """Ensure vault path/name mapping overrides defaults."""
        creator.config.obs_to_rem_rules = []
        target_path = os.path.abspath("/tmp/vaults/work")
        creator.config.vault_path_to_list = {target_path: "vault-cal"}
        creator.config.vault_name_to_list = {"work": "vault-cal"}
        obs_task = {"tags": [], "vault": {"name": "Work", "path": target_path}}

        assert creator.determine_target_calendar(obs_task) == "vault-cal"

    def test_determine_target_calendar_default_vault_fallback(self, creator):
        """Use default vault mapping when no explicit vault mapping exists."""
        creator.config.obs_to_rem_rules = []
        creator.config.rem_default_calendar_id = "global-default"
        creator.config.default_vault_path = os.path.abspath("/tmp/default_vault")
        creator.config.default_vault_name = "DefaultVault"
        creator.config.default_vault_list_id = "default-vault-cal"

        obs_task = {"tags": [], "vault": {"name": "DefaultVault", "path": "/tmp/default_vault"}}
        assert creator.determine_target_calendar(obs_task) == "default-vault-cal"

        # When vault metadata missing, fall back to default vault list before global default
        obs_task_no_vault = {"tags": []}
        assert creator.determine_target_calendar(obs_task_no_vault) == "default-vault-cal"

    def test_determine_target_file(self, creator):
        """Test determining target file for Reminders tasks."""
        # Set up mapping rules
        creator.config.rem_to_obs_rules = [
            {"list_name": "Work", "target_file": "~/work/tasks.md", "heading": "Imported"},
            {"list_name": "Personal", "target_file": "~/personal/tasks.md"}
        ]
        creator.config.obs_inbox_file = "~/inbox.md"
        
        # Task with matching rule
        work_task = {"list": {"name": "Work"}}
        file_path, heading = creator.determine_target_file(work_task)
        assert file_path == "~/work/tasks.md"
        assert heading == "Imported"
        
        # Task with matching rule but no heading
        personal_task = {"list": {"name": "Personal"}}
        file_path, heading = creator.determine_target_file(personal_task)
        assert file_path == "~/personal/tasks.md"
        assert heading is None
        
        # Task without matching rule
        other_task = {"list": {"name": "Other"}}
        file_path, heading = creator.determine_target_file(other_task)
        assert file_path == "~/inbox.md"
        assert heading is None
    
    def test_create_plan_basic(self, creator, sample_obs_index, sample_rem_index, sample_links_data):
        """Test basic creation plan generation."""
        plan = creator.create_plan(
            sample_obs_index, 
            sample_rem_index, 
            sample_links_data,
            direction="both",
            include_done=False
        )
        
        # Should have tasks to create in both directions
        assert len(plan.obs_to_rem) > 0
        assert len(plan.rem_to_obs) > 0
        assert plan.direction == "both"
        assert plan.total_creates > 0
    
    def test_create_plan_direction_filtering(self, creator, sample_obs_index, sample_rem_index, sample_links_data):
        """Test creation plan with direction filtering."""
        # Test obs-to-rem only
        plan_obs_to_rem = creator.create_plan(
            sample_obs_index, 
            sample_rem_index, 
            sample_links_data,
            direction="obs-to-rem"
        )
        assert len(plan_obs_to_rem.obs_to_rem) > 0
        assert len(plan_obs_to_rem.rem_to_obs) == 0
        
        # Test rem-to-obs only
        plan_rem_to_obs = creator.create_plan(
            sample_obs_index, 
            sample_rem_index, 
            sample_links_data,
            direction="rem-to-obs"
        )
        assert len(plan_rem_to_obs.obs_to_rem) == 0
        assert len(plan_rem_to_obs.rem_to_obs) > 0
    
    def test_create_plan_max_creates_limit(self, creator, sample_obs_index, sample_rem_index, sample_links_data):
        """Test creation plan with max creates limit."""
        plan = creator.create_plan(
            sample_obs_index, 
            sample_rem_index, 
            sample_links_data,
            max_creates=1
        )
        
        assert plan.total_creates <= 1
    
    def test_create_plan_include_done_filter(self, creator, sample_obs_index, sample_rem_index, sample_links_data):
        """Test creation plan with include_done filter."""
        plan_exclude_done = creator.create_plan(
            sample_obs_index, 
            sample_rem_index, 
            sample_links_data,
            include_done=False
        )
        
        plan_include_done = creator.create_plan(
            sample_obs_index, 
            sample_rem_index, 
            sample_links_data,
            include_done=True
        )
        
        # Including done tasks should result in more or equal tasks
        assert plan_include_done.total_creates >= plan_exclude_done.total_creates
    
    @patch('obs_tools.commands.create_missing_counterparts.MissingCounterpartsCreator._create_reminder_counterpart')
    @patch('obs_tools.commands.create_missing_counterparts.MissingCounterpartsCreator._create_obsidian_counterpart')
    def test_execute_plan_success(self, mock_create_obs, mock_create_rem, creator, temp_dir):
        """Test successful plan execution."""
        # Mock successful creation
        mock_create_rem.return_value = {
            "rem_uuid": "new-rem-uuid",
            "rem_task": {"uuid": "new-rem-uuid", "description": "New reminder"}
        }
        mock_create_obs.return_value = {
            "obs_uuid": "new-obs-uuid", 
            "obs_task": {"uuid": "new-obs-uuid", "description": "New obsidian task"}
        }
        
        # Create a simple plan
        plan = CreationPlan(
            obs_to_rem=[{
                "obs_uuid": "obs-1",
                "obs_task": {"uuid": "obs-1", "description": "Test task"},
                "target_calendar_id": "cal-1",
                "mapped_fields": {"title": "Test task"}
            }],
            rem_to_obs=[{
                "rem_uuid": "rem-1",
                "rem_task": {"uuid": "rem-1", "description": "Test reminder"},
                "target_file": "~/test.md",
                "mapped_fields": {"description": "Test reminder"}
            }]
        )
        
        links_path = os.path.join(temp_dir, "links.json")
        with open(links_path, 'w') as f:
            json.dump({"meta": {}, "links": []}, f)
        
        result = creator.execute_plan(plan, links_path, "test-run")
        
        assert result.success
        assert result.created_rem == 1
        assert result.created_obs == 1
        assert len(result.new_links) == 2
        assert len(result.errors) == 0


class TestCLIInterface:
    """Test command-line interface."""
    
    def test_main_dry_run(self, temp_dir):
        """Test main function in dry-run mode."""
        # Create minimal test files
        obs_path = os.path.join(temp_dir, "obs.json")
        rem_path = os.path.join(temp_dir, "rem.json")
        links_path = os.path.join(temp_dir, "links.json")
        
        # Create empty but valid indices
        for path, data in [(obs_path, {"meta": {}, "tasks": {}}),
                          (rem_path, {"meta": {}, "tasks": {}}),
                          (links_path, {"meta": {}, "links": []})]:
            with open(path, 'w') as f:
                json.dump(data, f)
        
        # Test dry-run mode (should not fail)
        argv = [
            "--obs", obs_path,
            "--rem", rem_path, 
            "--links", links_path,
            "--dry-run",
            "--direction", "both"
        ]
        
        # Should return 0 (success) even with no tasks
        result = main(argv)
        assert result == 0
    
    def test_main_invalid_args(self):
        """Test main function with invalid arguments."""
        # Test with invalid direction
        argv = ["--direction", "invalid-direction"]
        
        result = main(argv)
        assert result != 0  # Should fail
    
    def test_main_missing_files(self):
        """Test main function with missing input files."""
        argv = [
            "--obs", "/nonexistent/obs.json",
            "--rem", "/nonexistent/rem.json",
            "--links", "/nonexistent/links.json"
        ]
        
        result = main(argv)
        assert result != 0  # Should fail gracefully


class TestFieldMapping:
    """Test field mapping functions."""
    
    def test_priority_mapping_obs_to_rem(self):
        """Test priority mapping from Obsidian to Reminders."""
        creator = MissingCounterpartsCreator()
        
        test_cases = [
            ({"priority": "high"}, 9),
            ({"priority": "medium"}, 5),
            ({"priority": "low"}, 1),
            ({"priority": "unknown"}, None),
            ({}, None)
        ]
        
        for obs_task, expected in test_cases:
            mapped = creator.map_obsidian_to_reminders_fields(obs_task)
            assert mapped.get("priority") == expected
    
    def test_priority_mapping_rem_to_obs(self):
        """Test priority mapping from Reminders to Obsidian."""
        creator = MissingCounterpartsCreator()
        
        test_cases = [
            ({"priority": 9}, "high"),
            ({"priority": 8}, "high"),
            ({"priority": 5}, "medium"),
            ({"priority": 3}, "medium"),
            ({"priority": 1}, "low"),
            ({"priority": 0}, None),
            ({}, None)
        ]
        
        for rem_task, expected in test_cases:
            mapped = creator.map_reminders_to_obsidian_fields(rem_task)
            assert mapped.get("priority") == expected
    
    def test_status_mapping_rem_to_obs(self):
        """Test status mapping from Reminders to Obsidian."""
        creator = MissingCounterpartsCreator()
        
        completed_task = {"is_completed": True}
        todo_task = {"is_completed": False}
        
        completed_mapped = creator.map_reminders_to_obsidian_fields(completed_task)
        todo_mapped = creator.map_reminders_to_obsidian_fields(todo_task)
        
        assert completed_mapped["status"] == "done"
        assert todo_mapped["status"] == "todo"
    
    def test_date_normalization(self):
        """Test date normalization in field mapping."""
        creator = MissingCounterpartsCreator()
        
        # Test various date formats
        date_formats = [
            "2023-12-15",
            "2023-12-15T10:00:00Z",
            "2023-12-15T10:00:00.000Z",
        ]
        
        for date_str in date_formats:
            obs_task = {"due": date_str}
            rem_task = {"due_date": date_str}
            
            obs_mapped = creator.map_obsidian_to_reminders_fields(obs_task)
            rem_mapped = creator.map_reminders_to_obsidian_fields(rem_task)
            
            assert obs_mapped["due_date"] == "2023-12-15"
            assert rem_mapped["due"] == "2023-12-15"


@pytest.mark.integration
class TestIntegration:
    """Integration tests that test the full workflow."""
    
    def test_full_workflow_dry_run(self, temp_dir):
        """Test complete workflow in dry-run mode."""
        # Create realistic test data
        obs_data = {
            "meta": {"schema": 2, "generated_at": "2023-12-15T10:00:00Z"},
            "tasks": {
                "obs-unlinked": {
                    "uuid": "obs-unlinked",
                    "description": "Unlinked Obsidian task",
                    "status": "todo",
                    "due": "2023-12-15",
                    "tags": ["#work"],
                    "file": {"relative_path": "test.md", "line": 1},
                    "vault": {"name": "Test"},
                    "block_id": "block123",
                    "created_at": "2023-12-15T09:00:00Z",
                    "updated_at": "2023-12-15T09:00:00Z"
                }
            }
        }
        
        rem_data = {
            "meta": {"schema": 2, "generated_at": "2023-12-15T10:00:00Z"},
            "tasks": {
                "rem-unlinked": {
                    "uuid": "rem-unlinked",
                    "description": "Unlinked Reminders task",
                    "is_completed": False,
                    "due_date": "2023-12-16",
                    "priority": 5,
                    "list": {"name": "Tasks"},
                    "created_at": "2023-12-15T09:00:00Z",
                    "updated_at": "2023-12-15T09:00:00Z"
                }
            }
        }
        
        links_data = {
            "meta": {"schema": 1, "generated_at": "2023-12-15T10:00:00Z"},
            "links": []
        }
        
        # Write test files
        obs_path = os.path.join(temp_dir, "obs.json")
        rem_path = os.path.join(temp_dir, "rem.json")
        links_path = os.path.join(temp_dir, "links.json")
        
        with open(obs_path, 'w') as f:
            json.dump(obs_data, f)
        with open(rem_path, 'w') as f:
            json.dump(rem_data, f)
        with open(links_path, 'w') as f:
            json.dump(links_data, f)
        
        # Run the command
        argv = [
            "--obs", obs_path,
            "--rem", rem_path,
            "--links", links_path,
            "--dry-run",
            "--direction", "both",
            "--verbose"
        ]
        
        result = main(argv)
        assert result == 0
        
        # Verify links file wasn't modified (dry-run)
        with open(links_path, 'r') as f:
            links_after = json.load(f)
        assert len(links_after["links"]) == 0


if __name__ == "__main__":
    pytest.main([__file__])
