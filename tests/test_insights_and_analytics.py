"""
Unit tests for insights, analytics, and hygiene features.

Tests cover:
- Streak tracking (recording, calculating, cleanup)
- Insight aggregation and formatting
- Hygiene analysis (stagnant, overdue, missing due dates)
- Daily note snapshot injection
"""

import sys
import tempfile
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

from obs_sync.analytics.streaks import StreakTracker
from obs_sync.analytics.hygiene import HygieneAnalyzer
from obs_sync.utils.insights import (
    aggregate_insights,
    format_insight_snapshot_markdown,
    format_insight_cli_summary,
    format_hygiene_report_cli,
    INSIGHT_SECTION_START,
    INSIGHT_SECTION_END
)
from obs_sync.core.models import RemindersTask, TaskStatus, Priority
from obs_sync.calendar.daily_notes import DailyNoteManager
from obs_sync.reminders.tasks import RemindersTaskManager
from obs_sync.reminders.gateway import ReminderData
import traceback


def test_streak_tracking():
    """Test streak recording and calculation."""
    print("\n=== Test: Streak Tracking ===")
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        tracker = StreakTracker(data_path=f.name)
        
        # Record completions for consecutive days
        vault_id = "test-vault"
        today = date.today()
        
        # Day 1: Complete 3 tasks with #work tag
        tracker.record_completions(
            vault_id=vault_id,
            target_date=today - timedelta(days=2),
            by_tag={"work": 3},
            by_list={"Work Tasks": 3}
        )
        
        # Day 2: Complete 2 tasks with #work tag
        tracker.record_completions(
            vault_id=vault_id,
            target_date=today - timedelta(days=1),
            by_tag={"work": 2},
            by_list={"Work Tasks": 2}
        )
        
        # Day 3: Complete 1 task with #work tag
        tracker.record_completions(
            vault_id=vault_id,
            target_date=today,
            by_tag={"work": 1},
            by_list={"Work Tasks": 1}
        )
        
        # Check streak
        work_streak = tracker.get_streak(vault_id, "work", "tags")
        print(f"Work tag streak: current={work_streak['current']}, best={work_streak['best']}")
        
        assert work_streak['current'] >= 1, "Should have at least 1-day current streak"
        assert work_streak['best'] >= 1, "Should have at least 1-day best streak"
        
        # Get all active streaks
        all_streaks = tracker.get_all_streaks(vault_id, min_current=1)
        print(f"Active streaks: {len(all_streaks)}")
        assert len(all_streaks) >= 1, "Should have at least one active streak"
        
        # Cleanup old data
        tracker.cleanup_old_data(days_to_keep=30)
        
        print("✓ Streak tracking tests passed")
        
        # Cleanup
        Path(f.name).unlink()


def test_reminders_task_update_captures_completion_date():
    """Test that update_task captures completion_date when status flips to DONE."""
    print("\n=== Test: Update Task Captures Completion Date ===")
    
    from unittest.mock import Mock
    
    # Mock gateway
    mock_gateway = Mock()
    mock_gateway.update_reminder.return_value = True
    
    manager = RemindersTaskManager(gateway=mock_gateway)
    
    # Create a task that's currently TODO
    task = RemindersTask(
        uuid="task-1",
        item_id="item-1",
        calendar_id="cal-1",
        list_name="Work",
        status=TaskStatus.TODO,
        title="Test task",
        due_date=None,
        priority=None,
        notes="",
        tags=[],
        created_at=datetime.now(timezone.utc),
        modified_at=datetime.now(timezone.utc),
        completion_date=None
    )
    
    # Verify task has no completion_date initially
    assert task.completion_date is None, "Task should not have completion_date initially"
    
    # Update task to mark it as DONE
    updated_task = manager.update_task(task, {"status": TaskStatus.DONE})
    
    # Verify completion_date was captured
    assert updated_task is not None, "Update should succeed"
    assert updated_task.status == TaskStatus.DONE, "Task should be marked as done"
    assert updated_task.completion_date is not None, "completion_date should be captured"
    assert updated_task.completion_date == datetime.now(timezone.utc).date(), "completion_date should be today"
    assert isinstance(updated_task.modified_at, datetime), "modified_at should be datetime object"
    
    print(f"✓ Task marked as DONE captures completion_date: {updated_task.completion_date}")
    print(f"✓ modified_at is datetime object: {type(updated_task.modified_at)}")
    print("✓ Update task completion date capture tests passed")


