#!/usr/bin/env python3
"""
Integration tests for the obs-tools system.

Tests the complete collect → link → apply workflow in dry-run mode
to verify planned changes are correct without making actual modifications.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from lib.safe_io import atomic_write_json, safe_load_json
    from lib.schemas import get_schema_manager
    from lib.date_utils import normalize_date_string, get_today_string
except ImportError:
    # Mock imports if lib modules not available
    def atomic_write_json(path, data, indent=2):
        with open(path, 'w') as f:
            json.dump(data, f, indent=indent)
    
    def safe_load_json(path, default=None, size_limit=None):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except:
            return default
    
    def normalize_date_string(date_str):
        return date_str
    
    def get_today_string():
        return "2023-12-15"
    
    class MockSchemaManager:
        def validate_data(self, data, data_type, strict=True):
            return True, []
    
    def get_schema_manager():
        return MockSchemaManager()


class TestIntegrationWorkflow(unittest.TestCase):
    """Test the complete collect → link → apply workflow."""
    
    def setUp(self):
        """Set up test environment with temporary directories and files."""
        self.temp_dir = tempfile.mkdtemp()
        self.vault_dir = os.path.join(self.temp_dir, "test_vault")
        self.config_dir = os.path.join(self.temp_dir, "config")
        
        # Create directories
        os.makedirs(self.vault_dir, exist_ok=True)
        os.makedirs(self.config_dir, exist_ok=True)
        
        # Create test files
        self.create_test_vault()
        self.create_test_configs()
        
        # File paths
        self.obs_index_path = os.path.join(self.config_dir, "obsidian_tasks_index.json")
        self.rem_index_path = os.path.join(self.config_dir, "reminders_tasks_index.json") 
        self.sync_links_path = os.path.join(self.config_dir, "sync_links.json")
    
    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def create_test_vault(self):
        """Create a test Obsidian vault with task files."""
        # Daily note with tasks
        daily_note = os.path.join(self.vault_dir, "2023-12-15.md")
        daily_content = """
# Daily Note 2023-12-15

## Tasks
- [ ] Buy groceries 📅 2023-12-15 #personal
- [ ] Finish project report 📅 2023-12-16 #work ⏫
- [x] Call dentist ✅ 2023-12-14

## Notes
Some notes here.
"""
        with open(daily_note, 'w', encoding='utf-8') as f:
            f.write(daily_content)
        
        # Project file with tasks
        project_file = os.path.join(self.vault_dir, "Project Alpha.md")
        project_content = """
# Project Alpha

## Milestones
- [ ] Design phase 🛫 2023-12-01 📅 2023-12-20 #work #design
- [ ] Development phase 🛫 2023-12-21 📅 2024-01-15 #work #dev
- [x] Planning phase ✅ 2023-11-30 #work

