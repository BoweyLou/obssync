"""LaunchAgent management for macOS automation.

This module provides comprehensive LaunchAgent lifecycle management including:
- StartInterval and StartCalendarInterval scheduling
- KeepAlive and ThrottleInterval for reliability
- Absolute path resolution for ProgramArguments
- User-specified environment variables
- Plist version tracking and change detection
- Status reporting and automatic repair
"""

import hashlib
import os
import platform
import plistlib
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import logging


AGENT_LABEL = "com.obs-sync.sync-agent"
AGENT_FILENAME = f"{AGENT_LABEL}.plist"
PLIST_VERSION = "2.0.0"  # Increment when plist structure changes


@dataclass
class CalendarSchedule:
    """Represents a StartCalendarInterval schedule entry.

    Fields follow Apple's StartCalendarInterval spec:
    - minute: 0-59
    - hour: 0-23
    - day: 1-31 (day of month)
    - weekday: 0-6 (0=Sunday)
    - month: 1-12

    Omitted fields mean "every" (e.g., no hour means every hour).
    """
    minute: Optional[int] = None
    hour: Optional[int] = None
    day: Optional[int] = None
    weekday: Optional[int] = None
    month: Optional[int] = None

    def to_dict(self) -> Dict[str, int]:
        """Convert to plist-compatible dictionary."""
        result = {}
        if self.minute is not None:
            result["Minute"] = self.minute
        if self.hour is not None:
            result["Hour"] = self.hour
        if self.day is not None:
            result["Day"] = self.day
        if self.weekday is not None:
            result["Weekday"] = self.weekday
        if self.month is not None:
            result["Month"] = self.month
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CalendarSchedule":
        """Create from plist dictionary."""
        return cls(
            minute=data.get("Minute") or data.get("minute"),
            hour=data.get("Hour") or data.get("hour"),
            day=data.get("Day") or data.get("day"),
            weekday=data.get("Weekday") or data.get("weekday"),
            month=data.get("Month") or data.get("month"),
        )

    def describe(self) -> str:
        """Human-readable description of the schedule."""
        parts = []

        if self.minute is not None:
            parts.append(f"at minute {self.minute}")

        if self.hour is not None:
            hour_12 = self.hour % 12 or 12
            am_pm = "AM" if self.hour < 12 else "PM"
            parts.append(f"at {hour_12}:{self.minute or 0:02d} {am_pm}")

        if self.weekday is not None:
            days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
            parts.append(f"on {days[self.weekday]}")

        if self.day is not None:
            parts.append(f"on day {self.day}")

        if self.month is not None:
            months = ["", "January", "February", "March", "April", "May", "June",
                     "July", "August", "September", "October", "November", "December"]
            parts.append(f"in {months[self.month]}")

        if not parts:
            return "every minute"

        return ", ".join(parts)


@dataclass
class AgentStatus:
    """Detailed status of the LaunchAgent."""
    is_installed: bool = False
    is_loaded: bool = False
    plist_path: Optional[Path] = None
    plist_version: Optional[str] = None
    plist_checksum: Optional[str] = None
    config_checksum: Optional[str] = None
    is_outdated: bool = False
    schedule_type: Optional[str] = None  # "interval" or "calendar"
    interval_seconds: Optional[int] = None
    calendar_schedules: List[CalendarSchedule] = field(default_factory=list)
    last_exit_status: Optional[int] = None
    pid: Optional[int] = None
    run_count: Optional[int] = None
    last_run_time: Optional[datetime] = None
    error_message: Optional[str] = None

    def needs_repair(self) -> bool:
        """Check if the agent needs repair."""
        if not self.is_installed:
            return False
        if self.is_outdated:
            return True
        if self.plist_checksum and self.config_checksum:
            return self.plist_checksum != self.config_checksum
        return False

    def summary(self) -> str:
        """Return a human-readable status summary."""
        if not self.is_installed:
            return "Not installed"

        status_parts = []
        status_parts.append("installed" if self.is_installed else "not installed")
        status_parts.append("loaded" if self.is_loaded else "not loaded")

        if self.is_outdated:
            status_parts.append("OUTDATED")

        if self.schedule_type == "interval" and self.interval_seconds:
            status_parts.append(f"runs {describe_interval(self.interval_seconds)}")
        elif self.schedule_type == "calendar" and self.calendar_schedules:
            schedules = [s.describe() for s in self.calendar_schedules]
            status_parts.append(f"runs {'; '.join(schedules)}")

        if self.last_exit_status is not None and self.last_exit_status != 0:
            status_parts.append(f"last exit: {self.last_exit_status}")

        if self.error_message:
            status_parts.append(f"error: {self.error_message}")

        return ", ".join(status_parts)


