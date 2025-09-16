#!/usr/bin/env python3
"""
Test edge cases and error conditions for the fake reminders gateway.
This ensures the fake gateway properly emulates error scenarios
that might occur in the real EventKit integration.
"""

import pytest
from tests.e2e.fake_reminders_gateway import FakeRemindersGateway, FakeReminder


@pytest.mark.e2e
def test_fake_gateway_reminder_not_found():
    """Test error handling when reminder is not found."""
    fake = FakeRemindersGateway()
    
    # Try to update a non-existent reminder
    reminder_dict = {
        "status": "done",
        "external_ids": {"item": "nonexistent", "calendar": "test"}
    }
    
    fields = {"status_to_rem": True}
    
    result = fake.update_reminder(reminder_dict, fields, dry_run=False)
    
    assert not result.success
    assert "not found" in result.errors
    assert len(result.changes_applied) == 0
    assert result.reminder_id == "nonexistent"


@pytest.mark.e2e 
def test_fake_gateway_missing_item_id():
    """Test error handling when item ID is missing."""
    fake = FakeRemindersGateway()
    
    # Try to update without item ID
    reminder_dict = {
        "status": "done", 
        "external_ids": {}  # Missing item ID
    }
    
    fields = {"status_to_rem": True}
    
    result = fake.update_reminder(reminder_dict, fields, dry_run=False)
    
    assert not result.success
    assert "no id" in result.errors
    assert len(result.changes_applied) == 0


@pytest.mark.e2e
def test_fake_gateway_dry_run_mode():
    """Test that dry run mode doesn't actually modify reminders."""
    fake = FakeRemindersGateway()
    test_cal_id = "cal-test-1"
    
    # Create reminder
    reminder = FakeReminder(title="Test Task", calendar_id=test_cal_id, item_id="r1")
    fake.seed_list(test_cal_id, [reminder])
    
    assert not reminder.isCompleted()
    
    # Update in dry run mode
    reminder_dict = {
        "status": "done",
        "external_ids": {"item": "r1", "calendar": test_cal_id}
    }
    
    fields = {"status_to_rem": True}
    
    result = fake.update_reminder(reminder_dict, fields, dry_run=True)
    
    # Should report success and changes, but not actually modify
    assert result.success
    assert len(result.changes_applied) == 1
    assert result.changes_applied[0].field == "status"
    assert result.changes_applied[0].old_value == "todo"
    assert result.changes_applied[0].new_value == "done"
    
    # But reminder should not actually be changed
    assert not reminder.isCompleted()


@pytest.mark.e2e
def test_fake_gateway_no_changes_needed():
    """Test when no changes are needed (values already match)."""
    fake = FakeRemindersGateway()
    test_cal_id = "cal-test-1"
    
    # Create already-completed reminder
    reminder = FakeReminder(title="Already Done", calendar_id=test_cal_id, 
                          item_id="r1", completed=True)
    fake.seed_list(test_cal_id, [reminder])
    
    # Try to set it to done (already is done)
    reminder_dict = {
        "status": "done",
        "external_ids": {"item": "r1", "calendar": test_cal_id}
    }
    
    fields = {"status_to_rem": True}
    
    result = fake.update_reminder(reminder_dict, fields, dry_run=False)
    
    # Should succeed but report no changes
    assert result.success
    assert len(result.changes_applied) == 0
    assert len(result.errors) == 0


@pytest.mark.e2e
def test_fake_gateway_multiple_field_updates():
    """Test updating multiple fields at once."""
    fake = FakeRemindersGateway()
    test_cal_id = "cal-test-1"
    
    # Create reminder with some initial values
    reminder = FakeReminder(title="Multi Update", calendar_id=test_cal_id,
                          item_id="r1", due_date="2024-12-01", priority=9)
    fake.seed_list(test_cal_id, [reminder])
    
    # Update multiple fields
    reminder_dict = {
        "status": "done",
        "due": "2024-12-15",
        "priority": "high",
        "external_ids": {"item": "r1", "calendar": test_cal_id}
    }
    
    fields = {
        "status_to_rem": True,
        "due_to_rem": True, 
        "priority_to_rem": True
    }
    
    result = fake.update_reminder(reminder_dict, fields, dry_run=False)
    
    # Should succeed and apply all changes
    assert result.success
    assert len(result.changes_applied) == 3
    
    change_fields = [c.field for c in result.changes_applied]
    assert "status" in change_fields
    assert "due" in change_fields
    assert "priority" in change_fields
    
    # Verify actual changes
    assert reminder.isCompleted() is True
    assert reminder.dueDateComponents().year() == 2024
    assert reminder.dueDateComponents().month() == 12
    assert reminder.dueDateComponents().day() == 15
    assert reminder.priority() == 1  # high priority maps to 1


@pytest.mark.e2e
def test_fake_gateway_date_components_edge_cases():
    """Test date components handling with edge cases."""
    fake = FakeRemindersGateway()
    test_cal_id = "cal-test-1"
    
    # Create reminder
    reminder = FakeReminder(title="Date Test", calendar_id=test_cal_id, item_id="r1")
    fake.seed_list(test_cal_id, [reminder])
    
    # Test clearing due date (set to None)
    reminder_dict = {
        "due": None,
        "external_ids": {"item": "r1", "calendar": test_cal_id}
    }
    
    fields = {"due_to_rem": True}
    
    result = fake.update_reminder(reminder_dict, fields, dry_run=False)
    
    assert result.success
    assert reminder.dueDateComponents() is None