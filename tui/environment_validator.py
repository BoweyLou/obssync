#!/usr/bin/env python3
"""
Environment Validator - Validates runtime environment and dependencies.

This service handles validation of the runtime environment, including
checking for required dependencies like EventKit and validating Python paths.
"""

from __future__ import annotations

import os
import subprocess
from typing import Tuple, Optional


class EnvironmentValidator:
    """Validates runtime environment and dependencies."""

    def __init__(self, config_service):
        self.config_service = config_service
        self._eventkit_available = None  # Cache result

    def validate_eventkit_availability(self) -> bool:
        """Validate that EventKit is available in the managed Python environment."""
        if self._eventkit_available is not None:
            return self._eventkit_available

        try:
            python_path = self.config_service.get_managed_python_path()
            result = subprocess.run([
                python_path, "-c",
                "import objc, EventKit; print('OK')"
            ], capture_output=True, text=True, timeout=5)

            self._eventkit_available = (result.stdout.strip() == "OK")
            return self._eventkit_available
        except Exception:
            self._eventkit_available = False
            return False

    def validate_sync_environment(self) -> Tuple[bool, list]:
        """
        Validate the sync environment is properly configured.

        Returns:
            Tuple of (all_valid, list_of_issues)
        """
        issues = []
        paths = self.config_service.get_paths()

        # Check Obsidian config
        obs_config = os.path.expanduser(paths.get("obsidian_vaults", ""))
        if not os.path.exists(obs_config):
            issues.append("Obsidian vaults not configured (run 'Discover Vaults')")

        # Check Reminders config
        rem_config = os.path.expanduser(paths.get("reminders_lists", ""))
        if not os.path.exists(rem_config):
            issues.append("Reminders lists not configured (run 'Discover Reminders')")

        # Check EventKit for macOS
        import platform
        if platform.system() == "Darwin":
            if not self.validate_eventkit_availability():
                issues.append("EventKit not available (run 'Setup Dependencies')")

        # Check for indices
        obs_index = os.path.expanduser(paths.get("obsidian_index", ""))
        if not os.path.exists(obs_index):
            issues.append("Obsidian index not built (run 'Collect Obsidian')")

        rem_index = os.path.expanduser(paths.get("reminders_index", ""))
        if not os.path.exists(rem_index):
            issues.append("Reminders index not built (run 'Collect Reminders')")

        return (len(issues) == 0, issues)

    def check_eventkit_before_reminders_operation(self, operation_name: str) -> Tuple[bool, Optional[str]]:
        """
        Check EventKit availability before a Reminders operation.

        Args:
            operation_name: Name of the operation for error messages

        Returns:
            Tuple of (can_proceed, error_message)
        """
        import platform

        if platform.system() != "Darwin":
            return False, f"{operation_name} requires macOS (EventKit not available on this platform)"

        if not self.validate_eventkit_availability():
            return False, f"{operation_name} requires EventKit. Run 'Setup Dependencies' first."

        return True, None

    def validate_file_exists(self, file_path: str, description: str) -> Tuple[bool, Optional[str]]:
        """
        Validate that a required file exists.

        Args:
            file_path: Path to check
            description: Description for error message

        Returns:
            Tuple of (exists, error_message)
        """
        expanded_path = os.path.expanduser(file_path)
        if not os.path.exists(expanded_path):
            return False, f"{description} not found at {file_path}"
        return True, None

    def get_python_version(self) -> str:
        """Get the Python version of the managed environment."""
        try:
            python_path = self.config_service.get_managed_python_path()
            result = subprocess.run([
                python_path, "--version"
            ], capture_output=True, text=True, timeout=5)
            return result.stdout.strip() or result.stderr.strip()
        except Exception as e:
            return f"Unknown (error: {e})"