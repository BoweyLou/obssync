#!/usr/bin/env python3
"""
TUI View Module - Handles all curses drawing and display logic.

This module contains all the visual presentation logic for the TUI,
including screen layout, rendering, and terminal size handling.
"""

from __future__ import annotations

import curses
import json
import os
import signal
from typing import List, Dict, Any, Optional

import app_config as cfg


class TUIView:
    """Handles all visual presentation and curses rendering for the TUI."""
    
    def __init__(self, stdscr):
        self.stdscr = stdscr
        curses.curs_set(0)
        self.stdscr.nodelay(False)
        self.height, self.width = self.stdscr.getmaxyx()
        self._resize_flag = False
        
        # Set up signal handler for terminal resize
        def handle_resize(signum, frame):
            self._resize_flag = True
        
        signal.signal(signal.SIGWINCH, handle_resize)
    
    def handle_resize(self):
        """Handle terminal resize events."""
        if self._resize_flag:
            try:
                curses.endwin()
                self.stdscr = curses.initscr()
                curses.curs_set(0)
                self.stdscr.nodelay(False)
                self._resize_flag = False
            except curses.error:
                pass
        
        # Refresh terminal dimensions in case of resize
        self.height, self.width = self.stdscr.getmaxyx()
    
    def draw_main_screen(self, state: Dict[str, Any]):
        """
        Draw the main TUI screen with all components.
        
        Args:
            state: Dictionary containing all the state data needed for rendering:
                - menu: List of menu items
                - selected: Currently selected menu index
                - prefs: AppPreferences object
                - paths: Path configuration dict
                - log: List of log messages
                - status: Current status message
                - last_diff: Dict with obsidian/reminders/links diffs
                - is_busy: Boolean indicating if operation is running
        """
        # Handle terminal resize if needed
        self.handle_resize()
        
        # Validate minimum terminal size
        if self.height < 10 or self.width < 50:
            self.stdscr.clear()
            self.stdscr.addstr(0, 0, "Terminal too small (need 50x10 min)")
            self.stdscr.refresh()
            return
        
        self.stdscr.clear()
        
        # Draw title
        self._draw_title()
        
        # Draw menu
        self._draw_menu(state['menu'], state['selected'], state.get('is_busy', False))
        
        # Draw preferences summary
        self._draw_preferences(state['prefs'], state.get('current_vault', 'Unknown'))
        
        # Draw statistics
        self._draw_statistics(state['paths'], state['last_diff'])
        
        # Draw paths
        self._draw_paths(state['paths'])
        
        # Draw log
        self._draw_log(state['log'])
        
        # Draw status bar
        self._draw_status_bar(state['status'], state.get('is_busy', False))
        
        self.stdscr.refresh()
    
    def _draw_title(self):
        """Draw the application title."""
        title = "Obsidian ↔ Reminders — Task Sync"
        title_x = max(0, (self.width - len(title)) // 2)
        if title_x + len(title) <= self.width:
            self.stdscr.addstr(0, title_x, title, curses.A_BOLD)
    
    def _draw_menu(self, menu: List[str], selected: int, is_busy: bool = False):
        """Draw the main menu with selection highlighting."""
        menu_start_y = 2
        if menu_start_y < self.height:
            try:
                self.stdscr.addstr(menu_start_y, 2, "Actions:", curses.A_UNDERLINE)
            except curses.error:
                pass
            
            for i, item in enumerate(menu):
                menu_y = 3 + i
                if menu_y >= self.height - 3:  # Leave room for status bar
                    break
                try:
                    # Dim menu items when busy except for cancellation operations
                    attr = curses.A_REVERSE if i == selected else curses.A_NORMAL
                    if is_busy and item not in ["Quit", "Settings"]:
                        attr |= curses.A_DIM
                    
                    # Truncate menu item if too long
                    max_item_len = max(1, self.width - 6)
                    display_item = item[:max_item_len] if len(item) > max_item_len else item
                    
                    # Add busy indicator for operations that can't be started
                    if is_busy and item not in ["Quit", "Settings"]:
                        display_item += " (busy)" if len(display_item) + 7 <= max_item_len else " (…)"
                    
                    self.stdscr.addstr(menu_y, 4, display_item, attr)
                except curses.error:
                    pass
    
    def _draw_preferences(self, prefs, current_vault="Unknown"):
        """Draw the preferences summary in the right column."""
        prefs_x = 30
        if self.width > prefs_x + 20:  # Only show if we have room
            try:
                # Show vault organization status prominently
                if 2 < self.height:
                    vault_org_status = "✅ ON" if prefs.vault_organization_enabled else "❌ OFF"
                    self.stdscr.addstr(2, prefs_x, f"Vault Org: {vault_org_status}",
                                     curses.A_BOLD if prefs.vault_organization_enabled else curses.A_NORMAL)

                if 3 < self.height: self.stdscr.addstr(3, prefs_x, f"Min score: {prefs.min_score:.2f}")
                if 4 < self.height: self.stdscr.addstr(4, prefs_x, f"Days tol: {prefs.days_tolerance}")
                if 5 < self.height: self.stdscr.addstr(5, prefs_x, f"Include done: {prefs.include_done}")
                if 6 < self.height: self.stdscr.addstr(6, prefs_x, f"Ignore common: {prefs.ignore_common}")
                if 7 < self.height:
                    prune_label = "off" if (prefs.prune_days is None or prefs.prune_days < 0) else str(prefs.prune_days)
                    self.stdscr.addstr(7, prefs_x, f"Prune days: {prune_label}")
                if 8 < self.height:
                    create_label = "no limit" if prefs.creation_defaults.since_days == 0 else f"{prefs.creation_defaults.since_days} days"
                    self.stdscr.addstr(8, prefs_x, f"Create days: {create_label}")
                if 9 < self.height:
                    max_label = "no limit" if prefs.creation_defaults.max_creates_per_run == 0 else str(prefs.creation_defaults.max_creates_per_run)
                    self.stdscr.addstr(9, prefs_x, f"Max creates: {max_label}")
                if 10 < self.height:
                    vault_label = current_vault[:18] + "..." if len(current_vault) > 21 else current_vault
                    self.stdscr.addstr(10, prefs_x, f"Default vault: {vault_label}")
                if 11 < self.height and prefs.vault_organization_enabled:
                    catch_all = prefs.catch_all_filename[:15] + "..." if len(prefs.catch_all_filename) > 18 else prefs.catch_all_filename
                    self.stdscr.addstr(11, prefs_x, f"Catch-all: {catch_all}")
            except curses.error:
                pass
    
    def _draw_statistics(self, paths: Dict[str, str], last_diff: Dict[str, Any]):
        """Draw task and link statistics."""
        stats_row = 10
        stats_x = 30
        if self.width > stats_x + 25 and stats_row < self.height - 5:  # Only show if we have room
            try:
                self.stdscr.addstr(stats_row, stats_x, "Stats:", curses.A_UNDERLINE)
                obs_total = self._count_tasks(paths['obsidian_index'])
                rem_total = self._count_tasks(paths['reminders_index'])
                links_total = self._count_links(paths['links'])
                obs_active = self._count_active_tasks(paths['obsidian_index'])
                rem_active = self._count_active_tasks(paths['reminders_index'])
                if stats_row + 1 < self.height: self.stdscr.addstr(stats_row + 1, stats_x + 2, f"Obsidian: {obs_total} (active {obs_active})")
                if stats_row + 2 < self.height: self.stdscr.addstr(stats_row + 2, stats_x + 2, f"Reminders: {rem_total} (active {rem_active})")
                if stats_row + 3 < self.height: self.stdscr.addstr(stats_row + 3, stats_x + 2, f"Links: {links_total}")
            except curses.error:
                pass

        # Last update diffs with bounds checking
        drow = stats_row + 5
        if self.width > 70 and drow < self.height - 5:  # Only show if we have room
            try:
                if last_diff.get("obs") and drow < self.height:
                    nd = last_diff["obs"]
                    self.stdscr.addstr(drow, 30, f"Last Obsidian: +{nd['new']} ~{nd['updated']} ?{nd['missing']} -{nd['deleted']}")
                    drow += 1
                if last_diff.get("rem") and drow < self.height:
                    nd = last_diff["rem"]
                    self.stdscr.addstr(drow, 30, f"Last Reminders: +{nd['new']} ~{nd['updated']} ?{nd['missing']} -{nd['deleted']}")
                    drow += 1
                if last_diff.get("links") is not None and drow < self.height:
                    links_value = last_diff['links']
                    if isinstance(links_value, dict):
                        # Handle dict format from _diff_index (show new count as delta)
                        delta = links_value.get('new', 0)
                        self.stdscr.addstr(drow, 30, f"Last Links Δ: {delta:+d}")
                    else:
                        # Handle integer format from simple subtraction
                        self.stdscr.addstr(drow, 30, f"Last Links Δ: {links_value:+d}")
            except curses.error:
                pass
    
    def _draw_paths(self, paths: Dict[str, str]):
        """Draw the current path configuration."""
        # Calculate dynamic positioning based on other elements
        paths_row = max(15, self.height - 15)  # Flexible positioning
        if paths_row < self.height - 8:  # Only show if we have room for paths + log
            try:
                if paths_row < self.height: self.stdscr.addstr(paths_row, 2, "Paths:", curses.A_UNDERLINE)
                if paths_row + 1 < self.height:
                    path_text = f"Obsidian index: {paths['obsidian_index']}"
                    self.stdscr.addstr(paths_row + 1, 4, path_text[:self.width-6])
                if paths_row + 2 < self.height:
                    path_text = f"Reminders index: {paths['reminders_index']}"
                    self.stdscr.addstr(paths_row + 2, 4, path_text[:self.width-6])
                if paths_row + 3 < self.height:
                    path_text = f"Links: {paths['links']}"
                    self.stdscr.addstr(paths_row + 3, 4, path_text[:self.width-6])
            except curses.error:
                pass
    
    def _draw_log(self, log: List[str]):
        """Draw the log area."""
        # Calculate dynamic positioning
        log_row = max(16, self.height - 14)
        if log_row < self.height - 3:  # Need room for log header + status
            try:
                if log_row < self.height: self.stdscr.addstr(log_row, 2, "Log:", curses.A_UNDERLINE)
                log_h = max(1, self.height - (log_row + 3))  # Leave room for status bar
                for i, line in enumerate(log[-log_h:]):
                    log_line_y = log_row + 1 + i
                    if log_line_y >= self.height - 2:  # Stop before status bar
                        break
                    try:
                        display_line = line[:max(1, self.width - 6)] if self.width > 6 else line[:1]
                        self.stdscr.addstr(log_line_y, 4, display_line)
                    except curses.error:
                        pass
            except curses.error:
                pass
    
    def _draw_status_bar(self, status: str, is_busy: bool = False):
        """Draw the bottom status bar."""
        if self.height >= 2:  # Ensure we have room for status bar
            try:
                # Draw separator line
                sep_y = self.height - 2
                if sep_y >= 0:
                    self.stdscr.hline(sep_y, 0, ord("-"), min(self.width, curses.COLS))
                
                # Draw status line
                status_y = self.height - 1
                if status_y >= 0:
                    # Add busy indicator to status
                    busy_indicator = "[BUSY] " if is_busy else ""
                    cancel_hint = "  c: cancel" if is_busy else ""
                    status_line = f"{busy_indicator}{status} — Enter: run  ↑/↓: move  s: settings{cancel_hint}  q: quit"
                    
                    # Truncate status line if it's too long for the terminal width
                    max_status_len = max(1, self.width - 4)  # Leave some margin
                    if len(status_line) > max_status_len:
                        status_line = status_line[:max_status_len-3] + "..."
                    if len(status_line) > 0 and self.width > 2:
                        self.stdscr.addstr(status_y, 2, status_line[:self.width-2])
            except curses.error:
                # If drawing status fails, try minimal fallback
                try:
                    if self.height > 0 and self.width > 10:
                        self.stdscr.addstr(self.height - 1, 0, "Ready", curses.A_NORMAL)
                except curses.error:
                    pass  # Give up on status if terminal is too small
    
    def show_paged_content(self, lines: List[str], title: str = ""):
        """
        Display pageable content in a modal view.
        
        Args:
            lines: List of strings to display
            title: Optional title for the modal
        """
        top = 0
        while True:
            try:
                self.stdscr.clear()
                h, w = self.stdscr.getmaxyx()
                
                # Validate minimum size
                if h < 5 or w < 20:
                    self.stdscr.addstr(0, 0, "Terminal too small")
                    self.stdscr.refresh()
                    ch = self.stdscr.getch()
                    if ch in (ord('q'), 27):
                        break
                    continue
                    
                # Draw title
                if title and h > 1:
                    title_text = title[:w-4] if len(title) > w-4 else title
                    self.stdscr.addstr(0, 2, title_text, curses.A_BOLD)
                
                # Draw content
                view_h = max(1, h - 3)
                content_start_y = 2 if title else 1
                for i in range(view_h):
                    content_y = content_start_y + i
                    if content_y >= h - 1:  # Leave room for help line
                        break
                    idx = top + i
                    if idx >= len(lines):
                        break
                    line_text = str(lines[idx])[:max(1, w - 4)]
                    self.stdscr.addstr(content_y, 2, line_text)
                
                # Draw help line
                if h > 0:
                    help_text = "q: close  ↑/↓: scroll  PgUp/PgDn: faster"
                    help_text = help_text[:max(1, w - 4)]
                    self.stdscr.addstr(h - 1, 2, help_text)
                
                self.stdscr.refresh()
            except curses.error:
                # If drawing fails, try to continue
                try:
                    self.stdscr.refresh()
                except curses.error:
                    pass
            
            ch = self.stdscr.getch()
            if ch in (ord('q'), 27):
                break
            elif ch in (curses.KEY_DOWN, ord('j')):
                if top + view_h < len(lines):
                    top += 1
            elif ch in (curses.KEY_UP, ord('k')):
                if top > 0:
                    top -= 1
            elif ch == curses.KEY_NPAGE:  # PgDn
                top = min(len(lines) - 1, top + view_h)
            elif ch == curses.KEY_PPAGE:  # PgUp
                top = max(0, top - view_h)
    
    def show_selection_modal(self, title: str, options: List[tuple], current_selection: int = 0) -> Optional[int]:
        """
        Show a modal selection dialog.
        
        Args:
            title: Modal title
            options: List of (label, value) tuples
            current_selection: Initially selected index
            
        Returns:
            Selected index or None if cancelled
        """
        sel = current_selection
        while True:
            # Draw menu overlay
            self.stdscr.clear()
            self.stdscr.addstr(0, 2, title, curses.A_BOLD)
            
            # Draw warning if applicable
            if "dangerous" in title.lower() or "reset" in title.lower():
                self.stdscr.addstr(2, 2, "This will delete selected files/directories under ~/.config.")
            
            # Draw options
            start_y = 4 if "dangerous" in title.lower() or "reset" in title.lower() else 2
            for i, (label, _) in enumerate(options):
                attr = curses.A_REVERSE if i == sel else curses.A_NORMAL
                self.stdscr.addstr(start_y + i, 4, label, attr)
            
            # Draw help
            help_y = start_y + len(options) + 1
            self.stdscr.addstr(help_y, 2, "↑/↓: move  Enter: confirm  q: cancel")
            self.stdscr.refresh()

            ch = self.stdscr.getch()
            if ch in (ord('q'), 27):
                return None
            elif ch in (curses.KEY_DOWN, ord('j')):
                sel = (sel + 1) % len(options)
            elif ch in (curses.KEY_UP, ord('k')):
                sel = (sel - 1) % len(options)
            elif ch in (10, 13):
                return sel
    
    def get_user_input(self) -> int:
        """Get a single keypress from the user."""
        return self.stdscr.getch()
    
    def restore_curses_after_subprocess(self):
        """Restore curses state after running a subprocess."""
        self.stdscr = curses.initscr()
        curses.curs_set(0)
        self.stdscr.nodelay(False)
        self.height, self.width = self.stdscr.getmaxyx()
        
        # Restore signal handler for terminal resize
        def handle_resize(signum, frame):
            self._resize_flag = True
        signal.signal(signal.SIGWINCH, handle_resize)
    
    def cleanup_curses_for_subprocess(self):
        """Clean up curses state before running a subprocess."""
        try:
            curses.endwin()
        except Exception:
            pass
    
    # Helper methods for statistics
    def _count_tasks(self, path: str) -> int:
        """Count total tasks using lightweight file size estimation."""
        try:
            import os
            if not os.path.exists(path):
                return 0
            # Use file size as rough proxy to avoid expensive JSON parsing
            size_mb = os.path.getsize(path) / (1024 * 1024)
            return int(size_mb * 600)  # Rough estimate: ~600 tasks per MB
        except Exception:
            return 0

    def _count_links(self, path: str) -> int:
        """Count total links using lightweight file size estimation."""
        try:
            import os
            if not os.path.exists(path):
                return 0
            # Use file size as rough proxy to avoid expensive JSON parsing
            size_mb = os.path.getsize(path) / (1024 * 1024)
            return int(size_mb * 1500)  # Rough estimate: ~1500 links per MB
        except Exception:
            return 0

    def _count_active_tasks(self, path: str) -> int:
        """Count active tasks using lightweight estimation."""
        try:
            # Estimate ~90% of tasks are active (not deleted)
            total = self._count_tasks(path)
            return int(total * 0.9)
        except Exception:
            return 0

    def _load_available_vaults(self):
        """Load available vaults from configuration."""
        try:
            import json
            vault_config_path = os.path.expanduser("~/.config/obsidian_vaults.json")
            if os.path.exists(vault_config_path):
                with open(vault_config_path, 'r') as f:
                    vaults = json.load(f)
                return [{"name": v.get("name", "Unknown"), "path": v.get("path", "")} for v in vaults if v.get("name")]
            return []
        except Exception:
            return []

    def _modify_setting(self, prefs, setting, direction):
        key_path = setting["key"].split('.')
        obj = prefs
        for key in key_path[:-1]:
            obj = getattr(obj, key)

        key = key_path[-1]
        current_value = getattr(obj, key)

        if setting["type"] == "bool":
            setattr(obj, key, not current_value)
        elif setting["type"] == "int":
            setattr(obj, key, current_value + direction)
        elif setting["type"] == "float":
            setattr(obj, key, round(current_value + direction * 0.05, 2))
        elif setting["type"] == "vault_selector":
            # Handle vault selection
            available_vaults = self._load_available_vaults()
            if not available_vaults:
                return  # No vaults available

            vault_names = ["Auto-detect"] + [v["name"] for v in available_vaults]

            # Find current index
            current_index = 0
            if current_value:
                try:
                    current_index = vault_names.index(current_value)
                except ValueError:
                    current_index = 0

            # Move to next/previous vault
            new_index = (current_index + direction) % len(vault_names)
            new_value = vault_names[new_index] if new_index > 0 else ""
            setattr(obj, key, new_value)

    def show_settings_screen(self, prefs):
        """Display the settings screen as a full-screen modal with scrolling."""
        selected_setting = 0
        top_line = 0

        # Define settings layout
        settings_layout = {
            "Syncing": [
                {"key": "min_score", "label": "Min Score", "type": "float"},
                {"key": "days_tolerance", "label": "Days Tolerance", "type": "int"},
                {"key": "include_done", "label": "Include Done", "type": "bool"},
                {"key": "ignore_common", "label": "Ignore Common", "type": "bool"},
                {"key": "prune_days", "label": "Prune Days", "type": "int"},
            ],
            "Vault Organization": [
                {"key": "vault_organization_enabled", "label": "Vault Organization", "type": "bool"},
                {"key": "auto_create_vault_lists", "label": "Auto-Create Lists", "type": "bool"},
                {"key": "catch_all_filename", "label": "Catch-All File", "type": "str"},
                {"key": "list_naming_template", "label": "List Template", "type": "str"},
                {"key": "preserve_list_colors", "label": "Preserve Colors", "type": "bool"},
                {"key": "cleanup_legacy_mappings", "label": "Cleanup Legacy", "type": "bool"},
                {"key": "max_lists_per_cleanup", "label": "Max Cleanup Ops", "type": "int"},
            ],
            "Calendar": [
                {"key": "calendar_vault_name", "label": "Calendar Vault", "type": "vault_selector"},
            ],
            "Creation": [
                {"key": "creation_defaults.since_days", "label": "Since Days", "type": "int"},
                {"key": "creation_defaults.max_creates_per_run", "label": "Max Creates Per Run", "type": "int"},
                {"key": "creation_defaults.include_done", "label": "Include Done (Creation)", "type": "bool"},
            ],
        }

        # Build a flat list of display items for easy navigation
        display_items = []
        settings_map = []

        for category_name, settings in settings_layout.items():
            # Add category header
            display_items.append({"type": "category", "text": category_name})

            # Add settings in this category
            for setting in settings:
                key_path = setting["key"].split('.')
                value = prefs
                for key in key_path:
                    value = getattr(value, key)

                # Special display handling for vault selector
                if setting["type"] == "vault_selector":
                    display_value = value if value else "Auto-detect"
                else:
                    display_value = value

                display_items.append({
                    "type": "setting",
                    "text": f"  {setting['label']}: {display_value}",
                    "setting": setting
                })
                settings_map.append(setting)

            # Add spacer
            display_items.append({"type": "spacer", "text": ""})

        while True:
            try:
                h, w = self.stdscr.getmaxyx()

                # Clear screen and draw title
                self.stdscr.clear()
                self.stdscr.addstr(0, 2, "Settings", curses.A_BOLD)

                # Calculate available space for content
                content_start_y = 2
                content_height = h - 4  # Leave space for title and help

                # Track which settings item is currently selected (skip non-setting items)
                setting_index = 0
                current_setting_display_index = -1

                # Draw content with scrolling
                for i in range(content_height):
                    display_index = top_line + i
                    if display_index >= len(display_items):
                        break

                    item = display_items[display_index]
                    y_pos = content_start_y + i

                    if item["type"] == "category":
                        # Category header in bold
                        self.stdscr.addstr(y_pos, 2, item["text"], curses.A_BOLD)
                    elif item["type"] == "setting":
                        # Check if this is the selected setting
                        is_selected = setting_index == selected_setting
                        if is_selected:
                            current_setting_display_index = display_index

                        attr = curses.A_REVERSE if is_selected else curses.A_NORMAL
                        text = item["text"][:w-4] if len(item["text"]) > w-4 else item["text"]
                        self.stdscr.addstr(y_pos, 2, text, attr)
                        setting_index += 1
                    elif item["type"] == "spacer":
                        # Empty line for spacing
                        pass

                # Ensure selected item is visible by adjusting scroll position
                if current_setting_display_index != -1:
                    if current_setting_display_index < top_line:
                        top_line = max(0, current_setting_display_index)
                    elif current_setting_display_index >= top_line + content_height:
                        top_line = min(len(display_items) - content_height, current_setting_display_index - content_height + 1)

                # Draw help line at bottom
                help_text = "↑/↓: navigate  ←/→: edit  q: save & exit  PgUp/PgDn: scroll"
                if h > 1:
                    help_y = h - 1
                    help_text = help_text[:w-4] if len(help_text) > w-4 else help_text
                    self.stdscr.addstr(help_y, 2, help_text)

                self.stdscr.refresh()
            except curses.error:
                # Handle terminal resize or other drawing errors
                pass

            # Handle input
            ch = self.stdscr.getch()
            if ch in (ord('q'), 27):  # q or ESC
                break
            elif ch in (curses.KEY_UP, ord('k')):
                selected_setting = (selected_setting - 1) % len(settings_map)
            elif ch in (curses.KEY_DOWN, ord('j')):
                selected_setting = (selected_setting + 1) % len(settings_map)
            elif ch in (curses.KEY_LEFT, ord('h')):
                if selected_setting < len(settings_map):
                    self._modify_setting(prefs, settings_map[selected_setting], -1)
                    # Rebuild display to show updated value
                    self._update_display_items(display_items, settings_map, prefs)
            elif ch in (curses.KEY_RIGHT, ord('l')):
                if selected_setting < len(settings_map):
                    self._modify_setting(prefs, settings_map[selected_setting], 1)
                    # Rebuild display to show updated value
                    self._update_display_items(display_items, settings_map, prefs)
            elif ch == curses.KEY_NPAGE:  # Page Down
                top_line = min(len(display_items) - content_height, top_line + content_height)
            elif ch == curses.KEY_PPAGE:  # Page Up
                top_line = max(0, top_line - content_height)

    def _update_display_items(self, display_items, settings_map, prefs):
        """Update display items with current preference values."""
        setting_index = 0
        for item in display_items:
            if item["type"] == "setting":
                setting = settings_map[setting_index]

                # Get current value
                key_path = setting["key"].split('.')
                value = prefs
                for key in key_path:
                    value = getattr(value, key)

                # Special display handling for vault selector
                if setting["type"] == "vault_selector":
                    display_value = value if value else "Auto-detect"
                else:
                    display_value = value

                # Update display text
                item["text"] = f"  {setting['label']}: {display_value}"
                setting_index += 1