def is_macos() -> bool:
    """Check if running on macOS."""
    return platform.system() == "Darwin"


def get_launchagent_path() -> Path:
    """Get the path where the LaunchAgent plist should be installed."""
    return Path.home() / "Library" / "LaunchAgents" / AGENT_FILENAME


def compute_plist_checksum(plist_data: Dict) -> str:
    """Compute a checksum for plist content to detect changes.

    Args:
        plist_data: The plist dictionary

    Returns:
        SHA256 checksum of the plist content
    """
    # Convert to bytes in a deterministic way
    content = plistlib.dumps(plist_data)
    return hashlib.sha256(content).hexdigest()[:16]


def generate_plist(
    interval_seconds: Optional[int] = None,
    calendar_schedules: Optional[List[CalendarSchedule]] = None,
    obs_sync_path: str = "",
    log_dir: Path = Path.home(),
    working_dir: Path = Path.home(),
    env_vars: Optional[Dict[str, str]] = None,
    keep_alive: bool = False,
    throttle_interval: int = 60,
    logger: Optional[logging.Logger] = None
) -> Dict:
    """
    Generate LaunchAgent plist dictionary.

    Args:
        interval_seconds: Interval in seconds between runs (StartInterval)
        calendar_schedules: List of CalendarSchedule objects (StartCalendarInterval)
        obs_sync_path: Full path to obs-sync executable
        log_dir: Directory for stdout/stderr logs
        working_dir: Directory to use as OBS_SYNC_HOME / process working directory
        env_vars: Additional environment variables to set
        keep_alive: Whether to restart on exit (KeepAlive)
        throttle_interval: Minimum seconds between restarts (ThrottleInterval)
        logger: Optional logger instance

    Returns:
        Dictionary representing the plist structure

    Raises:
        ValueError: If neither interval_seconds nor calendar_schedules provided
    """
    if not interval_seconds and not calendar_schedules:
        raise ValueError("Either interval_seconds or calendar_schedules must be provided")

    if logger:
        logger.debug(f"Generating plist with interval={interval_seconds}s, exe={obs_sync_path}")

    # Ensure directories exist
    log_dir.mkdir(parents=True, exist_ok=True)
    working_dir.mkdir(parents=True, exist_ok=True)

    stdout_log = log_dir / "obs-sync-agent.stdout.log"
    stderr_log = log_dir / "obs-sync-agent.stderr.log"

    # Resolve absolute path for executable
    if obs_sync_path and not os.path.isabs(obs_sync_path):
        resolved = get_obs_sync_executable()
        if resolved:
            obs_sync_path = resolved

    # Build environment variables
    environment = {
        "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin",
        "OBS_SYNC_HOME": str(working_dir),
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
    }

    # Add user-specified environment variables
    if env_vars:
        environment.update(env_vars)

    plist: Dict[str, Any] = {
        "Label": AGENT_LABEL,
        "ProgramArguments": [obs_sync_path, "sync", "--apply"],
        "RunAtLoad": True,
        "StandardOutPath": str(stdout_log),
        "StandardErrorPath": str(stderr_log),
        "EnvironmentVariables": environment,
        "WorkingDirectory": str(working_dir),
        # Version tracking for change detection
        "Comment": f"obs-sync automation agent v{PLIST_VERSION}",
    }

    # Add scheduling - prefer calendar if both provided
    if calendar_schedules:
        if len(calendar_schedules) == 1:
            plist["StartCalendarInterval"] = calendar_schedules[0].to_dict()
        else:
            plist["StartCalendarInterval"] = [s.to_dict() for s in calendar_schedules]
    elif interval_seconds:
        plist["StartInterval"] = interval_seconds

    # Add reliability settings
    if keep_alive:
        plist["KeepAlive"] = {
            "SuccessfulExit": False,  # Restart on failure only
        }
        plist["ThrottleInterval"] = throttle_interval

    return plist


