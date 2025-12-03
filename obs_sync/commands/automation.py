"""
Automation command for managing macOS LaunchAgent.

Provides status reporting and repair functionality for the obs-sync
automation agent.
"""

from typing import List, Optional

from obs_sync.core.models import SyncConfig
from obs_sync.utils.launchd import (
    is_macos,
    get_launchagent_path,
    get_agent_status,
    get_obs_sync_executable,
    repair_agent,
    describe_interval,
    describe_schedule,
    CalendarSchedule,
    PLIST_VERSION,
    SCHEDULE_PRESETS,
)
from obs_sync.core.paths import get_path_manager


class AutomationCommand:
    """Command for managing automation (LaunchAgent) settings."""

    def __init__(self, config: SyncConfig, verbose: bool = False):
        """Initialize automation command.

        Args:
            config: Sync configuration
            verbose: Enable verbose output
        """
        self.config = config
        self.verbose = verbose

    def run(
        self,
        action: str = "status",
        force: bool = False,
    ) -> bool:
        """Run the automation command.

        Args:
            action: Action to perform ("status", "repair", "logs")
            force: Force repair even if not needed

        Returns:
            True if successful, False otherwise
        """
        if not is_macos():
            print("⚠️  Automation is only available on macOS.")
            return False

        if action == "status":
            return self._show_status()
        elif action == "repair":
            return self._repair_agent(force=force)
        elif action == "logs":
            return self._show_logs()
        else:
            print(f"❌ Unknown action: {action}")
            print("Available actions: status, repair, logs")
            return False

    def _show_status(self) -> bool:
        """Show detailed automation status."""
        print("🤖 Automation Status")
        print("=" * 50)

        # Get agent status
        status = get_agent_status()

        # Plist location
        print(f"\n📂 Plist location: {status.plist_path}")

        # Installation status
        if status.is_installed:
            print(f"✅ Installed: Yes")
            if status.plist_version:
                version_status = ""
                if status.is_outdated:
                    version_status = f" (OUTDATED - current: {PLIST_VERSION})"
                print(f"   Version: {status.plist_version}{version_status}")
        else:
            print("❌ Installed: No")

        # Loaded status
        if status.is_loaded:
            print("✅ Loaded: Yes (running)")
            if status.pid:
                print(f"   PID: {status.pid}")
            if status.last_exit_status is not None:
                exit_msg = "OK" if status.last_exit_status == 0 else f"Error ({status.last_exit_status})"
                print(f"   Last exit: {exit_msg}")
        else:
            print("⏸️  Loaded: No (not running)")

        # Schedule info
        print(f"\n📅 Schedule Configuration:")
        if status.schedule_type == "interval" and status.interval_seconds:
            print(f"   Type: Interval-based (StartInterval)")
            print(f"   Runs: {describe_interval(status.interval_seconds)}")
        elif status.schedule_type == "calendar" and status.calendar_schedules:
            print(f"   Type: Calendar-based (StartCalendarInterval)")
            for i, sched in enumerate(status.calendar_schedules, 1):
                print(f"   Schedule {i}: {sched.describe()}")
        else:
            print("   No schedule detected")

        # Config vs installed comparison
        print(f"\n⚙️  Configuration:")
        print(f"   Automation enabled: {'Yes' if self.config.automation_enabled else 'No'}")
        print(f"   Schedule type: {self.config.automation_schedule_type}")
        if self.config.automation_schedule_type == "interval":
            print(f"   Interval: {describe_interval(self.config.automation_interval)}")
        elif self.config.automation_calendar_schedules:
            print(f"   Calendar schedules: {len(self.config.automation_calendar_schedules)}")
        print(f"   Keep alive: {'Yes' if self.config.automation_keep_alive else 'No'}")
        if self.config.automation_env_vars:
            print(f"   Custom env vars: {len(self.config.automation_env_vars)}")

        # Sync status check
        print(f"\n🔄 Sync Status:")
        issues = []

        if self.config.automation_enabled and not status.is_installed:
            issues.append("Config enabled but agent not installed")
        elif not self.config.automation_enabled and status.is_installed:
            issues.append("Config disabled but agent is installed")

        if status.is_installed and not status.is_loaded:
            issues.append("Agent installed but not loaded")

        if status.is_outdated:
            issues.append(f"Plist version outdated (have {status.plist_version}, want {PLIST_VERSION})")

        if status.last_exit_status and status.last_exit_status != 0:
            issues.append(f"Last run failed with exit code {status.last_exit_status}")

        if issues:
            print("   ⚠️  Issues detected:")
            for issue in issues:
                print(f"      • {issue}")
            print("\n💡 Run 'obs-sync automation repair' to fix these issues")
        else:
            print("   ✅ All good!")

        # Log locations
        path_manager = get_path_manager()
        log_dir = path_manager.log_dir
        print(f"\n📝 Log files:")
        print(f"   stdout: {log_dir}/obs-sync-agent.stdout.log")
        print(f"   stderr: {log_dir}/obs-sync-agent.stderr.log")

        if status.error_message:
            print(f"\n❌ Error: {status.error_message}")

        return True

    def _repair_agent(self, force: bool = False) -> bool:
        """Repair the automation agent."""
        print("🔧 Automation Repair")
        print("=" * 50)

        if not self.config.automation_enabled and not force:
            print("\n⚠️  Automation is disabled in configuration.")
            print("Enable it first with 'obs-sync setup --reconfigure'")
            print("Or use --force to repair anyway.")
            return False

        # Get current status
        status = get_agent_status()

        if not status.needs_repair() and not force:
            print("\n✅ Agent appears healthy, no repair needed.")
            print("Use --force to repair anyway.")
            return True

        print("\n🔄 Repairing automation agent...")

        # Find executable
        obs_sync_path = get_obs_sync_executable()
        if not obs_sync_path:
            print("\n❌ Could not find obs-sync executable.")
            print("Ensure obs-sync is installed and in your PATH.")
            return False

        print(f"   Using executable: {obs_sync_path}")

        # Get paths
        path_manager = get_path_manager()
        log_dir = path_manager.log_dir
        working_dir = path_manager.working_dir

        # Prepare schedule
        calendar_schedules = None
        interval_seconds = None

        if self.config.automation_schedule_type == "calendar" and self.config.automation_calendar_schedules:
            calendar_schedules = [
                CalendarSchedule.from_dict(s)
                for s in self.config.automation_calendar_schedules
            ]
            print(f"   Schedule: calendar-based ({len(calendar_schedules)} entries)")
        else:
            interval_seconds = self.config.automation_interval
            print(f"   Schedule: {describe_interval(interval_seconds)}")

        # Perform repair
        success, error = repair_agent(
            interval_seconds=interval_seconds,
            calendar_schedules=calendar_schedules,
            obs_sync_path=obs_sync_path,
            log_dir=log_dir,
            working_dir=working_dir,
            env_vars=self.config.automation_env_vars or None,
            keep_alive=self.config.automation_keep_alive,
            throttle_interval=self.config.automation_throttle_interval,
        )

        if success:
            print("\n✅ Agent repaired successfully!")
            print(f"   Logs: {log_dir}/obs-sync-agent.*.log")
            return True
        else:
            print(f"\n❌ Repair failed: {error}")
            return False

    def _show_logs(self) -> bool:
        """Show recent log entries."""
        import subprocess

        path_manager = get_path_manager()
        log_dir = path_manager.log_dir
        stdout_log = log_dir / "obs-sync-agent.stdout.log"
        stderr_log = log_dir / "obs-sync-agent.stderr.log"

        print("📝 Recent Automation Logs")
        print("=" * 50)

        for log_name, log_path in [("stdout", stdout_log), ("stderr", stderr_log)]:
            print(f"\n--- {log_name} ({log_path}) ---")

            if not log_path.exists():
                print("   (file does not exist)")
                continue

            try:
                # Show last 20 lines
                result = subprocess.run(
                    ["tail", "-20", str(log_path)],
                    capture_output=True,
                    text=True,
                    check=False
                )
                if result.stdout:
                    for line in result.stdout.strip().split("\n"):
                        print(f"   {line}")
                else:
                    print("   (empty)")
            except Exception as e:
                print(f"   Error reading log: {e}")

        return True
