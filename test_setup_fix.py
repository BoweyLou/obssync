#!/usr/bin/env python3
"""
Test script to verify the --add setup flow fix works correctly.
This simulates the scenario where new Reminders lists should be available
when mapping new vaults.
"""

import sys
from unittest.mock import Mock, patch
from obs_sync.core.models import SyncConfig, Vault, RemindersList
from obs_sync.commands.setup import SetupCommand


def test_new_lists_available_for_vault_mapping():
    """Test that newly added lists are available when mapping new vaults."""
    
    # Create a mock config with existing data
    config = SyncConfig()
    config.vaults = [
        Vault(name="ExistingVault", path="/existing/path", vault_id="existing-id")
    ]
    config.reminders_lists = [
        RemindersList(name="Personal", identifier="personal-id", source_name="Reminders", 
                     source_type="local", color="blue", allows_modification=True)
    ]
    
    setup_cmd = SetupCommand(config, verbose=True)
    
    # Mock the collection methods to return new data
    new_vault = Vault(name="NewVault", path="/new/path", vault_id="new-id")
    new_list = RemindersList(name="Vault", identifier="vault-id", source_name="Reminders",
                            source_type="local", color="red", allows_modification=True)
    
    with patch.object(setup_cmd, '_collect_additional_vaults', return_value=[new_vault]), \
         patch.object(setup_cmd, '_collect_additional_lists', return_value=[new_list]), \
         patch.object(setup_cmd, '_handle_default_vault_change'), \
         patch.object(setup_cmd, '_handle_default_calendar_change'), \
         patch.object(setup_cmd, '_refresh_calendar_ids'), \
         patch('builtins.input', return_value='2'), \
         patch('builtins.print') as mock_print:
        
        # Run the additional flow
        result = setup_cmd._run_additional_flow()
        
        # Verify success
        assert result == True
        
        # Verify that new list was added to config
        assert len(config.reminders_lists) == 2
        assert config.reminders_lists[1].name == "Vault"
        
        # Verify that new vault was added
        assert len(config.vaults) == 2 
        assert config.vaults[1].name == "NewVault"
        
        # Check that the vault mapping UI showed both lists
        print_calls = [str(call) for call in mock_print.call_args_list]
        vault_mapping_calls = [call for call in print_calls if "Available lists:" in call or "1. Personal" in call or "2. Vault" in call]
        
        # Should show both the existing "Personal" and new "Vault" list
        assert any("1. Personal" in call for call in print_calls), "Should show existing Personal list"
        assert any("2. Vault" in call for call in print_calls), "Should show newly added Vault list"
        
        print("✅ Test passed: New lists are available for vault mapping")
        return True


if __name__ == "__main__":
    try:
        test_new_lists_available_for_vault_mapping()
        print("\n🎉 All tests passed! The fix works correctly.")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)