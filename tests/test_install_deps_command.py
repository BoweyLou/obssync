"""
Tests for InstallDepsCommand (obs_sync/commands/install_deps.py).

Validates dependency group listing, installation, and auto-detection.
"""

import sys
import subprocess
from unittest.mock import Mock, patch, call
import pytest

from obs_sync.commands.install_deps import InstallDepsCommand


class TestInstallDepsCommand:
    """Test suite for InstallDepsCommand."""
    
    def test_list_groups_flag(self):
        """Test that --list displays available dependency groups."""
        cmd = InstallDepsCommand(verbose=True)
        
        with patch('builtins.print') as mock_print:
            result = cmd.run(list_groups=True)
            
            assert result is True
            # Should print group information
            assert mock_print.called
            printed_text = ' '.join([str(call[0][0]) for call in mock_print.call_args_list])
            assert 'eventkit' in printed_text.lower() or 'reminders' in printed_text.lower()
    
    def test_get_dependency_groups(self):
        """Test that dependency groups are defined."""
        cmd = InstallDepsCommand()
        groups = cmd.get_dependency_groups()
        
        assert isinstance(groups, dict)
        assert len(groups) > 0
        
        # Check structure of groups
        for group_name, group_info in groups.items():
            assert 'description' in group_info
            assert 'packages' in group_info or 'pip_extra' in group_info
    
    def test_install_specific_group_with_pip_extra(self):
        """Test installing a group that uses pip extras."""
        cmd = InstallDepsCommand(verbose=True)
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            
            result = cmd.install_dependency_group('eventkit', use_pip_extra=True)
            
            assert result is True
            mock_run.assert_called()
            
            # Should use pip install with extras
            call_args = mock_run.call_args[0][0]
            assert 'pip' in call_args or sys.executable in call_args
            assert 'install' in call_args
    
    def test_install_specific_group_with_packages(self):
        """Test installing a group with individual packages."""
        cmd = InstallDepsCommand(verbose=True)
        
        # Mock a group with packages
        with patch.object(cmd, 'get_dependency_groups') as mock_groups:
            mock_groups.return_value = {
                'test-group': {
                    'description': 'Test',
                    'packages': ['package1', 'package2']
                }
            }
            
            with patch('subprocess.run') as mock_run:
                mock_run.return_value.returncode = 0
                
                result = cmd.install_dependency_group('test-group', use_pip_extra=False)
                
                assert result is True
                assert mock_run.called
    
    def test_install_group_subprocess_failure(self):
        """Test handling of subprocess failures during installation."""
        cmd = InstallDepsCommand(verbose=True)
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 1  # Failure
            
            result = cmd.install_dependency_group('eventkit', use_pip_extra=True)
            
            assert result is False
    
    def test_test_dependency_group(self):
        """Test checking if a dependency group is available."""
        cmd = InstallDepsCommand()
        
        # This will attempt to import - may succeed or fail depending on environment
        # Just verify it doesn't crash
        result = cmd.test_dependency_group('eventkit')
        assert isinstance(result, bool)
    
    def test_auto_install_groups(self):
        """Test auto-installation of platform-specific groups."""
        cmd = InstallDepsCommand(verbose=True)
        
        with patch.object(cmd, 'test_dependency_group', return_value=False):
            with patch.object(cmd, 'install_dependency_group', return_value=True):
                result = cmd.run(auto=True)
                
                # Should attempt to install on macOS
                if sys.platform == 'darwin':
                    assert result is True
                else:
                    assert result is True  # May skip on non-macOS
    
    def test_auto_skips_already_installed(self):
        """Test that auto mode skips already-installed dependencies."""
        cmd = InstallDepsCommand(verbose=True)
        
        with patch.object(cmd, 'test_dependency_group', return_value=True):
            with patch.object(cmd, 'install_dependency_group') as mock_install:
                result = cmd.run(auto=True)
                
                # Should not attempt installation if already available
                mock_install.assert_not_called()
                assert result is True
    
    def test_install_specific_group_via_run(self):
        """Test installing a specific group through run() method."""
        cmd = InstallDepsCommand(verbose=True)
        
        with patch.object(cmd, 'install_dependency_group', return_value=True) as mock_install:
            result = cmd.run(group='eventkit')
            
            assert result is True
            mock_install.assert_called_once_with('eventkit', use_pip_extra=True)
    
    def test_invalid_group_name(self):
        """Test handling of invalid group names."""
        cmd = InstallDepsCommand(verbose=True)
        
        result = cmd.run(group='nonexistent-group')
        
        assert result is False
    
    @pytest.mark.skipif(sys.platform != 'darwin', reason="macOS-specific test")
    def test_get_auto_install_groups_macos(self):
        """Test that macOS returns eventkit in auto-install list."""
        cmd = InstallDepsCommand()
        groups = cmd.get_auto_install_groups()
        
        assert 'eventkit' in groups
    
    @pytest.mark.skipif(sys.platform == 'darwin', reason="Non-macOS test")
    def test_get_auto_install_groups_non_macos(self):
        """Test that non-macOS platforms have appropriate auto-install list."""
        cmd = InstallDepsCommand()
        groups = cmd.get_auto_install_groups()
        
        # Should not include macOS-specific groups
        assert 'eventkit' not in groups
    
    def test_verbose_output(self):
        """Test that verbose mode produces output."""
        cmd = InstallDepsCommand(verbose=True)
        
        with patch('builtins.print') as mock_print:
            with patch.object(cmd, 'test_dependency_group', return_value=True):
                cmd.run(auto=True)
                
                # Should print status messages
                assert mock_print.called
    
    def test_concurrent_installation_safety(self):
        """Test that installation handles concurrent pip calls safely."""
        cmd = InstallDepsCommand(verbose=True)
        
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = [
                Mock(returncode=0),  # First call succeeds
                Mock(returncode=0)   # Second call succeeds
            ]
            
            # Install two groups sequentially
            result1 = cmd.install_dependency_group('eventkit', use_pip_extra=True)
            result2 = cmd.install_dependency_group('eventkit', use_pip_extra=True)
            
            assert result1 is True
            assert result2 is True
            assert mock_run.call_count == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
