#!/usr/bin/env python3
"""
Integration test for the new reconfigure amend functionality.
Tests the complete flow from CLI invocation through configuration changes.
"""

import os
import sys
import tempfile
import json
from unittest.mock import patch
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from obs_sync.core.models import SyncConfig, Vault, RemindersList
from obs_sync.core.config import save_config, load_config
from obs_sync.main import main


def test_reconfigure_amend_integration():
    """Test the complete reconfigure amend flow through the CLI."""
    
    # Create a temporary config file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        config_path = f.name
        
        # Create initial configuration
        config = SyncConfig()
        config.vaults = [
            Vault(name="TestVault", path="/test/vault", vault_id="test-vault-id", is_default=True)
        ]
        config.default_vault_id = "test-vault-id"
        config.reminders_lists = [
            RemindersList(name="TestList", identifier="test-list-id", source_name="Test",
                         source_type="local", color="blue", allows_modification=True),
            RemindersList(name="OtherList", identifier="other-list-id", source_name="Test",
                         source_type="local", color="green", allows_modification=True)
        ]
        config.default_calendar_id = "test-list-id"
        config.set_vault_mapping("test-vault-id", "test-list-id")
        
        # Save initial config
        save_config(config, config_path)
    
    try:
        # Test the amend flow through CLI
        with patch('builtins.input') as mock_input, \
             patch('builtins.print') as mock_print, \
             patch('obs_sync.commands.setup.SetupCommand._discover_vaults', return_value=[]), \
             patch('obs_sync.commands.setup.SetupCommand._discover_reminders_lists', return_value=[]):
            
            # Simulate user choosing:
            # 1. Amend option (2)
            # 2. Modify vault mappings (1)
            # 3. Change mapping to OtherList (2)
            mock_input.side_effect = [
                '2',  # Choose amend
                '1',  # Choose to modify vault mappings
                '2',  # Map TestVault to OtherList
            ]
            
            # Run the setup command with --reconfigure
            sys.argv = ['obs-sync', '--config', config_path, 'setup', '--reconfigure']
            result = main(['--config', config_path, 'setup', '--reconfigure'])
            
            # Check that the command succeeded
            assert result == 0, "Command should succeed"
            
            # Load the modified config
            modified_config = load_config(config_path)
            
            # Verify the mapping was changed
            assert modified_config.get_vault_mapping("test-vault-id") == "other-list-id", \
                   "Vault mapping should be updated to other-list-id"
            
            # Verify other settings remained unchanged
            assert modified_config.default_vault_id == "test-vault-id", \
                   "Default vault should remain unchanged"
            assert modified_config.default_calendar_id == "test-list-id", \
                   "Default calendar should remain unchanged"
            
            print("✅ Integration test passed: Reconfigure amend flow works end-to-end")
            return True
            
    finally:
        # Clean up temporary file
        if os.path.exists(config_path):
            os.unlink(config_path)


def test_reconfigure_reset_integration():
    """Test the complete reconfigure reset flow through the CLI."""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        config_path = f.name
        
        # Create initial configuration
        config = SyncConfig()
        config.vaults = [
            Vault(name="OldVault", path="/old/vault", vault_id="old-vault-id")
        ]
        save_config(config, config_path)
    
    try:
        with patch('builtins.input') as mock_input, \
             patch('builtins.print'), \
             patch('obs_sync.commands.setup.SetupCommand._discover_vaults') as mock_discover_vaults, \
             patch('obs_sync.commands.setup.SetupCommand._discover_reminders_lists') as mock_discover_lists:
            
            # Mock discoveries
            mock_discover_vaults.return_value = [
                Vault(name="NewVault", path="/new/vault", vault_id="new-vault-id")
            ]
            mock_discover_lists.return_value = [
                RemindersList(name="NewList", identifier="new-list-id", source_name="Test",
                            source_type="local", color="red", allows_modification=True)
            ]
            
            # Simulate reset flow
            mock_input.side_effect = [
                '1',     # Choose reset
                '1',     # Select vault 1
                '1',     # Select list 1
                '1',     # Map vault to list 1
                '',      # Keep default match score
                'n',     # Don't include completed
            ]
            
            sys.argv = ['obs-sync', '--config', config_path, 'setup', '--reconfigure']
            result = main(['--config', config_path, 'setup', '--reconfigure'])
            
            assert result == 0, "Command should succeed"
            
            # Load modified config
            modified_config = load_config(config_path)
            
            # Verify reset happened - old vault should be replaced
            assert len(modified_config.vaults) == 1
            assert modified_config.vaults[0].name == "NewVault"
            assert modified_config.vaults[0].vault_id == "new-vault-id"
            
            print("✅ Integration test passed: Reconfigure reset flow works end-to-end")
            return True
            
    finally:
        if os.path.exists(config_path):
            os.unlink(config_path)


if __name__ == "__main__":
    try:
        test_reconfigure_amend_integration()
        test_reconfigure_reset_integration()
        print("\n🎉 All integration tests passed!")
    except Exception as e:
        print(f"\n❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)