def install_agent(
    interval_seconds: Optional[int] = None,
    calendar_schedules: Optional[List[CalendarSchedule]] = None,
    obs_sync_path: str = "",
    log_dir: Path = Path.home(),
    working_dir: Path = Path.home(),
    env_vars: Optional[Dict[str, str]] = None,
    keep_alive: bool = False,
    throttle_interval: int = 60,
    logger: Optional[logging.Logger] = None
) -> Tuple[bool, Optional[str]]:
    """
    Install (write) the LaunchAgent plist file.

    Args:
        interval_seconds: Interval in seconds between runs (StartInterval)
        calendar_schedules: List of CalendarSchedule objects (StartCalendarInterval)
        obs_sync_path: Full path to obs-sync executable
        log_dir: Directory for logs
        working_dir: Directory for process working directory and OBS_SYNC_HOME
        env_vars: Additional environment variables to set
        keep_alive: Whether to restart on exit (KeepAlive)
        throttle_interval: Minimum seconds between restarts (ThrottleInterval)
        logger: Optional logger instance

    Returns:
        (success, error_message) tuple
    """
    if not is_macos():
        return False, "LaunchAgent automation is only available on macOS"

    try:
        plist_path = get_launchagent_path()
        plist_path.parent.mkdir(parents=True, exist_ok=True)

        plist_data = generate_plist(
            interval_seconds=interval_seconds,
            calendar_schedules=calendar_schedules,
            obs_sync_path=obs_sync_path,
            log_dir=log_dir,
            working_dir=working_dir,
            env_vars=env_vars,
            keep_alive=keep_alive,
            throttle_interval=throttle_interval,
            logger=logger,
        )

        with open(plist_path, "wb") as f:
            plistlib.dump(plist_data, f)

        if logger:
            logger.info(f"LaunchAgent plist installed at {plist_path}")

        return True, None

    except Exception as e:
        error = f"Failed to install LaunchAgent: {e}"
        if logger:
            logger.error(error)
        return False, error


def uninstall_agent(logger: Optional[logging.Logger] = None) -> Tuple[bool, Optional[str]]:
    """
    Uninstall (remove) the LaunchAgent plist file.

    Returns:
        (success, error_message) tuple
    """
    if not is_macos():
        return False, "LaunchAgent automation is only available on macOS"

    try:
        plist_path = get_launchagent_path()

        if not plist_path.exists():
            return True, None  # Already uninstalled

        plist_path.unlink()

        if logger:
            logger.info(f"LaunchAgent plist removed from {plist_path}")

        return True, None

    except Exception as e:
        error = f"Failed to uninstall LaunchAgent: {e}"
        if logger:
            logger.error(error)
        return False, error


def load_agent(logger: Optional[logging.Logger] = None) -> Tuple[bool, Optional[str]]:
    """
    Load the LaunchAgent (enable it).

    Returns:
        (success, error_message) tuple
    """
    if not is_macos():
        return False, "LaunchAgent automation is only available on macOS"

    try:
        plist_path = get_launchagent_path()

        if not plist_path.exists():
            return False, f"LaunchAgent plist not found at {plist_path}"

        result = subprocess.run(
            ["launchctl", "load", str(plist_path)],
            capture_output=True,
            text=True,
            check=False
        )

        if result.returncode != 0:
            # launchctl load can fail if already loaded; check stderr
            if "already loaded" in result.stderr.lower():
                if logger:
                    logger.debug("LaunchAgent already loaded")
                return True, None

            error = f"launchctl load failed: {result.stderr.strip()}"
            if logger:
                logger.error(error)
            return False, error

        if logger:
            logger.info("LaunchAgent loaded successfully")

        return True, None

    except Exception as e:
        error = f"Failed to load LaunchAgent: {e}"
        if logger:
            logger.error(error)
        return False, error


def unload_agent(logger: Optional[logging.Logger] = None) -> Tuple[bool, Optional[str]]:
    """
    Unload the LaunchAgent (disable it).

    Returns:
        (success, error_message) tuple
    """
    if not is_macos():
        return False, "LaunchAgent automation is only available on macOS"

    try:
        plist_path = get_launchagent_path()

        result = subprocess.run(
            ["launchctl", "unload", str(plist_path)],
            capture_output=True,
            text=True,
            check=False
        )

        if result.returncode != 0:
            # launchctl unload can fail if not loaded; check stderr
            if "could not find" in result.stderr.lower() or "no such" in result.stderr.lower():
                if logger:
                    logger.debug("LaunchAgent already unloaded")
                return True, None

            error = f"launchctl unload failed: {result.stderr.strip()}"
            if logger:
                logger.error(error)
            return False, error

        if logger:
            logger.info("LaunchAgent unloaded successfully")

        return True, None

    except Exception as e:
        error = f"Failed to unload LaunchAgent: {e}"
        if logger:
            logger.error(error)
        return False, error


