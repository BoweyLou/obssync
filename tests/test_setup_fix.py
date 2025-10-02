#!/usr/bin/env python3
"""
Test script to verify the setup addition flows work correctly through
`setup --reconfigure` and its amend options. This simulates the scenario
where new Reminders lists should be available when mapping new vaults.
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


def test_vault_removal():
    """Test vault removal functionality."""
    
    # Create a mock config with multiple vaults
    config = SyncConfig()
    config.vaults = [
        Vault(name="Work", path="/work/path", vault_id="work-id", is_default=True),
        Vault(name="Personal", path="/personal/path", vault_id="personal-id"),
        Vault(name="Archive", path="/archive/path", vault_id="archive-id")
    ]
    config.default_vault_id = "work-id"
    
    config.reminders_lists = [
        RemindersList(name="Work Tasks", identifier="work-list-id", source_name="Reminders",
                     source_type="local", color="blue", allows_modification=True),
        RemindersList(name="Personal", identifier="personal-list-id", source_name="Reminders",
                     source_type="local", color="green", allows_modification=True)
    ]
    
    # Set up mappings and tag routes for the vault we'll remove
    config.set_vault_mapping("personal-id", "personal-list-id")
    config.set_tag_route("personal-id", "urgent", "work-list-id")
    config.set_tag_route("personal-id", "home", "personal-list-id")
    
    setup_cmd = SetupCommand(config, verbose=True)
    
    # Mock the cleanup methods
    with patch.object(setup_cmd, '_clear_vault_inbox') as mock_clear_inbox, \
         patch.object(setup_cmd, '_clear_vault_sync_links') as mock_clear_links, \
         patch('builtins.input') as mock_input, \
         patch('builtins.print') as mock_print:
        
        # Simulate user choosing to remove Personal vault (option 2)
        mock_input.side_effect = ['2', 'yes']
        
        # Run the vault removal
        setup_cmd._remove_vault()
        
        # Verify the vault was removed
        vault_ids = [v.vault_id for v in config.vaults]
        assert "personal-id" not in vault_ids, "Personal vault should be removed"
        assert "work-id" in vault_ids, "Work vault should remain"
        assert "archive-id" in vault_ids, "Archive vault should remain"
        
        # Verify mappings were cleared
        personal_mapping = config.get_vault_mapping("personal-id")
        assert personal_mapping is None, "Personal vault mapping should be cleared"
        
        # Verify tag routes were cleared
        personal_routes = config.get_tag_routes_for_vault("personal-id")
        assert len(personal_routes) == 0, "Personal vault tag routes should be cleared"
        
        # Verify cleanup methods were called
        mock_clear_inbox.assert_called_once_with("/personal/path", "Personal")
        mock_clear_links.assert_called_once_with("personal-id")
        
        print("✅ Test passed: Vault removal works correctly")
        return True


def test_vault_removal_default_handling():
    """Test vault removal when removing the default vault."""
    
    # Create a mock config with multiple vaults
    config = SyncConfig()
    config.vaults = [
        Vault(name="Work", path="/work/path", vault_id="work-id", is_default=True),
        Vault(name="Personal", path="/personal/path", vault_id="personal-id")
    ]
    config.default_vault_id = "work-id"
    
    setup_cmd = SetupCommand(config, verbose=True)
    
    # Mock the cleanup methods
    with patch.object(setup_cmd, '_clear_vault_inbox'), \
         patch.object(setup_cmd, '_clear_vault_sync_links'), \
         patch('builtins.input') as mock_input, \
         patch('builtins.print') as mock_print:
        
        # Simulate user choosing to remove Work vault (the default, option 1)
        # and selecting Personal as the new default
        mock_input.side_effect = ['1', 'yes', '1']  # Remove work, confirm, select personal as new default
        
        # Run the vault removal
        setup_cmd._remove_vault()
        
        # Verify the Work vault was removed
        vault_ids = [v.vault_id for v in config.vaults]
        assert "work-id" not in vault_ids, "Work vault should be removed"
        assert "personal-id" in vault_ids, "Personal vault should remain"
        
        # Verify Personal became the new default
        assert config.default_vault_id == "personal-id", "Personal should be new default"
        personal_vault = next(v for v in config.vaults if v.vault_id == "personal-id")
        assert personal_vault.is_default, "Personal vault should have is_default=True"
        
        print("✅ Test passed: Default vault handling works correctly")
        return True


def test_reminders_list_removal():
    """Test Reminders list removal functionality."""
    
    # Create a mock config with multiple lists
    config = SyncConfig()
    config.vaults = [
        Vault(name="Work", path="/work/path", vault_id="work-id"),
        Vault(name="Personal", path="/personal/path", vault_id="personal-id")
    ]
    
    config.reminders_lists = [
        RemindersList(name="Work Tasks", identifier="work-list-id", source_name="Reminders",
                     source_type="local", color="blue", allows_modification=True),
        RemindersList(name="Personal", identifier="personal-list-id", source_name="Reminders",
                     source_type="local", color="green", allows_modification=True),
        RemindersList(name="Archive", identifier="archive-list-id", source_name="Reminders",
                     source_type="local", color="gray", allows_modification=True)
    ]
    config.default_calendar_id = "work-list-id"
    
    # Set up mappings and tag routes for the list we'll remove
    config.set_vault_mapping("work-id", "personal-list-id")
    config.set_vault_mapping("personal-id", "personal-list-id")
    config.set_tag_route("work-id", "urgent", "personal-list-id")
    
    setup_cmd = SetupCommand(config, verbose=True)
    
    with patch('builtins.input') as mock_input, \
         patch('builtins.print') as mock_print:
        
        # Simulate user choosing to remove Personal list (option 2)
        mock_input.side_effect = ['2', 'yes']
        
        # Run the list removal
        setup_cmd._remove_reminders_list()
        
        # Verify the list was removed
        list_ids = [lst.identifier for lst in config.reminders_lists]
        assert "personal-list-id" not in list_ids, "Personal list should be removed"
        assert "work-list-id" in list_ids, "Work list should remain"
        assert "archive-list-id" in list_ids, "Archive list should remain"
        
        # Verify mappings were cleared
        work_mapping = config.get_vault_mapping("work-id")
        personal_mapping = config.get_vault_mapping("personal-id")
        assert work_mapping is None, "Work vault mapping should be cleared"
        assert personal_mapping is None, "Personal vault mapping should be cleared"
        
        # Verify tag routes were cleared
        work_routes = config.get_tag_routes_for_vault("work-id")
        urgent_route = config.get_tag_route("work-id", "urgent")
        assert urgent_route is None, "Tag route should be cleared"
        
        print("✅ Test passed: Reminders list removal works correctly")
        return True


def test_removal_impact_analysis():
    """Test the impact analysis methods for removal operations."""
    
    # Create a mock config with complex relationships
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
    
    # Set up complex mappings and tag routes
    config.set_vault_mapping("work-id", "work-list-id")
    config.set_tag_route("work-id", "urgent", "personal-list-id")
    config.set_tag_route("work-id", "project", "work-list-id")
    
    # Test vault removal impact
    vault_impact = config.get_vault_removal_impact("work-id")
    assert vault_impact["vault_found"], "Should find the vault"
    assert vault_impact["vault_name"] == "Work", "Should return correct vault name"
    assert vault_impact["is_default"], "Should identify as default vault"
    assert vault_impact["mappings_cleared"] == 1, "Should count 1 mapping to clear"
    assert vault_impact["tag_routes_cleared"] == 2, "Should count 2 tag routes to clear"
    
    # Test list removal impact
    list_impact = config.get_list_removal_impact("work-list-id")
    assert list_impact["list_found"], "Should find the list"
    assert list_impact["list_name"] == "Work Tasks", "Should return correct list name"
    assert list_impact["is_default"], "Should identify as default list"
    assert list_impact["mappings_cleared"] == 1, "Should count 1 mapping to clear"
    assert list_impact["tag_routes_cleared"] == 1, "Should count 1 tag route to clear"
    assert "Work" in list_impact["affected_vaults"], "Should list affected vault"
    
    print("✅ Test passed: Impact analysis works correctly")
    return True


if __name__ == "__main__":
    try:
        test_new_lists_available_for_vault_mapping()
        test_reconfigure_amend_flow()
        test_reconfigure_reset_flow()
        test_amend_default_selections()
        test_vault_removal()
        test_vault_removal_default_handling()
        test_reminders_list_removal()
        test_removal_impact_analysis()
        print("🎉 All tests passed!")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)