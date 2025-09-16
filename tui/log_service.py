#!/usr/bin/env python3
"""
Log Service - Manages application logging and log viewing.

This service handles log management, log tailing, and finding run summaries
from the observability system.
"""

from __future__ import annotations

import time
import os
from typing import List, Optional
from pathlib import Path

from lib.observability import tail_logs


class LogService:
    """Manages application logging and log viewing."""

    def __init__(self, config_service):
        self.config_service = config_service
        self.log: List[str] = []
        self.log_max_lines = 500  # Prevent unbounded log growth

    def log_line(self, s: str) -> None:
        """Add a line to the application log with timestamp and bounds checking."""
        ts = time.strftime("%H:%M:%S")
        # Safely convert input to string to avoid format string errors with dict objects
        safe_s = str(s) if s is not None else "None"
        line = f"[{ts}] {safe_s}"
        self.log.append(line)

        # Trim log if it exceeds maximum lines (more efficient than pop(0))
        if len(self.log) > self.log_max_lines:
            self.log = self.log[-self.log_max_lines:]

        # Update last summary in preferences
        prefs = self.config_service.get_preferences()
        if prefs:
            prefs.last_summary = line
            self.config_service.save_preferences(prefs)

    def get_log_lines(self, count: Optional[int] = None) -> List[str]:
        """
        Get log lines.

        Args:
            count: Number of lines to return (None for all)

        Returns:
            List of log lines
        """
        if count is None:
            return self.log.copy()
        return self.log[-count:] if count > 0 else []

    def clear_log(self) -> None:
        """Clear the application log."""
        self.log = []

    def tail_component_logs(self, component: str, operation_name: Optional[str] = None) -> List[str]:
        """
        Tail logs for a specific component.

        Args:
            component: Component name to tail logs for
            operation_name: Optional operation name for context

        Returns:
            List of log lines
        """
        try:
            log_lines = tail_logs(component, n=50)
            if log_lines:
                if operation_name:
                    self.log_line(f"=== Recent {operation_name} logs ===")
                for line in log_lines:
                    self.log_line(line)
            return log_lines
        except Exception as e:
            error_msg = f"Could not read {component} logs: {e}"
            self.log_line(error_msg)
            return [error_msg]

    def find_latest_run_summary(self, component: str) -> Optional[str]:
        """
        Find the latest run summary for a component.

        Args:
            component: Component name to find summary for

        Returns:
            Summary string or None if not found
        """
        try:
            log_lines = tail_logs(component, n=100)
            if not log_lines:
                return None

            # Look for completion messages in reverse order
            for line in reversed(log_lines):
                line_lower = line.lower()
                if "completed" in line_lower and "after" in line_lower:
                    return line
                elif "failed" in line_lower and "after" in line_lower:
                    return line
                elif "error" in line_lower and component in line_lower:
                    return line

            return None
        except Exception:
            return None

    def get_log_file_path(self, component: str) -> Optional[Path]:
        """
        Get the path to a component's log file.

        Args:
            component: Component name

        Returns:
            Path to log file or None if not found
        """
        log_dir = Path.home() / ".obs-tools" / "logs"
        log_file = log_dir / f"{component}.log"

        if log_file.exists():
            return log_file
        return None

    def get_log_file_size(self, component: str) -> int:
        """
        Get the size of a component's log file.

        Args:
            component: Component name

        Returns:
            Size in bytes or 0 if not found
        """
        log_path = self.get_log_file_path(component)
        if log_path and log_path.exists():
            return log_path.stat().st_size
        return 0

    def rotate_logs_if_needed(self, component: str, max_size_mb: int = 10) -> bool:
        """
        Rotate log file if it exceeds max size.

        Args:
            component: Component name
            max_size_mb: Maximum size in megabytes

        Returns:
            True if rotation occurred
        """
        log_path = self.get_log_file_path(component)
        if not log_path or not log_path.exists():
            return False

        size_bytes = log_path.stat().st_size
        max_bytes = max_size_mb * 1024 * 1024

        if size_bytes > max_bytes:
            # Rotate the log
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            rotated_path = log_path.with_suffix(f".{timestamp}.log")
            log_path.rename(rotated_path)

            # Keep only last 3 rotated logs
            log_dir = log_path.parent
            rotated_logs = sorted(log_dir.glob(f"{component}.*.log"))
            if len(rotated_logs) > 3:
                for old_log in rotated_logs[:-3]:
                    old_log.unlink()

            return True
        return False