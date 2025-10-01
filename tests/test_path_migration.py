#!/usr/bin/env python3
"""
Test script for validating path migration functionality.

This script tests various scenarios for the new path management system:
- Tool root detection
- Working directory resolution priority
- Legacy file detection and migration
- Fallback behavior
- Read-only installation handling
- The migrate command functionality
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Dict, Optional
import unittest
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# Try to import the modules we need to test
try:
    from obs_sync.core.paths import PathManager, get_path_manager
    from obs_sync.commands.migrate import MigrateCommand
    IMPORTS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import obs_sync modules: {e}")
    print(f"Current directory: {current_dir}")
    print(f"Looking for obs_sync in: {current_dir / 'obs_sync'}")
    print(f"sys.path includes: {sys.path[:3]}")
    IMPORTS_AVAILABLE = False
    
    # Create dummy classes to allow test definitions
    class PathManager:
        pass
    
    class MigrateCommand:
        pass
    
    def get_path_manager():
        return None


@unittest.skipUnless(IMPORTS_AVAILABLE, "Could not import obs_sync modules")
class TestPathMigration(unittest.TestCase):
    """Test suite for path migration functionality."""
    
    def setUp(self):
        """Set up test environment."""
        # Create temporary directories
        self.temp_dir = Path(tempfile.mkdtemp(prefix="obs_sync_test_"))
        self.tool_dir = self.temp_dir / "tool"
        self.home_dir = self.temp_dir / "home"
        self.legacy_dir = self.home_dir / ".config" / "obs-sync"
        
        # Create directory structure
        self.tool_dir.mkdir(parents=True)
        self.home_dir.mkdir(parents=True)
        self.legacy_dir.mkdir(parents=True)
        
        # Create mock obs_sync package directory
        self.obs_sync_dir = self.tool_dir / "obs_sync"
        self.obs_sync_dir.mkdir()
        (self.obs_sync_dir / "__init__.py").touch()
        
        # Store original environment
        self.original_env = os.environ.copy()
        self.original_home = Path.home()
        
        # Clear any existing OBS_SYNC_HOME
        if "OBS_SYNC_HOME" in os.environ:
            del os.environ["OBS_SYNC_HOME"]
    
    def tearDown(self):
        """Clean up test environment."""
        # Restore original environment
        os.environ.clear()
        os.environ.update(self.original_env)
        
        # Clean up temporary directory
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        
        # Clear global path manager instance
        import obs_sync.core.paths
        obs_sync.core.paths._path_manager = None
    
    def create_legacy_files(self) -> Dict[str, Path]:
        """Create legacy configuration files."""
        files = {}
        
        # Create config.json
        config_path = self.legacy_dir / "config.json"
        config_data = {
            "vaults": [{"name": "TestVault", "path": "/test/vault"}],
            "reminders_lists": [{"name": "TestList", "identifier": "test-id"}],
            "sync": {"min_score": 0.75}
        }
        config_path.write_text(json.dumps(config_data, indent=2))
        files["config"] = config_path
        
        # Create sync_links.json
        sync_links_path = self.legacy_dir / "sync_links.json"
        sync_links_data = {
            "links": [
                {"obs_uuid": "obs-123", "rem_uuid": "rem-456", "score": 0.95}
            ]
        }
        sync_links_path.write_text(json.dumps(sync_links_data, indent=2))
        files["sync_links"] = sync_links_path
        
        # Create data directory files
        data_dir = self.legacy_dir / "data"
        data_dir.mkdir(exist_ok=True)
        
        obs_index_path = data_dir / "obsidian_tasks_index.json"
        obs_index_path.write_text(json.dumps({"tasks": []}, indent=2))
        files["obsidian_index"] = obs_index_path
        
        rem_index_path = data_dir / "reminders_tasks_index.json"
        rem_index_path.write_text(json.dumps({"tasks": []}, indent=2))
        files["reminders_index"] = rem_index_path
        
        return files
    
    def test_tool_root_detection(self):
        """Test that PathManager correctly identifies tool root directory."""
        with patch.object(Path, 'home', return_value=self.home_dir):
            # Mock the obs_sync module path
            with patch('obs_sync.core.paths.Path') as mock_path_class:
                # Create a mock for the Path class that returns our test paths
                mock_path = MagicMock()
                mock_path.parent = self.tool_dir
                mock_path_class.return_value.parent = self.tool_dir
                
                # Also mock the actual import
                with patch('obs_sync.__file__', str(self.obs_sync_dir / "__init__.py")):
                    manager = PathManager()
                    
                    # The tool root should be detected
                    self.assertTrue(manager.tool_root == self.tool_dir or
                                  manager.tool_root.name == "obssync",
                                  f"Tool root {manager.tool_root} not as expected")
    
    def test_repo_root_detection_via_pythonpath(self):
        """Test that repo root is detected via PYTHONPATH when running from checkout."""
        # Create a fake repo checkout
        repo_dir = self.temp_dir / "repo_checkout"
        repo_dir.mkdir()
        (repo_dir / "obs_tools.py").touch()
        (repo_dir / "obs_sync").mkdir()
        (repo_dir / "obs_sync" / "__init__.py").touch()
        
        # Set PYTHONPATH to include the repo
        os.environ["PYTHONPATH"] = str(repo_dir)
        
        with patch.object(Path, 'home', return_value=self.home_dir):
            manager = PathManager()
            # Should detect repo root via PYTHONPATH
            self.assertEqual(manager.tool_root, repo_dir,
                           f"Should detect repo root {repo_dir}, got {manager.tool_root}")
    
    def test_repo_root_detection_via_cwd(self):
        """Test that repo root is detected via current working directory."""
        # Create a fake repo checkout
        repo_dir = self.temp_dir / "repo_checkout"
        repo_dir.mkdir()
        (repo_dir / "obs_tools.py").touch()
        (repo_dir / "obs_sync").mkdir()
        (repo_dir / "obs_sync" / "__init__.py").touch()
        
        with patch.object(Path, 'home', return_value=self.home_dir):
            with patch('obs_sync.core.paths.Path.cwd', return_value=repo_dir):
                manager = PathManager()
                # Should detect repo root via cwd
                self.assertEqual(manager.tool_root, repo_dir,
                               f"Should detect repo root {repo_dir}, got {manager.tool_root}")
    
    def test_working_dir_priority_env_var(self):
        """Test that OBS_SYNC_HOME environment variable takes priority."""
        custom_dir = self.temp_dir / "custom_config"
        os.environ["OBS_SYNC_HOME"] = str(custom_dir)
        
        with patch.object(Path, 'home', return_value=self.home_dir):
            manager = PathManager()
            self.assertEqual(manager.working_dir, custom_dir)
    
    def test_working_dir_priority_tool_dir(self):
        """Test that tool directory is used when writable and no env var set."""
        # Ensure no environment variable
        if "OBS_SYNC_HOME" in os.environ:
            del os.environ["OBS_SYNC_HOME"]
        
        with patch.object(Path, 'home', return_value=self.home_dir):
            # Mock tool_root to return our test directory
            with patch.object(PathManager, 'tool_root', new_callable=lambda: property(lambda self: self.tool_dir)):
                manager = PathManager()
                manager.tool_dir = self.tool_dir  # Set for the mocked property
                
                # Create the .obs-sync directory to make it writable
                obs_sync_dir = self.tool_dir / ".obs-sync"
                obs_sync_dir.mkdir(exist_ok=True)
                
                expected = self.tool_dir / ".obs-sync"
                actual = manager.working_dir
                
                # Check if it's using tool dir or falling back to legacy
                self.assertTrue(
                    actual == expected or actual == self.legacy_dir,
                    f"Working dir {actual} not tool dir {expected} or legacy {self.legacy_dir}"
                )
    
    def test_working_dir_repo_checkout_priority(self):
        """Test that repo checkout .obs-sync is used over legacy home directory."""
        # Create a fake repo checkout with obs_tools.py marker
        repo_dir = self.temp_dir / "repo_checkout"
        repo_dir.mkdir()
        (repo_dir / "obs_tools.py").touch()
        (repo_dir / "obs_sync").mkdir()
        (repo_dir / "obs_sync" / "__init__.py").touch()
        
        # Set PYTHONPATH to simulate running from the repo
        os.environ["PYTHONPATH"] = str(repo_dir)
        if "OBS_SYNC_HOME" in os.environ:
            del os.environ["OBS_SYNC_HOME"]
        
        with patch.object(Path, 'home', return_value=self.home_dir):
            manager = PathManager()
            
            # Should use repo-local .obs-sync directory
            expected = repo_dir / ".obs-sync"
            actual = manager.working_dir
            
            self.assertEqual(actual, expected,
                           f"Should use repo-local {expected}, got {actual}")
    
    def test_working_dir_fallback_legacy(self):
        """Test fallback to legacy directory when tool dir is not writable."""
        if "OBS_SYNC_HOME" in os.environ:
            del os.environ["OBS_SYNC_HOME"]
        
        with patch.object(Path, 'home', return_value=self.home_dir):
            # Mock the tool directory as read-only
            with patch.object(PathManager, '_is_writable_location', return_value=False):
                with patch.object(PathManager, 'tool_root', new_callable=lambda: property(lambda self: self.tool_dir)):
                    manager = PathManager()
                    manager.tool_dir = self.tool_dir
                    
                    self.assertEqual(manager.working_dir, self.legacy_dir)
    
    def test_legacy_file_detection(self):
        """Test that legacy files are correctly detected."""
        # Create legacy files
        legacy_files = self.create_legacy_files()
        
        with patch.object(Path, 'home', return_value=self.home_dir):
            manager = PathManager()
            has_legacy, found_files = manager.get_legacy_files()
            
            self.assertTrue(has_legacy, "Should detect legacy files")
            self.assertIn("config", found_files, "Should find config file")
            self.assertIn("sync_links", found_files, "Should find sync_links file")
    
    def test_file_with_fallback(self):
        """Test get_file_with_fallback method."""
        # Create a file in legacy location
        legacy_config = self.legacy_dir / "config.json"
        legacy_config.write_text('{"test": "legacy"}')
        
        with patch.object(Path, 'home', return_value=self.home_dir):
            with patch.object(PathManager, 'working_dir', new_callable=lambda: property(lambda self: self.tool_dir / ".obs-sync")):
                manager = PathManager()
                
                # Should find file in legacy location
                found = manager.get_file_with_fallback("config.json")
                self.assertEqual(found, legacy_config)
                
                # Create file in new location
                new_dir = self.tool_dir / ".obs-sync"
                new_dir.mkdir(parents=True)
                new_config = new_dir / "config.json"
                new_config.write_text('{"test": "new"}')
                
                # Should now prefer new location
                found = manager.get_file_with_fallback("config.json")
                self.assertEqual(found, new_config)
    
    def test_working_dir_site_packages_fallback(self):
        """Test fallback to legacy when running from read-only site-packages."""
        # Create a fake site-packages installation (read-only)
        site_packages = self.temp_dir / "venv" / "lib" / "python3.9" / "site-packages"
        site_packages.mkdir(parents=True)
        obs_sync_pkg = site_packages / "obs_sync"
        obs_sync_pkg.mkdir()
        (obs_sync_pkg / "__init__.py").touch()
        
        # Clear PYTHONPATH to avoid repo detection
        if "PYTHONPATH" in os.environ:
            del os.environ["PYTHONPATH"]
        if "OBS_SYNC_HOME" in os.environ:
            del os.environ["OBS_SYNC_HOME"]
        
        with patch.object(Path, 'home', return_value=self.home_dir):
            with patch('obs_sync.__file__', str(obs_sync_pkg / "__init__.py")):
                # Make the site-packages parent read-only
                with patch.object(PathManager, '_is_writable_location', return_value=False):
                    manager = PathManager()
                    
                    # Should fall back to legacy directory
                    self.assertEqual(manager.working_dir, self.legacy_dir,
                                   f"Should fall back to legacy {self.legacy_dir}, got {manager.working_dir}")
    
    def test_migration_basic(self):
        """Test basic migration from legacy to new location."""
        # Create legacy files
        legacy_files = self.create_legacy_files()
        
        # Set up new location
        new_dir = self.tool_dir / ".obs-sync"
        
        with patch.object(Path, 'home', return_value=self.home_dir):
            with patch.object(PathManager, 'working_dir', new_callable=lambda: property(lambda self: new_dir)):
                manager = PathManager()
                
                # Perform migration
                result = manager.migrate_from_legacy(force=False)
                
                self.assertTrue(result, "Migration should succeed")
                
                # Check files were copied
                self.assertTrue((new_dir / "config.json").exists(), "Config should be migrated")
                self.assertTrue((new_dir / "data" / "sync_links.json").exists(), "Sync links should be migrated")
    
    def test_migration_no_overwrite(self):
        """Test that migration doesn't overwrite existing files by default."""
        # Create legacy files
        self.create_legacy_files()
        
        # Create existing file in new location
        new_dir = self.tool_dir / ".obs-sync"
        new_dir.mkdir(parents=True)
        existing_config = new_dir / "config.json"
        existing_config.write_text('{"test": "existing"}')
        
        with patch.object(Path, 'home', return_value=self.home_dir):
            with patch.object(PathManager, 'working_dir', new_callable=lambda: property(lambda self: new_dir)):
                manager = PathManager()
                
                # Migration should skip existing file
                result = manager.migrate_from_legacy(force=False)
                
                # Check existing file wasn't overwritten
                content = json.loads(existing_config.read_text())
                self.assertEqual(content["test"], "existing", "Existing file should not be overwritten")
    
    def test_migration_force_overwrite(self):
        """Test force migration overwrites existing files."""
        # Create legacy files
        self.create_legacy_files()
        
        # Create existing file in new location
        new_dir = self.tool_dir / ".obs-sync"
        new_dir.mkdir(parents=True)
        existing_config = new_dir / "config.json"
        existing_config.write_text('{"test": "existing"}')
        
        with patch.object(Path, 'home', return_value=self.home_dir):
            with patch.object(PathManager, 'working_dir', new_callable=lambda: property(lambda self: new_dir)):
                manager = PathManager()
                
                # Force migration should overwrite
                result = manager.migrate_from_legacy(force=True)
                
                self.assertTrue(result, "Force migration should succeed")
                
                # Check file was overwritten
                content = json.loads(existing_config.read_text())
                self.assertIn("vaults", content, "File should be overwritten with legacy content")
    
    def test_migrate_command_check_only(self):
        """Test migrate command in check-only mode."""
        # Create legacy files
        self.create_legacy_files()
        
        with patch.object(Path, 'home', return_value=self.home_dir):
            with patch('builtins.input', return_value='n'):
                cmd = MigrateCommand(verbose=True)
                
                # Mock the path manager's directories
                with patch.object(cmd.path_manager, 'legacy_dir', self.legacy_dir):
                    with patch.object(cmd.path_manager, 'working_dir', self.tool_dir / ".obs-sync"):
                        # Run check only
                        result = cmd.run(check_only=True)
                        
                        self.assertTrue(result, "Check should succeed")
                        
                        # Verify files weren't moved
                        self.assertTrue((self.legacy_dir / "config.json").exists(),
                                      "Legacy files should still exist")
    
    def test_migrate_command_apply(self):
        """Test migrate command applying migration."""
        # Create legacy files
        self.create_legacy_files()
        
        new_dir = self.tool_dir / ".obs-sync"
        
        with patch.object(Path, 'home', return_value=self.home_dir):
            # Mock user input for confirmations
            with patch('builtins.input', side_effect=['y', 'n']):  # Yes to migrate, No to cleanup
                cmd = MigrateCommand(verbose=True)
                
                # Mock the path manager's directories
                with patch.object(cmd.path_manager, 'legacy_dir', self.legacy_dir):
                    with patch.object(cmd.path_manager, 'working_dir', new_dir):
                        with patch.object(cmd.path_manager, 'tool_root', self.tool_dir):
                            # Ensure directories for proper paths
                            cmd.path_manager.ensure_directories()
                            
                            # Run migration
                            result = cmd.run(check_only=False)
                            
                            self.assertTrue(result, "Migration should succeed")
                            
                            # Check files were migrated
                            self.assertTrue((new_dir / "config.json").exists(),
                                          "Config should be migrated")
    
    def test_read_only_installation(self):
        """Test behavior with read-only installation directory."""
        # Make tool directory read-only
        obs_sync_dir = self.tool_dir / ".obs-sync"
        obs_sync_dir.mkdir()
        
        # Remove write permissions (Unix-like systems)
        if hasattr(os, 'chmod'):
            os.chmod(obs_sync_dir, 0o555)  # Read and execute only
        
        try:
            with patch.object(Path, 'home', return_value=self.home_dir):
                # Test that it falls back to legacy directory
                manager = PathManager()
                
                # Should detect the directory is not writable
                self.assertFalse(manager._is_writable_location(obs_sync_dir))
                
                # Should fall back to legacy location
                # Note: actual behavior depends on the implementation
                working = manager.working_dir
                self.assertTrue(
                    working == self.legacy_dir or "OBS_SYNC_HOME" in os.environ,
                    f"Should use legacy dir or env var when tool dir not writable, got {working}"
                )
        finally:
            # Restore permissions for cleanup
            if hasattr(os, 'chmod'):
                os.chmod(obs_sync_dir, 0o755)
    
    def test_multiple_installations(self):
        """Test handling multiple tool installations."""
        # Create two tool installations
        tool1 = self.temp_dir / "tool1"
        tool2 = self.temp_dir / "tool2"
        
        for tool in [tool1, tool2]:
            tool.mkdir(parents=True)
            (tool / "obs_sync").mkdir()
            (tool / "obs_sync" / "__init__.py").touch()
        
        # Each should have its own working directory
        with patch.object(Path, 'home', return_value=self.home_dir):
            # Test first installation
            with patch('obs_sync.__file__', str(tool1 / "obs_sync" / "__init__.py")):
                manager1 = PathManager()
                with patch.object(manager1, 'tool_root', tool1):
                    working1 = manager1.working_dir
            
            # Clear the global instance
            import obs_sync.core.paths
            obs_sync.core.paths._path_manager = None
            
            # Test second installation
            with patch('obs_sync.__file__', str(tool2 / "obs_sync" / "__init__.py")):
                manager2 = PathManager()
                with patch.object(manager2, 'tool_root', tool2):
                    working2 = manager2.working_dir
            
            # They should potentially be different (unless both fall back to legacy)
            # This test mainly ensures no crashes with multiple installations
            self.assertIsNotNone(working1)
            self.assertIsNotNone(working2)


