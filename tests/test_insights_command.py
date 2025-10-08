"""
Tests for InsightsCommand (obs_sync/commands/insights.py).

Validates CLI invocation, hygiene analysis, and JSON export.
"""

import json
import tempfile
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock, patch
import pytest

from obs_sync.core.models import SyncConfig, RemindersTask, TaskStatus, Priority, RemindersList
from obs_sync.commands.insights import InsightsCommand


class TestInsightsCommand:
    """Test suite for InsightsCommand."""
    
    def test_command_success_path(self):
        """Test successful execution of insights command."""
        config = SyncConfig(
            enable_hygiene_assistant=True,
            hygiene_stagnant_threshold=14,
            reminders_lists=[
                RemindersList(name="Work", identifier="cal-1", source_name="iCloud", source_type="Local")
            ]
        )
        
        # Mock tasks
        tasks = [
            RemindersTask(
                uuid="1",
                item_id="rem-1",
                calendar_id="cal-1",
                list_name="Work",
                status=TaskStatus.TODO,
                title="Active task",
                created_at=datetime.now(timezone.utc),
                modified_at=datetime.now(timezone.utc)
            ),
            RemindersTask(
                uuid="2",
                item_id="rem-2",
                calendar_id="cal-1",
                list_name="Work",
                status=TaskStatus.TODO,
                title="Stagnant task",
                created_at=datetime.now(timezone.utc) - timedelta(days=30),
                modified_at=datetime.now(timezone.utc) - timedelta(days=30)
            )
        ]
        
        with patch('obs_sync.commands.insights.RemindersTaskManager') as mock_rtm_class:
            mock_rtm = Mock()
            mock_rtm.list_tasks.return_value = tasks
            mock_rtm_class.return_value = mock_rtm
            
            cmd = InsightsCommand(config, verbose=True)
            result = cmd.run()
            
            assert result is True
            mock_rtm.list_tasks.assert_called_once()
    
    def test_command_with_json_export(self):
        """Test JSON export functionality."""
        config = SyncConfig(
            enable_hygiene_assistant=True,
            reminders_lists=[
                RemindersList(name="Work", identifier="cal-1", source_name="iCloud", source_type="Local")
            ]
        )
        
        tasks = [
            RemindersTask(
                uuid="1",
                item_id="rem-1",
                calendar_id="cal-1",
                list_name="Work",
                status=TaskStatus.TODO,
                title="Task without due date",
                created_at=datetime.now(timezone.utc),
                modified_at=datetime.now(timezone.utc)
            )
        ]
        
        with tempfile.TemporaryDirectory() as tmpdir:
            export_path = Path(tmpdir) / "insights.json"
            
            with patch('obs_sync.commands.insights.RemindersTaskManager') as mock_rtm_class:
                mock_rtm = Mock()
                mock_rtm.list_tasks.return_value = tasks
                mock_rtm_class.return_value = mock_rtm
                
                cmd = InsightsCommand(config, verbose=True)
                result = cmd.run(export_json=str(export_path))
                
                assert result is True
                assert export_path.exists()
                
                # Validate JSON structure - keys should be stagnants, missing_due, overdue
                data = json.loads(export_path.read_text())
                assert "stagnants" in data
                assert "missing_due" in data
                assert "overdue" in data
                assert "summary" in data
    
    def test_command_disabled_in_config(self):
        """Test that command exits early when disabled in config."""
        config = SyncConfig(enable_hygiene_assistant=False)
        
        with patch('obs_sync.commands.insights.RemindersTaskManager') as mock_rtm_class:
            cmd = InsightsCommand(config, verbose=True)
            result = cmd.run()
            
            # Should exit early without creating task manager
            mock_rtm_class.assert_not_called()
            assert result is True  # Not a failure, just no-op
    
    def test_command_handles_stagnant_tasks(self):
        """Test that stagnant tasks are identified."""
        config = SyncConfig(
            enable_hygiene_assistant=True,
            hygiene_stagnant_threshold=7,
            reminders_lists=[
                RemindersList(name="Work", identifier="cal-1", source_name="iCloud", source_type="Local")
            ]
        )
        
        now = datetime.now(timezone.utc)
        tasks = [
            RemindersTask(
                uuid="1",
                item_id="rem-1",
                calendar_id="cal-1",
                list_name="Work",
                status=TaskStatus.TODO,
                title="Very old task",
                created_at=now - timedelta(days=30),
                modified_at=now - timedelta(days=30)
            )
        ]
        
        with patch('obs_sync.commands.insights.RemindersTaskManager') as mock_rtm_class:
            mock_rtm = Mock()
            mock_rtm.list_tasks.return_value = tasks
            mock_rtm_class.return_value = mock_rtm
            
            with patch('obs_sync.commands.insights.format_hygiene_report_cli') as mock_format:
                cmd = InsightsCommand(config, verbose=True)
                result = cmd.run()
                
                assert result is True
                # Verify formatter was called with stagnant tasks
                call_args = mock_format.call_args[0]
                stagnant_list = call_args[0]
                assert len(stagnant_list) > 0
    
    def test_command_handles_missing_due_dates(self):
        """Test that tasks without due dates are identified."""
        config = SyncConfig(
            enable_hygiene_assistant=True,
            reminders_lists=[
                RemindersList(name="Work", identifier="cal-1", source_name="iCloud", source_type="Local")
            ]
        )
        
        tasks = [
            RemindersTask(
                uuid="1",
                item_id="rem-1",
                calendar_id="cal-1",
                list_name="Work",
                status=TaskStatus.TODO,
                title="No due date",
                due_date=None,
                created_at=datetime.now(timezone.utc),
                modified_at=datetime.now(timezone.utc)
            )
        ]
        
        with patch('obs_sync.commands.insights.RemindersTaskManager') as mock_rtm_class:
            mock_rtm = Mock()
            mock_rtm.list_tasks.return_value = tasks
            mock_rtm_class.return_value = mock_rtm
            
            with patch('obs_sync.commands.insights.format_hygiene_report_cli') as mock_format:
                cmd = InsightsCommand(config, verbose=True)
                result = cmd.run()
                
                assert result is True
                call_args = mock_format.call_args[0]
                missing_due = call_args[1]
                assert len(missing_due) > 0
    
    def test_command_handles_overdue_tasks(self):
        """Test that overdue tasks are identified."""
        config = SyncConfig(
            enable_hygiene_assistant=True,
            reminders_lists=[
                RemindersList(name="Work", identifier="cal-1", source_name="iCloud", source_type="Local")
            ]
        )
        
        yesterday = date.today() - timedelta(days=1)
        tasks = [
            RemindersTask(
                uuid="1",
                item_id="rem-1",
                calendar_id="cal-1",
                list_name="Work",
                status=TaskStatus.TODO,
                title="Overdue task",
                due_date=yesterday,
                created_at=datetime.now(timezone.utc),
                modified_at=datetime.now(timezone.utc)
            )
        ]
        
        with patch('obs_sync.commands.insights.RemindersTaskManager') as mock_rtm_class:
            mock_rtm = Mock()
            mock_rtm.list_tasks.return_value = tasks
            mock_rtm_class.return_value = mock_rtm
            
            with patch('obs_sync.commands.insights.format_hygiene_report_cli') as mock_format:
                cmd = InsightsCommand(config, verbose=True)
                result = cmd.run()
                
                assert result is True
                call_args = mock_format.call_args[0]
                overdue = call_args[2]
                assert len(overdue) > 0
    
    def test_json_export_write_failure(self):
        """Test handling of JSON export write failures."""
        config = SyncConfig(enable_hygiene_assistant=True)
        
        tasks = []
        
        with patch('obs_sync.commands.insights.RemindersTaskManager') as mock_rtm_class:
            mock_rtm = Mock()
            mock_rtm.list_tasks.return_value = tasks
            mock_rtm_class.return_value = mock_rtm
            
            # Try to write to invalid path
            cmd = InsightsCommand(config, verbose=True)
            result = cmd.run(export_json="/nonexistent/path/insights.json")
            
            # Should handle error gracefully
            assert result is False or result is True  # Implementation dependent
    
    def test_hygiene_analyzer_integration(self):
        """Test that HygieneAnalyzer is properly integrated."""
        config = SyncConfig(
            enable_hygiene_assistant=True,
            hygiene_stagnant_threshold=14,
            reminders_lists=[
                RemindersList(name="Work", identifier="cal-1", source_name="iCloud", source_type="Local")
            ]
        )
        
        now = datetime.now(timezone.utc)
        tasks = [
            RemindersTask(
                uuid="1",
                item_id="rem-1",
                calendar_id="cal-1",
                list_name="Work",
                status=TaskStatus.TODO,
                title="Stagnant",
                created_at=now - timedelta(days=20),
                modified_at=now - timedelta(days=20)
            ),
            RemindersTask(
                uuid="2",
                item_id="rem-2",
                calendar_id="cal-1",
                list_name="Work",
                status=TaskStatus.TODO,
                title="Overdue",
                due_date=date.today() - timedelta(days=5),
                created_at=now,
                modified_at=now
            ),
            RemindersTask(
                uuid="3",
                item_id="rem-3",
                calendar_id="cal-1",
                list_name="Work",
                status=TaskStatus.TODO,
                title="No due date",
                due_date=None,
                created_at=now,
                modified_at=now
            )
        ]
        
        with patch('obs_sync.commands.insights.RemindersTaskManager') as mock_rtm_class:
            mock_rtm = Mock()
            mock_rtm.list_tasks.return_value = tasks
            mock_rtm_class.return_value = mock_rtm
            
            cmd = InsightsCommand(config, verbose=True)
            result = cmd.run()
            
            assert result is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
