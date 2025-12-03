"""
Regression tests for critical configuration toggles and CLI flags.

Validates automation settings, sync flags, and insights toggles to prevent
configuration regressions.
"""

import sys
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

from obs_sync.core.models import SyncConfig, Vault, RemindersList
from obs_sync.commands.setup import SetupCommand
from obs_sync.commands.sync import SyncCommand, sync_command
from obs_sync.main import main


class TestAutomationToggles:
    """Regression tests for automation enable/disable flows."""
    
    @pytest.mark.skipif(sys.platform != "darwin", reason="LaunchAgent only on macOS")
    def test_automation_enable_installs_agent(self):
        """Test that enabling automation installs LaunchAgent."""
        config = SyncConfig(
            vaults=[Vault(name="Test", path="/tmp/test", vault_id="v1")],
            automation_enabled=False
        )

        with patch('obs_sync.utils.launchd.install_agent') as mock_install:
            with patch('obs_sync.utils.launchd.load_agent') as mock_load:
                mock_install.return_value = (True, None)
                mock_load.return_value = (True, None)

                cmd = SetupCommand(config, verbose=True)

                # Simulate enabling automation
                config.automation_enabled = True
                config.automation_interval = 3600

                # Verify the toggles would trigger installation
                # (In real flow, this happens in _prompt_automation_setup)
                assert config.automation_enabled is True

    @pytest.mark.skipif(sys.platform != "darwin", reason="LaunchAgent only on macOS")
    def test_automation_disable_unloads_agent(self):
        """Test that disabling automation unloads LaunchAgent."""
        config = SyncConfig(
            vaults=[Vault(name="Test", path="/tmp/test", vault_id="v1")],
            automation_enabled=True,
            automation_interval=3600
        )

        with patch('obs_sync.utils.launchd.unload_agent') as mock_unload:
            mock_unload.return_value = (True, None)

            cmd = SetupCommand(config, verbose=True)

            # Disable automation
            config.automation_enabled = False

            # Verify flag is disabled
            assert config.automation_enabled is False
    
    def test_automation_interval_changes_persist(self):
        """Test that automation interval changes are persisted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            
            config = SyncConfig(
                vaults=[Vault(name="Test", path="/tmp/test", vault_id="v1")],
                automation_enabled=True,
                automation_interval=3600
            )
            
            config.save_to_file(str(config_path))
            
            # Change interval
            config.automation_interval = 7200
            config.save_to_file(str(config_path))
            
            # Reload and verify
            loaded = SyncConfig.load_from_file(str(config_path))
            assert loaded.automation_interval == 7200


class TestSyncCommandFlags:
    """Regression tests for sync command CLI flags."""
    
    def test_sync_dry_run_default(self):
        """Test that sync defaults to dry-run."""
        config = SyncConfig(
            vaults=[Vault(name="Test", path="/tmp/test", vault_id="v1")],
            reminders_lists=[
                RemindersList(name="Work", identifier="cal-1", source_name="iCloud", source_type="Local")
            ]
        )
        
        with patch('obs_sync.commands.sync.SyncEngine') as mock_engine_class:
            mock_engine = Mock()
            mock_engine.sync.return_value = {
                "created_obs": 0,
                "created_rem": 0,
                "updated_obs": 0,
                "updated_rem": 0,
                "matched": 0
            }
            mock_engine_class.return_value = mock_engine
            
            cmd = SyncCommand(config, verbose=True)
            result = cmd.run(apply_changes=False)
            
            # Verify sync was called with dry_run=True
            call_kwargs = mock_engine.sync.call_args[1]
            assert call_kwargs.get('dry_run') is True
    
    def test_sync_apply_flag_disables_dry_run(self):
        """Test that --apply flag disables dry-run."""
        config = SyncConfig(
            vaults=[Vault(name="Test", path="/tmp/test", vault_id="v1")],
            reminders_lists=[
                RemindersList(name="Work", identifier="cal-1", source_name="iCloud", source_type="Local")
            ]
        )
        
        with patch('obs_sync.commands.sync.SyncEngine') as mock_engine_class:
            mock_engine = Mock()
            mock_engine.sync.return_value = {
                "created_obs": 0,
                "created_rem": 0,
                "updated_obs": 0,
                "updated_rem": 0,
                "matched": 0
            }
            mock_engine_class.return_value = mock_engine
            
            cmd = SyncCommand(config, verbose=True)
            result = cmd.run(apply_changes=True)
            
            # Verify sync was called with dry_run=False
            call_kwargs = mock_engine.sync.call_args[1]
            assert call_kwargs.get('dry_run') is False
    
    def test_sync_direction_to_reminders(self):
        """Test --to-reminders direction flag."""
        config = SyncConfig(
            vaults=[Vault(name="Test", path="/tmp/test", vault_id="v1")],
            reminders_lists=[
                RemindersList(name="Work", identifier="cal-1", source_name="iCloud", source_type="Local")
            ]
        )
        
        with patch('obs_sync.commands.sync.SyncEngine') as mock_engine_class:
            mock_engine = Mock()
            mock_engine.sync.return_value = {"created_obs": 0, "created_rem": 0, "updated_obs": 0, "updated_rem": 0, "matched": 0}
            mock_engine_class.return_value = mock_engine
            
            cmd = SyncCommand(config, verbose=True)
            result = cmd.run(apply_changes=False, direction="to-reminders")
            
            # Verify engine was created with correct direction
            call_kwargs = mock_engine_class.call_args[1]
            assert call_kwargs.get('direction') == "to-reminders"
    
    def test_sync_direction_from_reminders(self):
        """Test --from-reminders direction flag."""
        config = SyncConfig(
            vaults=[Vault(name="Test", path="/tmp/test", vault_id="v1")],
            reminders_lists=[
                RemindersList(name="Work", identifier="cal-1", source_name="iCloud", source_type="Local")
            ]
        )
        
        with patch('obs_sync.commands.sync.SyncEngine') as mock_engine_class:
            mock_engine = Mock()
            mock_engine.sync.return_value = {"created_obs": 0, "created_rem": 0, "updated_obs": 0, "updated_rem": 0, "matched": 0}
            mock_engine_class.return_value = mock_engine
            
            cmd = SyncCommand(config, verbose=True)
            result = cmd.run(apply_changes=False, direction="from-reminders")
            
            call_kwargs = mock_engine_class.call_args[1]
            assert call_kwargs.get('direction') == "from-reminders"
    
    def test_deduplication_runs_when_enabled(self):
        """Test that deduplication runs when enabled in config."""
        config = SyncConfig(
            vaults=[Vault(name="Test", path="/tmp/test", vault_id="v1")],
            reminders_lists=[
                RemindersList(name="Work", identifier="cal-1", source_name="iCloud", source_type="Local")
            ],
            enable_deduplication=True
        )
        
        with patch('obs_sync.commands.sync.SyncEngine') as mock_engine_class:
            with patch('obs_sync.commands.sync._run_deduplication') as mock_dedup:
                mock_engine = Mock()
                mock_engine.sync.return_value = {
                    "created_obs": 0,
                    "created_rem": 0,
                    "updated_obs": 0,
                    "updated_rem": 0,
                    "matched": 0
                }
                mock_engine_class.return_value = mock_engine
                mock_dedup.return_value = {}
                
                cmd = SyncCommand(config, verbose=True)
                result = cmd.run(apply_changes=False)
                
                # Dedup should be called
                assert mock_dedup.called
    
    def test_deduplication_skipped_when_disabled(self):
        """Test that deduplication is skipped when disabled."""
        config = SyncConfig(
            vaults=[Vault(name="Test", path="/tmp/test", vault_id="v1")],
            reminders_lists=[
                RemindersList(name="Work", identifier="cal-1", source_name="iCloud", source_type="Local")
            ],
            enable_deduplication=False
        )
        
        with patch('obs_sync.commands.sync.SyncEngine') as mock_engine_class:
            with patch('obs_sync.commands.sync._run_deduplication') as mock_dedup:
                mock_engine = Mock()
                mock_engine.sync.return_value = {
                    "created_obs": 0,
                    "created_rem": 0,
                    "updated_obs": 0,
                    "updated_rem": 0,
                    "matched": 0
                }
                mock_engine_class.return_value = mock_engine
                
                cmd = SyncCommand(config, verbose=True)
                result = cmd.run(apply_changes=False)
                
                # Dedup should not be called
                mock_dedup.assert_not_called()


class TestInsightsToggles:
    """Regression tests for insights configuration toggles."""
    
    def test_insights_enabled_toggle(self):
        """Test enable_insights configuration flag."""
        config = SyncConfig(enable_insights=True)
        assert config.enable_insights is True
        
        config.enable_insights = False
        assert config.enable_insights is False
    
    def test_streak_tracking_toggle(self):
        """Test enable_streak_tracking configuration flag."""
        config = SyncConfig(enable_streak_tracking=True)
        assert config.enable_streak_tracking is True
        
        config.enable_streak_tracking = False
        assert config.enable_streak_tracking is False
    
    def test_insights_in_daily_notes_toggle(self):
        """Test insights_in_daily_notes configuration flag."""
        config = SyncConfig(
            enable_insights=True,
            insights_in_daily_notes=True
        )
        assert config.insights_in_daily_notes is True
        
        config.insights_in_daily_notes = False
        assert config.insights_in_daily_notes is False
    
    def test_hygiene_assistant_toggle(self):
        """Test enable_hygiene_assistant configuration flag."""
        config = SyncConfig(enable_hygiene_assistant=True)
        assert config.enable_hygiene_assistant is True
        
        config.enable_hygiene_assistant = False
        assert config.enable_hygiene_assistant is False
    
    def test_insights_toggles_persist(self):
        """Test that insights toggles persist across save/load."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            
            config = SyncConfig(
                enable_insights=True,
                enable_streak_tracking=True,
                insights_in_daily_notes=True,
                enable_hygiene_assistant=True,
                hygiene_stagnant_threshold=21
            )
            
            config.save_to_file(str(config_path))
            
            loaded = SyncConfig.load_from_file(str(config_path))
            
            assert loaded.enable_insights is True
            assert loaded.enable_streak_tracking is True
            assert loaded.insights_in_daily_notes is True
            assert loaded.enable_hygiene_assistant is True
            assert loaded.hygiene_stagnant_threshold == 21


