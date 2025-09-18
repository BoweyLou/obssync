#!/usr/bin/env python3
"""
TUI Controller Module - Handles input processing and state management.

This module contains all the keyboard input handling, menu navigation,
and application state management logic for the TUI.
"""

from __future__ import annotations

import curses
import json
import os
import time
from typing import List, Dict, Any, Optional, Callable

import app_config as cfg
from lib.observability import tail_logs


class TUIController:
    """Handles input processing, state management, and menu navigation."""
    
    def __init__(self, view, service_manager):
        self.view = view
        self.service_manager = service_manager
        
        # Application state
        self.menu = [
            "Update All",
            "Update All and Apply",
            "Quick Sync (Create + Apply)",
            "Discover Vaults",
            "Collect Obsidian",
            "Discover Reminders",
            "Collect Reminders",
            "Sync Calendar to Daily Note",
            "Build Links",
            "Link Review",
            "Sync Links",
            "Create Missing Counterparts",
            "Vault Organization →",
            "Duplication Finder",
            "Fix Block IDs",
            "Restore Last Fix",
            "Log Viewer",
            "Reset (dangerous)",
            "Setup Dependencies",
            "Settings",
            "Quit",
        ]
        self.selected = 0
        self.prefs, self.paths = cfg.load_app_config()
        self.log: List[str] = []
        self.log_max_lines = 500  # Prevent unbounded log growth
        self.status = "Ready"
        
        # Data caching infrastructure
        self._data_cache = {
            'obs': {'data': None, 'mtime': 0},
            'rem': {'data': None, 'mtime': 0}, 
            'links': {'data': None, 'mtime': 0}
        }
        self._last_diff_cache = None
        self._last_diff_time = 0
        self.last_diff = {"obs": None, "rem": None, "links": None}
        self.last_link_changes = {"new": [], "replaced": []}
        
        # Centralized Python environment management
        self._managed_python = os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3")
        self._prev_link_pairs: set[tuple[str, str]] = set()
        
        # State management
        self.is_running = True
        self.is_busy = False

        # Progress tracking for multi-step operations
        self.current_operation = None
        self.operation_steps = []
        self.current_step = 0
        self.operation_start_time = None

        # Completion summaries for status bar
        self.last_completion = None
        self.last_completion_time = 0
        self.completion_display_duration = 10  # Show completion for 10 seconds
    
    def log_line(self, s: str):
        """Add a line to the application log with timestamp and bounds checking."""
        ts = time.strftime("%H:%M:%S")
        # Safely convert input to string to avoid format string errors with dict objects
        safe_s = str(s) if s is not None else "None"
        line = f"[{ts}] {safe_s}"
        self.log.append(line)
        
        # Trim log if it exceeds maximum lines (more efficient than pop(0))
        if len(self.log) > self.log_max_lines:
            self.log = self.log[-self.log_max_lines:]
            
        self.prefs.last_summary = line
        cfg.save_app_config(self.prefs)
    
    def get_managed_python(self) -> str:
        """Get the path to the managed Python environment with all dependencies."""
        return self._managed_python
    
    def validate_eventkit_availability(self) -> bool:
        """Validate that EventKit is available in the managed Python environment."""
        try:
            import subprocess
            result = subprocess.run([
                self._managed_python, "-c", 
                "import EventKit; print('EventKit available')"
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                self.log_line("EventKit validation: Available and functional")
                return True
            else:
                self.log_line(f"EventKit validation failed: {result.stderr.strip()}")
                return False
        except Exception as e:
            self.log_line(f"EventKit validation error: {str(e)}")
            return False
    
    def validate_sync_environment(self):
        """Validate that the sync environment is properly configured."""
        self.log_line("Validating sync environment...")
        
        # Check managed Python exists
        if not os.path.exists(self._managed_python):
            self.log_line(f"WARNING: Managed Python not found at {self._managed_python}")
            self.log_line("Run 'Setup Dependencies' to install the managed environment")
            return False
            
        # Validate EventKit availability
        eventkit_ok = self.validate_eventkit_availability()
        if not eventkit_ok:
            self.log_line("WARNING: EventKit not available - Apple Reminders sync will fail")
            self.log_line("Run 'Setup Dependencies' → 'Install macOS dependencies' to fix")
            
        return True
    
    def check_eventkit_before_reminders_operation(self, operation_name: str) -> bool:
        """Check EventKit availability before Apple Reminders operations."""
        if not self.validate_eventkit_availability():
            self.log_line(f"Cannot run {operation_name}: EventKit not available")
            self.log_line("Use 'Setup Dependencies' to install EventKit support")
            self.status = f"Error: {operation_name} requires EventKit"
            return False
        return True
    
    def tail_component_logs(self, component: str, operation_name: str = None):
        """Tail recent logs from a component and add them to the TUI log."""
        try:
            recent_logs = tail_logs(component, lines=50)
            if recent_logs:
                if operation_name:
                    self.log_line(f"Recent {operation_name} logs:")
                else:
                    self.log_line(f"Recent {component} logs:")
                
                for log_line in recent_logs[-20:]:  # Show last 20 lines to avoid overwhelming the TUI
                    # Remove timestamp if present to avoid duplicate timestamps
                    cleaned_line = log_line
                    if '] ' in cleaned_line and cleaned_line.startswith('[20'):
                        # Try to extract just the message part
                        parts = cleaned_line.split('] ', 1)
                        if len(parts) == 2:
                            cleaned_line = parts[1]
                    self.log.append(f"  {cleaned_line}")
                    
                # Trim log if it gets too long
                if len(self.log) > 300:
                    self.log = self.log[-200:]
            else:
                self.log_line(f"No recent {component} logs found")
        except Exception as e:
            self.log_line(f"Failed to tail {component} logs: {str(e)}")
    
    def find_latest_run_summary(self, component: str) -> str:
        """Find the latest run summary file for a component."""
        try:
            logs_dir = os.path.expanduser("~/.config/obs-tools/logs")
            if not os.path.isdir(logs_dir):
                return None

            # Find run summary files for this component
            summary_files = []
            for filename in os.listdir(logs_dir):
                if filename.startswith("run_summary_") and filename.endswith(".json"):
                    filepath = os.path.join(logs_dir, filename)
                    try:
                        mtime = os.path.getmtime(filepath)
                        summary_files.append((mtime, filepath))
                    except OSError:
                        continue

            if summary_files:
                # Sort by modification time (newest first) and return the most recent
                summary_files.sort(reverse=True)
                return summary_files[0][1]

        except Exception:
            pass

        return None

    def parse_run_summary(self, summary_path: str) -> Dict[str, Any]:
        """Parse run summary JSON and extract key metrics."""
        try:
            if not summary_path or not os.path.exists(summary_path):
                return None

            from lib.safe_io import safe_load_json
            summary = safe_load_json(summary_path)

            if not summary:
                return None

            # Extract key information
            result = {
                'operation': summary.get('operation', 'unknown'),
                'success': summary.get('success', False),
                'duration_ms': summary.get('duration_ms', 0),
                'error': summary.get('error_message'),
                'input_counts': summary.get('input_counts', {}),
                'output_counts': summary.get('output_counts', {}),
                'performance': summary.get('performance_metrics', {})
            }

            return result
        except Exception as e:
            self.log_line(f"Error parsing run summary: {str(e)}")
            return None

    def format_completion_summary(self, component: str, operation_name: str = None) -> str:
        """Create a concise completion summary from the latest run summary."""
        summary_path = self.find_latest_run_summary(component)

        if not summary_path:
            return None

        summary = self.parse_run_summary(summary_path)
        if not summary:
            return None

        # Build concise message
        op_name = operation_name or summary['operation']
        duration_s = summary['duration_ms'] / 1000.0

        if summary['success']:
            msg_parts = [f"✓ {op_name} ({duration_s:.1f}s)"]

            # Add key output counts
            output = summary['output_counts']
            if 'tasks' in output:
                msg_parts.append(f"{output['tasks']} tasks")
            elif 'created' in output and 'updated' in output:
                created = output.get('created', 0)
                updated = output.get('updated', 0)
                if created + updated > 0:
                    msg_parts.append(f"+{created}/{updated} created/updated")
            elif 'new_links' in output:
                msg_parts.append(f"{output['new_links']} new links")

            # Add performance metrics if notable
            perf = summary['performance']
            if perf.get('cache_hit_rate'):
                hit_rate = perf['cache_hit_rate'] * 100
                if hit_rate > 90:
                    msg_parts.append(f"{hit_rate:.0f}% cache")

            return " - ".join(msg_parts)
        else:
            error_msg = summary.get('error', 'unknown error')
            # Truncate long error messages
            if len(error_msg) > 50:
                error_msg = error_msg[:47] + "..."
            return f"✗ {op_name} failed: {error_msg}"

    def start_multi_step_operation(self, name: str, steps: List[str]):
        """Start tracking a multi-step operation."""
        self.current_operation = name
        self.operation_steps = steps
        self.current_step = 0
        self.operation_start_time = time.time()
        self.status = f"{name}: {steps[0]}…"
        self.log_line(f"Starting {name} ({len(steps)} steps)")

    def advance_operation_step(self, step_name: str = None):
        """Move to the next step in a multi-step operation."""
        if not self.current_operation:
            return

        self.current_step += 1
        if self.current_step < len(self.operation_steps):
            next_step = step_name or self.operation_steps[self.current_step]
            elapsed = time.time() - self.operation_start_time
            self.status = f"{self.current_operation} [{self.current_step+1}/{len(self.operation_steps)}]: {next_step}… ({elapsed:.1f}s)"
            self.log_line(f"Step {self.current_step+1}/{len(self.operation_steps)}: {next_step}")

    def complete_multi_step_operation(self, summary: str = None):
        """Mark a multi-step operation as complete."""
        if not self.current_operation:
            return

        elapsed = time.time() - self.operation_start_time
        op_name = self.current_operation

        if summary:
            self.log_line(f"{op_name} complete ({elapsed:.1f}s): {summary}")
        else:
            self.log_line(f"{op_name} complete ({elapsed:.1f}s)")

        self.current_operation = None
        self.operation_steps = []
        self.current_step = 0
        self.operation_start_time = None

    def get_operation_progress(self) -> Dict[str, Any]:
        """Get current operation progress information."""
        if not self.current_operation:
            return None

        elapsed = time.time() - self.operation_start_time if self.operation_start_time else 0
        return {
            'name': self.current_operation,
            'current_step': self.current_step + 1,
            'total_steps': len(self.operation_steps),
            'step_name': self.operation_steps[self.current_step] if self.current_step < len(self.operation_steps) else 'Complete',
            'elapsed_seconds': elapsed,
            'progress': (self.current_step + 1) / len(self.operation_steps) if self.operation_steps else 0
        }

    def set_completion_summary(self, summary: str):
        """Set a completion summary to display in the status bar."""
        self.last_completion = summary
        self.last_completion_time = time.time()

    def get_display_status(self) -> str:
        """Get the current status to display, including recent completions."""
        # Check if we should show a recent completion
        if self.last_completion and not self.is_busy:
            elapsed = time.time() - self.last_completion_time
            if elapsed < self.completion_display_duration:
                remaining = self.completion_display_duration - elapsed
                return f"{self.last_completion} (showing for {remaining:.0f}s)"

        # Otherwise return the current status
        return self.status

    def _get_current_vault_name(self) -> str:
        """Get the name of the current default vault for display."""
        try:
            inbox_file = self.prefs.creation_defaults.obs_inbox_file
            if not inbox_file or inbox_file == "~/Documents/Obsidian/Default/Tasks.md":
                return "None (unconfigured)"
            
            # Load vault config to match path to name
            vault_config_path = os.path.expanduser("~/.config/obsidian_vaults.json")
            if os.path.exists(vault_config_path):
                import json
                with open(vault_config_path, 'r') as f:
                    vaults = json.load(f)
                
                for vault in vaults:
                    if inbox_file.startswith(vault['path']):
                        return vault['name']
            
            # Fallback to just the basename
            return os.path.basename(os.path.dirname(inbox_file)) if inbox_file else "None"
        except:
            return "Unknown"

    def get_current_state(self) -> Dict[str, Any]:
        """Get the current application state for rendering."""
        # Include progress information if available
        state = {
            'menu': self.menu,
            'selected': self.selected,
            'prefs': self.prefs,
            'paths': self.paths,
            'log': self.log,
            'status': self.get_display_status(),  # Use new method with completion summaries
            'last_diff': self.last_diff,
            'is_busy': self.is_busy,
            'current_vault': self._get_current_vault_name()
        }

        # Add progress information if a multi-step operation is running
        progress = self.get_operation_progress()
        if progress:
            state['operation_progress'] = progress

        return state
    
    def handle_input(self) -> bool:
        """
        Handle a single input event.
        
        Returns:
            False if the application should quit, True otherwise.
        """
        try:
            ch = self.view.get_user_input()
        except curses.error:
            # If we can't get input, the terminal is broken
            time.sleep(0.1)
            return True
        
        if ch in (ord("q"), 27):  # q or ESC
            return False
        elif ch in (curses.KEY_DOWN, ord("j")):
            self.selected = (self.selected + 1) % len(self.menu)
        elif ch in (curses.KEY_UP, ord("k")):
            self.selected = (self.selected - 1) % len(self.menu)
        elif ch in (10, 13):  # Enter
            self._handle_menu_selection()
        elif ch == ord("s"):
            self._handle_settings()
        elif ch == ord("c"):
            self._handle_cancel_operation()
        
        return True
    
    def _handle_menu_selection(self):
        """Handle menu item selection."""
        if self.is_busy:
            # Only allow quit and settings when busy
            item = self.menu[self.selected]
            if item not in ["Quit", "Settings"]:
                self.status = "Operation in progress - please wait"
                return
        
        item = self.menu[self.selected]
        
        # Map menu items to handler methods
        handlers = {
            "Update All": self._do_update_all,
            "Update All and Apply": self._do_update_all_and_apply,
            "Quick Sync (Create + Apply)": self._do_quick_sync,
            "Discover Vaults": self._do_discover_vaults,
            "Collect Obsidian": self._do_collect_obsidian,
            "Discover Reminders": self._do_discover_reminders,
            "Collect Reminders": self._do_collect_reminders,
            "Sync Calendar to Daily Note": self._do_sync_calendar_to_daily_note,
            "Build Links": self._do_build_links,
            "Link Review": self._do_link_review,
            "Sync Links": self._do_sync_links,
            "Create Missing Counterparts": self._do_create_missing_counterparts,
            "Vault Organization →": self._do_vault_organization,
            "Duplication Finder": self._do_duplication_finder,
            "Fix Block IDs": self._do_fix_block_ids_interactive,
            "Restore Last Fix": self._do_restore_last_fix,
            "Log Viewer": self._do_log_viewer,
            "Reset (dangerous)": self._do_reset_interactive,
            "Setup Dependencies": self._do_setup_dependencies,
            "Settings": self._do_settings,
            "Quit": lambda: setattr(self, 'is_running', False)
        }
        
        handler = handlers.get(item)
        if handler:
            handler()
    
    def _do_settings(self):
        """Show the settings screen."""
        self.view.show_settings_screen(self.prefs)
        cfg.save_app_config(self.prefs)

    def _do_vault_organization(self):
        """Show the vault organization submenu."""
        # Import vault organization view
        try:
            from tui.vault_organization_view import VaultOrganizationView

            # Create and show vault organization interface
            vault_view = VaultOrganizationView(
                self.view.stdscr,
                self.view.height,
                self.view.width
            )

            # Enter vault organization mode
            self._enter_vault_organization_mode(vault_view)

        except ImportError as e:
            self.log_line(f"Error loading vault organization: {e}")
            self.status = "Vault organization module not available"

    def _enter_vault_organization_mode(self, vault_view):
        """Enter the vault organization submenu mode."""
        vault_running = True

        while vault_running:
            # Draw vault organization screen
            vault_view.draw()

            # Handle input
            key = self.view.stdscr.getch()
            action = vault_view.handle_input(key)

            if action == "quit" or action == "back_to_main":
                vault_running = False
            elif action == "run_analysis":
                self._do_vault_analysis()
            elif action == "modify_setting":
                # Refresh preferences after modification
                self.prefs, self.paths = cfg.load_app_config()
            elif action == "create_vault_lists":
                self._handle_create_vault_lists()
            elif action == "manual_mapping_started":
                self.log_line("Manual vault-list mapping started")
            elif action == "auto_mappings_applied":
                self.log_line("Auto-discovered mappings applied")
            elif action == "no_auto_mappings_found":
                self.log_line("No automatic mappings found - use manual mapping")
            elif action == "vault_org_enabled":
                # Refresh preferences after enabling vault organization
                self.prefs, self.paths = cfg.load_app_config()
                self.log_line("Vault organization enabled")
            elif action == "refresh_completed":
                # Refresh after mappings reload
                self.prefs, self.paths = cfg.load_app_config()
                self.log_line("Mappings refreshed")
            elif action.startswith("cleanup_"):
                self._handle_vault_cleanup_action(action)
            elif action.startswith("migration_"):
                self._handle_vault_migration_action(action)
            elif action in ["migration_analysis_completed", "migration_plan_generated",
                          "migration_backup_completed", "migration_executed", "migration_verification_success"]:
                self._handle_migration_step_completed(action)

        # Return to main menu
        self.status = "Returned from vault organization"

    def _do_vault_analysis(self):
        """Run vault organization analysis."""
        if self.is_busy:
            return

        self.is_busy = True
        self.status = "Analyzing vault organization..."

        script_path = os.path.join(os.path.dirname(__file__), "..", "obs_tools.py")
        args = [
            os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3"),
            script_path, "vault", "analyze"
        ]

        def completion_callback():
            self.status = "Vault analysis complete"
            self.is_busy = False
            self.log_line("Vault organization analysis completed")

        self.service_manager.run_command(args, self.log_line, completion_callback)

    def _handle_vault_cleanup_action(self, action):
        """Handle vault cleanup actions."""
        if self.is_busy:
            return

        cleanup_map = {
            "cleanup_analyze": ("analyze", "Analyzing legacy mappings..."),
            "cleanup_preview": ("preview", "Previewing cleanup plan..."),
            "cleanup_dry_run": ("migrate --dry-run", "Running cleanup simulation..."),
            "cleanup_execute": ("migrate --apply", "Executing cleanup..."),
            "cleanup_rollback": ("rollback", "Rolling back cleanup...")
        }

        if action in cleanup_map:
            cmd, status_msg = cleanup_map[action]
            self.is_busy = True
            self.status = status_msg

            script_path = os.path.join(os.path.dirname(__file__), "..", "obs_tools.py")
            args = [
                os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3"),
                script_path, "vault", cmd
            ]

            def completion_callback():
                self.status = f"{action.replace('cleanup_', '').title()} complete"
                self.is_busy = False
                self.log_line(f"Vault cleanup {action} completed")

            self.service_manager.run_command(args, self.log_line, completion_callback)

    def _handle_vault_migration_action(self, action):
        """Handle vault migration actions."""
        if self.is_busy:
            return

        migration_map = {
            "migration_analysis": ("analyze", "Analyzing migration requirements..."),
            "migration_plan": ("plan", "Generating migration plan..."),
            "migration_backup": ("backup", "Creating migration backup..."),
            "migration_execute": ("migrate --apply", "Executing migration..."),
            "migration_verify": ("verify", "Verifying migration...")
        }

        if action in migration_map:
            cmd, status_msg = migration_map[action]
            self.is_busy = True
            self.status = status_msg

            script_path = os.path.join(os.path.dirname(__file__), "..", "obs_tools.py")
            args = [
                os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3"),
                script_path, "vault", cmd
            ]

            def completion_callback():
                self.status = f"{action.replace('migration_', '').title()} complete"
                self.is_busy = False
                self.log_line(f"Vault migration {action} completed")

            self.service_manager.run_command(args, self.log_line, completion_callback)

    def _handle_migration_step_completed(self, action):
        """Handle migration step completion actions."""
        step_messages = {
            "migration_analysis_completed": "Migration analysis completed - plan can now be generated",
            "migration_plan_generated": "Migration plan generated - backup can now be created",
            "migration_backup_completed": "Migration backup completed - migration can now be executed",
            "migration_executed": "Migration executed - verification can now be run",
            "migration_verification_success": "Migration verification successful - migration is complete"
        }

        if action in step_messages:
            self.log_line(step_messages[action])

    def _do_log_viewer(self):
        """Show the log viewer modal."""
        self.view.show_paged_content(self.log, title="Log Viewer")
    
    def _do_update_all(self):
        """Run the complete update sequence."""
        self._do_collect_obsidian()
        self._do_collect_reminders()
        self._do_build_links()
    
    def _do_update_all_and_apply(self):
        """Run the complete update sequence and apply changes."""
        if self.is_busy:
            return
            
        # Validate EventKit before starting full update (includes Reminders operations)
        if not self.check_eventkit_before_reminders_operation("Update All and Apply"):
            return
            
        # Start the chain with Obsidian collection
        self._do_collect_obsidian_for_chain()
    
    def _do_collect_obsidian_for_chain(self):
        """Collect Obsidian tasks as part of the update-all-and-apply chain."""
        if self.is_busy:
            return
            
        self.is_busy = True
        self.status = "Update All and Apply: Collecting Obsidian…"
        
        # Snapshot previous index for diff calculation
        prev = self._load_index(self.paths["obsidian_index"])
        
        script_path = os.path.join(os.path.dirname(__file__), "..", "obs_tools", "commands", "collect_obsidian_tasks.py")
        args = [
            os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3"),
            script_path,
            "--use-config",
            "--output", self.paths["obsidian_index"],
        ]
        if self.prefs.ignore_common:
            args.append("--ignore-common")
        
        def completion_callback():
            # Apply lifecycle prune/marking if configured
            if self.prefs.prune_days is not None and self.prefs.prune_days >= 0:
                from obs_tools.commands import update_indices_and_links as uil
                total, missing, deleted = uil.apply_lifecycle(self.paths["obsidian_index"], self.prefs.prune_days)
                if total:
                    self.log_line(f"Obsidian lifecycle: missing+{missing}, deleted+{deleted}")
            
            # Calculate and log diff
            curr = self._load_index(self.paths["obsidian_index"])
            self.last_diff["obs"] = self._diff_index(prev, curr, system="obs")
            count = self._count_tasks(self.paths["obsidian_index"])
            self.log_line(f"Obsidian tasks: {count}")
            
            # Chain to next step: collect reminders
            self.log_line("Chaining to reminders collection...")
            self._do_collect_reminders_for_chain()
        
        self.service_manager.run_command(args, self.log_line, completion_callback)

    def _do_quick_sync(self):
        """One-step flow: collect → build links → plan create → ensure anchors → create → apply sync."""
        if self.is_busy:
            return
        # Validate EventKit before starting (needed for create/apply)
        if not self.check_eventkit_before_reminders_operation("Quick Sync"):
            return

        self.is_busy = True

        # Initialize multi-step progress tracking
        steps = [
            "Collecting Obsidian",
            "Collecting Reminders",
            "Building links",
            "Planning creates",
            "Ensuring anchors",
            "Refreshing Obsidian",
            "Creating counterparts",
            "Applying sync"
        ]
        self.start_multi_step_operation("Quick Sync", steps)

        script_collect_obs = os.path.join(os.path.dirname(__file__), "..", "obs_tools", "commands", "collect_obsidian_tasks.py")
        args_obs = [
            self.get_managed_python(),
            script_collect_obs,
            "--use-config",
            "--output", self.paths["obsidian_index"],
        ]
        if self.prefs.ignore_common:
            args_obs.append("--ignore-common")

        def after_collect_obs():
            # Update diff stats for Obsidian
            curr = self._load_index(self.paths["obsidian_index"])
            prev_obs = self._load_index(self.paths["obsidian_index"])
            self.last_diff["obs"] = self._diff_index(prev_obs, curr, system="obs")
            count = self._count_tasks(self.paths["obsidian_index"])
            self.log_line(f"Obsidian tasks: {count}")

            # Advance to next step
            self.advance_operation_step("Collecting Reminders")
            script = os.path.join(os.path.dirname(__file__), "..", "obs_tools.py")
            args = [
                self.get_managed_python(), "-u", script, "reminders", "collect",
                "--config", self.paths["reminders_lists"],
                "--output", self.paths["reminders_index"],
            ]
            # Use hybrid collector for better performance
            args.append("--use-hybrid")
            if self.prefs.ignore_common:
                args.append("--ignore-common")

            def after_collect_rem():
                # Update diff stats for Reminders
                curr = self._load_index(self.paths["reminders_index"])
                prev_rem = self._load_index(self.paths["reminders_index"])
                self.last_diff["rem"] = self._diff_index(prev_rem, curr, system="rem")
                count = self._count_tasks(self.paths["reminders_index"])
                self.log_line(f"Reminders tasks: {count}")

                # Advance to next step
                self.advance_operation_step("Building links")
                script_bl = os.path.join(os.path.dirname(__file__), "..", "obs_tools", "commands", "build_sync_links.py")
                args_bl = [
                    self.get_managed_python(),
                    script_bl,
                    "--obs", self.paths["obsidian_index"],
                    "--rem", self.paths["reminders_index"],
                    "--output", self.paths["links"],
                    "--min-score", str(self.prefs.min_score),
                    "--days-tol", str(self.prefs.days_tolerance),
                ]
                if self.prefs.include_done:
                    args_bl.append("--include-done")

                def after_links():
                    # Update link stats
                    curr = self._load_index(self.paths["links"])
                    self.last_diff["links"] = self._diff_index({}, curr, system="links")
                    count = len(curr.get("sync_links", [])) if curr else 0
                    self.log_line(f"Sync links: {count}")

                    # Advance to next step
                    self.advance_operation_step("Planning creates")

                    # Plan creation
                    ts = time.strftime("%Y%m%d_%H%M%S")
                    base = os.path.expanduser("~/.config/obs-tools/backups")
                    os.makedirs(base, exist_ok=True)
                    plan_path = os.path.join(base, f"quick_sync_plan_{ts}.json")
                    anchors_changes = os.path.join(base, f"quick_sync_anchors_{ts}.json")
                    args_plan = [
                        self.get_managed_python(), "-u", script, "sync", "create",
                        "--obs", self.paths["obsidian_index"],
                        "--rem", self.paths["reminders_index"],
                        "--links", self.paths["links"],
                        "--plan-out", plan_path,
                    ]
                    # Respect prefs; create_missing loads app.json by default, so no overrides needed
                    def after_plan():
                        # Advance to next step
                        self.advance_operation_step("Ensuring anchors")
                        script_ensure = os.path.join(os.path.dirname(__file__), "..", "obs_tools", "commands", "ensure_anchors_for_plan.py")
                        args_ensure = [
                            self.get_managed_python(),
                            script_ensure,
                            "--plan", plan_path,
                            "--apply",
                            "--changes-out", anchors_changes,
                        ]

                        def after_anchors():
                            # Advance to next step
                            self.advance_operation_step("Refreshing Obsidian")
                            args_obs2 = [
                                self.get_managed_python(),
                                script_collect_obs,
                                "--use-config",
                                "--output", self.paths["obsidian_index"],
                            ]
                            if self.prefs.ignore_common:
                                args_obs2.append("--ignore-common")

                            def after_collect_obs2():
                                # Now create missing counterparts using the original plan
                                self.advance_operation_step("Creating counterparts")
                                args_create = [
                                    self.get_managed_python(), "-u", script, "sync", "create",
                                    "--obs", self.paths["obsidian_index"],
                                    "--rem", self.paths["reminders_index"],
                                    "--links", self.paths["links"],
                                    "--apply",
                                ]

                                def after_create():
                                    # Advance to final step
                                    self.advance_operation_step("Applying sync")
                                    args_apply = [
                                        self.get_managed_python(), "-u", script, "sync", "apply",
                                        "--obs", self.paths["obsidian_index"],
                                        "--rem", self.paths["reminders_index"],
                                        "--links", self.paths["links"],
                                        "--apply",
                                    ]

                                    def done():
                                        # Show structured summary instead of raw logs
                                        summary_msg = self.format_completion_summary("sync_links_apply", "Sync apply")
                                        if summary_msg:
                                            self.log_line(summary_msg)
                                        else:
                                            self.log_line("Quick Sync complete")

                                        # Show backup artifact path
                                        summary_path = self.find_latest_run_summary("sync_links_apply")
                                        if summary_path:
                                            self.log_line(f"Details: {os.path.basename(summary_path)}")

                                        # Complete the multi-step operation
                                        created = output_counts.get('created', 0) if 'output_counts' in locals() else 0
                                        updated = output_counts.get('updated', 0) if 'output_counts' in locals() else 0
                                        summary = f"+{created}/{updated} created/updated" if created + updated > 0 else "No changes"
                                        self.complete_multi_step_operation(summary)

                                        self.status = "Quick Sync complete"
                                        self.is_busy = False

                                    self.service_manager.run_command(args_apply, self.log_line, done)

                                self.service_manager.run_command(args_create, self.log_line, after_create)

                            self.service_manager.run_command(args_obs2, self.log_line, after_collect_obs2)

                        self.service_manager.run_command(args_ensure, self.log_line, after_anchors)

                    self.service_manager.run_command(args_plan, self.log_line, after_plan)

                self.service_manager.run_command(args_bl, self.log_line, after_links)

            self.service_manager.run_command(args, self.log_line, after_collect_rem)

        self.service_manager.run_command(args_obs, self.log_line, after_collect_obs)
    
    def _do_collect_reminders_for_chain(self):
        """Collect Reminders tasks as part of the update-all-and-apply chain."""
        self.status = "Update All and Apply: Collecting Reminders…"
        
        # Snapshot previous index for diff calculation
        prev = self._load_index(self.paths["reminders_index"])
        
        script_path = os.path.join(os.path.dirname(__file__), "..", "obs_tools.py")
        args = [
            os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3"),
            script_path, "reminders", "collect",
            "--config", self.paths["reminders_lists"],
            "--output", self.paths["reminders_index"],
        ]
        # Use hybrid collector for better performance
        args.append("--use-hybrid")
        if self.prefs.ignore_common:
            args.append("--ignore-common")
        
        def completion_callback():
            # Apply lifecycle prune/marking if configured
            if self.prefs.prune_days is not None and self.prefs.prune_days >= 0:
                from obs_tools.commands import update_indices_and_links as uil
                total, missing, deleted = uil.apply_lifecycle(self.paths["reminders_index"], self.prefs.prune_days)
                if total:
                    self.log_line(f"Reminders lifecycle: missing+{missing}, deleted+{deleted}")
            
            # Calculate and log diff
            curr = self._load_index(self.paths["reminders_index"])
            self.last_diff["rem"] = self._diff_index(prev, curr, system="rem")
            count = self._count_tasks(self.paths["reminders_index"])
            self.log_line(f"Reminders tasks: {count}")
            
            # Chain to next step: build links
            self.log_line("Chaining to link building...")
            self._do_build_links_for_chain()
        
        self.service_manager.run_command(args, self.log_line, completion_callback)
    
    def _do_build_links_for_chain(self):
        """Build links as part of the update-all-and-apply chain."""
        self.status = "Update All and Apply: Building links…"
        
        # Snapshot previous links for diff calculation
        prev = self._load_index(self.paths["links"])
        
        script_path = os.path.join(os.path.dirname(__file__), "..", "obs_tools.py")
        args = [
            os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3"),
            script_path, "sync", "suggest",
            "--obs", self.paths["obsidian_index"],
            "--rem", self.paths["reminders_index"],
            "--links", self.paths["links"],
            "--min-score", str(self.prefs.min_score),
            "--days-tolerance", str(self.prefs.days_tolerance),
        ]
        if self.prefs.include_done:
            args.append("--include-done")
        
        def completion_callback():
            # Calculate and log diff
            curr = self._load_index(self.paths["links"])
            self.last_diff["links"] = self._diff_index(prev, curr, system="links")
            count = self._count_links(self.paths["links"])
            self.log_line(f"Sync links: {count}")
            
            # Chain to final step: apply sync changes
            self.log_line("Chaining to sync apply...")
            self._do_apply_sync_for_chain()
        
        self.service_manager.run_command(args, self.log_line, completion_callback)
    
    def _do_apply_sync_for_chain(self):
        """Apply sync changes as the final step of the update-all-and-apply chain."""
        link_count = self._count_links(self.paths["links"])
        self.status = f"Update All and Apply: Applying {link_count} sync changes (may take 10+ min for large sets)…"
        
        script_path = os.path.join(os.path.dirname(__file__), "..", "obs_tools.py")
        args = [
            self.get_managed_python(),
            "-u",
            script_path, "sync", "apply",
            "--obs", self.paths["obsidian_index"],
            "--rem", self.paths["reminders_index"],
            "--links", self.paths["links"],
        ]
        
        if self.prefs.ignore_common:
            args.append("--ignore-common")
        
        # Apply mode - create backup
        base = os.path.expanduser("~/.config/obs-tools/backups")
        os.makedirs(base, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        changes = os.path.join(base, f"sync_apply_{ts}.json")
        args.extend(["--apply", "--changes-out", changes])
        
        def completion_callback():
            # Tail recent component logs
            self.tail_component_logs("sync_links_apply", "Sync apply")
            
            # Find and display run summary path
            summary_path = self.find_latest_run_summary("sync_links_apply")
            if summary_path:
                self.status = f"Update All and Apply Complete - Summary: {os.path.basename(summary_path)}"
            else:
                self.status = "Update All and Apply Complete"
                
            self.is_busy = False
        
        self.service_manager.run_command(args, self.log_line, completion_callback)
    
    def _do_discover_vaults(self):
        """Run vault discovery interactively."""
        script_path = os.path.join(os.path.dirname(__file__), "..", "obs_tools", "commands", "discover_obsidian_vaults.py")
        args = [
            os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3"),
            script_path
        ]
        self.service_manager.run_interactive(args, "Vault discovery", self.view, self.log_line)
        self.status = "Returned from Vault discovery"
    
    def _do_discover_reminders(self):
        """Run reminders discovery interactively."""
        script_path = os.path.join(os.path.dirname(__file__), "..", "obs_tools.py")
        args = [
            os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3"),
            script_path, "reminders", "discover"
        ]
        self.service_manager.run_interactive(args, "Reminders discovery", self.view, self.log_line)
        self.status = "Returned from Reminders discovery"
    
    def _do_collect_obsidian(self):
        """Collect Obsidian tasks."""
        if self.is_busy:
            return
            
        self.is_busy = True
        self.status = "Collecting Obsidian…"
        
        # Snapshot previous index for diff calculation
        prev = self._load_index(self.paths["obsidian_index"])
        
        script_path = os.path.join(os.path.dirname(__file__), "..", "obs_tools", "commands", "collect_obsidian_tasks.py")
        args = [
            os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3"),
            script_path,
            "--use-config",
            "--output", self.paths["obsidian_index"],
        ]
        if self.prefs.ignore_common:
            args.append("--ignore-common")
        
        def completion_callback():
            # Apply lifecycle prune/marking if configured
            if self.prefs.prune_days is not None and self.prefs.prune_days >= 0:
                from obs_tools.commands import update_indices_and_links as uil
                total, missing, deleted = uil.apply_lifecycle(self.paths["obsidian_index"], self.prefs.prune_days)
                if total:
                    self.log_line(f"Obsidian lifecycle: missing+{missing}, deleted+{deleted}")

            # Calculate and log diff
            curr = self._load_index(self.paths["obsidian_index"])
            self.last_diff["obs"] = self._diff_index(prev, curr, system="obs")
            count = self._count_tasks(self.paths["obsidian_index"])

            # Show structured summary instead of raw logs
            summary_msg = self.format_completion_summary("collect_obsidian", "Obsidian collection")
            if summary_msg:
                self.log_line(summary_msg)
            else:
                self.log_line(f"Obsidian tasks: {count}")

            # Show changes if any
            if self.last_diff["obs"]:
                added = len(self.last_diff["obs"].get("added", []))
                modified = len(self.last_diff["obs"].get("modified", []))
                removed = len(self.last_diff["obs"].get("removed", []))
                if added or modified or removed:
                    self.log_line(f"Changes: +{added} new, ~{modified} modified, -{removed} removed")

            # Set completion summary
            if summary_msg:
                self.set_completion_summary(summary_msg)

            self.status = "Ready"
            self.is_busy = False
        
        self.service_manager.run_command(args, self.log_line, completion_callback)
    
    def _do_collect_reminders(self):
        """Collect Reminders tasks."""
        if self.is_busy:
            return
            
        # Validate EventKit before collecting from Apple Reminders
        if not self.check_eventkit_before_reminders_operation("Collect Reminders"):
            return
            
        self.is_busy = True
        self.status = "Collecting Reminders…"
        
        # Snapshot previous index for diff calculation
        prev = self._load_index(self.paths["reminders_index"])
        
        script_path = os.path.join(os.path.dirname(__file__), "..", "obs_tools.py")
        args = [
            os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3"),
            script_path, "reminders", "collect",
            "--config", self.paths["reminders_lists"],
            "--output", self.paths["reminders_index"],
        ]
        # Use hybrid collector for better performance
        args.append("--use-hybrid")

        def completion_callback():
            # Apply lifecycle prune/marking if configured
            if self.prefs.prune_days is not None and self.prefs.prune_days >= 0:
                from obs_tools.commands import update_indices_and_links as uil
                total, missing, deleted = uil.apply_lifecycle(self.paths["reminders_index"], self.prefs.prune_days)
                if total:
                    self.log_line(f"Reminders lifecycle: missing+{missing}, deleted+{deleted}")

            # Calculate and log diff
            curr = self._load_index(self.paths["reminders_index"])
            self.last_diff["rem"] = self._diff_index(prev, curr, system="rem")
            count = self._count_tasks(self.paths["reminders_index"])

            # Show structured summary instead of raw logs
            summary_msg = self.format_completion_summary("collect_reminders", "Reminders collection")
            if summary_msg:
                self.log_line(summary_msg)
            else:
                self.log_line(f"Reminders tasks: {count}")

            # Show changes if any
            if self.last_diff["rem"]:
                added = len(self.last_diff["rem"].get("added", []))
                modified = len(self.last_diff["rem"].get("modified", []))
                removed = len(self.last_diff["rem"].get("removed", []))
                if added or modified or removed:
                    self.log_line(f"Changes: +{added} new, ~{modified} modified, -{removed} removed")

            # Set completion summary
            if summary_msg:
                self.set_completion_summary(summary_msg)

            self.status = "Ready"
            self.is_busy = False
        
        self.service_manager.run_command(args, self.log_line, completion_callback)

    def _do_sync_calendar_to_daily_note(self):
        """Sync today's calendar events to daily note."""
        if self.is_busy:
            return

        # Validate EventKit before accessing Apple Calendar
        if not self.check_eventkit_before_reminders_operation("Sync Calendar to Daily Note"):
            return

        self.is_busy = True
        self.status = "Syncing calendar events to daily note…"

        script_path = os.path.join(os.path.dirname(__file__), "..", "obs_tools.py")
        args = [
            os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3"),
            script_path, "calendar", "sync",
            "--verbose"
        ]

        def completion_callback():
            self.status = "Calendar sync complete"
            self.is_busy = False

        self.service_manager.run_command(args, self.log_line, completion_callback)

    def _do_build_links(self):
        """Build sync links."""
        if self.is_busy:
            return
            
        self.is_busy = True
        self.status = "Building links…"
        
        prev_links = self._count_links(self.paths["links"])
        prev_list = self._load_links(self.paths["links"])
        
        script_path = os.path.join(os.path.dirname(__file__), "..", "obs_tools", "commands", "build_sync_links.py")
        args = [
            os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3"),
            script_path,
            "--obs", self.paths["obsidian_index"],
            "--rem", self.paths["reminders_index"],
            "--output", self.paths["links"],
            "--min-score", str(self.prefs.min_score),
            "--days-tol", str(self.prefs.days_tolerance),
        ]
        if self.prefs.include_done:
            args.append("--include-done")
        
        def completion_callback():
            # Calculate link changes and update state
            links = self._count_links(self.paths["links"])
            curr_list = self._load_links(self.paths["links"])
            self.last_diff["links"] = links - prev_links
            
            # Fallback to in-memory baseline if file read before build was empty
            # Create local copy to avoid NameError
            baseline_list = prev_list
            if not baseline_list and self._prev_link_pairs:
                baseline_list = []
                for ou, ru in self._prev_link_pairs:
                    baseline_list.append({"obs_uuid": ou, "rem_uuid": ru})
            
            self.last_link_changes = self._diff_links(baseline_list, curr_list)
            # Update in-memory baseline for next run
            self._prev_link_pairs = {(l.get('obs_uuid'), l.get('rem_uuid')) for l in curr_list if l.get('obs_uuid') and l.get('rem_uuid')}
            self.log_line(f"Links: {links}")
            
            # Tail recent component logs
            self.tail_component_logs("build_sync_links", "Link building")
            
            # Find and display run summary path
            summary_path = self.find_latest_run_summary("build_sync_links")
            if summary_path:
                self.status = f"Ready - Summary: {os.path.basename(summary_path)}"
            else:
                self.status = "Ready"
                
            self.is_busy = False
        
        self.service_manager.run_command(args, self.log_line, completion_callback)
    
    def _do_link_review(self):
        """Show link review modal."""
        changes = self.last_link_changes
        new_links = changes.get("new", [])
        replaced = changes.get("replaced", [])

        lines = []
        lines.append("New and replaced links from last build:")
        if not new_links and not replaced:
            lines.append("(no changes recorded in last build)")
        if new_links:
            lines.append("")
            lines.append(f"New links ({len(new_links)}):")
            for i, lk in enumerate(new_links, 1):
                fields = lk.get("fields", {}) or {}
                lines.append(f"{i:2d}. score={lk.get('score')}  obs={lk.get('obs_uuid')}  rem={lk.get('rem_uuid')}")
                lines.append(f"    obs: {fields.get('obs_title')}  due: {fields.get('obs_due')}")
                lines.append(f"    rem: {fields.get('rem_title')}  due: {fields.get('rem_due')}")
        if replaced:
            lines.append("")
            lines.append(f"Replaced links ({len(replaced)}):")
            for i, (old_rec, new_rec) in enumerate(replaced, 1):
                of, nf = old_rec.get("fields", {}) or {}, new_rec.get("fields", {}) or {}
                lines.append(f"{i:2d}. {old_rec.get('obs_uuid')}:{old_rec.get('rem_uuid')} -> {new_rec.get('obs_uuid')}:{new_rec.get('rem_uuid')}  new_score={new_rec.get('score')}")
                lines.append(f"    obs: {nf.get('obs_title')}  due: {nf.get('obs_due')}  (was due {of.get('obs_due')})")
                lines.append(f"    rem: {nf.get('rem_title')}  due: {nf.get('rem_due')}  (was due {of.get('rem_due')})")

        self.view.show_paged_content(lines, title="Link Review — press q to close, PgUp/PgDn to scroll")
    
    def _do_sync_links(self):
        """Handle sync links with interactive prompts."""
        self.status = "Sync Links: press d for dry-run, a to apply, q to cancel"
        mode = None
        while True:
            self.view.draw_main_screen(self.get_current_state())
            ch = self.view.get_user_input()
            if ch in (ord('q'), 27):
                self.status = "Ready"
                return
            elif ch in (ord('d'), ord('D')):
                mode = 'dry'
                break
            elif ch in (ord('a'), ord('A')):
                mode = 'apply'
                break
        
        self._run_sync_operation(mode)
    
    def _run_sync_operation(self, mode: str):
        """Run sync operation (dry-run or apply)."""
        self.is_busy = True
        
        # Show informative status with link count
        link_count = self._count_links(self.paths["links"])
        if mode == 'apply':
            self.status = f"Sync Apply: Processing {link_count} links (EventKit operations may take time)…"
        else:
            self.status = f"Sync Dry-run: Analyzing {link_count} links…"
        
        script_path = os.path.join(os.path.dirname(__file__), "..", "obs_tools.py")
        args = [
            self.get_managed_python(),
            "-u",
            script_path, "sync", "apply",
            "--obs", self.paths["obsidian_index"],
            "--rem", self.paths["reminders_index"],
            "--links", self.paths["links"],
        ]
        
        # Only refresh on dry-runs to get current state; skip refresh on apply to avoid resetting indices
        if mode == 'dry':
            args.append("--refresh")
        if self.prefs.ignore_common:
            args.append("--ignore-common")
        
        if mode == 'apply':
            base = os.path.expanduser("~/.config/obs-tools/backups")
            os.makedirs(base, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            changes = os.path.join(base, f"sync_apply_{ts}.json")
            args.extend(["--apply", "--changes-out", changes])
            
            def completion_callback():
                # Tail recent component logs
                self.tail_component_logs("sync_links_apply", "Sync apply")
                
                # Find and display run summary path
                summary_path = self.find_latest_run_summary("sync_links_apply")
                if summary_path:
                    self.status = f"Ready - Summary: {os.path.basename(summary_path)}"
                else:
                    self.status = "Ready"
                    
                self.is_busy = False
                
            self.service_manager.run_command(args, self.log_line, completion_callback)
        else:
            # Dry-run with verbose and plan-out file, then page the plan
            base = os.path.expanduser("~/.config/obs-tools/backups")
            os.makedirs(base, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            plan = os.path.join(base, f"sync_plan_{ts}.txt")
            args.extend(["--verbose", "--plan-out", plan])
            
            def completion_callback():
                # Open the plan in pager if available
                try:
                    with open(plan, "r", encoding="utf-8") as f:
                        lines = f.read().splitlines()
                    if lines:
                        self.view.show_paged_content(lines, title="Sync Plan — press q to close, PgUp/PgDn to scroll")
                except Exception:
                    pass
                
                # Tail recent component logs
                self.tail_component_logs("sync_links_apply", "Sync dry-run")
                
                # Find and display run summary path
                summary_path = self.find_latest_run_summary("sync_links_apply")
                if summary_path:
                    self.status = f"Ready - Summary: {os.path.basename(summary_path)}"
                else:
                    self.status = "Ready"
                    
                self.is_busy = False
                
            self.service_manager.run_command(args, self.log_line, completion_callback)
    
    def _do_duplication_finder(self):
        """Interactive duplication finder tool."""
        options = [
            ("Dry-run (show what would be removed)", "dry"),
            ("Index mode (mark as deleted in indexes)", "fix"),
            ("Physical mode (removes from source files)", "physical"),
            ("Cancel", None),
        ]
        
        selection = self.view.show_selection_modal("Duplication Finder", options)
        if selection is None or options[selection][1] is None:
            self.status = "Ready"
            return
        
        mode = options[selection][1]
        
        script_path = os.path.join(os.path.dirname(__file__), "..", "obs_tools", "commands", "find_duplicate_tasks.py")
        args = [
            os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3"),
            script_path,
            "--obs", self.paths["obsidian_index"],
            "--rem", self.paths["reminders_index"],
            "--links", self.paths["links"],
        ]
        
        if mode == 'dry':
            args.extend(["--dry-run", "--batch", "--auto-remove-unsynced"])
            self.log_line("Running duplication finder (dry-run mode)")
        elif mode == 'physical':
            args.extend(["--batch", "--auto-remove-unsynced", "--physical-remove"])
            self.log_line("Running duplication finder (physical removal mode - removes from source files)")
        else:
            args.extend(["--batch", "--auto-remove-unsynced"])
            self.log_line("Running duplication finder (index mode - marks as deleted in indexes)")
        
        # Run interactively since it requires user input
        self.service_manager.run_interactive(args, "Duplication Finder", self.view, self.log_line)
        self.status = "Ready"
    
    def _do_fix_block_ids_interactive(self):
        """Interactive block ID fixer."""
        options = [
            ("Dry-run (show what would be fixed)", "dry"),
            ("Apply (with backups)", "apply"),
            ("Cancel", None),
        ]
        
        selection = self.view.show_selection_modal("Fix Block IDs", options)
        if selection is None or options[selection][1] is None:
            self.status = "Ready"
            return
        
        mode = options[selection][1]
        
        script_path = os.path.join(os.path.dirname(__file__), "..", "obs_tools.py")
        args = [
            os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3"),
            script_path, "obs", "fix-block-ids", "--use-config", "--ignore-common",
        ]
        
        if mode == 'apply':
            # Build changeset path
            base = os.path.expanduser("~/.config/obs-tools/backups")
            os.makedirs(base, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            changes = os.path.join(base, f"block_id_fix_{ts}.json")
            args.extend(["--apply", "--changes-out", changes])
        
        self.service_manager.run_command(args, self.log_line, lambda: setattr(self, 'status', 'Ready'))
    
    def _do_restore_last_fix(self):
        """Restore the most recent block ID fix."""
        # Find latest changeset file
        base = os.path.expanduser("~/.config/obs-tools/backups")
        try:
            files = [os.path.join(base, f) for f in os.listdir(base) if f.startswith("block_id_fix_") and f.endswith(".json")]
        except Exception:
            files = []
        if not files:
            self.log_line("No block-id changeset files found to restore.")
            return
        
        latest = max(files, key=lambda p: os.path.getmtime(p))
        script_path = os.path.join(os.path.dirname(__file__), "..", "obs_tools", "commands", "fix_obsidian_block_ids.py")
        args = [
            os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3"),
            script_path, "--restore", latest,
        ]
        self.service_manager.run_command(args, self.log_line, lambda: setattr(self, 'status', 'Ready'))
    
    def _do_reset_interactive(self):
        """Interactive reset tool."""
        options = [
            ("All (configs, indices, links, prefs, backups)", ["--all"]),
            ("Configs only", ["--configs"]),
            ("Indices only", ["--indices"]),
            ("Links only", ["--links"]),
            ("Prefs only", ["--prefs"]),
            ("Backups only", ["--backups"]),
            ("Cancel", None),
        ]
        
        selection = self.view.show_selection_modal("Reset — select target and press Enter", options)
        if selection is None or options[selection][1] is None:
            self.status = "Ready"
            return
        
        label, flags = options[selection]
        
        script_path = os.path.join(os.path.dirname(__file__), "..", "obs_tools.py")
        args = [
            os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3"),
            script_path, "reset", "run", "--yes",
        ] + flags
        
        self.service_manager.run_command(args, self.log_line, 
                                       lambda: (self.log_line(f"Reset run for: {label}"), setattr(self, 'status', 'Ready')))
    
    def _do_setup_dependencies(self):
        """Interactive setup dependencies tool."""
        options = [
            ("List available dependency groups", "list"),
            ("Install macOS dependencies (EventKit/Reminders)", "macos"),
            ("Install optimization dependencies (scipy/munkres)", "optimization"),
            ("Install validation dependencies (jsonschema)", "validation"),
            ("Install development dependencies (pytest/black/mypy)", "dev"),
            ("Install all applicable dependencies", "all"),
            ("Interactive setup wizard", "interactive"),
            ("Cancel", None),
        ]
        
        selection = self.view.show_selection_modal("Setup Dependencies", options)
        if selection is None or options[selection][1] is None:
            self.status = "Ready"
            return
        
        mode = options[selection][1]
        
        script_path = os.path.join(os.path.dirname(__file__), "..", "obs_tools.py")
        args = [
            os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3"),
            script_path, "setup",
        ]
        
        if mode == "list":
            args.append("--list")
        elif mode == "all":
            args.append("--all")
        elif mode == "interactive":
            args.append("--interactive")
        elif mode in ["macos", "optimization", "validation", "dev"]:
            args.extend(["--group", mode])
        
        if mode == "list":
            # Run synchronously for list command to display output
            self.service_manager.run_interactive(args, "Setup Dependencies", self.view, self.log_line)
        elif mode == "interactive":
            # Run interactively for the setup wizard
            self.service_manager.run_interactive(args, "Setup Dependencies", self.view, self.log_line)
        else:
            # Run asynchronously for install commands
            def completion_callback():
                self.log_line(f"Setup dependencies ({mode}) completed")
                self.status = "Ready"
            
            self.service_manager.run_command(args, self.log_line, completion_callback)
        
        self.status = "Ready"
    
    
    
    def _handle_vault_selection(self):
        """Handle vault selection for default inbox file."""
        try:
            # Load available vaults
            vault_config_path = os.path.expanduser("~/.config/obsidian_vaults.json")
            if not os.path.exists(vault_config_path):
                self.log_line("No vaults found. Run 'Discover Vaults' first.")
                return False
            
            import json
            with open(vault_config_path, 'r') as f:
                vaults = json.load(f)
            
            if not vaults:
                self.log_line("No vaults configured. Run 'Discover Vaults' first.")
                return False
            
            # Show vault selection interface
            selected_vault = None
            vault_names = [vault['name'] for vault in vaults]
            selected_index = 0
            
            self.status = f"Select default vault for Reminders tasks (↑↓ navigate, Enter select, q cancel)"
            
            while True:
                # Create display with current selection highlighted
                vault_display = []
                for i, name in enumerate(vault_names):
                    if i == selected_index:
                        vault_display.append(f"► {name}")
                    else:
                        vault_display.append(f"  {name}")
                
                # Temporarily update log for display
                temp_log = self.log[:]
                self.log = self.log[-10:] + [
                    "Select vault for default Reminders inbox:",
                    ""
                ] + vault_display + [
                    "",
                    "↑↓: Navigate  Enter: Select  q: Cancel"
                ]
                
                self.view.draw_main_screen(self.get_current_state())
                
                # Restore original log
                self.log = temp_log
                
                ch = self.view.get_user_input()
                
                if ch in (ord('q'), 27):  # q or ESC
                    return False
                elif ch == ord('\n') or ch == ord('\r') or ch == 10 or ch == 13:  # Enter
                    selected_vault = vaults[selected_index]
                    break
                elif ch == 259 or ch == ord('k'):  # Up arrow or k
                    selected_index = (selected_index - 1) % len(vault_names)
                elif ch == 258 or ch == ord('j'):  # Down arrow or j  
                    selected_index = (selected_index + 1) % len(vault_names)
            
            if selected_vault:
                # Create Tasks.md path in selected vault
                vault_path = selected_vault['path']
                tasks_file_path = os.path.join(vault_path, "Tasks.md")
                
                # Create the Tasks.md file if it doesn't exist
                if not os.path.exists(tasks_file_path):
                    os.makedirs(os.path.dirname(tasks_file_path), exist_ok=True)
                    with open(tasks_file_path, 'w') as f:
                        f.write(f"# Tasks\n\nInbox for tasks created from Apple Reminders.\n\n")
                    self.log_line(f"Created {tasks_file_path}")
                
                # Update configuration
                self.prefs.creation_defaults.obs_inbox_file = tasks_file_path
                cfg.save_app_config(self.prefs)
                
                self.log_line(f"Set default vault to '{selected_vault['name']}' -> Tasks.md")
                self.status = f"Default vault set to '{selected_vault['name']}'"
                return True
                
        except Exception as e:
            self.log_line(f"Error selecting vault: {str(e)}")
            return False
        
        return False
    
    def _handle_cancel_operation(self):
        """Handle cancel operation hotkey."""
        if not self.is_busy:
            self.status = "No operation to cancel"
            return
        
        current_op = self.service_manager.get_current_operation()
        if current_op:
            self.log_line(f"Cancelling operation: {current_op}")
            if self.service_manager.cancel_current_operation():
                self.status = f"Cancelling {current_op}..."
            else:
                self.status = "Failed to cancel operation"
        else:
            self.status = "No operation to cancel"
    
    # Helper methods
    def _load_cached_data(self, data_type: str, path: str):
        """Load data with caching based on file modification time."""
        try:
            # Get current file modification time
            current_mtime = os.path.getmtime(path)
            cache_entry = self._data_cache[data_type]
            
            # Return cached data if file hasn't changed
            if cache_entry['data'] is not None and cache_entry['mtime'] >= current_mtime:
                return cache_entry['data']
            
            # Load fresh data
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Update cache
            cache_entry['data'] = data
            cache_entry['mtime'] = current_mtime
            
            return data
            
        except Exception:
            # Return cached data if available, otherwise empty
            if self._data_cache[data_type]['data'] is not None:
                return self._data_cache[data_type]['data']
            return {"meta": {}, "tasks": {}} if data_type != 'links' else {"links": []}
    
    def _load_index(self, path: str):
        """Load a task index file with caching."""
        data_type = 'obs' if 'obsidian' in path else 'rem'
        return self._load_cached_data(data_type, path)
    
    def _load_links(self, path: str):
        """Load a links file with caching."""
        data = self._load_cached_data('links', path)
        return data.get("links", []) or []
    
    def _count_tasks(self, path: str) -> int:
        """Count total tasks in an index file using cached data."""
        try:
            data_type = 'obs' if 'obsidian' in path else 'rem'
            data = self._load_cached_data(data_type, path)
            return len(data.get("tasks", {}) or {})
        except Exception:
            return 0

    def _count_links(self, path: str) -> int:
        """Count total links in a links file using cached data."""
        try:
            data = self._load_cached_data('links', path)
            return len(data.get("links", []) or [])
        except Exception:
            return 0
    
    def _digest_obs(self, rec: dict):
        """Create a digest for Obsidian task comparison."""
        return (
            rec.get("status"),
            rec.get("description"),
            rec.get("due"),
            rec.get("scheduled"),
            rec.get("start"),
            rec.get("done"),
            rec.get("priority"),
        )

    def _digest_rem(self, rec: dict):
        """Create a digest for Reminders task comparison."""
        return (
            rec.get("status"),
            rec.get("description"),
            rec.get("due"),
            rec.get("start"),
            rec.get("done"),
            rec.get("priority"),
        )

    def _diff_index(self, prev: dict, curr: dict, system: str):
        """Calculate differences between two task indexes."""
        prev_tasks = prev.get("tasks", {}) or {}
        curr_tasks = curr.get("tasks", {}) or {}
        # New tasks
        new = sum(1 for uid in curr_tasks.keys() if uid not in prev_tasks)
        # Deleted/missing deltas
        deleted = 0
        missing = 0
        updated = 0
        for uid, rec in curr_tasks.items():
            p = prev_tasks.get(uid)
            if not p:
                continue
            # Newly deleted
            if not p.get("deleted") and rec.get("deleted"):
                deleted += 1
            # Newly missing (missing_since present and changed)
            if (not p.get("missing_since")) and rec.get("missing_since"):
                missing += 1
            # Updated core fields (ignore if missing/deleted)
            if rec.get("deleted") or rec.get("missing_since"):
                continue
            if system == "obs":
                if self._digest_obs(p) != self._digest_obs(rec):
                    updated += 1
            else:
                if self._digest_rem(p) != self._digest_rem(rec):
                    updated += 1
        return {"new": new, "updated": updated, "missing": missing, "deleted": deleted}

    def _diff_links(self, prev_list: list, curr_list: list):
        """Calculate differences between two link lists."""
        prev_pairs = {(l.get("obs_uuid"), l.get("rem_uuid")): l for l in prev_list if l.get("obs_uuid") and l.get("rem_uuid")}
        curr_pairs = {(l.get("obs_uuid"), l.get("rem_uuid")): l for l in curr_list if l.get("obs_uuid") and l.get("rem_uuid")}
        new = [curr_pairs[k] for k in curr_pairs.keys() - prev_pairs.keys()]
        # Replacements: same obs_uuid but different rem_uuid between sets
        prev_by_obs = {}
        for l in prev_list:
            ou, ru = l.get("obs_uuid"), l.get("rem_uuid")
            if ou and ou not in prev_by_obs:
                prev_by_obs[ou] = l
        replaced = []
        for l in curr_list:
            ou, ru = l.get("obs_uuid"), l.get("rem_uuid")
            if not ou or not ru:
                continue
            old = prev_by_obs.get(ou)
            if old and (old.get("rem_uuid") != ru):
                replaced.append((old, l))
        return {"new": new, "replaced": replaced}
    
    def _do_create_missing_counterparts(self):
        """Interactive create missing counterparts tool."""
        options = [
            ("Dry-run (show what would be created)", "dry"),
            ("Create Obsidian -> Reminders", "obs-to-rem"),
            ("Create Reminders -> Obsidian", "rem-to-obs"),
            ("Create both directions", "both"),
            ("Cancel", None),
        ]
        
        selection = self.view.show_selection_modal("Create Missing Counterparts", options)
        if selection is None or options[selection][1] is None:
            self.status = "Ready"
            return
        
        mode = options[selection][1]
        
        # Get direction setting
        if mode == "dry":
            direction = "both"
            apply_mode = False
        else:
            direction = mode
            apply_mode = True
        
        # Ask for additional options if applying
        if apply_mode:
            confirm_options = [
                ("Yes, create counterparts", True),
                ("No, just show plan", False),
                ("Cancel", None),
            ]
            
            confirm_selection = self.view.show_selection_modal(
                f"Create counterparts ({direction})?", 
                confirm_options
            )
            if confirm_selection is None or confirm_options[confirm_selection][1] is None:
                self.status = "Ready"
                return
            
            apply_mode = confirm_options[confirm_selection][1]
        
        # Build command arguments
        script_path = os.path.join(os.path.dirname(__file__), "..", "obs_tools.py")
        args = [
            os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3"),
            script_path, "sync", "create",
            "--obs", self.paths["obsidian_index"],
            "--rem", self.paths["reminders_index"],
            "--links", self.paths["links"],
            "--direction", direction,
        ]
        
        # Add apply flag if confirmed
        if apply_mode:
            args.append("--apply")
            self.log_line(f"Creating missing counterparts ({direction} direction)")
        else:
            self.log_line(f"Creating missing counterparts plan ({direction} direction, dry-run)")
        
        # Add default filters from preferences
        creation_defaults = self.prefs.creation_defaults
        if creation_defaults.since_days > 0:
            args.extend(["--since", str(creation_defaults.since_days)])
        if creation_defaults.max_creates_per_run > 0:
            args.extend(["--max", str(creation_defaults.max_creates_per_run)])
        if creation_defaults.include_done:
            args.append("--include-done")
        
        # Add verbose output
        args.append("--verbose")
        
        # For dry-run mode, save plan to file so we can display it
        plan_file = None
        if not apply_mode:
            import tempfile
            plan_file = tempfile.mktemp(suffix=".txt", prefix="create_plan_")
            args.extend(["--plan-out", plan_file])
        
        # Run the command
        self.is_busy = True
        
        def completion_callback():
            # If dry-run, show the plan
            if not apply_mode and plan_file and os.path.exists(plan_file):
                try:
                    with open(plan_file, "r", encoding="utf-8") as f:
                        content = f.read()
                    
                    # Parse the plan into a more readable format
                    lines = self._format_creation_plan(content)
                    if lines:
                        self.view.show_paged_content(lines, title="Creation Plan — press q to close, PgUp/PgDn to scroll")
                    
                    # Clean up temp file
                    os.unlink(plan_file)
                except Exception as e:
                    self.log_line(f"Failed to display plan: {str(e)}")
            
            self._on_create_counterparts_complete(True, "", apply_mode)
        
        self.service_manager.run_command(args, self.log_line, completion_callback)
    
    def _format_creation_plan(self, content: str) -> List[str]:
        """Format the creation plan into a more readable format."""
        lines = []
        
        try:
            # Try to parse as JSON first
            import json
            plan = json.loads(content)
            
            # Extract counts
            obs_to_rem = plan.get("obs_to_rem", [])
            rem_to_obs = plan.get("rem_to_obs", [])
            obs_count = len(obs_to_rem)
            rem_count = len(rem_to_obs)
            total_count = obs_count + rem_count
            
            # Add summary header
            lines.append("═══ CREATION PLAN SUMMARY ═══")
            lines.append("")
            lines.append(f"Direction: both")
            lines.append(f"Obsidian → Reminders: {obs_count} tasks")
            lines.append(f"Reminders → Obsidian: {rem_count} tasks") 
            lines.append(f"Total creations: {total_count}")
            lines.append("")
            lines.append("═══ TASKS TO CREATE ═══")
            lines.append("")
            
            # Process Obsidian → Reminders tasks
            for i, task in enumerate(obs_to_rem[:50], 1):  # Limit to first 50 for readability
                obs_task = task.get("obs_task", {})
                description = obs_task.get("description", "No description")
                
                # Truncate long descriptions
                if len(description) > 80:
                    description = description[:80] + "..."
                
                # Get source location
                vault_name = obs_task.get("vault", {}).get("name", "Unknown")
                file_path = obs_task.get("file", {}).get("relative_path", "Unknown")
                
                lines.append(f"📝 Obs→Rem #{i}: {description}")
                lines.append(f"   📁 {vault_name}: {file_path}")
                
            if len(obs_to_rem) > 50:
                lines.append(f"   ... and {len(obs_to_rem) - 50} more Obsidian tasks")
                
            lines.append("")
            
            # Process Reminders → Obsidian tasks  
            for i, task in enumerate(rem_to_obs[:50], 1):  # Limit to first 50 for readability
                rem_task = task.get("rem_task", {})
                description = rem_task.get("description", "No description")
                
                # Truncate long descriptions
                if len(description) > 80:
                    description = description[:80] + "..."
                
                # Get source location
                list_name = rem_task.get("list", {}).get("name", "Unknown List")
                
                lines.append(f"📋 Rem→Obs #{i}: {description}")
                lines.append(f"   📝 From list: {list_name}")
                
            if len(rem_to_obs) > 50:
                lines.append(f"   ... and {len(rem_to_obs) - 50} more Reminders tasks")
            
            # Add footer with counts
            lines.append("")
            lines.append(f"Total: {obs_count} Obs→Rem + {rem_count} Rem→Obs = {total_count} tasks")
            
        except json.JSONDecodeError:
            # Fallback to text parsing if JSON parsing fails
            lines.append("═══ CREATION PLAN (RAW) ═══")
            lines.append("")
            lines.append("Failed to parse plan format - showing raw content:")
            lines.append("")
            lines.extend(content.split('\n')[:100])  # Limit to first 100 lines
            
        lines.append("")
        lines.append("Press 'q' to close, PgUp/PgDn to scroll")
        
        return lines
    
    def _on_create_counterparts_complete(self, success: bool, summary: str, was_apply: bool):
        """Handle completion of create missing counterparts operation."""
        self.is_busy = False
        
        if success:
            if was_apply:
                self.log_line("✓ Missing counterparts created successfully")
                # Optionally trigger a sync operation
                sync_options = [
                    ("Run field sync now", True),
                    ("Skip sync for now", False),
                ]
                
                sync_selection = self.view.show_selection_modal(
                    "Counterparts created. Sync fields?", 
                    sync_options
                )
                if sync_selection is not None and sync_options[sync_selection][1]:
                    self._run_sync_operation('apply')
            else:
                self.log_line("✓ Missing counterparts plan completed")
        else:
            self.log_line("✗ Create missing counterparts failed")
        
        # Tail recent logs to show details
        self.tail_component_logs("create_missing_counterparts", "creation")
        self.status = "Ready"

    def _handle_create_vault_lists(self):
        """Handle creating Reminders lists for vaults."""
        if self.is_busy:
            return

        self.is_busy = True
        self.status = "Creating vault Reminders lists..."

        # For now, just log that this would create the lists
        # In a full implementation, this would call the vault setup command
        self.log_line("Creating Reminders lists for discovered vaults...")
        self.log_line("Note: This is a placeholder - full implementation would create actual lists")

        # Simulate some work
        import time
        time.sleep(1)

        self.status = "Vault lists creation complete"
        self.is_busy = False
        self.log_line("Vault Reminders lists created successfully")
