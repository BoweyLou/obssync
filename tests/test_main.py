"""
Tests for CLI entry point (obs_sync/main.py).

Validates argument parsing, command dispatch, and error handling.
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

from obs_sync.main import main
from obs_sync.core.models import SyncConfig, Vault, RemindersList


class TestMainCLI:
    """Test suite for main CLI entry point."""

    def test_setup_command_dispatch(self):
        """Test that 'setup' command dispatches to SetupCommand."""
        with patch('obs_sync.main.SetupCommand') as mock_setup:
            mock_instance = Mock()
            mock_instance.run.return_value = True
            mock_setup.return_value = mock_instance
            
            with patch('obs_sync.main.load_config', return_value=SyncConfig()):
                result = main(['setup'])
                
            mock_setup.assert_called_once()
            mock_instance.run.assert_called_once()
            assert result == 0

    def test_sync_command_dispatch(self):
        """Test that 'sync' command dispatches to SyncCommand."""
        with patch('obs_sync.main.SyncCommand') as mock_sync:
            mock_instance = Mock()
            mock_instance.run.return_value = True
            mock_sync.return_value = mock_instance
            
            with patch('obs_sync.main.load_config', return_value=SyncConfig()):
                result = main(['sync'])
                
            mock_sync.assert_called_once()
            mock_instance.run.assert_called_once()
            assert result == 0

    def test_sync_command_with_apply_flag(self):
        """Test that sync --apply passes apply_changes=True."""
        with patch('obs_sync.main.SyncCommand') as mock_sync:
            mock_instance = Mock()
            mock_instance.run.return_value = True
            mock_sync.return_value = mock_instance
            
            with patch('obs_sync.main.load_config', return_value=SyncConfig()):
                result = main(['sync', '--apply'])
                
            mock_instance.run.assert_called_once_with(
                apply_changes=True,
                direction='both'
            )
            assert result == 0

    def test_sync_command_with_direction_flags(self):
        """Test that sync direction flags work correctly."""
        with patch('obs_sync.main.SyncCommand') as mock_sync:
            mock_instance = Mock()
            mock_instance.run.return_value = True
            mock_sync.return_value = mock_instance
            
            with patch('obs_sync.main.load_config', return_value=SyncConfig()):
                # Test --to-reminders
                main(['sync', '--to-reminders'])
                mock_instance.run.assert_called_with(
                    apply_changes=False,
                    direction='to-reminders'
                )
                
                # Test --from-reminders
                main(['sync', '--from-reminders'])
                mock_instance.run.assert_called_with(
                    apply_changes=False,
                    direction='from-reminders'
                )

    def test_calendar_command_dispatch(self):
        """Test that 'calendar' command dispatches to CalendarCommand."""
        with patch('obs_sync.main.CalendarCommand') as mock_cal:
            mock_instance = Mock()
            mock_instance.run.return_value = True
            mock_cal.return_value = mock_instance
            
            with patch('obs_sync.main.load_config', return_value=SyncConfig()):
                result = main(['calendar'])
                
            mock_cal.assert_called_once()
            mock_instance.run.assert_called_once()
            assert result == 0

    def test_insights_command_dispatch(self):
        """Test that 'insights' command dispatches to InsightsCommand."""
        with patch('obs_sync.main.InsightsCommand') as mock_insights:
            mock_instance = Mock()
            mock_instance.run.return_value = True
            mock_insights.return_value = mock_instance
            
            with patch('obs_sync.main.load_config', return_value=SyncConfig()):
                result = main(['insights'])
                
            mock_insights.assert_called_once()
            mock_instance.run.assert_called_once()
            assert result == 0

    def test_update_command_dispatch(self):
        """Test that 'update' command dispatches to UpdateCommand."""
        with patch('obs_sync.main.UpdateCommand') as mock_update:
            mock_instance = Mock()
            mock_instance.run.return_value = True
            mock_update.return_value = mock_instance
            
            with patch('obs_sync.main.load_config', return_value=SyncConfig()):
                result = main(['update'])
                
            mock_update.assert_called_once()
            mock_instance.run.assert_called_once()
            assert result == 0

    def test_migrate_command_dispatch(self):
        """Test that 'migrate' command dispatches to MigrateCommand."""
        with patch('obs_sync.main.MigrateCommand') as mock_migrate:
            mock_instance = Mock()
            mock_instance.run.return_value = True
            mock_migrate.return_value = mock_instance
            
            result = main(['migrate', '--check'])
            
            mock_migrate.assert_called_once()
            mock_instance.run.assert_called_once_with(check_only=True, force=False)
            assert result == 0

    def test_install_deps_command_dispatch(self):
        """Test that 'install-deps' command dispatches to InstallDepsCommand."""
        with patch('obs_sync.main.InstallDepsCommand') as mock_deps:
            mock_instance = Mock()
            mock_instance.run.return_value = True
            mock_deps.return_value = mock_instance
            
            result = main(['install-deps', '--list'])
            
            mock_deps.assert_called_once()
            mock_instance.run.assert_called_once_with(
                group=None,
                auto=False,
                list_groups=True
            )
            assert result == 0

    def test_verbose_flag_propagation(self):
        """Test that --verbose flag is passed to commands."""
        with patch('obs_sync.main.SyncCommand') as mock_sync:
            mock_instance = Mock()
            mock_instance.run.return_value = True
            mock_sync.return_value = mock_instance
            
            with patch('obs_sync.main.load_config', return_value=SyncConfig()):
                main(['sync', '--verbose'])
                
            # Check that verbose was passed to constructor
            call_args = mock_sync.call_args
            assert call_args[1]['verbose'] is True

    def test_command_failure_exit_code(self):
        """Test that command failures return exit code 1."""
        with patch('obs_sync.main.SyncCommand') as mock_sync:
            mock_instance = Mock()
            mock_instance.run.return_value = False  # Failure
            mock_sync.return_value = mock_instance
            
            with patch('obs_sync.main.load_config', return_value=SyncConfig()):
                result = main(['sync'])
                
            assert result == 1

    def test_exception_handling(self):
        """Test that exceptions are caught and logged."""
        with patch('obs_sync.main.SyncCommand') as mock_sync:
            mock_sync.side_effect = Exception("Test error")
            
            with patch('obs_sync.main.load_config', return_value=SyncConfig()):
                result = main(['sync'])
                
            assert result == 1

    def test_config_load_error_handling(self):
        """Test graceful handling when config fails to load."""
        with patch('obs_sync.main.load_config', side_effect=FileNotFoundError()):
            # Setup command should still work (creates new config)
            with patch('obs_sync.main.SetupCommand') as mock_setup:
                mock_instance = Mock()
                mock_instance.run.return_value = True
                mock_setup.return_value = mock_instance
                
                result = main(['setup'])
                assert result == 0

    def test_no_arguments_shows_help(self):
        """Test that running with no arguments shows help."""
        with patch('sys.stderr'):  # Suppress argparse output
            result = main([])
            assert result == 2  # argparse exits with 2 for usage errors

    def test_invalid_command_shows_error(self):
        """Test that invalid commands show error."""
        with patch('sys.stderr'):  # Suppress argparse output
            result = main(['invalid-command'])
            assert result == 2


def test_main_entry_point():
    """Test that main can be called without arguments (uses sys.argv)."""
    with patch('sys.argv', ['obs-sync', 'install-deps', '--list']):
        with patch('obs_sync.main.InstallDepsCommand') as mock_deps:
            mock_instance = Mock()
            mock_instance.run.return_value = True
            mock_deps.return_value = mock_instance
            
            result = main()
            assert result == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
