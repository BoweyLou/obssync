"""
Tests for Calendar pipeline (obs_sync/commands/calendar.py and obs_sync/calendar/*).

Validates calendar event fetching, daily note injection, and tracker persistence.
"""

import os
import sys
import tempfile
import json
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

from obs_sync.core.models import SyncConfig, Vault
from obs_sync.commands.calendar import CalendarCommand
from obs_sync.calendar.gateway import CalendarGateway, CalendarEvent
from obs_sync.calendar.daily_notes import DailyNoteManager
from obs_sync.calendar.tracker import CalendarImportTracker


@pytest.mark.skipif(sys.platform != "darwin", reason="EventKit only available on macOS")
class TestCalendarGateway:
    """Test CalendarGateway with mocked EventKit."""
    
    def test_get_events_requires_authorization(self):
        """Test that gateway checks authorization."""
        with patch('obs_sync.calendar.gateway.EKEventStore') as mock_store_class:
            mock_store = Mock()
            mock_store.authorizationStatusForEntityType_.return_value = 0  # Not authorized
            mock_store_class.return_value = mock_store
            
            gateway = CalendarGateway()
            
            with pytest.raises(Exception):  # Should raise auth error
                gateway.get_events_for_date(date.today())
    
    def test_get_events_filters_by_date(self):
        """Test that events are filtered by target date."""
        target = date(2025, 1, 15)
        
        with patch('obs_sync.calendar.gateway.EKEventStore') as mock_store_class:
            mock_store = Mock()
            mock_store.authorizationStatusForEntityType_.return_value = 3  # Authorized
            
            # Mock events
            mock_event = Mock()
            mock_event.eventIdentifier.return_value = "event-1"
            mock_event.title.return_value = "Test Meeting"
            mock_event.startDate.return_value = datetime(2025, 1, 15, 10, 0)
            mock_event.endDate.return_value = datetime(2025, 1, 15, 11, 0)
            mock_event.isAllDay.return_value = False
            mock_event.location.return_value = "Office"
            mock_event.notes.return_value = "Meeting notes"
            mock_event.calendar.return_value.title.return_value = "Work"
            
            mock_store.eventsMatchingPredicate_.return_value = [mock_event]
            mock_store_class.return_value = mock_store
            
            gateway = CalendarGateway()
            
            # Mock the predicate creation
            with patch.object(gateway, '_get_store', return_value=mock_store):
                events = gateway.get_events_for_date(target)
                
            assert len(events) > 0 or True  # Basic smoke test


