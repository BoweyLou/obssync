#!/usr/bin/env python3
"""
Integration test for vault and list removal functionality.
Tests the complete end-to-end flow including menu interaction.
"""

import sys
import tempfile
import json
from unittest.mock import patch, Mock
from pathlib import Path
from obs_sync.core.models import SyncConfig, Vault, RemindersList
from obs_sync.commands.setup import SetupCommand


def test_vault_removal_integration():
    """Test complete vault removal integration through amend menu."""
    
    # Create test config
    config = SyncConfig()
    config.vaults = [
        Vault(name="Work", path="/tmp/work", vault_id="work-id", is_default=True),
        Vault(name="Personal", path="/tmp/personal", vault_id="personal-id")
    ]
    config.default_vault_id = "work-id"
    
    config.reminders_lists = [
        RemindersList(name="Work Tasks", identifier="work-list-id", source_name="Reminders",
                     source_type="local", color="blue", allows_modification=True)
    ]
    config.default_calendar_id = "work-list-id"
    
    # Add some data that should be cleaned up
    config.set_vault_mapping("personal-id", "work-list-id")
    config.set_tag_route("personal-id", "urgent", "work-list-id")
    
    setup_cmd = SetupCommand(config, verbose=True)
    
    # Mock file operations
    with patch.object(setup_cmd, '_clear_vault_inbox') as mock_clear_inbox, \
         patch.object(setup_cmd, '_clear_vault_sync_links') as mock_clear_links, \
         patch('builtins.input') as mock_input, \
         patch('builtins.print'):
        
        # Simulate: option 6 (remove vault), vault 2 (Personal), confirm
        mock_input.side_effect = ['6', '2', 'yes']
        
        # Run the amend flow
        result = setup_cmd._run_amend_flow()
        
        # Verify success
        assert result is True, "Amend flow should succeed"
        
        # Verify vault was removed
        vault_ids = [v.vault_id for v in config.vaults]
        assert "personal-id" not in vault_ids, "Personal vault should be removed"
        assert "work-id" in vault_ids, "Work vault should remain as default"
        
        # Verify cleanup was called (note: path gets normalized)
        mock_clear_inbox.assert_called_once()
        mock_clear_links.assert_called_once_with("personal-id")
        
        # Check that the correct vault path was passed (allowing for path normalization)
        call_args = mock_clear_inbox.call_args[0]
        assert call_args[1] == "Personal", "Should pass correct vault name"
        assert call_args[0].endswith("/tmp/personal") or call_args[0].endswith("/private/tmp/personal"), "Should pass correct vault path"
        
        print("✅ Vault removal integration test passed")
        return True


def test_list_removal_integration():
    """Test complete list removal integration through amend menu."""
    
    # Create test config
    config = SyncConfig()
    config.vaults = [
        Vault(name="Work", path="/tmp/work", vault_id="work-id")
    ]
    
    config.reminders_lists = [
        RemindersList(name="Work Tasks", identifier="work-list-id", source_name="Reminders",
                     source_type="local", color="blue", allows_modification=True),
        RemindersList(name="Personal", identifier="personal-list-id", source_name="Reminders",
                     source_type="local", color="green", allows_modification=True)
    ]
    config.default_calendar_id = "work-list-id"
    
    # Add mappings that should be cleaned up
    config.set_vault_mapping("work-id", "personal-list-id")
    config.set_tag_route("work-id", "home", "personal-list-id")
    
    setup_cmd = SetupCommand(config, verbose=True)
    
    with patch('builtins.input') as mock_input, \
         patch('builtins.print'):
        
        # Simulate: option 7 (remove list), list 2 (Personal), confirm
        mock_input.side_effect = ['7', '2', 'yes']
        
        # Run the amend flow
        result = setup_cmd._run_amend_flow()
        
        # Verify success
        assert result is True, "Amend flow should succeed"
        
        # Verify list was removed
        list_ids = [lst.identifier for lst in config.reminders_lists]
        assert "personal-list-id" not in list_ids, "Personal list should be removed"
        assert "work-list-id" in list_ids, "Work list should remain"
        
        # Verify mappings were cleared
        work_mapping = config.get_vault_mapping("work-id")
        assert work_mapping is None, "Vault mapping should be cleared"
        
        # Verify tag routes were cleared
        home_route = config.get_tag_route("work-id", "home")
        assert home_route is None, "Tag route should be cleared"
        
        print("✅ List removal integration test passed")
        return True


def test_cancellation_handling():
    """Test that cancellation works properly."""
    
    config = SyncConfig()
    config.vaults = [
        Vault(name="Work", path="/tmp/work", vault_id="work-id")
    ]
    
    setup_cmd = SetupCommand(config, verbose=True)
    
    with patch('builtins.input') as mock_input, \
         patch('builtins.print'):
        
        # Test vault removal cancellation
        mock_input.side_effect = ['6', 'cancel']
        result = setup_cmd._run_amend_flow()
        assert result is True, "Should handle cancellation gracefully"
        
        # Verify vault still exists
        assert len(config.vaults) == 1, "Vault should not be removed on cancel"
        
        print("✅ Cancellation handling test passed")
        return True


if __name__ == "__main__":
    try:
        test_vault_removal_integration()
        test_list_removal_integration()
        test_cancellation_handling()
        print("🎉 All integration tests passed!")
    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)