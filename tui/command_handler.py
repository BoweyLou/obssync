#!/usr/bin/env python3
"""
Command Handler - Orchestrates command execution for sync operations.

This service handles the execution of various sync commands, managing
their dependencies and orchestrating complex multi-step operations.
"""

from __future__ import annotations

import os
from typing import List, Callable, Optional, Dict, Any
from pathlib import Path


class CommandHandler:
    """Orchestrates command execution for sync operations."""

    def __init__(self, service_manager, config_service, environment_validator, log_service):
        self.service_manager = service_manager
        self.config_service = config_service
        self.environment_validator = environment_validator
        self.log_service = log_service

    def execute_discover_vaults(self, callback: Optional[Callable] = None) -> None:
        """Execute vault discovery operation."""
        paths = self.config_service.get_paths()
        args = [
            self.config_service.get_managed_python_path(),
            "obs_tools.py",
            "vaults", "discover",
            "--config", paths["obsidian_config"]
        ]
        self.service_manager.run_interactive(args, "Vault discovery", None, self.log_service.log_line)
        if callback:
            callback()

    def execute_discover_reminders(self, callback: Optional[Callable] = None) -> None:
        """Execute reminders discovery operation."""
        # Check EventKit first
        can_proceed, error = self.environment_validator.check_eventkit_before_reminders_operation("Discover Reminders")
        if not can_proceed:
            self.log_service.log_line(error)
            if callback:
                callback()
            return

        paths = self.config_service.get_paths()
        args = [
            self.config_service.get_managed_python_path(),
            "obs_tools.py",
            "reminders", "discover",
            "--config", paths["reminders_config"]
        ]
        self.service_manager.run_interactive(args, "Reminders discovery", None, self.log_service.log_line)
        if callback:
            callback()

    def execute_collect_obsidian(self, callback: Optional[Callable] = None,
                                  ignore_common: bool = True) -> None:
        """Execute Obsidian task collection."""
        paths = self.config_service.get_paths()
        args = [
            self.config_service.get_managed_python_path(),
            "obs_tools.py",
            "tasks", "collect",
            "--use-config",
            "--config", paths["obsidian_config"],
            "--output", paths["obsidian_index"]
        ]
        if ignore_common:
            args.append("--ignore-common")

        def completion_callback():
            self.log_service.tail_component_logs("collect_obsidian", "Obsidian collection")
            if callback:
                callback()

        self.service_manager.run_command(args, self.log_service.log_line, completion_callback)

    def execute_collect_reminders(self, callback: Optional[Callable] = None) -> None:
        """Execute Reminders task collection."""
        # Check EventKit first
        can_proceed, error = self.environment_validator.check_eventkit_before_reminders_operation("Collect Reminders")
        if not can_proceed:
            self.log_service.log_line(error)
            if callback:
                callback()
            return

        paths = self.config_service.get_paths()
        args = [
            self.config_service.get_managed_python_path(),
            "obs_tools.py",
            "reminders", "collect",
            "--config", paths["reminders_config"],
            "--output", paths["reminders_index"],
            "--use-hybrid"
        ]

        def completion_callback():
            self.log_service.tail_component_logs("collect_reminders", "Reminders collection")
            if callback:
                callback()

        self.service_manager.run_command(args, self.log_service.log_line, completion_callback)

    def execute_build_links(self, callback: Optional[Callable] = None,
                            min_score: Optional[float] = None,
                            include_done: bool = False) -> None:
        """Execute link building operation."""
        paths = self.config_service.get_paths()
        prefs = self.config_service.get_preferences()

        args = [
            self.config_service.get_managed_python_path(),
            "obs_tools.py",
            "sync", "suggest",
            "--obs", paths["obsidian_index"],
            "--rem", paths["reminders_index"],
            "--output", paths["sync_links"]
        ]

        if min_score is not None:
            args.extend(["--min-score", str(min_score)])
        elif hasattr(prefs, 'min_score'):
            args.extend(["--min-score", str(prefs.min_score)])

        if include_done or getattr(prefs, 'include_done', False):
            args.append("--include-done")

        def completion_callback():
            self.log_service.tail_component_logs("build_sync_links", "Link building")
            if callback:
                callback()

        self.service_manager.run_command(args, self.log_service.log_line, completion_callback)

    def execute_sync_apply(self, callback: Optional[Callable] = None) -> None:
        """Execute sync apply operation."""
        paths = self.config_service.get_paths()
        args = [
            self.config_service.get_managed_python_path(),
            "obs_tools.py",
            "sync", "apply",
            "--links", paths["sync_links"],
            "--obs-index", paths["obsidian_index"],
            "--rem-index", paths["reminders_index"],
            "--obs-config", paths["obsidian_config"],
            "--rem-config", paths["reminders_config"]
        ]

        def completion_callback():
            self.log_service.tail_component_logs("sync_links_apply", "Sync apply")
            if callback:
                callback()

        self.service_manager.run_command(args, self.log_service.log_line, completion_callback)

    def execute_create_counterparts(self, direction: str, since_days: Optional[int] = None,
                                     apply: bool = False, callback: Optional[Callable] = None) -> None:
        """Execute create missing counterparts operation."""
        paths = self.config_service.get_paths()
        args = [
            self.config_service.get_managed_python_path(),
            "obs_tools.py",
            "sync", "create",
            "--obs-index", paths["obsidian_index"],
            "--rem-index", paths["reminders_index"],
            "--links", paths["sync_links"],
            "--obs-config", paths["obsidian_config"],
            "--rem-config", paths["reminders_config"],
            "--direction", direction
        ]

        if since_days is not None:
            args.extend(["--since", str(since_days)])

        if apply:
            args.append("--apply")
        else:
            args.append("--dry-run")

        self.service_manager.run_command(args, self.log_service.log_line, callback)

    def execute_update_all(self, skip_obs: bool = False, skip_rem: bool = False,
                           skip_links: bool = False, apply: bool = False,
                           callback: Optional[Callable] = None) -> None:
        """Execute full update operation."""
        paths = self.config_service.get_paths()
        prefs = self.config_service.get_preferences()

        args = [
            self.config_service.get_managed_python_path(),
            "obs_tools.py",
            "sync", "update",
            "--obs-config", paths["obsidian_config"],
            "--rem-config", paths["reminders_config"],
            "--obs-output", paths["obsidian_index"],
            "--rem-output", paths["reminders_index"],
            "--links-output", paths["sync_links"]
        ]

        if skip_obs:
            args.append("--skip-obs")
        if skip_rem:
            args.append("--skip-rem")
        if skip_links:
            args.append("--skip-links")

        if getattr(prefs, 'include_done', False):
            args.append("--include-done")
        if getattr(prefs, 'prune_days', None) is not None:
            args.extend(["--prune-days", str(prefs.prune_days)])

        def completion_callback():
            self.log_service.tail_component_logs("update_indices_and_links", "Update")
            if apply:
                # Chain to apply operation
                self.execute_sync_apply(callback)
            elif callback:
                callback()

        self.service_manager.run_command(args, self.log_service.log_line, completion_callback)

    def execute_calendar_sync(self, date: Optional[str] = None, callback: Optional[Callable] = None) -> None:
        """Execute calendar sync to daily note."""
        paths = self.config_service.get_paths()
        args = [
            self.config_service.get_managed_python_path(),
            "obs_tools.py",
            "calendar", "sync",
            "--vault-config", paths["obsidian_config"]
        ]

        if date:
            args.extend(["--date", date])

        self.service_manager.run_command(args, self.log_service.log_line, callback)

    def execute_fix_block_ids(self, apply: bool = False, backup: bool = True,
                               callback: Optional[Callable] = None) -> None:
        """Execute fix block IDs operation."""
        paths = self.config_service.get_paths()
        prefs = self.config_service.get_preferences()

        args = [
            self.config_service.get_managed_python_path(),
            "obs_tools.py",
            "ids", "remove",
            "--use-config",
            "--config", paths["obsidian_config"]
        ]

        if apply:
            args.append("--apply")
        if backup:
            args.append("--backup")
        if getattr(prefs, 'ignore_common', True):
            args.append("--ignore-common")

        self.service_manager.run_command(args, self.log_service.log_line, callback)

    def execute_find_duplicates(self, callback: Optional[Callable] = None) -> None:
        """Execute duplicate finder operation."""
        paths = self.config_service.get_paths()
        args = [
            self.config_service.get_managed_python_path(),
            "obs_tools.py",
            "duplicates", "find",
            "--obs-index", paths["obsidian_index"],
            "--rem-index", paths["reminders_index"]
        ]

        self.service_manager.run_command(args, self.log_service.log_line, callback)

    def execute_reset(self, callback: Optional[Callable] = None) -> None:
        """Execute reset operation."""
        args = [
            self.config_service.get_managed_python_path(),
            "obs_tools.py",
            "reset"
        ]
        self.service_manager.run_command(args, self.log_service.log_line, callback)

    def execute_setup_dependencies(self, callback: Optional[Callable] = None) -> None:
        """Execute dependency setup."""
        args = [
            self.config_service.get_managed_python_path(),
            "obs_tools.py",
            "setup"
        ]
        self.service_manager.run_command(args, self.log_service.log_line, callback)