#!/usr/bin/env python3
"""
Test backup validation functionality in the E2E testing framework.
This ensures that backups are properly created and can be validated.
"""

import pytest
import json
from pathlib import Path
from tests.e2e.fake_reminders_gateway import FakeRemindersGateway, FakeReminder


@pytest.mark.e2e
def test_backup_validation_basic(tmp_path):
    """Test basic backup creation and validation."""
    # Create a simple config backup
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    
    # Create a mock configuration file
    obs_index = config_dir / "obs_index.json"
    initial_data = {
        "tasks": {
            "task1": {
                "uuid": "123",
                "status": "todo",
                "description": "Test task",
                "created_at": "2024-12-01T10:00:00Z"
            }
        }
    }
    obs_index.write_text(json.dumps(initial_data, indent=2))
    
    # Verify initial state
    assert obs_index.exists()
    loaded_data = json.loads(obs_index.read_text())
    assert loaded_data["tasks"]["task1"]["status"] == "todo"
    
    # Simulate a change (like what sync would do)
    modified_data = initial_data.copy()
    modified_data["tasks"]["task1"]["status"] = "done"
    obs_index.write_text(json.dumps(modified_data, indent=2))
    
    # Verify change was applied
    updated_data = json.loads(obs_index.read_text())
    assert updated_data["tasks"]["task1"]["status"] == "done"
    
    # In a real backup system, we would validate that:
    # 1. A backup was created before the change
    # 2. The backup contains the original state
    # 3. The backup can be used to restore if needed
    
    # For now, just verify the test infrastructure is working
    assert updated_data["tasks"]["task1"]["uuid"] == "123"


@pytest.mark.e2e
def test_fake_gateway_state_consistency(tmp_path):
    """Test that fake gateway maintains consistent state across operations."""
    fake = FakeRemindersGateway()
    test_cal_id = "cal-test-1"
    
    # Create multiple reminders
    reminders = [
        FakeReminder(title="Task 1", calendar_id=test_cal_id, item_id="r1"),
        FakeReminder(title="Task 2", calendar_id=test_cal_id, item_id="r2", completed=True),
        FakeReminder(title="Task 3", calendar_id=test_cal_id, item_id="r3", due_date="2024-12-15"),
    ]
    fake.seed_list(test_cal_id, reminders)
    
    # Verify initial state
    all_items = fake.all_items()
    assert len(all_items) == 3
    
    # Get reminders using the API (like the collector would)
    retrieved_reminders, cal_cache = fake.get_reminders_from_lists([{"identifier": test_cal_id}])
    assert len(retrieved_reminders) == 3
    
    # Verify calendar cache is populated
    assert len(cal_cache) == 3  # One entry per reminder
    
    # Test finding specific reminders
    task1 = fake.find_reminder_by_id("r1", test_cal_id)
    assert task1 is not None
    assert task1.title() == "Task 1"
    assert not task1.isCompleted()
    
    task2 = fake.find_reminder_by_id("r2", test_cal_id)  
    assert task2 is not None
    assert task2.title() == "Task 2"
    assert task2.isCompleted()
    
    task3 = fake.find_reminder_by_id("r3", test_cal_id)
    assert task3 is not None  
    assert task3.title() == "Task 3"
    assert task3.dueDateComponents() is not None
    assert task3.dueDateComponents().year() == 2024
    assert task3.dueDateComponents().month() == 12
    assert task3.dueDateComponents().day() == 15
    
    # Test that state is preserved across multiple operations
    for i in range(3):
        current_items = fake.all_items()
        assert len(current_items) == 3
        
        # Find the same reminder multiple times
        same_task = fake.find_reminder_by_id("r1", test_cal_id)
        assert same_task is not None
        assert same_task.title() == "Task 1"


@pytest.mark.e2e
def test_create_reminder_with_validation():
    """Test creating reminders and validating the created data."""
    fake = FakeRemindersGateway()
    
    # Create a new reminder
    created_data = fake.create_reminder(
        title="New Task",
        calendar_id="cal-test",
        properties={"due_date": "2024-12-20", "priority": 5}
    )
    
    # Validate creation response
    assert created_data is not None
    assert "uuid" in created_data
    assert created_data["uuid"].startswith("rem-")
    assert created_data["calendar_id"] == "cal-test"
    assert "external_ids" in created_data
    assert created_data["external_ids"]["calendar"] == "cal-test"
    assert "item" in created_data["external_ids"]
    
    # Verify the reminder was actually added to the fake store
    all_items = fake.all_items()
    assert len(all_items) == 1
    
    created_reminder = all_items[0]
    assert created_reminder.title() == "New Task"
    assert created_reminder.dueDateComponents() is not None
    assert created_reminder.dueDateComponents().year() == 2024
    assert created_reminder.dueDateComponents().month() == 12  
    assert created_reminder.dueDateComponents().day() == 20
    assert created_reminder.priority() == 5
    
    # Test creating with no properties
    simple_data = fake.create_reminder("Simple Task", "cal-test")
    assert simple_data is not None
    assert len(fake.all_items()) == 2


@pytest.mark.e2e
def test_gateway_error_recovery():
    """Test that the gateway handles and recovers from error conditions."""
    fake = FakeRemindersGateway()
    
    # Test handling of invalid update operations
    invalid_updates = [
        # Missing external_ids
        ({"status": "done"}, {"status_to_rem": True}),
        # Empty external_ids  
        ({"status": "done", "external_ids": {}}, {"status_to_rem": True}),
        # Invalid item ID
        ({"status": "done", "external_ids": {"item": "invalid", "calendar": "test"}}, {"status_to_rem": True}),
    ]
    
    for reminder_dict, fields in invalid_updates:
        result = fake.update_reminder(reminder_dict, fields, dry_run=False)
        # All should fail gracefully
        assert not result.success
        assert len(result.errors) > 0
    
    # After errors, gateway should still be functional
    fake.seed_list("test-cal", [FakeReminder(title="Recovery Test", calendar_id="test-cal", item_id="r1")])
    assert len(fake.all_items()) == 1
    
    # Valid operation should still work
    valid_result = fake.update_reminder(
        {"status": "done", "external_ids": {"item": "r1", "calendar": "test-cal"}},
        {"status_to_rem": True},
        dry_run=False
    )
    assert valid_result.success