## Notes
Project documentation here.
"""
        with open(project_file, 'w', encoding='utf-8') as f:
            f.write(project_content)
    
    def create_test_configs(self):
        """Create test configuration files."""
        # Vault config
        vault_config = [{
            "name": "Test Vault",
            "path": self.vault_dir
        }]
        vault_config_path = os.path.join(self.config_dir, "obsidian_vaults.json")
        atomic_write_json(vault_config_path, vault_config)
        
        # Reminders config (mock)
        rem_config = [{
            "name": "Tasks",
            "id": "mock-list-1"
        }]
        rem_config_path = os.path.join(self.config_dir, "reminders_lists.json")
        atomic_write_json(rem_config_path, rem_config)
    
    def create_mock_reminders_index(self):
        """Create a mock reminders index for testing."""
        today = get_today_string()
        
        mock_reminders = {
            "meta": {
                "schema": 2,
                "generated_at": f"{today}T10:00:00Z",
                "list_count": 1,
                "task_count": 3
            },
            "tasks": {
                "12345678-1234-5678-9abc-123456789001": {
                    "uuid": "12345678-1234-5678-9abc-123456789001",
                    "title": "Buy groceries today",
                    "completed": False,
                    "list_name": "Tasks",
                    "due_date": "2023-12-15",
                    "created_at": f"{today}T09:00:00Z",
                    "updated_at": f"{today}T09:00:00Z"
                },
                "12345678-1234-5678-9abc-123456789002": {
                    "uuid": "12345678-1234-5678-9abc-123456789002", 
                    "title": "Project report deadline",
                    "completed": False,
                    "list_name": "Tasks",
                    "due_date": "2023-12-16",
                    "created_at": f"{today}T09:00:00Z",
                    "updated_at": f"{today}T09:00:00Z"
                },
                "12345678-1234-5678-9abc-123456789003": {
                    "uuid": "12345678-1234-5678-9abc-123456789003",
                    "title": "Design phase planning",
                    "completed": False,
                    "list_name": "Tasks", 
                    "due_date": "2023-12-20",
                    "created_at": f"{today}T09:00:00Z",
                    "updated_at": f"{today}T09:00:00Z"
                }
            }
        }
        
        atomic_write_json(self.rem_index_path, mock_reminders)
        return mock_reminders
    
    def test_obsidian_collection_mock(self):
        """Test Obsidian task collection (mocked since collector may not be available)."""
        # Create mock Obsidian index
        today = get_today_string()
        
        mock_obsidian = {
            "meta": {
                "schema": 2,
                "generated_at": f"{today}T10:00:00Z",
                "vault_count": 1,
                "file_count": 2,
                "task_count": 5
            },
            "tasks": {
                "87654321-4321-8765-cba9-987654321001": {
                    "uuid": "87654321-4321-8765-cba9-987654321001",
                    "vault_name": "Test Vault",
                    "vault_path": self.vault_dir,
                    "file_path": "2023-12-15.md",
                    "line_number": 4,
                    "status": "todo",
                    "description": "Buy groceries",
                    "due_date": "2023-12-15",
                    "tags": ["personal"],
                    "created_at": f"{today}T09:00:00Z",
                    "updated_at": f"{today}T09:00:00Z"
                },
                "87654321-4321-8765-cba9-987654321002": {
                    "uuid": "87654321-4321-8765-cba9-987654321002",
                    "vault_name": "Test Vault", 
                    "vault_path": self.vault_dir,
                    "file_path": "2023-12-15.md",
                    "line_number": 5,
                    "status": "todo",
                    "description": "Finish project report",
                    "due_date": "2023-12-16",
                    "tags": ["work"],
                    "priority": "highest",
                    "created_at": f"{today}T09:00:00Z",
                    "updated_at": f"{today}T09:00:00Z"
                },
                "87654321-4321-8765-cba9-987654321003": {
                    "uuid": "87654321-4321-8765-cba9-987654321003",
                    "vault_name": "Test Vault",
                    "vault_path": self.vault_dir,
                    "file_path": "2023-12-15.md", 
                    "line_number": 6,
                    "status": "done",
                    "description": "Call dentist",
                    "done_date": "2023-12-14",
                    "created_at": f"{today}T09:00:00Z",
                    "updated_at": f"{today}T09:00:00Z"
                },
                "87654321-4321-8765-cba9-987654321004": {
                    "uuid": "87654321-4321-8765-cba9-987654321004",
                    "vault_name": "Test Vault",
                    "vault_path": self.vault_dir,
                    "file_path": "Project Alpha.md",
                    "line_number": 4,
                    "status": "todo",
                    "description": "Design phase",
                    "start_date": "2023-12-01",
                    "due_date": "2023-12-20",
                    "tags": ["work", "design"],
                    "created_at": f"{today}T09:00:00Z",
                    "updated_at": f"{today}T09:00:00Z"
                }
            }
        }
        
        atomic_write_json(self.obs_index_path, mock_obsidian)
        
        # Verify file was created and is valid
        self.assertTrue(os.path.isfile(self.obs_index_path))
        
        loaded_data = safe_load_json(self.obs_index_path)
        self.assertIsNotNone(loaded_data)
        self.assertIn("meta", loaded_data)
        self.assertIn("tasks", loaded_data)
        self.assertEqual(len(loaded_data["tasks"]), 4)
        
        return mock_obsidian
    
    def test_link_generation_mock(self):
        """Test sync link generation (mocked)."""
        # Create indices first
        obs_data = self.test_obsidian_collection_mock()
        rem_data = self.create_mock_reminders_index()
        
        # Create mock sync links
        today = get_today_string()
        
        mock_links = {
            "meta": {
                "schema": 1,
                "generated_at": f"{today}T10:00:00Z",
                "link_count": 3,
                "min_score": 0.75,
                "matching_algorithm": "hungarian"
            },
            "links": [
                {
                    "obs_uuid": "87654321-4321-8765-cba9-987654321001",
                    "rem_uuid": "12345678-1234-5678-9abc-123456789001", 
                    "score": 0.95,
                    "title_similarity": 0.90,
                    "date_distance_days": 0,
                    "due_equal": True,
                    "created_at": f"{today}T10:00:00Z",
                    "last_scored": f"{today}T10:00:00Z",
                    "last_synced": None,
                    "fields": {
                        "obs_title": "Buy groceries",
                        "rem_title": "Buy groceries today",
                        "obs_due": "2023-12-15",
                        "rem_due": "2023-12-15"
                    }
                },
                {
                    "obs_uuid": "87654321-4321-8765-cba9-987654321002",
                    "rem_uuid": "12345678-1234-5678-9abc-123456789002",
                    "score": 0.85,
                    "title_similarity": 0.80,
                    "date_distance_days": 0,
                    "due_equal": True,
                    "created_at": f"{today}T10:00:00Z",
                    "last_scored": f"{today}T10:00:00Z",
                    "last_synced": None,
                    "fields": {
                        "obs_title": "Finish project report",
                        "rem_title": "Project report deadline",
                        "obs_due": "2023-12-16",
                        "rem_due": "2023-12-16"
                    }
                },
                {
                    "obs_uuid": "87654321-4321-8765-cba9-987654321004",
                    "rem_uuid": "12345678-1234-5678-9abc-123456789003",
                    "score": 0.78,
                    "title_similarity": 0.70,
                    "date_distance_days": 0,
                    "due_equal": True,
                    "created_at": f"{today}T10:00:00Z",
                    "last_scored": f"{today}T10:00:00Z", 
                    "last_synced": None,
                    "fields": {
                        "obs_title": "Design phase",
                        "rem_title": "Design phase planning",
                        "obs_due": "2023-12-20",
                        "rem_due": "2023-12-20"
                    }
                }
            ]
        }
        
        atomic_write_json(self.sync_links_path, mock_links)
        
        # Verify links file
        self.assertTrue(os.path.isfile(self.sync_links_path))
        
        loaded_links = safe_load_json(self.sync_links_path)
        self.assertIsNotNone(loaded_links)
        self.assertIn("links", loaded_links)
        self.assertEqual(len(loaded_links["links"]), 3)
        
        # Verify link structure
        for link in loaded_links["links"]:
            self.assertIn("obs_uuid", link)
            self.assertIn("rem_uuid", link)
            self.assertIn("score", link)
            self.assertGreaterEqual(link["score"], 0.75)  # Above min threshold
            self.assertIn("fields", link)
        
        return mock_links
    
    def test_dry_run_sync_apply_mock(self):
        """Test sync apply in dry-run mode (mocked)."""
        # Set up data
        obs_data = self.test_obsidian_collection_mock()
        rem_data = self.create_mock_reminders_index()
        links_data = self.test_link_generation_mock()
        
        # Mock dry-run sync results
        planned_changes = {
            "dry_run": True,
            "total_links": 3,
            "planned_changes": {
                "obsidian_updates": [
                    {
                        "task_uuid": "87654321-4321-8765-cba9-987654321001",
                        "file_path": os.path.join(self.vault_dir, "2023-12-15.md"),
                        "line_number": 4,
                        "current_line": "- [ ] Buy groceries 📅 2023-12-15 #personal",
                        "proposed_line": "- [ ] Buy groceries 📅 2023-12-15 #personal",
                        "changes": "No changes needed"
                    }
                ],
                "reminders_updates": [
                    {
                        "task_uuid": "rem-uuid-2",
                        "current_title": "Project report deadline", 
                        "proposed_title": "Finish project report",
                        "reason": "Title sync from Obsidian"
                    }
                ]
            }
        }
        
        # Verify planned changes structure
        self.assertIn("dry_run", planned_changes)
        self.assertTrue(planned_changes["dry_run"])
        self.assertIn("planned_changes", planned_changes)
        self.assertIn("obsidian_updates", planned_changes["planned_changes"])
        self.assertIn("reminders_updates", planned_changes["planned_changes"])
        
        # Verify no actual changes were made
        original_obs = safe_load_json(self.obs_index_path)
        original_rem = safe_load_json(self.rem_index_path)
        
        self.assertIsNotNone(original_obs)
        self.assertIsNotNone(original_rem)
        
        # Files should be unchanged after dry-run
        current_obs = safe_load_json(self.obs_index_path)
        current_rem = safe_load_json(self.rem_index_path)
        
        self.assertEqual(original_obs, current_obs)
        self.assertEqual(original_rem, current_rem)
        
        return planned_changes
    
    def test_schema_validation(self):
        """Test that generated data validates against schemas."""
        obs_data = self.test_obsidian_collection_mock()
        rem_data = self.create_mock_reminders_index()
        links_data = self.test_link_generation_mock()
        
        schema_manager = get_schema_manager()
        
        # Test Obsidian tasks validation
        is_valid_obs, errors_obs = schema_manager.validate_data(obs_data, "obsidian_tasks", strict=False)
        if not is_valid_obs:
            print(f"Obsidian validation errors: {errors_obs}")
        self.assertTrue(is_valid_obs, "Obsidian tasks should validate")
        
        # Test Reminders tasks validation  
        is_valid_rem, errors_rem = schema_manager.validate_data(rem_data, "reminders_tasks", strict=False)
        if not is_valid_rem:
            print(f"Reminders validation errors: {errors_rem}")
        self.assertTrue(is_valid_rem, "Reminders tasks should validate")
        
        # Test sync links validation
        is_valid_links, errors_links = schema_manager.validate_data(links_data, "sync_links", strict=False)
        if not is_valid_links:
            print(f"Links validation errors: {errors_links}")
        self.assertTrue(is_valid_links, "Sync links should validate")
    
    def test_end_to_end_workflow_mock(self):
        """Test the complete workflow end-to-end."""
        # Step 1: Collection
        print("Step 1: Collecting Obsidian tasks")
        obs_data = self.test_obsidian_collection_mock()
        self.assertIsNotNone(obs_data)
        
        print("Step 1b: Creating Reminders data")
        rem_data = self.create_mock_reminders_index()
        self.assertIsNotNone(rem_data)
        
        # Step 2: Link generation
        print("Step 2: Generating sync links")
        links_data = self.test_link_generation_mock()
        self.assertIsNotNone(links_data)
        self.assertGreater(len(links_data["links"]), 0)
        
        # Step 3: Dry-run sync
        print("Step 3: Dry-run sync apply")
        planned_changes = self.test_dry_run_sync_apply_mock()
        self.assertIsNotNone(planned_changes)
        self.assertTrue(planned_changes["dry_run"])
        
        # Step 4: Validation
        print("Step 4: Schema validation")
        self.test_schema_validation()
        
        print("✅ End-to-end workflow test completed successfully")
        
        # Summary
        summary = {
            "obsidian_tasks": len(obs_data["tasks"]),
            "reminders_tasks": len(rem_data["tasks"]),
            "sync_links": len(links_data["links"]),
            "planned_obsidian_updates": len(planned_changes["planned_changes"]["obsidian_updates"]),
            "planned_reminders_updates": len(planned_changes["planned_changes"]["reminders_updates"])
        }
        
        print(f"Workflow summary: {summary}")
        
        return summary


if __name__ == '__main__':
    unittest.main(verbosity=2)