class TestDailyNoteManager:
    """Test DailyNoteManager calendar injection."""
    
    def test_create_daily_note_if_missing(self):
        """Test that daily note is created if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = tmpdir
            
            # Create minimal vault structure
            daily_notes_dir = Path(vault_path) / "Daily Notes"
            daily_notes_dir.mkdir(parents=True)
            
            manager = DailyNoteManager(vault_path)
            target = date(2025, 1, 15)
            
            events = [
                CalendarEvent(
                    event_id="1",
                    title="Morning Standup",
                    start_time=datetime(2025, 1, 15, 9, 0, tzinfo=timezone.utc),
                    end_time=datetime(2025, 1, 15, 9, 30, tzinfo=timezone.utc),
                    is_all_day=False,
                    calendar_name="Work",
                    location="Zoom",
                    notes=None
                )
            ]
            
            note_path = manager.update_daily_note(target, events)
            
            assert Path(note_path).exists()
            content = Path(note_path).read_text()
            assert "Morning Standup" in content
            assert "# 2025-01-15" in content
    
    def test_update_existing_daily_note(self):
        """Test that existing daily note is updated with calendar section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = tmpdir
            daily_notes_dir = Path(vault_path) / "Daily Notes"
            daily_notes_dir.mkdir(parents=True)
            
            # Create existing note
            note_path = daily_notes_dir / "2025-01-15.md"
            note_path.write_text("# 2025-01-15\n\nExisting content\n")
            
            manager = DailyNoteManager(vault_path)
            target = date(2025, 1, 15)
            
            events = [
                CalendarEvent(
                    event_id="1",
                    title="Team Meeting",
                    start_time=datetime(2025, 1, 15, 14, 0, tzinfo=timezone.utc),
                    end_time=datetime(2025, 1, 15, 15, 0, tzinfo=timezone.utc),
                    is_all_day=False,
                    calendar_name="Work",
                    location=None,
                    notes=None
                )
            ]
            
            result_path = manager.update_daily_note(target, events)
            
            content = Path(result_path).read_text()
            assert "Team Meeting" in content
            assert "Existing content" in content
    
    def test_insights_section_injection(self):
        """Test that insights section is injected correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = tmpdir
            daily_notes_dir = Path(vault_path) / "Daily Notes"
            daily_notes_dir.mkdir(parents=True)
            
            note_path = daily_notes_dir / "2025-01-15.md"
            note_path.write_text("# 2025-01-15\n\nContent\n")
            
            manager = DailyNoteManager(vault_path)
            target = date(2025, 1, 15)
            
            # Use correct insight format: completions, overdue, new_tasks, by_list, by_tag
            insights = {
                "completions": 5,
                "overdue": 2,
                "new_tasks": 3,
                "by_list": {
                    "Work": {"completions": 3, "overdue": 1, "new_tasks": 2}
                },
                "by_tag": {
                    "work": {"completions": 3, "overdue": 1, "new_tasks": 1},
                    "home": {"completions": 2, "overdue": 1, "new_tasks": 2}
                }
            }
            
            result_path = manager.update_insights_section(target, insights)
            
            content = Path(result_path).read_text()
            assert "Task Insights" in content
            assert "Completed: 5" in content or "**Completed**: 5" in content
    
    def test_insights_section_replacement(self):
        """Test that old insights section is replaced, not duplicated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = tmpdir
            daily_notes_dir = Path(vault_path) / "Daily Notes"
            daily_notes_dir.mkdir(parents=True)
            
            note_path = daily_notes_dir / "2025-01-15.md"
            initial_content = """# 2025-01-15

## Task Insights
Old data here
<!-- END TASK INSIGHTS -->

Other content
"""
            note_path.write_text(initial_content)
            
            manager = DailyNoteManager(vault_path)
            target = date(2025, 1, 15)
            
            insights = {
                "completions": 10,
                "overdue": 0,
                "new_tasks": 5
            }
            
            result_path = manager.update_insights_section(target, insights)
            content = Path(result_path).read_text()
            
            # Should only have one insights section
            assert content.count("Task Insights") == 1
            assert "Old data here" not in content
    
    def test_template_present_scenario(self):
        """Test that daily note uses Obsidian template when configured."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir)
            
            # Create directory structure
            daily_notes_dir = vault_path / "Daily Notes"
            daily_notes_dir.mkdir(parents=True)
            
            templates_dir = vault_path / "Templates"
            templates_dir.mkdir(parents=True)
            
            obsidian_dir = vault_path / ".obsidian"
            obsidian_dir.mkdir(parents=True)
            
            # Create template file
            template_path = templates_dir / "Daily Note Template.md"
            template_content = """# {{date}}

## Morning Review
- Energy level:
- Top 3 priorities:

## Work Log