def is_agent_loaded(logger: Optional[logging.Logger] = None) -> bool:
    """
    Check if the LaunchAgent is currently loaded.

    Returns:
        True if loaded, False otherwise
    """
    if not is_macos():
        return False

    try:
        result = subprocess.run(
            ["launchctl", "list", AGENT_LABEL],
            capture_output=True,
            text=True,
            check=False
        )

        return result.returncode == 0

    except Exception as e:
        if logger:
            logger.warning(f"Failed to check LaunchAgent status: {e}")
        return False


def get_agent_status(
    config_checksum: Optional[str] = None,
    logger: Optional[logging.Logger] = None
) -> AgentStatus:
    """
    Get detailed status of the LaunchAgent.

    Args:
        config_checksum: Expected checksum from config for comparison
        logger: Optional logger instance

    Returns:
        AgentStatus with detailed information
    """
    status = AgentStatus()

    if not is_macos():
        status.error_message = "Not on macOS"
        return status

    plist_path = get_launchagent_path()
    status.plist_path = plist_path

    # Check if plist exists
    if plist_path.exists():
        status.is_installed = True

        try:
            with open(plist_path, "rb") as f:
                plist_data = plistlib.load(f)

            # Extract version from Comment field
            comment = plist_data.get("Comment", "")
            if "v" in comment:
                status.plist_version = comment.split("v")[-1].strip()

            # Compute checksum
            status.plist_checksum = compute_plist_checksum(plist_data)
            status.config_checksum = config_checksum

            # Check if outdated
            if status.plist_version and status.plist_version != PLIST_VERSION:
                status.is_outdated = True

            # Extract schedule info
            if "StartInterval" in plist_data:
                status.schedule_type = "interval"
                status.interval_seconds = plist_data["StartInterval"]
            elif "StartCalendarInterval" in plist_data:
                status.schedule_type = "calendar"
                cal_data = plist_data["StartCalendarInterval"]
                if isinstance(cal_data, list):
                    status.calendar_schedules = [CalendarSchedule.from_dict(c) for c in cal_data]
                else:
                    status.calendar_schedules = [CalendarSchedule.from_dict(cal_data)]

        except Exception as e:
            if logger:
                logger.warning(f"Failed to read plist: {e}")
            status.error_message = f"Failed to read plist: {e}"

    # Check if loaded using launchctl list
    try:
        result = subprocess.run(
            ["launchctl", "list", AGENT_LABEL],
            capture_output=True,
            text=True,
            check=False
        )

        if result.returncode == 0:
            status.is_loaded = True

            # Parse output for PID and exit status
            # Format: PID    Status  Label
            lines = result.stdout.strip().split('\n')
            for line in lines:
                parts = line.split()
                if len(parts) >= 3 and AGENT_LABEL in line:
                    try:
                        if parts[0] != '-':
                            status.pid = int(parts[0])
                        if parts[1] != '-':
                            status.last_exit_status = int(parts[1])
                    except (ValueError, IndexError):
                        pass
                    break

    except Exception as e:
        if logger:
            logger.warning(f"Failed to check loaded status: {e}")

    return status


def repair_agent(
    interval_seconds: Optional[int] = None,
    calendar_schedules: Optional[List[CalendarSchedule]] = None,
    obs_sync_path: str = "",
    log_dir: Path = Path.home(),
    working_dir: Path = Path.home(),
    env_vars: Optional[Dict[str, str]] = None,
    keep_alive: bool = False,
    throttle_interval: int = 60,
    logger: Optional[logging.Logger] = None
) -> Tuple[bool, Optional[str]]:
    """
    Repair the LaunchAgent by unloading, reinstalling, and reloading.

    This is useful when:
    - The plist version is outdated
    - The plist checksum doesn't match expected config
    - The agent is in a bad state

    Args:
        interval_seconds: Interval in seconds between runs (StartInterval)
        calendar_schedules: List of CalendarSchedule objects (StartCalendarInterval)
        obs_sync_path: Full path to obs-sync executable
        log_dir: Directory for logs
        working_dir: Directory for process working directory
        env_vars: Additional environment variables to set
        keep_alive: Whether to restart on exit (KeepAlive)
        throttle_interval: Minimum seconds between restarts (ThrottleInterval)
        logger: Optional logger instance

    Returns:
        (success, error_message) tuple
    """
    if not is_macos():
        return False, "LaunchAgent automation is only available on macOS"

    errors = []

    # Step 1: Unload if loaded
    if is_agent_loaded(logger):
        success, error = unload_agent(logger)
        if not success:
            errors.append(f"Unload: {error}")

    # Step 2: Remove old plist
    plist_path = get_launchagent_path()
    if plist_path.exists():
        try:
            plist_path.unlink()
        except Exception as e:
            errors.append(f"Remove plist: {e}")

    # Step 3: Install new plist
    success, error = install_agent(
        interval_seconds=interval_seconds,
        calendar_schedules=calendar_schedules,
        obs_sync_path=obs_sync_path,
        log_dir=log_dir,
        working_dir=working_dir,
        env_vars=env_vars,
        keep_alive=keep_alive,
        throttle_interval=throttle_interval,
        logger=logger,
    )
    if not success:
        errors.append(f"Install: {error}")
        return False, "; ".join(errors)

    # Step 4: Load the agent
    success, error = load_agent(logger)
    if not success:
        errors.append(f"Load: {error}")
        return False, "; ".join(errors)

    if errors:
        return False, "; ".join(errors)

    return True, None


