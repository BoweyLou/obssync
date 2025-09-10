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
            "Discover Vaults", 
            "Collect Obsidian",
            "Discover Reminders",
            "Collect Reminders",
            "Build Links",
            "Link Review",
            "Sync Links",
            "Duplication Finder",
            "Fix Block IDs",
            "Restore Last Fix",
            "Reset (dangerous)",
            "Setup Dependencies",
            "Settings",
            "Quit",
        ]
        self.selected = 0
        self.prefs, self.paths = cfg.load_app_config()
        self.log: List[str] = []
        self.status = "Ready"
        self.last_diff = {"obs": None, "rem": None, "links": None}
        self.last_link_changes = {"new": [], "replaced": []}
        self._prev_link_pairs: set[tuple[str, str]] = set()
        
        # State management
        self.is_running = True
        self.is_busy = False
    
    def log_line(self, s: str):
        """Add a line to the application log with timestamp."""
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {s}"
        self.log.append(line)
        if len(self.log) > 200:
            self.log.pop(0)
        self.prefs.last_summary = line
        cfg.save_app_config(self.prefs)
    
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
            self.log_line(f"Failed to tail {component} logs: {e}")
    
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
    
    def get_current_state(self) -> Dict[str, Any]:
        """Get the current application state for rendering."""
        return {
            'menu': self.menu,
            'selected': self.selected,
            'prefs': self.prefs,
            'paths': self.paths,
            'log': self.log,
            'status': self.status,
            'last_diff': self.last_diff,
            'is_busy': self.is_busy
        }
    
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
            "Discover Vaults": self._do_discover_vaults,
            "Collect Obsidian": self._do_collect_obsidian,
            "Discover Reminders": self._do_discover_reminders,
            "Collect Reminders": self._do_collect_reminders,
            "Build Links": self._do_build_links,
            "Link Review": self._do_link_review,
            "Sync Links": self._do_sync_links,
            "Duplication Finder": self._do_duplication_finder,
            "Fix Block IDs": self._do_fix_block_ids_interactive,
            "Restore Last Fix": self._do_restore_last_fix,
            "Reset (dangerous)": self._do_reset_interactive,
            "Setup Dependencies": self._do_setup_dependencies,
            "Settings": self._handle_settings,
            "Quit": lambda: setattr(self, 'is_running', False)
        }
        
        handler = handlers.get(item)
        if handler:
            handler()
    
    def _do_update_all(self):
        """Run the complete update sequence."""
        self._do_collect_obsidian()
        self._do_collect_reminders()
        self._do_build_links()
    
    def _do_discover_vaults(self):
        """Run vault discovery interactively."""
        script_path = os.path.join(os.path.dirname(__file__), "..", "discover_obsidian_vaults.py")
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
        
        script_path = os.path.join(os.path.dirname(__file__), "..", "collect_obsidian_tasks.py")
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
                import update_indices_and_links as uil
                total, missing, deleted = uil.apply_lifecycle(self.paths["obsidian_index"], self.prefs.prune_days)
                if total:
                    self.log_line(f"Obsidian lifecycle: missing+{missing}, deleted+{deleted}")
            
            # Calculate and log diff
            curr = self._load_index(self.paths["obsidian_index"])
            self.last_diff["obs"] = self._diff_index(prev, curr, system="obs")
            count = self._count_tasks(self.paths["obsidian_index"])
            self.log_line(f"Obsidian tasks: {count}")
            
            # Tail recent component logs
            self.tail_component_logs("collect_obsidian", "Obsidian collection")
            
            # Find and display run summary path
            summary_path = self.find_latest_run_summary("collect_obsidian")
            if summary_path:
                self.status = f"Ready - Summary: {os.path.basename(summary_path)}"
            else:
                self.status = "Ready"
                
            self.is_busy = False
        
        self.service_manager.run_command(args, self.log_line, completion_callback)
    
    def _do_collect_reminders(self):
        """Collect Reminders tasks."""
        if self.is_busy:
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
        
        def completion_callback():
            # Apply lifecycle prune/marking if configured
            if self.prefs.prune_days is not None and self.prefs.prune_days >= 0:
                import update_indices_and_links as uil
                total, missing, deleted = uil.apply_lifecycle(self.paths["reminders_index"], self.prefs.prune_days)
                if total:
                    self.log_line(f"Reminders lifecycle: missing+{missing}, deleted+{deleted}")
            
            # Calculate and log diff
            curr = self._load_index(self.paths["reminders_index"])
            self.last_diff["rem"] = self._diff_index(prev, curr, system="rem")
            count = self._count_tasks(self.paths["reminders_index"])
            self.log_line(f"Reminders tasks: {count}")
            
            # Tail recent component logs
            self.tail_component_logs("collect_reminders", "Reminders collection")
            
            # Find and display run summary path
            summary_path = self.find_latest_run_summary("collect_reminders")
            if summary_path:
                self.status = f"Ready - Summary: {os.path.basename(summary_path)}"
            else:
                self.status = "Ready"
                
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
        
        script_path = os.path.join(os.path.dirname(__file__), "..", "build_sync_links.py")
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
            if not prev_list and self._prev_link_pairs:
                prev_list = []
                for ou, ru in self._prev_link_pairs:
                    prev_list.append({"obs_uuid": ou, "rem_uuid": ru})
            
            self.last_link_changes = self._diff_links(prev_list, curr_list)
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
        
        script_path = os.path.join(os.path.dirname(__file__), "..", "obs_tools.py")
        args = [
            os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3"),
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
        
        script_path = os.path.join(os.path.dirname(__file__), "..", "find_duplicate_tasks.py")
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
        script_path = os.path.join(os.path.dirname(__file__), "..", "fix_obsidian_block_ids.py")
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
    
    def _handle_settings(self):
        """Handle settings adjustment interface."""
        self.status = "Settings: +/- score, </> tol, d toggle done, i toggle ignore, [/] prune- days, p toggle prune"
        while True:
            self.view.draw_main_screen(self.get_current_state())
            ch = self.view.get_user_input()
            if ch in (ord("q"), 27):
                break
            elif ch == ord("+"):
                self.prefs.min_score = min(0.99, round(self.prefs.min_score + 0.05, 2))
            elif ch == ord("-"):
                self.prefs.min_score = max(0.0, round(self.prefs.min_score - 0.05, 2))
            elif ch == ord("<"):
                self.prefs.days_tolerance = max(0, self.prefs.days_tolerance - 1)
            elif ch == ord(">"):
                self.prefs.days_tolerance = min(30, self.prefs.days_tolerance + 1)
            elif ch == ord("d"):
                self.prefs.include_done = not self.prefs.include_done
            elif ch == ord("i"):
                self.prefs.ignore_common = not self.prefs.ignore_common
            elif ch == ord("["):
                # decrease prune days (min -1 = off)
                if self.prefs.prune_days is None:
                    self.prefs.prune_days = -1
                self.prefs.prune_days = max(-1, self.prefs.prune_days - 1)
            elif ch == ord("]"):
                # increase prune days
                if self.prefs.prune_days is None or self.prefs.prune_days < 0:
                    self.prefs.prune_days = 7
                else:
                    self.prefs.prune_days = min(365, self.prefs.prune_days + 1)
            elif ch == ord("p"):
                # toggle prune on/off (default 7 days when turning on)
                if self.prefs.prune_days is None or self.prefs.prune_days < 0:
                    self.prefs.prune_days = 7
                else:
                    self.prefs.prune_days = -1
            cfg.save_app_config(self.prefs)
        self.status = "Ready"
    
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
    def _load_index(self, path: str):
        """Load a task index file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except Exception:
            return {"meta": {}, "tasks": {}}
    
    def _load_links(self, path: str):
        """Load a links file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("links", []) or []
        except Exception:
            return []
    
    def _count_tasks(self, path: str) -> int:
        """Count total tasks in an index file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return len(data.get("tasks", {}) or {})
        except Exception:
            return 0

    def _count_links(self, path: str) -> int:
        """Count total links in a links file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
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