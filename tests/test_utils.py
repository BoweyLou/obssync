"""
Tests for utility modules (obs_sync/utils/{io,launchd,venv}.py).

Validates atomic writes, LaunchAgent generation, and venv path resolution.
"""

import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

from obs_sync.utils.io import safe_read_json, safe_write_json, atomic_write
from obs_sync.utils.launchd import (
    is_macos, generate_plist, get_launchagent_path, describe_interval,
    describe_schedule, CalendarSchedule, AgentStatus, compute_plist_checksum,
    PLIST_VERSION, SCHEDULE_PRESETS
)
from obs_sync.utils.venv import repo_root, venv_paths, default_home


class TestIOUtils:
    """Test suite for obs_sync/utils/io.py."""
    
    def test_safe_read_json_existing_file(self):
        """Test reading existing JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.json"
            test_data = {"key": "value", "number": 42}
            test_file.write_text(json.dumps(test_data))
            
            result = safe_read_json(str(test_file))
            
            assert result == test_data
    
    def test_safe_read_json_nonexistent_file(self):
        """Test reading non-existent file returns default."""
        result = safe_read_json("/nonexistent/file.json", default={"empty": True})
        
        assert result == {"empty": True}
    
    def test_safe_read_json_invalid_json(self):
        """Test reading invalid JSON returns default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "invalid.json"
            test_file.write_text("not valid json {{{")
            
            result = safe_read_json(str(test_file), default={})
            
            assert result == {}
    
    def test_safe_write_json_success(self):
        """Test writing JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "output.json"
            test_data = {"items": [1, 2, 3], "name": "test"}
            
            result = safe_write_json(str(test_file), test_data)
            
            assert result is True
            assert test_file.exists()
            
            # Verify content
            loaded = json.loads(test_file.read_text())
            assert loaded == test_data
    
    def test_safe_write_json_creates_parent_dirs(self):
        """Test that parent directories are created if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "nested" / "dir" / "file.json"
            
            result = safe_write_json(str(test_file), {"test": True})
            
            assert result is True
            assert test_file.exists()
    
    def test_safe_write_json_permission_error(self):
        """Test handling of write permission errors."""
        # Try to write to a read-only location
        result = safe_write_json("/root/protected.json", {"test": True})
        
        assert result is False
    
    def test_atomic_write_success(self):
        """Test atomic file write."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "atomic.txt"
            content = "This is atomic content\nWith multiple lines"
            
            result = atomic_write(str(test_file), content)
            
            assert result is True
            assert test_file.read_text() == content
    
    def test_atomic_write_overwrites(self):
        """Test that atomic write overwrites existing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "existing.txt"
            test_file.write_text("Old content")
            
            new_content = "New content"
            result = atomic_write(str(test_file), new_content)
            
            assert result is True
            assert test_file.read_text() == new_content
    
    def test_atomic_write_creates_parent_dirs(self):
        """Test that atomic write creates parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "nested" / "file.txt"
            
            result = atomic_write(str(test_file), "content")
            
            assert result is True
            assert test_file.exists()


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-specific tests")
class TestLaunchdUtils:
    """Test suite for obs_sync/utils/launchd.py."""
    
    def test_is_macos(self):
        """Test is_macos detection."""
        result = is_macos()
        assert result is True
    
    def test_get_launchagent_path(self):
        """Test LaunchAgent path construction."""
        path = get_launchagent_path()
        
        assert path.name == "com.obs-sync.sync-agent.plist"
        assert "LaunchAgents" in str(path)
    
    def test_generate_plist_structure(self):
        """Test plist generation creates valid structure."""
        plist = generate_plist(
            interval_seconds=3600,
            obs_sync_path="/usr/local/bin/obs-sync",
            log_dir=Path("/tmp/logs")
        )

        assert isinstance(plist, dict)
        assert "Label" in plist
        assert plist["Label"] == "com.obs-sync.sync-agent"
        assert "ProgramArguments" in plist
        assert "StartInterval" in plist
        assert plist["StartInterval"] == 3600
        assert "StandardOutPath" in plist
        assert "StandardErrorPath" in plist
        assert "Comment" in plist
        assert PLIST_VERSION in plist["Comment"]

    def test_generate_plist_program_arguments(self):
        """Test that plist includes correct program arguments."""
        obs_sync_path = "/custom/path/obs-sync"
        plist = generate_plist(
            interval_seconds=1800,
            obs_sync_path=obs_sync_path,
            log_dir=Path("/tmp")
        )

        args = plist["ProgramArguments"]
        assert obs_sync_path in args
        assert "sync" in args
        assert "--apply" in args

    def test_generate_plist_with_calendar_schedule(self):
        """Test plist generation with StartCalendarInterval."""
        schedule = CalendarSchedule(hour=9, minute=0)
        plist = generate_plist(
            calendar_schedules=[schedule],
            obs_sync_path="/usr/local/bin/obs-sync",
            log_dir=Path("/tmp/logs")
        )

        assert "StartCalendarInterval" in plist
        assert "StartInterval" not in plist
        cal_interval = plist["StartCalendarInterval"]
        assert cal_interval["Hour"] == 9
        assert cal_interval["Minute"] == 0

    def test_generate_plist_with_multiple_calendar_schedules(self):
        """Test plist with multiple calendar schedules."""
        schedules = [
            CalendarSchedule(hour=9, minute=0),
            CalendarSchedule(hour=18, minute=0),
        ]
        plist = generate_plist(
            calendar_schedules=schedules,
            obs_sync_path="/usr/local/bin/obs-sync",
            log_dir=Path("/tmp/logs")
        )

        assert "StartCalendarInterval" in plist
        cal_intervals = plist["StartCalendarInterval"]
        assert isinstance(cal_intervals, list)
        assert len(cal_intervals) == 2
        assert cal_intervals[0]["Hour"] == 9
        assert cal_intervals[1]["Hour"] == 18

    def test_generate_plist_with_keep_alive(self):
        """Test plist generation with KeepAlive enabled."""
        plist = generate_plist(
            interval_seconds=3600,
            obs_sync_path="/usr/local/bin/obs-sync",
            log_dir=Path("/tmp/logs"),
            keep_alive=True,
            throttle_interval=120
        )

        assert "KeepAlive" in plist
        assert plist["KeepAlive"]["SuccessfulExit"] is False
        assert "ThrottleInterval" in plist
        assert plist["ThrottleInterval"] == 120

    def test_generate_plist_with_env_vars(self):
        """Test plist generation with custom environment variables."""
        custom_vars = {"CUSTOM_VAR": "custom_value", "ANOTHER_VAR": "another_value"}
        plist = generate_plist(
            interval_seconds=3600,
            obs_sync_path="/usr/local/bin/obs-sync",
            log_dir=Path("/tmp/logs"),
            env_vars=custom_vars
        )

        env = plist["EnvironmentVariables"]
        assert "CUSTOM_VAR" in env
        assert env["CUSTOM_VAR"] == "custom_value"
        assert "PATH" in env  # Default still present
    
    def test_describe_interval_minutes(self):
        """Test interval description for minutes."""
        assert describe_interval(60) == "every 1 minute"
        assert describe_interval(300) == "every 5 minutes"
        assert describe_interval(120) == "every 2 minutes"

    def test_describe_interval_hours(self):
        """Test interval description for hours."""
        assert describe_interval(3600) == "every 1 hour"
        assert describe_interval(7200) == "every 2 hours"
    
    def test_describe_interval_mixed(self):
        """Test interval description for mixed units."""
        # 90 minutes = 1.5 hours
        result = describe_interval(5400)
        assert "hour" in result or "minute" in result

    def test_calendar_schedule_to_dict(self):
        """Test CalendarSchedule serialization."""
        schedule = CalendarSchedule(hour=9, minute=30, weekday=1)
        result = schedule.to_dict()

        assert result["Hour"] == 9
        assert result["Minute"] == 30
        assert result["Weekday"] == 1
        assert "Day" not in result
        assert "Month" not in result

    def test_calendar_schedule_from_dict(self):
        """Test CalendarSchedule deserialization."""
        data = {"Hour": 14, "Minute": 15, "Weekday": 5}
        schedule = CalendarSchedule.from_dict(data)

        assert schedule.hour == 14
        assert schedule.minute == 15
        assert schedule.weekday == 5

    def test_calendar_schedule_describe(self):
        """Test human-readable schedule description."""
        schedule = CalendarSchedule(hour=9, minute=0)
        desc = schedule.describe()
        assert "9:00 AM" in desc

        schedule_pm = CalendarSchedule(hour=18, minute=30)
        desc_pm = schedule_pm.describe()
        assert "6:30 PM" in desc_pm

        schedule_weekday = CalendarSchedule(hour=9, minute=0, weekday=1)
        desc_weekday = schedule_weekday.describe()
        assert "Monday" in desc_weekday

    def test_describe_schedule_with_interval(self):
        """Test describe_schedule with interval."""
        result = describe_schedule(interval_seconds=3600)
        assert "hour" in result

    def test_describe_schedule_with_calendar(self):
        """Test describe_schedule with calendar schedules."""
        schedules = [CalendarSchedule(hour=9, minute=0)]
        result = describe_schedule(calendar_schedules=schedules)
        assert "9:00 AM" in result

    def test_compute_plist_checksum(self):
        """Test plist checksum computation."""
        plist1 = {"Label": "test", "StartInterval": 3600}
        plist2 = {"Label": "test", "StartInterval": 3600}
        plist3 = {"Label": "test", "StartInterval": 7200}

        checksum1 = compute_plist_checksum(plist1)
        checksum2 = compute_plist_checksum(plist2)
        checksum3 = compute_plist_checksum(plist3)

        assert checksum1 == checksum2
        assert checksum1 != checksum3
        assert len(checksum1) == 16

    def test_agent_status_needs_repair_outdated(self):
        """Test AgentStatus.needs_repair with outdated plist."""
        status = AgentStatus(
            is_installed=True,
            is_outdated=True,
        )
        assert status.needs_repair() is True

    def test_agent_status_needs_repair_checksum_mismatch(self):
        """Test AgentStatus.needs_repair with checksum mismatch."""
        status = AgentStatus(
            is_installed=True,
            plist_checksum="abc123",
            config_checksum="def456",
        )
        assert status.needs_repair() is True

    def test_agent_status_summary(self):
        """Test AgentStatus summary generation."""
        status = AgentStatus(
            is_installed=True,
            is_loaded=True,
            schedule_type="interval",
            interval_seconds=3600,
        )
        summary = status.summary()
        assert "installed" in summary
        assert "loaded" in summary
        assert "hour" in summary

    def test_schedule_presets_exist(self):
        """Test that schedule presets are defined."""
        assert "hourly" in SCHEDULE_PRESETS
        assert "twice_daily" in SCHEDULE_PRESETS
        assert "daily_morning" in SCHEDULE_PRESETS
        assert "description" in SCHEDULE_PRESETS["hourly"]


class TestVenvUtils:
    """Test suite for obs_sync/utils/venv.py."""
    
    def test_repo_root_detection(self):
        """Test repository root detection."""
        root = repo_root()
        
        assert isinstance(root, Path)
        assert root.exists()
        # Should contain obs_sync package
        assert (root / "obs_sync").exists()
    
    def test_default_home_from_env(self):
        """Test default home reads from environment variable."""
        with patch.dict('os.environ', {'OBS_TOOLS_HOME': '/custom/home'}):
            home = default_home()
            
            assert home == Path('/custom/home')
    
    def test_default_home_fallback(self):
        """Test default home fallback when env var not set."""
        with patch.dict('os.environ', {}, clear=True):
            home = default_home()
            
            assert isinstance(home, Path)
            assert "obs-tools" in str(home).lower() or "Library" in str(home)
    
    def test_venv_paths_structure(self):
        """Test venv paths returns (venv_dir, python_path) tuple."""
        venv_dir, python_path = venv_paths()
        
        assert isinstance(venv_dir, Path)
        assert isinstance(python_path, Path)
        assert "venv" in str(venv_dir)
        assert "python" in python_path.name.lower()
    
    def test_venv_paths_with_custom_env(self):
        """Test venv paths with custom environment."""
        custom_env = {'OBS_TOOLS_HOME': '/tmp/custom-home'}
        
        venv_dir, python_path = venv_paths(env=custom_env)
        
        assert "/tmp/custom-home" in str(venv_dir)
    
    def test_build_env_includes_pythonpath(self):
        """Test that build_env includes PYTHONPATH."""
        from obs_sync.utils.venv import build_env
        
        env = build_env()
        
        assert 'PYTHONPATH' in env
        assert 'PATH' in env
    
    def test_build_env_with_overrides(self):
        """Test that build_env respects overrides."""
        from obs_sync.utils.venv import build_env
        
        overrides = {'CUSTOM_VAR': 'custom_value'}
        env = build_env(overrides=overrides)
        
        assert env['CUSTOM_VAR'] == 'custom_value'


@pytest.mark.skipif(sys.platform == "darwin", reason="Non-macOS test")
class TestLaunchdUtilsNonMacOS:
    """Test launchd utils on non-macOS platforms."""
    
    def test_is_macos_false_on_non_macos(self):
        """Test that is_macos returns False on non-macOS."""
        result = is_macos()
        assert result is False


class TestIOUtilsEdgeCases:
    """Test edge cases for I/O utilities."""
    
    def test_safe_write_json_with_unicode(self):
        """Test writing JSON with unicode characters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "unicode.json"
            test_data = {
                "emoji": "🎉",
                "chinese": "中文",
                "mixed": "Test 测试 ✓"
            }
            
            result = safe_write_json(str(test_file), test_data)
            
            assert result is True
            loaded = safe_read_json(str(test_file))
            assert loaded == test_data
    
    def test_safe_write_json_with_nested_structures(self):
        """Test writing deeply nested JSON structures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "nested.json"
            test_data = {
                "level1": {
                    "level2": {
                        "level3": {
                            "items": [1, 2, 3],
                            "meta": {"key": "value"}
                        }
                    }
                }
            }
            
            result = safe_write_json(str(test_file), test_data)
            
            assert result is True
            loaded = safe_read_json(str(test_file))
            assert loaded == test_data
    
    def test_atomic_write_empty_content(self):
        """Test atomic write with empty string."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "empty.txt"
            
            result = atomic_write(str(test_file), "")
            
            assert result is True
            assert test_file.read_text() == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