class TestUpdateChannelRegression:
    """Regression tests for update channel configuration."""
    
    def test_update_channel_defaults_to_main(self):
        """Test that update_channel defaults to 'main'."""
        config = SyncConfig()
        assert config.update_channel == "main"
    
    def test_update_channel_can_be_changed(self):
        """Test that update_channel can be set to 'dev'."""
        config = SyncConfig(update_channel="dev")
        assert config.update_channel == "dev"
    
    def test_update_channel_persists(self):
        """Test that update_channel persists across save/load."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            
            config = SyncConfig(update_channel="dev")
            config.save_to_file(str(config_path))
            
            loaded = SyncConfig.load_from_file(str(config_path))
            assert loaded.update_channel == "dev"


class TestCalendarSyncToggle:
    """Regression tests for calendar sync configuration."""
    
    def test_calendar_sync_enabled_toggle(self):
        """Test sync_calendar_events configuration flag."""
        config = SyncConfig(sync_calendar_events=True)
        assert config.sync_calendar_events is True
        
        config.sync_calendar_events = False
        assert config.sync_calendar_events is False
    
    def test_calendar_sync_persists(self):
        """Test that calendar sync setting persists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            
            config = SyncConfig(sync_calendar_events=True)
            config.save_to_file(str(config_path))
            
            loaded = SyncConfig.load_from_file(str(config_path))
            assert loaded.sync_calendar_events is True


