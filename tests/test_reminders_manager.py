"""
Tests for RemindersTaskManager create/delete flows (obs_sync/reminders/tasks.py).

Validates task creation, deletion, and gateway error handling.
"""

import sys
from datetime import datetime, timezone, date, timedelta
from unittest.mock import Mock, patch
import pytest

from obs_sync.core.models import RemindersTask, TaskStatus, Priority
from obs_sync.reminders.tasks import RemindersTaskManager
from obs_sync.reminders.gateway import RemindersGateway, ReminderData


class TestRemindersTaskManagerCreate:
    """Test suite for RemindersTaskManager.create_task()."""
    
    def test_create_task_basic(self):
        """Test basic task creation."""
        mock_gateway = Mock(spec=RemindersGateway)
        mock_gateway.create_reminder.return_value = "new-reminder-uuid"
        
        # Mock get_reminders to return the created task
        mock_gateway.get_reminders.return_value = [
            ReminderData(
                uuid="new-reminder-uuid",
                title="Test Task",
                completed=False,
                list_id="list-1",
                list_name="Work",
                created_at=datetime.now(timezone.utc).isoformat(),
                modified_at=datetime.now(timezone.utc).isoformat()
            )
        ]
        
        manager = RemindersTaskManager(gateway=mock_gateway)
        
        task = RemindersTask(
            uuid="temp-uuid",
            item_id=None,
            calendar_id="list-1",
            list_name="Work",
            status=TaskStatus.TODO,
            title="Test Task"
        )
        
        result = manager.create_task("list-1", task)
        
        assert result is not None
        assert result.title == "Test Task"
        mock_gateway.create_reminder.assert_called_once()
    
    def test_create_task_with_due_date(self):
        """Test creating task with due date."""
        mock_gateway = Mock(spec=RemindersGateway)
        mock_gateway.create_reminder.return_value = "new-uuid"
        mock_gateway.get_reminders.return_value = [
            ReminderData(
                uuid="new-uuid",
                title="Task with due",
                completed=False,
                due_date="2025-06-15",
                list_id="list-1",
                list_name="Work",
                created_at=datetime.now(timezone.utc).isoformat(),
                modified_at=datetime.now(timezone.utc).isoformat()
            )
        ]
        
        manager = RemindersTaskManager(gateway=mock_gateway)
        
        task = RemindersTask(
            uuid="temp",
            item_id=None,
            calendar_id="list-1",
            list_name="Work",
            status=TaskStatus.TODO,
            title="Task with due",
            due_date=date(2025, 6, 15)
        )
        
        result = manager.create_task("list-1", task)
        
        assert result is not None
        # Verify due_date was passed to gateway
        call_kwargs = mock_gateway.create_reminder.call_args[1]
        assert 'due_date' in call_kwargs
    
    def test_create_task_with_priority(self):
        """Test creating task with priority."""
        mock_gateway = Mock(spec=RemindersGateway)
        mock_gateway.create_reminder.return_value = "new-uuid"
        mock_gateway.get_reminders.return_value = [
            ReminderData(
                uuid="new-uuid",
                title="High priority",
                completed=False,
                priority="high",
                list_id="list-1",
                list_name="Work",
                created_at=datetime.now(timezone.utc).isoformat(),
                modified_at=datetime.now(timezone.utc).isoformat()
            )
        ]
        
        manager = RemindersTaskManager(gateway=mock_gateway)
        
        task = RemindersTask(
            uuid="temp",
            item_id=None,
            calendar_id="list-1",
            list_name="Work",
            status=TaskStatus.TODO,
            title="High priority",
            priority=Priority.HIGH
        )
        
        result = manager.create_task("list-1", task)
        
        assert result is not None
        call_kwargs = mock_gateway.create_reminder.call_args[1]
        assert 'priority' in call_kwargs
    
    def test_create_task_with_notes_and_tags(self):
        """Test creating task with notes and tags."""
        mock_gateway = Mock(spec=RemindersGateway)
        mock_gateway.create_reminder.return_value = "new-uuid"
        mock_gateway.get_reminders.return_value = [
            ReminderData(
                uuid="new-uuid",
                title="Task with metadata",
                completed=False,
                notes="Task notes",
                tags=["work", "important"],
                list_id="list-1",
                list_name="Work",
                created_at=datetime.now(timezone.utc).isoformat(),
                modified_at=datetime.now(timezone.utc).isoformat()
            )
        ]
        
        manager = RemindersTaskManager(gateway=mock_gateway)
        
        task = RemindersTask(
            uuid="temp",
            item_id=None,
            calendar_id="list-1",
            list_name="Work",
            status=TaskStatus.TODO,
            title="Task with metadata",
            notes="Task notes",
            tags=["work", "important"]
        )
        
        result = manager.create_task("list-1", task)
        
        assert result is not None
        call_kwargs = mock_gateway.create_reminder.call_args[1]
        assert 'notes' in call_kwargs
        assert 'tags' in call_kwargs
    
    def test_create_task_gateway_failure(self):
        """Test handling of gateway failures during creation."""
        mock_gateway = Mock(spec=RemindersGateway)
        mock_gateway.create_reminder.return_value = None  # Failure
        
        manager = RemindersTaskManager(gateway=mock_gateway)
        
        task = RemindersTask(
            uuid="temp",
            item_id=None,
            calendar_id="list-1",
            list_name="Work",
            status=TaskStatus.TODO,
            title="Failed task"
        )
        
        result = manager.create_task("list-1", task)
        
        assert result is None
    
    def test_create_task_gateway_exception(self):
        """Test handling of gateway exceptions during creation."""
        mock_gateway = Mock(spec=RemindersGateway)
        mock_gateway.create_reminder.side_effect = Exception("EventKit error")
        
        manager = RemindersTaskManager(gateway=mock_gateway)
        
        task = RemindersTask(
            uuid="temp",
            item_id=None,
            calendar_id="list-1",
            list_name="Work",
            status=TaskStatus.TODO,
            title="Exception task"
        )
        
        result = manager.create_task("list-1", task)
        
        # Should handle exception gracefully
        assert result is None