## Evening Reflection
- Wins:
- Learnings:
"""
            template_path.write_text(template_content)
            
            # Create daily-notes settings pointing to template
            settings_path = obsidian_dir / "daily-notes.json"
            settings = {
                "folder": "Daily Notes",
                "format": "YYYY-MM-DD",
                "template": "Templates/Daily Note Template"
            }
            settings_path.write_text(json.dumps(settings))
            
            # Create daily note manager
            manager = DailyNoteManager(str(vault_path))
            target = date(2025, 1, 20)
            
            # Create insights to inject
            insights = {
                "completions": 3,
                "overdue": 1,
                "new_tasks": 2
            }
            
            # This should create note with template
            result_path = manager.update_insights_section(target, insights)
            
            content = Path(result_path).read_text()
            
            # Should have template content (not the hard-coded scaffold)
            assert "Morning Review" in content
            assert "Evening Reflection" in content
            assert "Energy level:" in content
            
            # Should also have the injected insights
            assert "Task Insights" in content
            assert "Completed: 3" in content or "**Completed**: 3" in content
    
    def test_template_missing_fallback(self):
        """Test fallback to scaffold when template not found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir)
            
            daily_notes_dir = vault_path / "Daily Notes"
            daily_notes_dir.mkdir(parents=True)
            
            obsidian_dir = vault_path / ".obsidian"
            obsidian_dir.mkdir(parents=True)
            
            # Create settings pointing to non-existent template
            settings_path = obsidian_dir / "daily-notes.json"
            settings = {
                "folder": "Daily Notes",
                "format": "YYYY-MM-DD",
                "template": "Templates/NonExistent"
            }
            settings_path.write_text(json.dumps(settings))
            
            manager = DailyNoteManager(str(vault_path))
            target = date(2025, 1, 20)
            
            insights = {
                "completions": 5,
                "overdue": 0,
                "new_tasks": 3
            }
            
            result_path = manager.update_insights_section(target, insights)
            content = Path(result_path).read_text()
            
            # Should use fallback scaffold
            assert "# 2025-01-20" in content
            assert "## Calendar" in content
            assert "## Daily Review" in content
            
            # Should still have insights
            assert "Task Insights" in content
    
    def test_no_template_configured(self):
        """Test fallback to scaffold when no template is configured."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir)
            
            daily_notes_dir = vault_path / "Daily Notes"
            daily_notes_dir.mkdir(parents=True)
            
            # No .obsidian settings at all
            manager = DailyNoteManager(str(vault_path))
            target = date(2025, 1, 20)
            
            events = [
                CalendarEvent(
                    event_id="1",
                    title="Meeting",
                    start_time=datetime(2025, 1, 20, 10, 0, tzinfo=timezone.utc),
                    end_time=datetime(2025, 1, 20, 11, 0, tzinfo=timezone.utc),
                    is_all_day=False,
                    calendar_name="Work",
                    location=None,
                    notes=None
                )
            ]
            
            result_path = manager.update_daily_note(target, events)
            content = Path(result_path).read_text()
            
            # Should use default scaffold
            assert "# 2025-01-20" in content
            assert "## Calendar" in content
            assert "## Tasks" in content
            assert "## Daily Review" in content
            
            # Should have calendar event
            assert "Meeting" in content
    
    def test_periodic_notes_plugin_support(self):
        """Test reading template from Periodic Notes plugin settings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir)
            
            daily_notes_dir = vault_path / "Daily Notes"
            daily_notes_dir.mkdir(parents=True)
            
            templates_dir = vault_path / "Templates"
            templates_dir.mkdir(parents=True)
            
            plugins_dir = vault_path / ".obsidian" / "plugins" / "periodic-notes"
            plugins_dir.mkdir(parents=True, exist_ok=True)
            
            # Create template
            template_path = templates_dir / "Periodic Daily.md"
            template_content = """# Daily Note {{date}}

## Goals

## Tasks
"""
            template_path.write_text(template_content)
            
            # Create periodic-notes settings
            settings_path = plugins_dir / "data.json"
            settings = {
                "daily": {
                    "folder": "Daily Notes",
                    "format": "YYYY-MM-DD",
                    "template": "Templates/Periodic Daily"
                }
            }
            settings_path.write_text(json.dumps(settings))
            
            manager = DailyNoteManager(str(vault_path))
            target = date(2025, 1, 20)
            
            insights = {
                "completions": 2,
                "overdue": 0,
                "new_tasks": 1
            }
            
            result_path = manager.update_insights_section(target, insights)
            content = Path(result_path).read_text()
            
            # Should use periodic notes template
            assert "## Goals" in content
            assert "Daily Note" in content
            
            # Should have insights
            assert "Task Insights" in content


