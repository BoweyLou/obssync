#!/usr/bin/env python3
"""
Tests for vault-based organization system.

This test suite covers:
- Vault discovery and UUID generation
- List classification and mapping
- Vault-to-list sync mechanics
- Catch-all file management
- Legacy cleanup operations
- End-to-end workflow validation
"""

import json
import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

# Import modules under test
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.vault_organization import (
    VaultOrganizer, VaultListManager, generate_stable_vault_id,
    classify_reminders_list, VaultListPlan, CatchAllPlan
)
from lib.catch_all_manager import CatchAllManager, SectionInfo, FileStructure
from lib.legacy_cleanup import LegacyCleanupManager, CleanupPlan, DuplicateGroup
from lib.reminders_domain import (
    ListLocationType, RemindersList, ReminderItem, RemindersStoreSnapshot,
    VaultMapping, CatchAllMapping, ReminderStatus, ReminderPriority, DataSource
)
from lib.vault_observability import VaultMetricsCollector, OperationType, OperationStatus
from app_config import AppPreferences


class TestVaultOrganizer(unittest.TestCase):
    """Test vault organization orchestration."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.app_prefs = AppPreferences(
            vault_organization_enabled=True,
            default_vault_id="test-vault-1",
            catch_all_filename="OtherAppleReminders.md",
            auto_create_vault_lists=True
        )

        self.organizer = VaultOrganizer(
            app_prefs=self.app_prefs,
            vault_config={},
            reminders_config={}
        )

    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_generate_stable_vault_id(self):
        """Test stable vault ID generation."""
        path1 = "/Users/test/Documents/Vault1"
        path2 = "/Users/test/Documents/Vault2"

        # Same path should generate same ID
        id1a = generate_stable_vault_id(path1)
        id1b = generate_stable_vault_id(path1)
        self.assertEqual(id1a, id1b)

        # Different paths should generate different IDs
        id2 = generate_stable_vault_id(path2)
        self.assertNotEqual(id1a, id2)

        # ID should be valid UUID format
        import re
        uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        self.assertTrue(re.match(uuid_pattern, id1a))

    def test_analyze_current_mappings(self):
        """Test analysis of current vault-list mappings."""
        # Create test vaults
        vaults = [
            {"name": "Work", "path": "/path/to/work", "vault_id": "vault-1"},
            {"name": "Personal", "path": "/path/to/personal", "vault_id": "vault-2"},
            {"name": "Research", "path": "/path/to/research", "vault_id": "vault-3"}
        ]

        # Create test reminders lists
        lists = {
            "list-1": RemindersList(identifier="list-1", name="Work"),
            "list-2": RemindersList(identifier="list-2", name="Personal"),
            "list-3": RemindersList(identifier="list-3", name="Shopping"),
        }

        snapshot = RemindersStoreSnapshot(
            reminders={},
            lists=lists,
            collected_at=datetime.now().isoformat()
        )

        # Analyze mappings
        analysis = self.organizer.analyze_current_mappings(vaults, snapshot)

        # Verify analysis results
        self.assertEqual(analysis["vault_count"], 3)
        self.assertEqual(analysis["list_count"], 3)
        self.assertEqual(analysis["mapped_vaults"], 2)  # Work and Personal match
        self.assertEqual(len(analysis["unmapped_vaults"]), 1)  # Research
        self.assertEqual(len(analysis["unmapped_lists"]), 1)  # Shopping

        # Check potential mappings
        mapping_names = [m["vault_name"] for m in analysis["potential_mappings"]]
        self.assertIn("Work", mapping_names)
        self.assertIn("Personal", mapping_names)

    def test_generate_vault_list_plan(self):
        """Test vault-list plan generation."""
        vaults = [
            {"name": "Work", "path": "/path/to/work", "vault_id": "vault-1"},
            {"name": "Personal", "path": "/path/to/personal", "vault_id": "vault-2"}
        ]

        # No existing lists
        snapshot = RemindersStoreSnapshot(
            reminders={}, lists={}, collected_at=datetime.now().isoformat()
        )

        plans = self.organizer.generate_vault_list_plan(vaults, snapshot)

        # Verify plans
        self.assertEqual(len(plans), 2)

        work_plan = next(p for p in plans if p.vault_name == "Work")
        self.assertEqual(work_plan.action, "create")
        self.assertEqual(work_plan.target_list_name, "Work")

        personal_plan = next(p for p in plans if p.vault_name == "Personal")
        self.assertEqual(personal_plan.action, "create")
        self.assertEqual(personal_plan.target_list_name, "Personal")

    def test_generate_catch_all_plan(self):
        """Test catch-all plan generation."""
        unmapped_lists = [
            {"list_id": "list-1", "list_name": "Shopping"},
            {"list_id": "list-2", "list_name": "Travel Ideas"}
        ]

        default_vault_path = "/path/to/default/vault"
        plans = self.organizer.generate_catch_all_plan(unmapped_lists, default_vault_path)

        # Verify plans
        self.assertEqual(len(plans), 2)

        shopping_plan = next(p for p in plans if p.list_name == "Shopping")
        self.assertEqual(shopping_plan.section_heading, "## Shopping")
        self.assertEqual(shopping_plan.anchor_start, "<!-- obs-tools:section:shopping:start -->")
        self.assertEqual(shopping_plan.anchor_end, "<!-- obs-tools:section:shopping:end -->")

        travel_plan = next(p for p in plans if p.list_name == "Travel Ideas")
        self.assertEqual(travel_plan.section_heading, "## Travel Ideas")
        self.assertTrue("travel-ideas" in travel_plan.anchor_start)


class TestCatchAllManager(unittest.TestCase):
    """Test catch-all file management."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.temp_dir, "OtherAppleReminders.md")

    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_parse_empty_file(self):
        """Test parsing of non-existent file."""
        manager = CatchAllManager(self.test_file)
        structure = manager.parse_file_structure()

        # Should create default structure
        self.assertEqual(structure.file_path, self.test_file)
        self.assertTrue(len(structure.header_lines) > 0)
        self.assertEqual(len(structure.sections), 0)

    def test_parse_file_with_sections(self):
        """Test parsing of file with existing sections."""
        # Create test file with sections
        test_content = """# Other Apple Reminders

This file contains reminders from external lists.

<!-- obs-tools:section:shopping:start -->
## Shopping

- [ ] Buy groceries
- [x] Get new laptop

<!-- obs-tools:section:shopping:end -->

<!-- obs-tools:section:travel:start -->
## Travel Ideas

- [ ] Plan vacation to Japan
- [ ] Book flights

<!-- obs-tools:section:travel:end -->

Some manual content at the end.
"""

        with open(self.test_file, 'w', encoding='utf-8') as f:
            f.write(test_content)

        manager = CatchAllManager(self.test_file)
        structure = manager.parse_file_structure()

        # Verify parsing
        self.assertEqual(len(structure.sections), 2)
        self.assertTrue("synthetic-shopping" in structure.sections)
        self.assertTrue("synthetic-travel" in structure.sections)

        shopping_section = structure.sections["synthetic-shopping"]
        self.assertEqual(shopping_section.list_name, "Shopping")
        self.assertEqual(len(shopping_section.content_lines), 4)  # Heading + blank + 2 tasks

    def test_update_sections(self):
        """Test updating sections with new content."""
        manager = CatchAllManager(self.test_file)

        # Create test mapping and reminders data
        list_mappings = {
            "list-1": {
                "list_name": "Shopping",
                "section_heading": "## Shopping",
                "anchor_start": "<!-- obs-tools:section:shopping:start -->",
                "anchor_end": "<!-- obs-tools:section:shopping:end -->"
            }
        }

        # Create test reminders
        reminder1 = ReminderItem(
            uuid="task-1",
            source_key="rem:task-1",
            list_info=RemindersList(identifier="list-1", name="Shopping"),
            status=ReminderStatus.TODO,
            description="Buy groceries",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            last_seen=datetime.now().isoformat()
        )

        snapshot = RemindersStoreSnapshot(
            reminders={"task-1": reminder1},
            lists={"list-1": RemindersList(identifier="list-1", name="Shopping")},
            collected_at=datetime.now().isoformat()
        )

        # Update sections
        updated = manager.update_sections(list_mappings, snapshot)
        self.assertTrue(updated)

        # Verify file was created and has correct content
        self.assertTrue(os.path.exists(self.test_file))

        with open(self.test_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("## Shopping", content)
        self.assertIn("- [ ] Buy groceries", content)
        self.assertIn("<!-- obs-tools:section:shopping:start -->", content)
        self.assertIn("<!-- obs-tools:section:shopping:end -->", content)


class TestLegacyCleanup(unittest.TestCase):
    """Test legacy cleanup operations."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.app_prefs = AppPreferences(cleanup_legacy_mappings=True)
        self.cleanup_manager = LegacyCleanupManager(self.app_prefs, self.temp_dir)

    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_find_duplicate_tasks(self):
        """Test duplicate task detection."""
        # Create test reminders with duplicates
        reminder1 = ReminderItem(
            uuid="task-1",
            source_key="obs:task-1",
            list_info=RemindersList(identifier="list-1", name="Work"),
            status=ReminderStatus.TODO,
            description="Complete project documentation",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            last_seen=datetime.now().isoformat()
        )

        # Duplicate with same content but different source
        reminder2 = ReminderItem(
            uuid="task-2",
            source_key="rem:task-2",
            list_info=RemindersList(identifier="list-2", name="Tasks"),
            status=ReminderStatus.TODO,
            description="Complete project documentation",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            last_seen=datetime.now().isoformat()
        )

        # Different task
        reminder3 = ReminderItem(
            uuid="task-3",
            source_key="obs:task-3",
            list_info=RemindersList(identifier="list-1", name="Work"),
            status=ReminderStatus.TODO,
            description="Review code changes",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            last_seen=datetime.now().isoformat()
        )

        snapshot = RemindersStoreSnapshot(
            reminders={
                "task-1": reminder1,
                "task-2": reminder2,
                "task-3": reminder3
            },
            lists={},
            collected_at=datetime.now().isoformat()
        )

        # Find duplicates
        duplicates = self.cleanup_manager._find_duplicate_tasks(snapshot)

        # Verify duplicate detection
        self.assertEqual(len(duplicates), 1)

        duplicate_group = duplicates[0]
        self.assertEqual(duplicate_group.canonical_uuid, "task-1")  # Most recent
        self.assertEqual(duplicate_group.duplicate_uuids, ["task-2"])
        self.assertIn("obsidian", duplicate_group.source_systems)
        self.assertIn("reminders", duplicate_group.source_systems)

    def test_analyze_legacy_mappings(self):
        """Test legacy mapping analysis."""
        # Create test data with legacy lists
        lists = {
            "list-1": RemindersList(
                identifier="list-1",
                name="Old Tasks",
                list_location_type=ListLocationType.LEGACY
            ),
            "list-2": RemindersList(
                identifier="list-2",
                name="Work",
                list_location_type=ListLocationType.VAULT_DEDICATED,
                vault_identifier="vault-1"
            )
        }

        snapshot = RemindersStoreSnapshot(
            reminders={},
            lists=lists,
            collected_at=datetime.now().isoformat()
        )

        vault_mappings = {
            "vault-1": VaultMapping(
                vault_id="vault-1",
                vault_name="Work",
                vault_path="/path/to/work",
                list_id="list-2",
                list_name="Work"
            )
        }

        # Analyze legacy mappings
        plan = self.cleanup_manager.analyze_legacy_mappings(snapshot, vault_mappings)

        # Verify analysis
        self.assertEqual(len(plan.legacy_mappings), 1)

        legacy_mapping = plan.legacy_mappings[0]
        self.assertEqual(legacy_mapping.list_name, "Old Tasks")
        self.assertEqual(legacy_mapping.mapping_type, "orphaned")


class TestVaultMetrics(unittest.TestCase):
    """Test vault organization metrics collection."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.metrics_collector = VaultMetricsCollector(self.temp_dir, enabled=True)

    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_track_operation_success(self):
        """Test successful operation tracking."""
        with self.metrics_collector.track_operation(
            OperationType.VAULT_DISCOVERY,
            vault_organization_enabled=True
        ) as op_log:
            op_log.vault_ids = ["vault-1", "vault-2"]
            # Simulate some work
            import time
            time.sleep(0.01)

        # Verify operation was recorded
        self.assertEqual(op_log.status, OperationStatus.SUCCESS)
        self.assertIsNotNone(op_log.completed_at)
        self.assertEqual(len(op_log.vault_ids), 2)

    def test_track_operation_failure(self):
        """Test failed operation tracking."""
        try:
            with self.metrics_collector.track_operation(
                OperationType.LIST_CREATION,
                vault_organization_enabled=True
            ) as op_log:
                op_log.vault_ids = ["vault-1"]
                raise ValueError("Test error")
        except ValueError:
            pass  # Expected

        # Verify failure was recorded
        self.assertEqual(op_log.status, OperationStatus.FAILED)
        self.assertEqual(len(op_log.errors), 1)
        self.assertEqual(op_log.errors[0]["error_type"], "ValueError")

    def test_metrics_persistence(self):
        """Test metrics are persisted to files."""
        # Record some metrics
        self.metrics_collector.record_vault_discovery(3, 150.0)
        self.metrics_collector.record_list_creation("vault-1", "list-1", 50.0, True)

        # Check metrics file exists
        metrics_file = os.path.join(self.temp_dir, "vault_metrics.jsonl")
        self.assertTrue(os.path.exists(metrics_file))

        # Verify content
        with open(metrics_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        self.assertEqual(len(lines), 2)

        # Parse first metric
        metric1 = json.loads(lines[0])
        self.assertEqual(metric1["operation_type"], "vault_discovery")
        self.assertEqual(metric1["vault_count"], 3)
        self.assertEqual(metric1["duration_ms"], 150.0)

    def test_performance_report_generation(self):
        """Test performance report generation."""
        # Record some test metrics
        self.metrics_collector.record_vault_discovery(2, 100.0)
        self.metrics_collector.record_list_creation("vault-1", "list-1", 75.0, True)
        self.metrics_collector.record_list_creation("vault-2", "list-2", 80.0, False)

        # Generate report
        report = self.metrics_collector.generate_performance_report(days=1)

        # Verify report structure
        self.assertIn("total_operations", report)
        self.assertIn("operations_by_type", report)
        self.assertIn("success_rate", report)

        # Verify statistics
        self.assertEqual(report["total_operations"], 3)
        self.assertAlmostEqual(report["success_rate"], 2/3, places=2)


class TestEndToEndWorkflow(unittest.TestCase):
    """Test complete end-to-end vault organization workflows."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.vault_dir1 = os.path.join(self.temp_dir, "vault1")
        self.vault_dir2 = os.path.join(self.temp_dir, "vault2")

        # Create mock vault directories
        os.makedirs(os.path.join(self.vault_dir1, ".obsidian"))
        os.makedirs(os.path.join(self.vault_dir2, ".obsidian"))

        self.app_prefs = AppPreferences(
            vault_organization_enabled=True,
            auto_create_vault_lists=True,
            catch_all_filename="OtherAppleReminders.md"
        )

    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('reminders_gateway.RemindersGateway')
    def test_complete_vault_setup_workflow(self, mock_gateway):
        """Test complete vault setup workflow."""
        # Mock gateway responses
        mock_gateway_instance = Mock()
        mock_gateway.return_value = mock_gateway_instance
        mock_gateway_instance.create_list.side_effect = ["list-1", "list-2"]

        # Create test vaults
        vaults = [
            {
                "name": "Work",
                "path": self.vault_dir1,
                "vault_id": generate_stable_vault_id(self.vault_dir1)
            },
            {
                "name": "Personal",
                "path": self.vault_dir2,
                "vault_id": generate_stable_vault_id(self.vault_dir2)
            }
        ]

        # Create organizer
        organizer = VaultOrganizer(self.app_prefs, {}, {})

        # Generate plans
        list_plans = organizer.generate_vault_list_plan(vaults, RemindersStoreSnapshot(
            reminders={}, lists={}, collected_at=datetime.now().isoformat()
        ))

        # Execute vault-list creation
        results = organizer.execute_vault_list_plan(list_plans, mock_gateway_instance)

        # Verify results
        self.assertEqual(len(results["created_lists"]), 2)
        self.assertEqual(len(results["vault_mappings"]), 2)
        self.assertEqual(len(results["errors"]), 0)

        # Verify gateway calls
        mock_gateway_instance.create_list.assert_any_call("Work")
        mock_gateway_instance.create_list.assert_any_call("Personal")

    def test_catch_all_file_workflow(self):
        """Test catch-all file creation and update workflow."""
        # Set default vault
        self.app_prefs.default_vault_id = generate_stable_vault_id(self.vault_dir1)

        # Create catch-all manager
        catch_all_file = os.path.join(self.vault_dir1, "OtherAppleReminders.md")
        manager = CatchAllManager(catch_all_file)

        # Create test external reminders
        shopping_reminder = ReminderItem(
            uuid="shop-1",
            source_key="rem:shop-1",
            list_info=RemindersList(identifier="shopping-list", name="Shopping"),
            status=ReminderStatus.TODO,
            description="Buy milk",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            last_seen=datetime.now().isoformat()
        )

        travel_reminder = ReminderItem(
            uuid="travel-1",
            source_key="rem:travel-1",
            list_info=RemindersList(identifier="travel-list", name="Travel"),
            status=ReminderStatus.TODO,
            description="Book hotel",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            last_seen=datetime.now().isoformat()
        )

        snapshot = RemindersStoreSnapshot(
            reminders={"shop-1": shopping_reminder, "travel-1": travel_reminder},
            lists={
                "shopping-list": RemindersList(identifier="shopping-list", name="Shopping"),
                "travel-list": RemindersList(identifier="travel-list", name="Travel")
            },
            collected_at=datetime.now().isoformat()
        )

        # Create catch-all mappings
        list_mappings = {
            "shopping-list": {
                "list_name": "Shopping",
                "section_heading": "## Shopping",
                "anchor_start": "<!-- obs-tools:section:shopping:start -->",
                "anchor_end": "<!-- obs-tools:section:shopping:end -->"
            },
            "travel-list": {
                "list_name": "Travel",
                "section_heading": "## Travel",
                "anchor_start": "<!-- obs-tools:section:travel:start -->",
                "anchor_end": "<!-- obs-tools:section:travel:end -->"
            }
        }

        # Update catch-all file
        updated = manager.update_sections(list_mappings, snapshot)
        self.assertTrue(updated)

        # Verify file content
        with open(catch_all_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("## Shopping", content)
        self.assertIn("- [ ] Buy milk", content)
        self.assertIn("## Travel", content)
        self.assertIn("- [ ] Book hotel", content)

        # Test file structure preservation on re-update
        updated_again = manager.update_sections(list_mappings, snapshot)
        self.assertFalse(updated_again)  # No changes, so no update needed


if __name__ == '__main__':
    unittest.main()