class TestRemindersTaskManagerDelete:
    """Test suite for RemindersTaskManager.delete_task()."""
    
    def test_delete_task_success(self):
        """Test successful task deletion."""
        mock_gateway = Mock(spec=RemindersGateway)
        mock_gateway.delete_reminder.return_value = True
        
        manager = RemindersTaskManager(gateway=mock_gateway)
        
        task = RemindersTask(
            uuid="task-to-delete",
            item_id="rem-1",
            calendar_id="list-1",
            list_name="Work",
            status=TaskStatus.TODO,
            title="Delete me"
        )
        
        result = manager.delete_task(task)
        
        assert result is True
        mock_gateway.delete_reminder.assert_called_once_with("task-to-delete")
    
    def test_delete_task_failure(self):
        """Test handling of deletion failures."""
        mock_gateway = Mock(spec=RemindersGateway)
        mock_gateway.delete_reminder.return_value = False
        
        manager = RemindersTaskManager(gateway=mock_gateway)
        
        task = RemindersTask(
            uuid="task-uuid",
            item_id="rem-1",
            calendar_id="list-1",
            list_name="Work",
            status=TaskStatus.TODO,
            title="Failed delete"
        )
        
        result = manager.delete_task(task)
        
        assert result is False
    
    def test_delete_task_gateway_exception(self):
        """Test handling of gateway exceptions during deletion."""
        mock_gateway = Mock(spec=RemindersGateway)
        mock_gateway.delete_reminder.side_effect = Exception("EventKit error")
        
        manager = RemindersTaskManager(gateway=mock_gateway)
        
        task = RemindersTask(
            uuid="task-uuid",
            item_id="rem-1",
            calendar_id="list-1",
            list_name="Work",
            status=TaskStatus.TODO,
            title="Exception delete"
        )
        
        result = manager.delete_task(task)
        
        # Should handle exception and return False
        assert result is False
    
    def test_delete_nonexistent_task(self):
        """Test deleting a task that doesn't exist."""
        mock_gateway = Mock(spec=RemindersGateway)
        mock_gateway.delete_reminder.return_value = False
        
        manager = RemindersTaskManager(gateway=mock_gateway)
        
        task = RemindersTask(
            uuid="nonexistent",
            item_id=None,
            calendar_id="list-1",
            list_name="Work",
            status=TaskStatus.TODO,
            title="Ghost task"
        )
        
        result = manager.delete_task(task)
        
        assert result is False


class TestRemindersTaskManagerList:
    """Test suite for RemindersTaskManager.list_tasks() edge cases."""
    
    def test_list_tasks_gateway_exception(self):
        """Test handling of gateway exceptions during listing."""
        mock_gateway = Mock(spec=RemindersGateway)
        mock_gateway.get_reminders.side_effect = Exception("EventKit error")
        
        manager = RemindersTaskManager(gateway=mock_gateway)
        
        # Should handle exception gracefully
        result = manager.list_tasks()
        
        assert result == [] or result is None
    
    def test_list_tasks_with_completion_filtering(self):
        """Test that include_completed parameter works."""
        mock_gateway = Mock(spec=RemindersGateway)
        mock_gateway.get_reminders.return_value = [
            ReminderData(
                uuid="1",
                title="Todo",
                completed=False,
                list_id="list-1",
                list_name="Work",
                created_at=datetime.now(timezone.utc).isoformat(),
                modified_at=datetime.now(timezone.utc).isoformat()
            ),
            ReminderData(
                uuid="2",
                title="Done",
                completed=True,
                list_id="list-1",
                list_name="Work",
                created_at=datetime.now(timezone.utc).isoformat(),
                modified_at=datetime.now(timezone.utc).isoformat()
            )
        ]
        
        manager = RemindersTaskManager(gateway=mock_gateway)
        
        # List with completed tasks
        all_tasks = manager.list_tasks(include_completed=True)
        assert len(all_tasks) >= 2
        
        # List without completed tasks
        todo_tasks = manager.list_tasks(include_completed=False)
        assert len(todo_tasks) >= 1
        assert all(task.status == TaskStatus.TODO for task in todo_tasks)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
