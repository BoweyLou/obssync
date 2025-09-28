#!/usr/bin/env python3
"""
Test script to verify the --add setup flow fix works correctly and test
the new amend functionality for --reconfigure.
This simulates the scenario where new Reminders lists should be available
when mapping new vaults.
"""

import sys
from unittest.mock import Mock, patch, call
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


def test_reconfigure_amend_flow():
    """Test the new amend flow for --reconfigure."""
    
    # Create a mock config with existing configuration
    config = SyncConfig()
    config.vaults = [
        Vault(name="Work", path="/work/path", vault_id="work-id", is_default=True),
        Vault(name="Personal", path="/personal/path", vault_id="personal-id")
    ]
    config.default_vault_id = "work-id"
    
    config.reminders_lists = [
        RemindersList(name="Work Tasks", identifier="work-list-id", source_name="Reminders",
                     source_type="local", color="blue", allows_modification=True),
        RemindersList(name="Personal", identifier="personal-list-id", source_name="Reminders",
                     source_type="local", color="green", allows_modification=True)
    ]
    config.default_calendar_id = "work-list-id"
    
    # Set up existing mappings
    config.set_vault_mapping("work-id", "work-list-id")
    config.set_vault_mapping("personal-id", "personal-list-id")
    
    setup_cmd = SetupCommand(config, verbose=True)
    
    # Test choosing amend option
    with patch('builtins.input') as mock_input, \
         patch('builtins.print') as mock_print:
        
        # Simulate user choosing amend (option 2) and then modifying vault mappings (option 1)
        mock_input.side_effect = [
            '2',  # Choose amend option
            '1',  # Choose to modify vault mappings
            '2',  # Change Work vault to Personal list
            '',   # Keep Personal vault mapping as-is
        ]
        
        # Run the reconfigure flow
        result = setup_cmd._handle_reconfigure_choice()
        
        # Verify success
        assert result == True
        
        # Verify the mapping was changed
        assert config.get_vault_mapping("work-id") == "personal-list-id"
        assert config.get_vault_mapping("personal-id") == "personal-list-id"
        
        # Check that the amend UI was shown
        print_calls = [str(call_obj) for call_obj in mock_print.call_args_list]
        assert any("Reconfigure Options:" in call for call in print_calls)
        assert any("Amending existing configuration" in call for call in print_calls)
        
        print("✅ Test passed: Amend flow works correctly")
        return True


def test_reconfigure_reset_flow():
    """Test that choosing reset option leads to full setup."""
    
    config = SyncConfig()
    config.vaults = [
        Vault(name="Existing", path="/existing", vault_id="existing-id")
    ]
    
    setup_cmd = SetupCommand(config, verbose=True)
    
    with patch('builtins.input') as mock_input, \
         patch('builtins.print') as mock_print, \
         patch.object(setup_cmd, '_continue_full_setup', return_value=True) as mock_full_setup:
        
        # Simulate user choosing reset (option 1)
        mock_input.return_value = '1'
        
        result = setup_cmd._handle_reconfigure_choice()
        
        # Verify success and that full setup was called
        assert result == True
        mock_full_setup.assert_called_once()
        
        # Check that reset message was shown
        print_calls = [str(call_obj) for call_obj in mock_print.call_args_list]
        assert any("Resetting configuration" in call for call in print_calls)
        
        print("✅ Test passed: Reset flow works correctly")
        return True


def test_amend_default_selections():
    """Test amending default vault and list selections."""
    
    config = SyncConfig()
    config.vaults = [
        Vault(name="Vault1", path="/path1", vault_id="id1", is_default=True),
        Vault(name="Vault2", path="/path2", vault_id="id2")
    ]
    config.default_vault_id = "id1"
    
    config.reminders_lists = [
        RemindersList(name="List1", identifier="list1-id", source_name="Reminders",
                     source_type="local", color="blue", allows_modification=True),
        RemindersList(name="List2", identifier="list2-id", source_name="Reminders",
                     source_type="local", color="green", allows_modification=True)
    ]
    config.default_calendar_id = "list1-id"
    
    setup_cmd = SetupCommand(config, verbose=True)
    
    # Test changing default vault
    with patch('builtins.input', return_value='2'), \
         patch('builtins.print'):
        
        setup_cmd._amend_default_vault()
        assert config.default_vault_id == "id2"
        assert config.vaults[0].is_default == False
        assert config.vaults[1].is_default == True
    
    # Test changing default list
    with patch('builtins.input', return_value='2'), \
         patch('builtins.print'):
        
        setup_cmd._amend_default_list()
        assert config.default_calendar_id == "list2-id"
    
    print("✅ Test passed: Default amendments work correctly")
    return True


if __name__ == "__main__":
    try:
        test_new_lists_available_for_vault_mapping()
        test_reconfigure_amend_flow()
        test_reconfigure_reset_flow()
        test_amend_default_selections()
        print("\n🎉 All tests passed! The fix works correctly.")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)