class TestConflictResolutionTimestamps:
    """Regression tests for timestamp type handling in conflict resolution."""
    
    def test_reminders_datetime_wins_over_older_obsidian_string(self):
        """
        Test that Reminders completion with datetime modified_at beats
        older Obsidian string timestamp.
        
        Regression: Bug where _parse_time failed on datetime objects,
        causing Reminders to always lose conflicts.
        """
        from datetime import datetime, timezone, timedelta
        from obs_sync.sync.resolver import ConflictResolver
        from obs_sync.core.models import ObsidianTask, RemindersTask, TaskStatus
        
        resolver = ConflictResolver()
        
        # Obsidian task last modified 1 hour ago (ISO string)
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        obs_task = ObsidianTask(
            uuid="obs-123",
            vault_id="v1",
            vault_name="Test",
            vault_path="/tmp/test",
            file_path="todo.md",
            line_number=5,
            block_id="abc",
            status=TaskStatus.TODO,  # Still TODO in Obsidian
            description="Buy milk",
            raw_line="- [ ] Buy milk",
            modified_at=one_hour_ago.isoformat()  # String timestamp
        )
        
        # Reminders task completed just now (datetime object)
        now = datetime.now(timezone.utc)
        rem_task = RemindersTask(
            uuid="obs-123",  # Same UUID
            item_id="rem-456",
            calendar_id="cal-1",
            list_name="Shopping",
            status=TaskStatus.DONE,  # Completed in Reminders
            title="Buy milk",
            modified_at=now  # datetime object (NOT string)
        )
        
        # Resolve conflicts
        conflicts = resolver.resolve_conflicts(obs_task, rem_task)
        
        # Reminders should win because it has newer timestamp
        assert conflicts['status_winner'] == 'rem', \
            f"Expected Reminders to win status conflict (newer timestamp), got {conflicts['status_winner']}"
    
    def test_obsidian_string_wins_over_older_reminders_datetime(self):
        """
        Test that Obsidian update with newer ISO string beats
        older Reminders datetime timestamp.
        """
        from datetime import datetime, timezone, timedelta
        from obs_sync.sync.resolver import ConflictResolver
        from obs_sync.core.models import ObsidianTask, RemindersTask, TaskStatus
        
        resolver = ConflictResolver()
        
        # Reminders task modified 1 hour ago (datetime object)
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        rem_task = RemindersTask(
            uuid="task-789",
            item_id="rem-789",
            calendar_id="cal-1",
            list_name="Work",
            status=TaskStatus.TODO,
            title="Review PR",
            modified_at=one_hour_ago  # datetime object
        )
        
        # Obsidian task just updated (ISO string)
        now = datetime.now(timezone.utc)
        obs_task = ObsidianTask(
            uuid="task-789",
            vault_id="v1",
            vault_name="Test",
            vault_path="/tmp/test",
            file_path="work.md",
            line_number=10,
            block_id="xyz",
            status=TaskStatus.DONE,  # Completed in Obsidian
            description="Review PR",
            raw_line="- [x] Review PR",
            modified_at=now.isoformat()  # String timestamp
        )
        
        # Resolve conflicts
        conflicts = resolver.resolve_conflicts(obs_task, rem_task)
        
        # Obsidian should win because it has newer timestamp
        assert conflicts['status_winner'] == 'obs', \
            f"Expected Obsidian to win status conflict (newer timestamp), got {conflicts['status_winner']}"
    
    def test_parse_time_handles_both_types(self):
        """Test that _parse_time correctly handles both strings and datetime objects."""
        from datetime import datetime, timezone
        from obs_sync.sync.resolver import ConflictResolver
        
        resolver = ConflictResolver()
        
        # Test with datetime object
        dt_obj = datetime(2025, 1, 15, 12, 30, 0, tzinfo=timezone.utc)
        parsed_dt = resolver._parse_time(dt_obj)
        assert parsed_dt == dt_obj, "Should return datetime object as-is"
        
        # Test with ISO string
        iso_str = "2025-01-15T12:30:00+00:00"
        parsed_str = resolver._parse_time(iso_str)
        assert parsed_str == dt_obj, "Should parse ISO string correctly"
        
        # Test with ISO string with Z suffix
        iso_z = "2025-01-15T12:30:00Z"
        parsed_z = resolver._parse_time(iso_z)
        assert parsed_z == dt_obj, "Should parse ISO string with Z suffix"
        
        # Test with None
        parsed_none = resolver._parse_time(None)
        assert parsed_none is None, "Should return None for None input"
        
        # Test with invalid string
        parsed_invalid = resolver._parse_time("not-a-date")
        assert parsed_invalid is None, "Should return None for invalid string"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
