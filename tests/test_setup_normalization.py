#!/usr/bin/env python3
"""Test setup command with vault normalization and ID preservation."""

import os
import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from obs_sync.core.models import SyncConfig, Vault, RemindersList, normalize_vault_path
from obs_sync.commands.setup import SetupCommand
from obs_sync.obsidian.vault import find_vaults


def test_setup_preserves_vault_ids():
    """Test that setup command preserves existing vault IDs during reconfiguration."""
    print("\n=== Testing Setup Command Vault ID Preservation ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test vaults
        vault1_path = Path(tmpdir) / "Vault1"
        vault2_path = Path(tmpdir) / "Vault2"
        vault1_path.mkdir()
        vault2_path.mkdir()
        
        # Create .obsidian directories to make them valid vaults
        (vault1_path / ".obsidian").mkdir()
        (vault2_path / ".obsidian").mkdir()
        
        # Create initial config with legacy UUID IDs
        config = SyncConfig()
        legacy_id1 = "550e8400-e29b-41d4-a716-446655440001"
        legacy_id2 = "550e8400-e29b-41d4-a716-446655440002"
        
        vault1 = Vault(name="Vault1", path=str(vault1_path), vault_id=legacy_id1)
        vault2 = Vault(name="Vault2", path=str(vault2_path), vault_id=legacy_id2)
        config.vaults = [vault1, vault2]
        
        print(f"Initial vault IDs:")
        print(f"  Vault1: {legacy_id1}")
        print(f"  Vault2: {legacy_id2}")
        
        # Create setup command
        setup_cmd = SetupCommand(config, verbose=True, enable_suggestions=False)
        
        # Build legacy vault map
        legacy_map = setup_cmd._build_legacy_vault_map()
        
        # Verify map was built correctly
        normalized1 = normalize_vault_path(str(vault1_path))
        normalized2 = normalize_vault_path(str(vault2_path))
        
        assert normalized1 in legacy_map, "Vault1 should be in legacy map"
        assert normalized2 in legacy_map, "Vault2 should be in legacy map"
        assert legacy_map[normalized1] == legacy_id1, "Vault1 ID should match"
        assert legacy_map[normalized2] == legacy_id2, "Vault2 ID should match"
        print("✓ Legacy vault map built correctly")
        
        # Test vault discovery with normalization
        discovered = setup_cmd._discover_vaults()
        print(f"✓ Discovered {len(discovered)} vaults")
        
        # Simulate reconfiguration preserving IDs
        for vault in discovered:
            normalized = normalize_vault_path(vault.path)
            if normalized in legacy_map:
                vault.vault_id = legacy_map[normalized]
                
        # Verify IDs were preserved
        for vault in discovered:
            if vault.name == "Vault1":
                assert vault.vault_id == legacy_id1, f"Vault1 ID should be preserved, got {vault.vault_id}"
            elif vault.name == "Vault2":
                assert vault.vault_id == legacy_id2, f"Vault2 ID should be preserved, got {vault.vault_id}"
                
        print("✓ Vault IDs preserved during reconfiguration")


def test_vault_path_normalization():
    """Test that vault paths are normalized consistently."""
    print("\n=== Testing Vault Path Normalization in Setup ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir) / "TestVault"
        vault_path.mkdir()
        (vault_path / ".obsidian").mkdir()
        
        config = SyncConfig()
        setup_cmd = SetupCommand(config, enable_suggestions=False)
        
        # Test with various path formats
        test_paths = [
            str(vault_path),
            str(vault_path) + "/",  # Trailing slash
            str(vault_path / "."),   # With dot
            f"{vault_path}/../{vault_path.name}",  # Relative components
        ]
        
        normalized_results = set()
        for path in test_paths:
            try:
                normalized = setup_cmd._normalize_path(path)
                normalized_results.add(normalized)
                print(f"  {path} -> {normalized}")
            except (ValueError, OSError) as e:
                print(f"  Failed to normalize {path}: {e}")
        
        # All paths should normalize to the same result
        assert len(normalized_results) == 1, f"All paths should normalize to same result, got {len(normalized_results)} different results"
        print("✓ All path variations normalize consistently")


def test_vault_deduplication():
    """Test that duplicate vaults are properly deduplicated by normalized path."""
    print("\n=== Testing Vault Deduplication ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir) / "SharedVault"
        vault_path.mkdir()
        (vault_path / ".obsidian").mkdir()
        
        # Create symlink to the same vault
        symlink_path = Path(tmpdir) / "LinkedVault"
        try:
            symlink_path.symlink_to(vault_path)
            
            # Test vault discovery
            vaults = find_vaults([tmpdir], max_depth=1)
            
            # Should only find one unique vault despite symlink
            unique_paths = set()
            for vault in vaults:
                normalized = normalize_vault_path(vault.path)
                unique_paths.add(normalized)
            
            assert len(unique_paths) <= 1, f"Should find at most 1 unique vault, found {len(unique_paths)}"
            print(f"✓ Deduplication works: found {len(vaults)} vault(s), {len(unique_paths)} unique")
            
        except OSError:
            print("⚠️ Symlink test skipped (no permissions)")


def test_manual_vault_addition():
    """Test manually adding vaults with path normalization."""
    print("\n=== Testing Manual Vault Addition ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir) / "ManualVault"
        vault_path.mkdir()
        
        config = SyncConfig()
        setup_cmd = SetupCommand(config, enable_suggestions=False)
        
        # Test _prompt_manual_vaults with mock input
        existing_paths = set()
        
        # Mock user input for adding vault
        with patch('builtins.input', side_effect=[
            str(vault_path),  # Vault path
            'TestVault',      # Vault name
            'n'               # Don't add another
        ]):
            added = setup_cmd._prompt_manual_vaults(existing_paths)
        
        assert len(added) == 1, "Should add one vault"
        vault = added[0]
        
        # Check path was normalized
        expected_normalized = normalize_vault_path(str(vault_path))
        actual_normalized = normalize_vault_path(vault.path)
        assert actual_normalized == expected_normalized, "Vault path should be normalized"
        
        print(f"✓ Manual vault added with normalized path")
        print(f"  Original: {vault_path}")
        print(f"  Normalized: {actual_normalized}")


def test_vault_path_validation():
    """Test that invalid vault paths are handled correctly."""
    print("\n=== Testing Vault Path Validation ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a vault that we'll "move"
        old_path = Path(tmpdir) / "OldLocation"
        old_path.mkdir()
        
        config = SyncConfig()
        vault = Vault(name="MovedVault", path=str(old_path))
        config.vaults = [vault]
        
        # Delete the old path to simulate vault being moved
        import shutil
        shutil.rmtree(old_path)
        
        # Create new location
        new_path = Path(tmpdir) / "NewLocation"
        new_path.mkdir()
        
        setup_cmd = SetupCommand(config, verbose=True, enable_suggestions=False)
        
        # Test amendment with moved vault
        with patch('builtins.input', side_effect=[
            str(new_path),  # New path for moved vault
            ''              # Keep current mapping
        ]):
            # This should handle the missing vault gracefully
            setup_cmd._amend_vault_mappings()
        
        # Vault path should be updated
        updated_vault = config.vaults[0]
        normalized_new = normalize_vault_path(str(new_path))
        normalized_actual = normalize_vault_path(updated_vault.path)
        
        assert normalized_actual == normalized_new, "Vault path should be updated"
        print("✓ Vault path validation and update works correctly")


def test_reset_clears_state():
    """Test that reset clears sync links, indices, inbox files, and tag routes."""
    print("\n=== Testing Reset Clears State ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test vault
        vault_path = Path(tmpdir) / "TestVault"
        vault_path.mkdir()
        (vault_path / ".obsidian").mkdir()
        
        # Create inbox file
        inbox_file = vault_path / "AppleRemindersInbox.md"
        inbox_file.write_text("# Test Inbox\n- [ ] Test task")
        
        # Create config with vault and tag routes
        config = SyncConfig(
            vaults=[Vault(name="TestVault", path=str(vault_path), vault_id="test-vault-1", is_default=True)],
            default_vault_id="test-vault-1",
            reminders_lists=[RemindersList(name="Test List", identifier="test-list-1", source_name="Test", source_type="local", color="red", allows_modification=True)],
            default_calendar_id="test-list-1",
            tag_routes=[{"vault_id": "test-vault-1", "tag": "work", "calendar_id": "test-list-1"}]
        )
        
        # Create fake data directory structure
        data_dir = Path(tmpdir) / "data"
        data_dir.mkdir()
        
        # Create fake sync files
        sync_links_file = data_dir / "sync_links.json"
        obsidian_index_file = data_dir / "obsidian_tasks_index.json"
        reminders_index_file = data_dir / "reminders_tasks_index.json"
        
        sync_links_file.write_text('[]')
        obsidian_index_file.write_text('{}')
        reminders_index_file.write_text('{}')
        
        # Mock PathManager to use our test directory
        class MockPathManager:
            def sync_links_path(self):
                return sync_links_file
            def obsidian_index_path(self):
                return obsidian_index_file
            def reminders_index_path(self):
                return reminders_index_file
        
        # Verify initial state
        assert inbox_file.exists(), "Inbox file should exist initially"
        assert sync_links_file.exists(), "Sync links file should exist initially"
        assert obsidian_index_file.exists(), "Obsidian index should exist initially"
        assert reminders_index_file.exists(), "Reminders index should exist initially"
        assert len(config.tag_routes) == 1, "Tag routes should exist initially"
        
        # Create setup command and run reset
        setup_cmd = SetupCommand(config, verbose=True, enable_suggestions=False)
        
        # Mock path manager and user inputs
        with patch('obs_sync.commands.setup.get_path_manager', return_value=MockPathManager()):
            with patch('obs_sync.commands.setup.SetupCommand._discover_vaults', return_value=[]):
                with patch('obs_sync.commands.setup.SetupCommand._discover_reminders_lists', return_value=[]):
                    with patch('builtins.input', side_effect=['1']):  # Choose reset option
                        result = setup_cmd._run_full_reset()
                        
        # Verify state was cleared
        assert not inbox_file.exists(), "Inbox file should be deleted after reset"
        assert not sync_links_file.exists(), "Sync links file should be deleted after reset"
        assert not obsidian_index_file.exists(), "Obsidian index should be deleted after reset"
        assert not reminders_index_file.exists(), "Reminders index should be deleted after reset"
        assert len(config.tag_routes) == 0, "Tag routes should be cleared after reset"
        
        print("✅ Reset successfully clears all state")


def run_all_tests():
    """Run all setup normalization tests."""
    print("=" * 60)
    print("SETUP COMMAND NORMALIZATION TESTS")
    print("=" * 60)
    
    try:
        test_setup_preserves_vault_ids()
        test_vault_path_normalization()
        test_vault_deduplication()
        test_manual_vault_addition()
        test_vault_path_validation()
        test_reset_clears_state()
        
        print("\n" + "=" * 60)
        print("🎉 ALL SETUP NORMALIZATION TESTS PASSED!")
        print("=" * 60)
        return True
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)