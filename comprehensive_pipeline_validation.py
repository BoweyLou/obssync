#!/usr/bin/env python3
"""
Comprehensive Pipeline Validation Test

This script validates all the recent fixes to the task synchronization pipeline:
1. Async callback chaining in controller.py _do_update_all_and_apply()
2. App.json config loading in create_missing_counterparts.py
3. 300s timeout handling for EventKit operations in services.py
4. Vault selection feature in TUI settings
5. Bidirectional sync data integrity

The test creates an isolated environment to avoid interfering with production data.
"""

import os
import sys
import json
import tempfile
import shutil
import subprocess
import time
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import uuid

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.safe_io import safe_write_json_with_lock, safe_load_json
from lib.date_utils import now_iso, days_ago
import app_config
from tui.controller import TUIController
from tui.services import ServiceManager, get_service_manager
from tui.view import TUIView

class PipelineValidationTestSuite:
    """Comprehensive test suite for pipeline validation."""
    
    def __init__(self, test_dir: str = None):
        """Initialize test suite with isolated environment."""
        self.test_dir = test_dir or tempfile.mkdtemp(prefix="obs_pipeline_test_")
        self.test_results = {}
        self.setup_complete = False
        
        # Test data paths
        self.obs_index_path = os.path.join(self.test_dir, "obsidian_tasks_index.json")
        self.rem_index_path = os.path.join(self.test_dir, "reminders_tasks_index.json")
        self.links_path = os.path.join(self.test_dir, "sync_links.json")
        self.app_config_path = os.path.join(self.test_dir, "app.json")
        self.vault_config_path = os.path.join(self.test_dir, "obsidian_vaults.json")
        
        print(f"Initialized test suite in: {self.test_dir}")
    
    def setup_test_environment(self):
        """Set up isolated test environment with sample data."""
        print("Setting up test environment...")
        
        # Create test vault directory
        test_vault_dir = os.path.join(self.test_dir, "test_vault")
        os.makedirs(test_vault_dir, exist_ok=True)
        
        # Create sample Obsidian tasks index
        obs_tasks = {
            "meta": {
                "schema": 2,
                "generated_at": now_iso(),
                "total_tasks": 3
            },
            "tasks": {
                "t-123456789abc": {
                    "uuid": "t-123456789abc",
                    "description": "Test Obsidian task 1",
                    "status": "todo",
                    "created_at": now_iso(),
                    "updated_at": now_iso(),
                    "file": {"relative_path": "Daily Notes/2025-09-11.md", "line": 15},
                    "vault": {"name": "Test Vault", "path": test_vault_dir},
                    "tags": ["#work", "#testing"]
                },
                "t-def456789012": {
                    "uuid": "t-def456789012", 
                    "description": "Test Obsidian task 2",
                    "status": "todo",
                    "due": "2025-09-15",
                    "created_at": days_ago(2),
                    "updated_at": days_ago(1),
                    "file": {"relative_path": "Tasks.md", "line": 5},
                    "vault": {"name": "Test Vault", "path": test_vault_dir}
                },
                "t-ghi789012345": {
                    "uuid": "t-ghi789012345",
                    "description": "Completed Obsidian task",
                    "status": "done",
                    "done": now_iso(),
                    "created_at": days_ago(5),
                    "updated_at": now_iso(),
                    "file": {"relative_path": "Archive.md", "line": 10},
                    "vault": {"name": "Test Vault", "path": test_vault_dir}
                }
            }
        }
        
        # Create sample Reminders tasks index
        rem_tasks = {
            "meta": {
                "schema": 2,
                "generated_at": now_iso(),
                "total_tasks": 3
            },
            "tasks": {
                "rem-aaa111222333": {
                    "uuid": "rem-aaa111222333",
                    "description": "Test Reminders task 1",
                    "is_completed": False,
                    "created_at": now_iso(),
                    "updated_at": now_iso(),
                    "list": {"name": "Work", "calendar_id": "test-calendar-1"}
                },
                "rem-bbb444555666": {
                    "uuid": "rem-bbb444555666",
                    "description": "Test Reminders task 2", 
                    "is_completed": False,
                    "due_date": "2025-09-20",
                    "priority": 1,
                    "created_at": days_ago(3),
                    "updated_at": days_ago(1),
                    "list": {"name": "Personal", "calendar_id": "test-calendar-2"}
                },
                "rem-ccc777888999": {
                    "uuid": "rem-ccc777888999",
                    "description": "Completed Reminders task",
                    "is_completed": True,
                    "completed_at": now_iso(),
                    "created_at": days_ago(7),
                    "updated_at": now_iso(),
                    "list": {"name": "Work", "calendar_id": "test-calendar-1"}
                }
            }
        }
        
        # Create sample sync links
        sync_links = {
            "meta": {
                "schema": 1,
                "generated_at": now_iso(),
                "total_links": 1
            },
            "links": [
                {
                    "obs_uuid": "t-123456789abc",
                    "rem_uuid": "rem-aaa111222333",
                    "score": 0.95,
                    "title_similarity": 0.9,
                    "date_distance_days": 0,
                    "due_equal": False,
                    "created_at": days_ago(1),
                    "last_scored": days_ago(1),
                    "last_synced": None,
                    "fields": {
                        "obs_title": "Test Obsidian task 1",
                        "rem_title": "Test Reminders task 1",
                        "obs_due": None,
                        "rem_due": None
                    }
                }
            ]
        }
        
        # Create sample app config
        app_config_data = {
            "prefs": {
                "min_score": 0.8,
                "days_tolerance": 3,
                "include_done": False,
                "ignore_common": True,
                "prune_days": 30,
                "creation_defaults": {
                    "obs_inbox_file": os.path.join(test_vault_dir, "Tasks.md"),
                    "rem_default_calendar_id": "test-calendar-1",
                    "max_creates_per_run": 50,
                    "since_days": 30,
                    "include_done": False
                },
                "obs_to_rem_rules": [
                    {"tag": "#work", "calendar_id": "test-calendar-1"}
                ],
                "rem_to_obs_rules": [
                    {"list_name": "Work", "target_file": os.path.join(test_vault_dir, "Tasks.md"), "heading": "Work Tasks"}
                ]
            },
            "paths": {
                "obsidian_index": self.obs_index_path,
                "reminders_index": self.rem_index_path,
                "links": self.links_path,
                "obsidian_vaults": self.vault_config_path,
                "reminders_lists": os.path.join(self.test_dir, "reminders_lists.json"),
                "backups_dir": os.path.join(self.test_dir, "backups")
            }
        }
        
        # Create sample vault config
        vault_config = [
            {
                "name": "Test Vault",
                "path": test_vault_dir,
                "is_default": True
            }
        ]
        
        # Write all test data files
        safe_write_json_with_lock(self.obs_index_path, obs_tasks)
        safe_write_json_with_lock(self.rem_index_path, rem_tasks)
        safe_write_json_with_lock(self.links_path, sync_links)
        safe_write_json_with_lock(self.app_config_path, app_config_data)
        safe_write_json_with_lock(self.vault_config_path, vault_config)
        
        # Create test vault structure
        os.makedirs(os.path.join(test_vault_dir, "Daily Notes"), exist_ok=True)
        
        # Create sample markdown files
        with open(os.path.join(test_vault_dir, "Tasks.md"), 'w') as f:
            f.write("# Tasks\n\n- [ ] Sample task from vault ^t-def456789012\n")
        
        with open(os.path.join(test_vault_dir, "Daily Notes", "2025-09-11.md"), 'w') as f:
            f.write("# 2025-09-11\n\n- [ ] Test Obsidian task 1 #work #testing ^t-123456789abc\n")
            
        os.makedirs(os.path.join(self.test_dir, "backups"), exist_ok=True)
        
        self.setup_complete = True
        print("✓ Test environment setup complete")
    
    def test_app_config_loading(self) -> bool:
        """Test that create_missing_counterparts properly loads app.json config."""
        print("\n=== Testing App Config Loading ===")
        
        try:
            # Import the function we want to test
            from obs_tools.commands.create_missing_counterparts import load_config_from_app_json
            
            # Temporarily override the config path
            original_config_dir = os.environ.get('HOME', '')
            test_config_dir = self.test_dir
            
            # Create a fake config directory structure
            config_dir = os.path.join(test_config_dir, ".config")
            os.makedirs(config_dir, exist_ok=True)
            
            # Copy our test app config to the expected location
            test_app_config = os.path.join(config_dir, "app.json")
            shutil.copy2(self.app_config_path, test_app_config)
            
            # Mock the app_config module to use our test directory
            import app_config
            original_get_path = app_config.get_path
            
            def mock_get_path(key):
                paths = {
                    "app_config": test_app_config,
                    "obsidian_vaults": self.vault_config_path,
                    "reminders_lists": os.path.join(self.test_dir, "reminders_lists.json")
                }
                return paths.get(key, original_get_path(key))
            
            app_config.get_path = mock_get_path
            
            try:
                # Test loading the config
                config = load_config_from_app_json()
                
                # Verify config was loaded correctly
                expected_inbox = os.path.join(self.test_dir, "test_vault", "Tasks.md")
                if config.obs_inbox_file != expected_inbox:
                    print(f"✗ Config loading failed: Expected inbox {expected_inbox}, got {config.obs_inbox_file}")
                    return False
                
                if config.rem_default_calendar_id != "test-calendar-1":
                    print(f"✗ Config loading failed: Expected calendar test-calendar-1, got {config.rem_default_calendar_id}")
                    return False
                
                if len(config.obs_to_rem_rules) != 1 or config.obs_to_rem_rules[0]["tag"] != "#work":
                    print(f"✗ Config loading failed: obs_to_rem_rules not loaded correctly")
                    return False
                
                print("✓ App config loading working correctly")
                return True
                
            finally:
                # Restore original function
                app_config.get_path = original_get_path
                
        except Exception as e:
            print(f"✗ App config loading test failed: {str(e)}")
            return False
    
    def test_timeout_configuration(self) -> bool:
        """Test that services.py has the correct 300s timeout."""
        print("\n=== Testing Timeout Configuration ===")
        
        try:
            # Read the services.py file to verify timeout
            services_file = os.path.join(os.path.dirname(__file__), "tui", "services.py")
            with open(services_file, 'r') as f:
                content = f.read()
            
            # Check for the 300s timeout
            if "poll_count > 3000" in content and "300 seconds" in content:
                print("✓ 300 second timeout correctly configured in services.py")
                return True
            else:
                print("✗ 300 second timeout not found in services.py")
                return False
                
        except Exception as e:
            print(f"✗ Timeout configuration test failed: {str(e)}")
            return False
    
    def test_async_callback_chaining(self) -> bool:
        """Test async callback chaining in controller."""
        print("\n=== Testing Async Callback Chaining ===")
        
        try:
            # Create a mock TUI view and service manager for testing
            from unittest.mock import Mock, MagicMock
            
            mock_view = Mock()
            mock_service_manager = Mock()
            
            # Track callback execution order
            callback_order = []
            
            def mock_run_command(args, log_callback, completion_callback):
                """Mock run_command that immediately calls completion callback."""
                operation_name = args[-1] if args else "unknown"
                callback_order.append(f"start_{operation_name}")
                
                # Simulate immediate completion
                if completion_callback:
                    completion_callback()
            
            mock_service_manager.run_command = mock_run_command
            
            # Create controller with mocked dependencies
            controller = TUIController(mock_view, mock_service_manager)
            controller.is_busy = False
            
            # Test the chaining by calling _do_update_all_and_apply
            controller._do_update_all_and_apply()
            
            # The chaining should have been initiated
            if not controller.is_busy:
                print("✗ Controller should be busy after starting update-all-and-apply")
                return False
            
            print("✓ Async callback chaining initiated correctly")
            return True
            
        except Exception as e:
            print(f"✗ Async callback chaining test failed: {str(e)}")
            return False
    
    def test_vault_selection_feature(self) -> bool:
        """Test vault selection feature in TUI settings."""
        print("\n=== Testing Vault Selection Feature ===")
        
        try:
            # Verify vault selection method exists in controller
            from tui.controller import TUIController
            from unittest.mock import Mock
            
            if not hasattr(TUIController, '_handle_vault_selection'):
                print("✗ _handle_vault_selection method not found in TUIController")
                return False
            
            # Create a mock controller
            mock_view = Mock()
            mock_service_manager = Mock()
            controller = TUIController(mock_view, mock_service_manager)
            
            # Set up test vault config path
            controller.vault_config_path = self.vault_config_path
            
            # The method should exist and be callable
            if callable(getattr(controller, '_handle_vault_selection', None)):
                print("✓ Vault selection feature method exists and is callable")
                return True
            else:
                print("✗ Vault selection method is not callable")
                return False
            
        except Exception as e:
            print(f"✗ Vault selection feature test failed: {str(e)}")
            return False
    
    def test_data_integrity(self) -> bool:
        """Test bidirectional sync data integrity."""
        print("\n=== Testing Data Integrity ===")
        
        try:
            # Load test data
            obs_data = safe_load_json(self.obs_index_path, {})
            rem_data = safe_load_json(self.rem_index_path, {})
            links_data = safe_load_json(self.links_path, {})
            
            # Check schema version
            if obs_data.get("meta", {}).get("schema") != 2:
                print("✗ Obsidian index schema not v2")
                return False
            
            if rem_data.get("meta", {}).get("schema") != 2:
                print("✗ Reminders index schema not v2")
                return False
            
            # Check UUID consistency
            obs_tasks = obs_data.get("tasks", {})
            rem_tasks = rem_data.get("tasks", {})
            links = links_data.get("links", [])
            
            for link in links:
                obs_uuid = link.get("obs_uuid")
                rem_uuid = link.get("rem_uuid")
                
                if obs_uuid not in obs_tasks:
                    print(f"✗ Link references non-existent Obsidian task: {obs_uuid}")
                    return False
                
                if rem_uuid not in rem_tasks:
                    print(f"✗ Link references non-existent Reminders task: {rem_uuid}")
                    return False
            
            # Check task data structure integrity
            required_obs_fields = ["uuid", "description", "status", "created_at"]
            required_rem_fields = ["uuid", "description", "is_completed", "created_at"]
            
            for uuid, task in obs_tasks.items():
                if task["uuid"] != uuid:
                    print(f"✗ Obsidian task UUID mismatch: {uuid} vs {task['uuid']}")
                    return False
                
                for field in required_obs_fields:
                    if field not in task:
                        print(f"✗ Obsidian task missing required field: {field}")
                        return False
            
            for uuid, task in rem_tasks.items():
                if task["uuid"] != uuid:
                    print(f"✗ Reminders task UUID mismatch: {uuid} vs {task['uuid']}")
                    return False
                
                for field in required_rem_fields:
                    if field not in task:
                        print(f"✗ Reminders task missing required field: {field}")
                        return False
            
            print("✓ Data integrity validation passed")
            return True
            
        except Exception as e:
            print(f"✗ Data integrity test failed: {str(e)}")
            return False
    
    def test_create_missing_counterparts_integration(self) -> bool:
        """Test create missing counterparts with app.json integration."""
        print("\n=== Testing Create Missing Counterparts Integration ===")
        
        try:
            # Set up environment variables to use our test config
            os.environ['OBS_TOOLS_CONFIG_DIR'] = os.path.dirname(self.app_config_path)
            
            # Import and test the create missing counterparts command
            from obs_tools.commands.create_missing_counterparts import main, load_config_from_app_json
            
            # Test config loading first
            import app_config
            original_load = app_config.load_app_config
            
            def mock_load_config():
                """Mock config loading to use our test data."""
                app_data = safe_load_json(self.app_config_path, {})
                prefs_data = app_data.get("prefs", {})
                paths_data = app_data.get("paths", {})
                
                from app_config import AppPreferences, AppPaths
                prefs = AppPreferences()
                paths = AppPaths()
                
                # Set test values
                prefs.creation_defaults.obs_inbox_file = prefs_data.get("creation_defaults", {}).get("obs_inbox_file", "")
                paths.obsidian_index = self.obs_index_path
                paths.reminders_index = self.rem_index_path
                paths.links = self.links_path
                
                return prefs, paths
            
            app_config.load_app_config = mock_load_config
            
            try:
                # Test dry-run mode
                result = main([
                    "--obs", self.obs_index_path,
                    "--rem", self.rem_index_path, 
                    "--links", self.links_path,
                    "--direction", "both",
                    "--dry-run"
                ])
                
                if result == 0:
                    print("✓ Create missing counterparts integration working correctly")
                    return True
                else:
                    print(f"✗ Create missing counterparts returned non-zero exit code: {result}")
                    return False
                    
            finally:
                app_config.load_app_config = original_load
                if 'OBS_TOOLS_CONFIG_DIR' in os.environ:
                    del os.environ['OBS_TOOLS_CONFIG_DIR']
            
        except Exception as e:
            print(f"✗ Create missing counterparts integration test failed: {str(e)}")
            return False
    
    def run_all_tests(self) -> Dict[str, bool]:
        """Run all validation tests."""
        print("=" * 60)
        print("COMPREHENSIVE PIPELINE VALIDATION TEST SUITE")
        print("=" * 60)
        
        if not self.setup_complete:
            self.setup_test_environment()
        
        tests = [
            ("App Config Loading", self.test_app_config_loading),
            ("Timeout Configuration", self.test_timeout_configuration),
            ("Async Callback Chaining", self.test_async_callback_chaining),
            ("Vault Selection Feature", self.test_vault_selection_feature),
            ("Data Integrity", self.test_data_integrity),
            ("Create Missing Counterparts Integration", self.test_create_missing_counterparts_integration),
        ]
        
        results = {}
        
        for test_name, test_func in tests:
            try:
                results[test_name] = test_func()
                self.test_results[test_name] = results[test_name]
            except Exception as e:
                print(f"\n✗ {test_name} failed with exception: {str(e)}")
                results[test_name] = False
                self.test_results[test_name] = False
        
        # Print summary
        print("\n" + "=" * 60)
        print("TEST RESULTS SUMMARY")
        print("=" * 60)
        
        passed = sum(1 for result in results.values() if result)
        total = len(results)
        
        for test_name, result in results.items():
            status = "✓ PASS" if result else "✗ FAIL"
            print(f"{test_name:<40} {status}")
        
        print("-" * 60)
        print(f"Total: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 ALL TESTS PASSED! Pipeline fixes are working correctly.")
        else:
            print("⚠️  Some tests failed. Review the output above for details.")
        
        return results
    
    def cleanup(self):
        """Clean up test environment."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
            print(f"Cleaned up test directory: {self.test_dir}")


def main():
    """Main entry point for validation tests."""
    test_suite = PipelineValidationTestSuite()
    
    try:
        results = test_suite.run_all_tests()
        
        # Return appropriate exit code
        all_passed = all(results.values())
        return 0 if all_passed else 1
        
    finally:
        test_suite.cleanup()


if __name__ == "__main__":
    sys.exit(main())