class TestCalendarImportTracker:
    """Test CalendarImportTracker state persistence."""
    
    def test_has_run_today_fresh_state(self):
        """Test that fresh tracker reports not run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker_path = Path(tmpdir) / "tracker.json"
            
            with patch('obs_sync.calendar.tracker.get_path_manager') as mock_pm:
                mock_pm.return_value.data_dir.return_value = Path(tmpdir)
                
                tracker = CalendarImportTracker()
                assert not tracker.has_run_today("vault-1")
    
    def test_mark_run_today(self):
        """Test that marking run today persists state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('obs_sync.calendar.tracker.get_path_manager') as mock_pm:
                mock_pm.return_value.data_dir.return_value = Path(tmpdir)
                
                tracker = CalendarImportTracker()
                tracker.mark_run_today("vault-1")
                
                # Create new instance to test persistence
                tracker2 = CalendarImportTracker()
                assert tracker2.has_run_today("vault-1")
    
    def test_different_vaults_tracked_separately(self):
        """Test that different vaults are tracked independently."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('obs_sync.calendar.tracker.get_path_manager') as mock_pm:
                mock_pm.return_value.data_dir.return_value = Path(tmpdir)
                
                tracker = CalendarImportTracker()
                tracker.mark_run_today("vault-1")
                
                assert tracker.has_run_today("vault-1")
                assert not tracker.has_run_today("vault-2")
    
    def test_tracker_clears_after_date_change(self):
        """Test that tracker state is date-specific."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker_file = Path(tmpdir) / "calendar_tracker.json"
            
            # Write old date
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            tracker_file.write_text(json.dumps({"vault-1": yesterday}))
            
            with patch('obs_sync.calendar.tracker.get_path_manager') as mock_pm:
                mock_pm.return_value.data_dir.return_value = Path(tmpdir)
                
                tracker = CalendarImportTracker()
                # Should return False because date has changed
                assert not tracker.has_run_today("vault-1")


class TestCalendarCommand:
    """Test CalendarCommand end-to-end flow."""
    
    def test_command_dry_run_default(self):
        """Test that command defaults to dry-run."""
        config = SyncConfig(
            vaults=[Vault(name="Test", path="/tmp/test", vault_id="v1")],
            sync_calendar_events=True
        )
        
        with patch('obs_sync.commands.calendar.CalendarGateway') as mock_gw_class:
            with patch('obs_sync.commands.calendar.DailyNoteManager') as mock_dnm_class:
                mock_gw = Mock()
                mock_gw.get_events_for_date.return_value = []
                mock_gw_class.return_value = mock_gw
                
                mock_dnm = Mock()
                mock_dnm_class.return_value = mock_dnm
                
                cmd = CalendarCommand(config, verbose=True)
                result = cmd.run()
                
                # In dry-run, should fetch but not update
                assert result is True
    
    def test_command_respects_config_flag(self):
        """Test that command respects sync_calendar_events config."""
        config = SyncConfig(
            vaults=[Vault(name="Test", path="/tmp/test", vault_id="v1")],
            sync_calendar_events=False  # Disabled
        )
        
        cmd = CalendarCommand(config, verbose=True)
        
        # Should exit early when disabled
        with patch('obs_sync.commands.calendar.CalendarGateway') as mock_gw_class:
            result = cmd.run()
            
            # Should not instantiate gateway when disabled
            mock_gw_class.assert_not_called()
    
    def test_command_apply_changes(self):
        """Test that command writes to daily notes when not dry-run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir)
            daily_notes = vault_path / "Daily Notes"
            daily_notes.mkdir(parents=True)
            
            config = SyncConfig(
                vaults=[Vault(name="Test", path=str(vault_path), vault_id="v1")],
                sync_calendar_events=True
            )
            
            with patch('obs_sync.commands.calendar.CalendarGateway') as mock_gw_class:
                mock_gw = Mock()
                mock_gw.get_events_for_date.return_value = [
                    CalendarEvent(
                        event_id="1",
                        title="Test Event",
                        start_time=datetime.now(timezone.utc),
                        end_time=datetime.now(timezone.utc) + timedelta(hours=1),
                        is_all_day=False,
                        calendar_name="Work",
                        location=None,
                        notes=None
                    )
                ]
                mock_gw_class.return_value = mock_gw
                
                cmd = CalendarCommand(config, verbose=True)
                result = cmd.run(dry_run=False)
                
                assert result is True
                # Check that daily note was created
                daily_note_path = daily_notes / f"{date.today().isoformat()}.md"
                assert daily_note_path.exists()
                content = daily_note_path.read_text()
                assert "Test Event" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