def get_obs_sync_executable() -> Optional[str]:
    """
    Find the obs-sync executable path.

    Returns:
        Full path to obs-sync, or None if not found
    """
    # Check common locations
    candidates = [
        Path.home() / ".local" / "bin" / "obs-sync",
        Path("/usr/local/bin/obs-sync"),
        Path("/opt/homebrew/bin/obs-sync"),
    ]

    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)

    # Fall back to `which obs-sync`
    try:
        result = subprocess.run(
            ["which", "obs-sync"],
            capture_output=True,
            text=True,
            check=False
        )

        if result.returncode == 0:
            path = result.stdout.strip()
            if path:
                return path
    except Exception:
        pass

    return None


def describe_interval(seconds: int) -> str:
    """
    Human-readable description of an interval.

    Args:
        seconds: Interval in seconds

    Returns:
        Readable string like "every hour", "every 12 hours", etc.
    """
    if seconds < 60:
        return f"every {seconds} seconds"
    elif seconds < 3600:
        minutes = seconds // 60
        if minutes == 1:
            return "every 1 minute"
        return f"every {minutes} minutes"
    elif seconds < 86400:
        hours = seconds // 3600
        if hours == 1:
            return "every 1 hour"
        return f"every {hours} hours"
    else:
        days = seconds // 86400
        if days == 1:
            return "every 1 day"
        return f"every {days} days"


def describe_schedule(
    interval_seconds: Optional[int] = None,
    calendar_schedules: Optional[List[CalendarSchedule]] = None
) -> str:
    """
    Human-readable description of a schedule configuration.

    Args:
        interval_seconds: StartInterval value
        calendar_schedules: List of CalendarSchedule objects

    Returns:
        Human-readable schedule description
    """
    if calendar_schedules:
        descriptions = [s.describe() for s in calendar_schedules]
        return "; ".join(descriptions)
    elif interval_seconds:
        return describe_interval(interval_seconds)
    else:
        return "no schedule configured"


# Common preset schedules
SCHEDULE_PRESETS = {
    "hourly": {"interval_seconds": 3600, "description": "Every hour"},
    "twice_daily": {"interval_seconds": 43200, "description": "Every 12 hours"},
    "daily_morning": {
        "calendar_schedules": [CalendarSchedule(hour=9, minute=0)],
        "description": "Daily at 9:00 AM",
    },
    "daily_evening": {
        "calendar_schedules": [CalendarSchedule(hour=18, minute=0)],
        "description": "Daily at 6:00 PM",
    },
    "twice_daily_calendar": {
        "calendar_schedules": [
            CalendarSchedule(hour=9, minute=0),
            CalendarSchedule(hour=18, minute=0),
        ],
        "description": "Daily at 9:00 AM and 6:00 PM",
    },
    "workdays_morning": {
        "calendar_schedules": [
            CalendarSchedule(hour=9, minute=0, weekday=1),  # Monday
            CalendarSchedule(hour=9, minute=0, weekday=2),  # Tuesday
            CalendarSchedule(hour=9, minute=0, weekday=3),  # Wednesday
            CalendarSchedule(hour=9, minute=0, weekday=4),  # Thursday
            CalendarSchedule(hour=9, minute=0, weekday=5),  # Friday
        ],
        "description": "Weekdays at 9:00 AM",
    },
}