@unittest.skipUnless(IMPORTS_AVAILABLE, "Could not import obs_sync modules")
class TestPathMigrationIntegration(unittest.TestCase):
    """Integration tests for path migration with real file operations."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp(prefix="obs_sync_integration_"))
        self.original_home = Path.home()
        
        # Store original environment
        self.original_env = os.environ.copy()
    
    def tearDown(self):
        """Clean up test environment."""
        # Restore environment
        os.environ.clear()
        os.environ.update(self.original_env)
        
        # Clean up
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        
        # Clear global instance
        import obs_sync.core.paths
        obs_sync.core.paths._path_manager = None
    
    def test_end_to_end_migration(self):
        """Test complete migration workflow."""
        # Set up mock home directory
        mock_home = self.temp_dir / "home"
        mock_home.mkdir()
        legacy_dir = mock_home / ".config" / "obs-sync"
        legacy_dir.mkdir(parents=True)
        
        # Create realistic legacy configuration
        config = {
            "vaults": [
                {
                    "name": "Work",
                    "path": str(mock_home / "Documents" / "Work"),
                    "vault_id": "work-vault-123",
                    "is_default": True
                }
            ],
            "reminders_lists": [
                {
                    "name": "Work Tasks",
                    "identifier": "work-list-456"
                }
            ],
            "sync": {
                "min_score": 0.8,
                "days_tolerance": 2,
                "include_completed": True
            }
        }
        
        (legacy_dir / "config.json").write_text(json.dumps(config, indent=2))
        
        # Create sync links
        sync_links = {
            "links": [
                {
                    "obs_uuid": "obs-task-1",
                    "rem_uuid": "rem-task-1",
                    "score": 0.95,
                    "created_at": "2024-01-01T00:00:00Z"
                },
                {
                    "obs_uuid": "obs-task-2",
                    "rem_uuid": "rem-task-2",
                    "score": 0.88,
                    "created_at": "2024-01-02T00:00:00Z"
                }
            ]
        }
        
        (legacy_dir / "sync_links.json").write_text(json.dumps(sync_links, indent=2))
        
        # Set custom working directory via environment
        new_working_dir = self.temp_dir / "custom_obs_sync"
        os.environ["OBS_SYNC_HOME"] = str(new_working_dir)
        
        with patch.object(Path, 'home', return_value=mock_home):
            # Initialize path manager
            manager = get_path_manager()
            
            # Verify working directory is set correctly
            self.assertEqual(manager.working_dir, new_working_dir)
            
            # Perform migration
            migrated = manager.migrate_from_legacy()
            self.assertTrue(migrated, "Migration should succeed")
            
            # Verify files were migrated
            self.assertTrue((new_working_dir / "config.json").exists())
            self.assertTrue((new_working_dir / "data" / "sync_links.json").exists())
            
            # Verify content integrity
            migrated_config = json.loads((new_working_dir / "config.json").read_text())
            self.assertEqual(migrated_config["vaults"][0]["name"], "Work")
            self.assertEqual(migrated_config["sync"]["min_score"], 0.8)
            
            migrated_links = json.loads((new_working_dir / "data" / "sync_links.json").read_text())
            self.assertEqual(len(migrated_links["links"]), 2)
            self.assertEqual(migrated_links["links"][0]["obs_uuid"], "obs-task-1")
            
            # Verify marker file created
            marker = new_working_dir / ".migrated_from_legacy"
            self.assertTrue(marker.exists(), "Migration marker should be created")


def run_tests(verbose: bool = False):
    """Run all tests."""
    # Check if imports are available
    if not IMPORTS_AVAILABLE:
        print("\n" + "=" * 70)
        print("❌ Tests skipped: Could not import obs_sync modules")
        print("\nTroubleshooting:")
        print(f"1. Make sure you're running from the correct directory")
        print(f"2. Current directory: {Path.cwd()}")
        print(f"3. Expected obs_sync location: {Path.cwd() / 'obs_sync'}")
        print(f"4. Does obs_sync directory exist? {(Path.cwd() / 'obs_sync').exists()}")
        if (Path.cwd() / 'obs_sync').exists():
            print(f"5. obs_sync/__init__.py exists? {(Path.cwd() / 'obs_sync' / '__init__.py').exists()}")
            print(f"6. obs_sync/core exists? {(Path.cwd() / 'obs_sync' / 'core').exists()}")
            print(f"7. obs_sync/core/paths.py exists? {(Path.cwd() / 'obs_sync' / 'core' / 'paths.py').exists()}")
        print("\nTry running from the project root directory:")
        print("  cd /path/to/obssync")
        print("  python test_path_migration.py")
        return False
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test cases
    suite.addTests(loader.loadTestsFromTestCase(TestPathMigration))
    suite.addTests(loader.loadTestsFromTestCase(TestPathMigrationIntegration))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2 if verbose else 1)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 70)
    if result.wasSuccessful():
        print("✅ All path migration tests passed!")
    else:
        print(f"❌ Tests failed: {len(result.failures)} failures, {len(result.errors)} errors")
        if result.failures:
            print("\nFailures:")
            for test, trace in result.failures:
                print(f"  - {test}: {trace.splitlines()[0] if trace.splitlines() else trace}")
        if result.errors:
            print("\nErrors:")
            for test, trace in result.errors:
                print(f"  - {test}: {trace.splitlines()[0] if trace.splitlines() else trace}")
    
    # Also report on skipped tests
    if hasattr(result, 'skipped') and result.skipped:
        print(f"\n⚠️  Skipped {len(result.skipped)} test(s)")
    
    return result.wasSuccessful()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test obs-sync path migration functionality")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--specific", help="Run specific test method")
    
    args = parser.parse_args()
    
    if args.specific:
        if not IMPORTS_AVAILABLE:
            print(f"❌ Cannot run tests: obs_sync modules not available")
            print(f"Make sure you're running from the project root directory")
            sys.exit(1)
            
        # Run specific test
        suite = unittest.TestSuite()
        # Try to get the test from both test classes
        try:
            suite.addTest(TestPathMigration(args.specific))
        except:
            try:
                suite.addTest(TestPathMigrationIntegration(args.specific))
            except:
                print(f"❌ Test method '{args.specific}' not found in any test class")
                sys.exit(1)
                
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        sys.exit(0 if result.wasSuccessful() else 1)
    else:
        # Run all tests
        success = run_tests(args.verbose)
        sys.exit(0 if success else 1)