def test_reminders_task_completion_date():
    """Test that RemindersTask.completion_date is populated from modified_at for completed tasks."""
    print("\n=== Test: RemindersTask Completion Date ===")
    
    from unittest.mock import Mock
    
    # Mock gateway that returns ReminderData with ISO timestamp strings
    mock_gateway = Mock()
    
    completed_time = datetime.now(timezone.utc) - timedelta(hours=2)
    completed_iso = completed_time.isoformat()
    
    mock_gateway.get_reminders.return_value = [
        ReminderData(
            uuid="completed-task-1",
            title="Completed task",
            completed=True,
            due_date="2025-01-10",
            priority=None,
            notes="",
            tags=[],
            list_id="list-1",
            list_name="Work",
            created_at=(datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
            modified_at=completed_iso
        ),
        ReminderData(
            uuid="todo-task-1",
            title="Todo task",
            completed=False,
            due_date="2025-01-15",
            priority=None,
            notes="",
            tags=[],
            list_id="list-1",
            list_name="Work",
            created_at=datetime.now(timezone.utc).isoformat(),
            modified_at=datetime.now(timezone.utc).isoformat()
        )
    ]
    
    manager = RemindersTaskManager(gateway=mock_gateway)
    tasks = manager.list_tasks()
    
    # Find the completed task
    completed_task = next(t for t in tasks if t.uuid == "completed-task-1")
    todo_task = next(t for t in tasks if t.uuid == "todo-task-1")
    
    # Check that completed task has completion_date set to modified_at.date()
    assert completed_task.status == TaskStatus.DONE, "Task should be marked as done"
    assert completed_task.completion_date is not None, "Completed task should have completion_date"
    assert completed_task.completion_date == completed_time.date(), "completion_date should match modified_at date"
    
    # Check that todo task does NOT have completion_date
    assert todo_task.status == TaskStatus.TODO, "Task should be marked as todo"
    assert todo_task.completion_date is None, "Todo task should not have completion_date"
    
    # Check that created_at and modified_at are datetime objects, not strings
    assert isinstance(completed_task.created_at, datetime), "created_at should be datetime object"
    assert isinstance(completed_task.modified_at, datetime), "modified_at should be datetime object"
    assert isinstance(todo_task.created_at, datetime), "created_at should be datetime object"
    assert isinstance(todo_task.modified_at, datetime), "modified_at should be datetime object"
    
    print(f"✓ Completed task has completion_date: {completed_task.completion_date}")
    print(f"✓ Todo task has no completion_date: {todo_task.completion_date}")
    print(f"✓ Timestamp fields are datetime objects, not strings")
    print("✓ RemindersTask completion_date tests passed")


def test_reminders_task_from_dict_parses_timestamps():
    """Test that RemindersTask.from_dict properly parses ISO timestamps to datetime objects."""
    print("\n=== Test: RemindersTask from_dict Timestamp Parsing ===")
    
    # Create test data dict with ISO timestamp strings
    test_time = datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    data = {
        "uuid": "task-1",
        "external_ids": {"item": "item-1", "calendar": "cal-1"},
        "list": {"name": "Work"},
        "status": "done",
        "description": "Test task",
        "due": "2025-01-20",
        "priority": None,
        "notes": "Test notes",
        "tags": ["work"],
        "created_at": test_time.isoformat(),
        "updated_at": (test_time + timedelta(hours=2)).isoformat(),
        "completion_date": "2025-01-15"
    }
    
    # Parse from dict
    task = RemindersTask.from_dict(data)
    
    # Verify timestamps are parsed to datetime objects
    assert isinstance(task.created_at, datetime), "created_at should be datetime object"
    assert isinstance(task.modified_at, datetime), "modified_at should be datetime object"
    assert task.created_at == test_time, "created_at should match original time"
    assert task.modified_at == test_time + timedelta(hours=2), "modified_at should match original time"
    assert task.completion_date == date(2025, 1, 15), "completion_date should be parsed correctly"
    
    # Test backwards compatibility with datetime objects
    data_with_datetime = data.copy()
    data_with_datetime["created_at"] = test_time
    data_with_datetime["updated_at"] = test_time + timedelta(hours=2)
    
    task2 = RemindersTask.from_dict(data_with_datetime)
    assert isinstance(task2.created_at, datetime), "Should handle datetime objects"
    assert task2.created_at == test_time, "Should preserve datetime values"
    
    # Test to_dict serialization
    serialized = task.to_dict()
    assert isinstance(serialized["created_at"], str), "to_dict should serialize to ISO string"
    assert serialized["created_at"] == test_time.isoformat(), "Should serialize correctly"
    
    print(f"✓ from_dict parses ISO strings to datetime: {type(task.created_at)}")
    print(f"✓ from_dict handles datetime objects: {type(task2.created_at)}")
    print(f"✓ to_dict serializes to ISO strings: {type(serialized['created_at'])}")
    print("✓ RemindersTask timestamp parsing tests passed")


def test_streak_recording_per_completion_date():
    """Test that streak recording logs completions for the actual completion date, not aggregated."""
    print("\n=== Test: Streak Recording Per Completion Date ===")
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        tracker = StreakTracker(data_path=f.name)
        vault_id = "test-vault"
        today = date.today()
        
        # Simulate the new behavior: record completions for specific dates
        # Day 1: 2 completions
        tracker.record_completions(
            vault_id=vault_id,
            target_date=today - timedelta(days=2),
            by_tag={"work": 2},
            by_list={"Work": 2}
        )
        
        # Day 2: 1 completion
        tracker.record_completions(
            vault_id=vault_id,
            target_date=today - timedelta(days=1),
            by_tag={"work": 1},
            by_list={"Work": 1}
        )
        
        # Day 3 (today): 3 completions
        tracker.record_completions(
            vault_id=vault_id,
            target_date=today,
            by_tag={"work": 3},
            by_list={"Work": 3}
        )
        
        # Load raw data to verify per-day recording
        with open(f.name, 'r') as data_file:
            raw_data = json.load(data_file)
        
        # Verify each day has its own entry
        work_tag_data = raw_data[vault_id]["tags"]["work"]
        date_keys = sorted(work_tag_data.keys())
        
        assert len(date_keys) == 3, f"Should have 3 separate date entries, got {len(date_keys)}"
        assert work_tag_data[(today - timedelta(days=2)).isoformat()] == 2, "Day 1 should have 2 completions"
        assert work_tag_data[(today - timedelta(days=1)).isoformat()] == 1, "Day 2 should have 1 completion"
        assert work_tag_data[today.isoformat()] == 3, "Day 3 should have 3 completions"
        
        print(f"✓ Each completion date has separate entry: {date_keys}")
        print(f"✓ Counts preserved per date: day1=2, day2=1, day3=3")
        print("✓ Streak recording per-date tests passed")
        
        # Cleanup
        Path(f.name).unlink()


def test_hygiene_analysis():
    """Test hygiene analyzer for stagnant, overdue, and missing-due tasks."""
    print("\n=== Test: Hygiene Analysis ===")
    
    analyzer = HygieneAnalyzer(stagnant_threshold_days=14)
    
    today = date.today()
    
    # Create test tasks
    tasks = [
        # Stagnant task (created 20 days ago, no due date)
        RemindersTask(
            uuid="stagnant-1",
            item_id="item-1",
            calendar_id="cal-1",
            list_name="Tasks",
            status=TaskStatus.TODO,
            title="Old task without due date",
            due_date=None,
            priority=None,
            notes="",
            tags=[],
            created_at=datetime.now(timezone.utc) - timedelta(days=20),
            modified_at=datetime.now(timezone.utc) - timedelta(days=20)
        ),
        
        # Overdue task
        RemindersTask(
            uuid="overdue-1",
            item_id="item-2",
            calendar_id="cal-1",
            list_name="Tasks",
            status=TaskStatus.TODO,
            title="Overdue task",
            due_date=today - timedelta(days=5),
            priority=Priority.HIGH,
            notes="",
            tags=[],
            created_at=datetime.now(timezone.utc) - timedelta(days=10),
            modified_at=datetime.now(timezone.utc) - timedelta(days=10)
        ),
        
        # Task missing due date (recent)
        RemindersTask(
            uuid="no-due-1",
            item_id="item-3",
            calendar_id="cal-1",
            list_name="Tasks",
            status=TaskStatus.TODO,
            title="Recent task without due date",
            due_date=None,
            priority=None,
            notes="",
            tags=[],
            created_at=datetime.now(timezone.utc) - timedelta(days=2),
            modified_at=datetime.now(timezone.utc) - timedelta(days=2)
        ),
        
        # Healthy task (has due date in future)
        RemindersTask(
            uuid="healthy-1",
            item_id="item-4",
            calendar_id="cal-1",
            list_name="Tasks",
            status=TaskStatus.TODO,
            title="Upcoming task",
            due_date=today + timedelta(days=7),
            priority=None,
            notes="",
            tags=[],
            created_at=datetime.now(timezone.utc),
            modified_at=datetime.now(timezone.utc)
        ),
        
        # Completed task (should be ignored)
        RemindersTask(
            uuid="done-1",
            item_id="item-5",
            calendar_id="cal-1",
            list_name="Tasks",
            status=TaskStatus.DONE,
            title="Completed task",
            due_date=today - timedelta(days=1),
            priority=None,
            notes="",
            tags=[],
            created_at=datetime.now(timezone.utc) - timedelta(days=5),
            modified_at=datetime.now(timezone.utc)
        ),
    ]
    
    # Analyze
    analysis = analyzer.analyze(tasks)
    
    stagnant = analysis['stagnant']
    overdue = analysis['overdue']
    missing_due = analysis['missing_due']
    
    print(f"Stagnant tasks: {len(stagnant)}")
    print(f"Overdue tasks: {len(overdue)}")
    print(f"Missing due dates: {len(missing_due)}")
    
    assert len(stagnant) >= 1, "Should detect at least one stagnant task"
    assert len(overdue) == 1, "Should detect exactly one overdue task"
    assert len(missing_due) >= 1, "Should detect at least one task without due date"
    
    # Test suggestions
    suggestions = analyzer.get_actionable_suggestions(analysis, max_suggestions=5)
    print(f"Generated {len(suggestions)} suggestions")
    assert len(suggestions) > 0, "Should generate at least one suggestion"
    
    print("✓ Hygiene analysis tests passed")


def test_insight_aggregation():
    """Test insight aggregation across multiple vaults."""
    print("\n=== Test: Insight Aggregation ===")
    
    vault_insights = [
        {
            "completions": 5,
            "overdue": 2,
            "new_tasks": 3,
            "by_list": {
                "Work": {"completions": 3, "overdue": 1, "new_tasks": 2},
                "Personal": {"completions": 2, "overdue": 1, "new_tasks": 1}
            },
            "by_tag": {
                "urgent": {"completions": 2, "overdue": 1, "new_tasks": 0}
            }
        },
        {
            "completions": 3,
            "overdue": 1,
            "new_tasks": 2,
            "by_list": {
                "Work": {"completions": 2, "overdue": 1, "new_tasks": 1},
                "Shopping": {"completions": 1, "overdue": 0, "new_tasks": 1}
            },
            "by_tag": {
                "urgent": {"completions": 1, "overdue": 0, "new_tasks": 1}
            }
        }
    ]
    
    combined = aggregate_insights(vault_insights)
    
    print(f"Total completions: {combined['completions']}")
    print(f"Total overdue: {combined['overdue']}")
    print(f"Total new tasks: {combined['new_tasks']}")
    
    assert combined['completions'] == 8, "Should sum completions correctly"
    assert combined['overdue'] == 3, "Should sum overdue correctly"
    assert combined['new_tasks'] == 5, "Should sum new tasks correctly"
    
    assert combined['by_list']['Work']['completions'] == 5, "Should merge list stats"
    assert combined['by_tag']['urgent']['completions'] == 3, "Should merge tag stats"
    
    print("✓ Insight aggregation tests passed")


def test_symmetric_new_task_counting():
    """Test that new tasks are counted from both Obsidian and Reminders."""
    print("\n=== Test: Symmetric New Task Counting ===\n")
    
    # Simulate insights data that would come from engine
    # Engine should count both created_rem_task_ids and created_obs_task_ids
    
    insights_with_rem_only = {
        "completions": 0,
        "overdue": 0,
        "new_tasks": 3,  # 3 new Reminders tasks
        "by_list": {
            "Work": {"completions": 0, "overdue": 0, "new_tasks": 3}
        },
        "by_tag": {}
    }
    
    insights_with_obs_only = {
        "completions": 0,
        "overdue": 0,
        "new_tasks": 2,  # 2 new Obsidian tasks
        "by_list": {
            "Personal": {"completions": 0, "overdue": 0, "new_tasks": 2}
        },
        "by_tag": {
            "urgent": {"completions": 0, "overdue": 0, "new_tasks": 2}
        }
    }
    
    insights_with_both = {
        "completions": 0,
        "overdue": 0,
        "new_tasks": 5,  # 3 Reminders + 2 Obsidian
        "by_list": {
            "Work": {"completions": 0, "overdue": 0, "new_tasks": 3},
            "Personal": {"completions": 0, "overdue": 0, "new_tasks": 2}
        },
        "by_tag": {
            "urgent": {"completions": 0, "overdue": 0, "new_tasks": 2}
        }
    }
    
    # Aggregate all scenarios
    combined = aggregate_insights([insights_with_rem_only, insights_with_obs_only, insights_with_both])
    
    # Should sum correctly across all vaults
    assert combined['new_tasks'] == 10, f"Should count 10 total new tasks (3+2+5), got {combined['new_tasks']}"
    assert combined['by_list']['Work']['new_tasks'] == 6, "Should sum Work list new tasks"
    assert combined['by_list']['Personal']['new_tasks'] == 4, "Should sum Personal list new tasks"
    assert combined['by_tag']['urgent']['new_tasks'] == 4, "Should sum urgent tag new tasks"
    
    print(f"✓ Total new tasks counted correctly: {combined['new_tasks']}")
    print(f"✓ By-list breakdown correct: Work={combined['by_list']['Work']['new_tasks']}, Personal={combined['by_list']['Personal']['new_tasks']}")
    print(f"✓ By-tag breakdown correct: urgent={combined['by_tag']['urgent']['new_tasks']}")
    print("✓ Symmetric new task counting tests passed")


def test_insight_formatting():
    """Test insight formatting for markdown and CLI."""
    print("\n=== Test: Insight Formatting ===")
    
    insights = {
        "completions": 10,
        "overdue": 3,
        "new_tasks": 5,
        "by_list": {
            "Work": {"completions": 6, "overdue": 2, "new_tasks": 3},
            "Personal": {"completions": 4, "overdue": 1, "new_tasks": 2}
        },
        "by_tag": {
            "urgent": {"completions": 3, "overdue": 1, "new_tasks": 1}
        }
    }
    
    streaks = {
        "tag:work": {"current": 5, "best": 10},
        "list:Work": {"current": 3, "best": 7}
    }
    
    # Test markdown formatting
    markdown = format_insight_snapshot_markdown(insights, streaks, "2025-01-15")
    assert INSIGHT_SECTION_START in markdown, "Should include section start marker"
    assert INSIGHT_SECTION_END in markdown, "Should include section end marker"
    assert "Completed**: 10" in markdown, "Should include completion count"
    assert "Momentum Streaks" in markdown, "Should include streaks section"
    print("✓ Markdown formatting works")
    
    # Test CLI formatting
    cli_output = format_insight_cli_summary(insights)
    assert "TASK INSIGHTS" in cli_output, "Should include header"
    assert "10" in cli_output, "Should include completions"
    print("✓ CLI formatting works")
    
    print("✓ Insight formatting tests passed")


def test_daily_note_injection():
    """Test daily note insight snapshot injection."""
    print("\n=== Test: Daily Note Injection ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir)
        daily_notes_dir = vault_path / "01-Daily-Notes"
        daily_notes_dir.mkdir()
        
        manager = DailyNoteManager(str(vault_path))
        
        insights = {
            "completions": 5,
            "overdue": 2,
            "new_tasks": 3,
            "by_list": {"Work": {"completions": 5, "overdue": 2, "new_tasks": 3}},
            "by_tag": {}
        }
        
        today = date.today()
        
        # First injection
        note_path = manager.update_insights_section(today, insights)
        assert Path(note_path).exists(), "Should create daily note"
        
        with open(note_path, 'r') as f:
            content = f.read()
        
        assert INSIGHT_SECTION_START in content, "Should include insights section"
        assert "Completed**: 5" in content, "Should include data"
        assert content.rstrip().endswith(INSIGHT_SECTION_END), "Insights should be last section"
        
        # Second injection (should replace, not duplicate)
        insights['completions'] = 8
        manager.update_insights_section(today, insights)
        
        with open(note_path, 'r') as f:
            content = f.read()
        
        # Check that section appears only once
        count = content.count(INSIGHT_SECTION_START)
        assert count == 1, f"Insights section should appear exactly once, found {count}"
        assert "Completed**: 8" in content, "Should update with new data"
        assert content.rstrip().endswith(INSIGHT_SECTION_END), "Insights should remain last after replacement"
        
        print("✓ Daily note injection tests passed")


def run_all_tests():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("Running Insights and Analytics Tests")
    print("=" * 60)
    
    try:
        test_reminders_task_update_captures_completion_date()
        test_reminders_task_completion_date()
        test_reminders_task_from_dict_parses_timestamps()
        test_streak_recording_per_completion_date()
        test_streak_tracking()
        test_hygiene_analysis()
        test_insight_aggregation()
        test_symmetric_new_task_counting()
        test_insight_formatting()
        test_daily_note_injection()
        
        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
        return True
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
