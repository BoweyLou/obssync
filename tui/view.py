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
        self._draw_preferences(state['prefs'])
        
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
    
    def _draw_preferences(self, prefs):
        """Draw the preferences summary in the right column."""
        prefs_x = 30
        if self.width > prefs_x + 20:  # Only show if we have room
            try:
                if 3 < self.height: self.stdscr.addstr(3, prefs_x, f"Min score: {prefs.min_score:.2f}")
                if 4 < self.height: self.stdscr.addstr(4, prefs_x, f"Days tol: {prefs.days_tolerance}")
                if 5 < self.height: self.stdscr.addstr(5, prefs_x, f"Include done: {prefs.include_done}")
                if 6 < self.height: self.stdscr.addstr(6, prefs_x, f"Ignore common: {prefs.ignore_common}")
                if 7 < self.height:
                    prune_label = "off" if (prefs.prune_days is None or prefs.prune_days < 0) else str(prefs.prune_days)
                    self.stdscr.addstr(7, prefs_x, f"Prune days: {prune_label}")
            except curses.error:
                pass
    
    def _draw_statistics(self, paths: Dict[str, str], last_diff: Dict[str, Any]):
        """Draw task and link statistics."""
        stats_row = 8
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
                    self.stdscr.addstr(drow, 30, f"Last Links Δ: {last_diff['links']:+d}")
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
        log_row = max(20, self.height - 10)
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

    def _count_active_tasks(self, path: str) -> int:
        """Count active (non-deleted) tasks in an index file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            tasks = data.get("tasks", {}) or {}
            return sum(1 for rec in tasks.values() if not rec.get("deleted"))
        except Exception:
            return 0