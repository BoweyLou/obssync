#!/usr/bin/env python3
from __future__ import annotations

import curses
import os
import signal
import subprocess
import time
from typing import List

import app_config as cfg
import update_indices_and_links as uil
import json


class App:
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

    def log_line(self, s: str):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {s}"
        self.log.append(line)
        if len(self.log) > 200:
            self.log.pop(0)
        self.prefs.last_summary = line
        cfg.save_app_config(self.prefs)

    def draw(self):
        # Handle terminal resize if needed
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
        
        # Validate minimum terminal size
        if self.height < 10 or self.width < 50:
            self.stdscr.clear()
            self.stdscr.addstr(0, 0, "Terminal too small (need 50x10 min)")
            self.stdscr.refresh()
            return
            
        self.stdscr.clear()
        title = "Obsidian ↔ Reminders — Task Sync"
        title_x = max(0, (self.width - len(title)) // 2)
        if title_x + len(title) <= self.width:
            self.stdscr.addstr(0, title_x, title, curses.A_BOLD)

        # Menu with bounds checking
        menu_start_y = 2
        if menu_start_y < self.height:
            try:
                self.stdscr.addstr(menu_start_y, 2, "Actions:", curses.A_UNDERLINE)
            except curses.error:
                pass
            
            for i, item in enumerate(self.menu):
                menu_y = 3 + i
                if menu_y >= self.height - 3:  # Leave room for status bar
                    break
                try:
                    attr = curses.A_REVERSE if i == self.selected else curses.A_NORMAL
                    # Truncate menu item if too long
                    max_item_len = max(1, self.width - 6)
                    display_item = item[:max_item_len] if len(item) > max_item_len else item
                    self.stdscr.addstr(menu_y, 4, display_item, attr)
                except curses.error:
                    pass

        # Prefs summary (right column) with bounds checking
        prefs_x = 30
        if self.width > prefs_x + 20:  # Only show if we have room
            try:
                if 3 < self.height: self.stdscr.addstr(3, prefs_x, f"Min score: {self.prefs.min_score:.2f}")
                if 4 < self.height: self.stdscr.addstr(4, prefs_x, f"Days tol: {self.prefs.days_tolerance}")
                if 5 < self.height: self.stdscr.addstr(5, prefs_x, f"Include done: {self.prefs.include_done}")
                if 6 < self.height: self.stdscr.addstr(6, prefs_x, f"Ignore common: {self.prefs.ignore_common}")
                if 7 < self.height:
                    prune_label = "off" if (self.prefs.prune_days is None or self.prefs.prune_days < 0) else str(self.prefs.prune_days)
                    self.stdscr.addstr(7, prefs_x, f"Prune days: {prune_label}")
            except curses.error:
                pass

        # Stats with bounds checking
        stats_row = 8
        stats_x = 30
        if self.width > stats_x + 25 and stats_row < self.height - 5:  # Only show if we have room
            try:
                self.stdscr.addstr(stats_row, stats_x, "Stats:", curses.A_UNDERLINE)
                obs_total = self._count_tasks(self.paths['obsidian_index'])
                rem_total = self._count_tasks(self.paths['reminders_index'])
                links_total = self._count_links(self.paths['links'])
                obs_active = self._count_active_tasks(self.paths['obsidian_index'])
                rem_active = self._count_active_tasks(self.paths['reminders_index'])
                if stats_row + 1 < self.height: self.stdscr.addstr(stats_row + 1, stats_x + 2, f"Obsidian: {obs_total} (active {obs_active})")
                if stats_row + 2 < self.height: self.stdscr.addstr(stats_row + 2, stats_x + 2, f"Reminders: {rem_total} (active {rem_active})")
                if stats_row + 3 < self.height: self.stdscr.addstr(stats_row + 3, stats_x + 2, f"Links: {links_total}")
            except curses.error:
                pass

        # Last update diffs with bounds checking
        drow = stats_row + 5
        if self.width > 70 and drow < self.height - 5:  # Only show if we have room
            try:
                if self.last_diff.get("obs") and drow < self.height:
                    nd = self.last_diff["obs"]
                    self.stdscr.addstr(drow, 30, f"Last Obsidian: +{nd['new']} ~{nd['updated']} ?{nd['missing']} -{nd['deleted']}")
                    drow += 1
                if self.last_diff.get("rem") and drow < self.height:
                    nd = self.last_diff["rem"]
                    self.stdscr.addstr(drow, 30, f"Last Reminders: +{nd['new']} ~{nd['updated']} ?{nd['missing']} -{nd['deleted']}")
                    drow += 1
                if self.last_diff.get("links") is not None and drow < self.height:
                    self.stdscr.addstr(drow, 30, f"Last Links Δ: {self.last_diff['links']:+d}")
            except curses.error:
                pass

        # Paths with bounds checking
        paths_row = drow + 1
        if paths_row < self.height - 8:  # Only show if we have room for paths + log
            try:
                if paths_row < self.height: self.stdscr.addstr(paths_row, 2, "Paths:", curses.A_UNDERLINE)
                if paths_row + 1 < self.height:
                    path_text = f"Obsidian index: {self.paths['obsidian_index']}"
                    self.stdscr.addstr(paths_row + 1, 4, path_text[:self.width-6])
                if paths_row + 2 < self.height:
                    path_text = f"Reminders index: {self.paths['reminders_index']}"
                    self.stdscr.addstr(paths_row + 2, 4, path_text[:self.width-6])
                if paths_row + 3 < self.height:
                    path_text = f"Links: {self.paths['links']}"
                    self.stdscr.addstr(paths_row + 3, 4, path_text[:self.width-6])
            except curses.error:
                pass

        # Log area with bounds checking
        log_row = paths_row + 5
        if log_row < self.height - 3:  # Need room for log header + status
            try:
                if log_row < self.height: self.stdscr.addstr(log_row, 2, "Log:", curses.A_UNDERLINE)
                log_h = max(1, self.height - (log_row + 3))  # Leave room for status bar
                for i, line in enumerate(self.log[-log_h:]):
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

        # Status bar with bounds checking
        if self.height >= 2:  # Ensure we have room for status bar
            try:
                # Draw separator line
                sep_y = self.height - 2
                if sep_y >= 0:
                    self.stdscr.hline(sep_y, 0, ord("-"), min(self.width, curses.COLS))
                
                # Draw status line
                status_y = self.height - 1
                if status_y >= 0:
                    status_line = f"{self.status} — Enter: run  ↑/↓: move  s: settings  q: quit"
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

        self.stdscr.refresh()

    def run_cmd(self, args: List[str]):
        # Run a subprocess and stream minimal output into log when it finishes
        try:
            self.log_line("Running: " + " ".join(args))
            proc = subprocess.run(args, capture_output=True, text=True)
            emitted = False
            if proc.stdout:
                out_lines = proc.stdout.strip().splitlines()
                for line in out_lines[-100:]:
                    self.log_line(line)
                emitted = emitted or bool(out_lines)
            if proc.stderr:
                err_lines = proc.stderr.strip().splitlines()
                for line in err_lines[-3:]:
                    self.log_line("ERR: " + line)
                emitted = emitted or bool(err_lines)
            # Ensure we always show a completion line
            self.log_line(f"Completed (exit {proc.returncode})")
            self.status = f"Exit {proc.returncode}"
        except Exception as e:
            self.log_line(f"Exception: {e}")
            self.status = "Error"

    def run_interactive(self, args: List[str], title: str = ""):
        # Temporarily hand terminal to the child process for interactive flows
        self.log_line("Interactive: " + " ".join(args))
        try:
            curses.endwin()
        except Exception:
            pass
        try:
            subprocess.call(args)
        finally:
            # Restore curses UI
            self.stdscr = curses.initscr()
            curses.curs_set(0)
            self.stdscr.nodelay(False)
            self.height, self.width = self.stdscr.getmaxyx()
            
            # Restore signal handler for terminal resize
            def handle_resize(signum, frame):
                self._resize_flag = True
            signal.signal(signal.SIGWINCH, handle_resize)
            
            self.status = f"Returned from {title or 'command'}"

    def do_discover_vaults(self):
        self.run_interactive([os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3"), os.path.join(os.path.dirname(__file__), "discover_obsidian_vaults.py")], title="Vault discovery")

    def do_discover_reminders(self):
        # Use launcher to ensure EventKit env
        self.run_interactive([os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3"), os.path.join(os.path.dirname(__file__), "obs_tools.py"), "reminders", "discover"], title="Reminders discovery") 

    def do_collect_obsidian(self):
        # Snapshot previous index
        prev = self._load_index(self.paths["obsidian_index"]) 
        # Run via subprocess to capture output lines
        args = [
            os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3"),
            os.path.join(os.path.dirname(__file__), "collect_obsidian_tasks.py"),
            "--use-config",
            "--output",
            self.paths["obsidian_index"],
        ]
        if self.prefs.ignore_common:
            args.append("--ignore-common")
        self.status = "Collecting Obsidian…"
        self.run_cmd(args)
        # Optionally apply lifecycle prune/marking
        if self.prefs.prune_days is not None and self.prefs.prune_days >= 0:
            total, missing, deleted = uil.apply_lifecycle(self.paths["obsidian_index"], self.prefs.prune_days)
            if total:
                self.log_line(f"Obsidian lifecycle: missing+{missing}, deleted+{deleted}")
        # Log resulting count and diff
        curr = self._load_index(self.paths["obsidian_index"]) 
        self.last_diff["obs"] = self._diff_index(prev, curr, system="obs")
        count = self._count_tasks(self.paths["obsidian_index"]) 
        self.log_line(f"Obsidian tasks: {count}")
        self.status = "Ready"

    def do_collect_reminders(self):
        # Snapshot previous index
        prev = self._load_index(self.paths["reminders_index"]) 
        # Use launcher for EventKit
        self.status = "Collecting Reminders…"
        self.run_cmd([
            os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3"),
            os.path.join(os.path.dirname(__file__), "obs_tools.py"),
            "reminders",
            "collect",
            "--config",
            self.paths["reminders_lists"],
            "--output",
            self.paths["reminders_index"],
        ])
        # Optionally apply lifecycle prune/marking
        if self.prefs.prune_days is not None and self.prefs.prune_days >= 0:
            total, missing, deleted = uil.apply_lifecycle(self.paths["reminders_index"], self.prefs.prune_days)
            if total:
                self.log_line(f"Reminders lifecycle: missing+{missing}, deleted+{deleted}")
        # Log resulting count and diff
        curr = self._load_index(self.paths["reminders_index"]) 
        self.last_diff["rem"] = self._diff_index(prev, curr, system="rem")
        count = self._count_tasks(self.paths["reminders_index"]) 
        self.log_line(f"Reminders tasks: {count}")
        self.status = "Ready"

    def do_build_links(self):
        prev_links = self._count_links(self.paths["links"]) 
        prev_list = self._load_links(self.paths["links"]) 
        args = [
            os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3"),
            os.path.join(os.path.dirname(__file__), "build_sync_links.py"),
            "--obs",
            self.paths["obsidian_index"],
            "--rem",
            self.paths["reminders_index"],
            "--output",
            self.paths["links"],
            "--min-score",
            str(self.prefs.min_score),
            "--days-tol",
            str(self.prefs.days_tolerance),
        ]
        if self.prefs.include_done:
            args.append("--include-done")
        self.status = "Building links…"
        self.run_cmd(args)
        # Log resulting count
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
        self.status = "Ready"

    def do_sync_links(self):
        # Prompt for dry-run or apply
        self.status = "Sync Links: press d for dry-run, a to apply, q to cancel"
        mode = None
        while True:
            self.draw()
            ch = self.stdscr.getch()
            if ch in (ord('q'), 27):
                self.status = "Ready"
                return
            elif ch in (ord('d'), ord('D')):
                mode = 'dry'
                break
            elif ch in (ord('a'), ord('A')):
                mode = 'apply'
                break
        args = [
            os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3"),
            os.path.join(os.path.dirname(__file__), "obs_tools.py"),
            "sync", "apply",
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
        else:
            # Dry-run with verbose and plan-out file, then page the plan
            base = os.path.expanduser("~/.config/obs-tools/backups")
            os.makedirs(base, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            plan = os.path.join(base, f"sync_plan_{ts}.txt")
            args.extend(["--verbose", "--plan-out", plan])
        self.run_cmd(args)
        if mode == 'dry':
            # Open the plan in pager if available
            try:
                with open(plan, "r", encoding="utf-8") as f:
                    lines = f.read().splitlines()
                if lines:
                    self._show_paged(lines, title="Sync Plan — press q to close, PgUp/PgDn to scroll")
            except Exception:
                pass
        self.status = "Ready"

    def do_duplication_finder(self):
        """Interactive duplication finder tool."""
        self.status = "Duplication Finder: d=dry-run, f=index-only, p=physical, q=cancel"
        mode = None
        while True:
            self.draw()
            ch = self.stdscr.getch()
            if ch in (ord('q'), 27):
                self.status = "Ready"
                return
            elif ch in (ord('d'), ord('D')):
                mode = 'dry'
                break
            elif ch in (ord('f'), ord('F')):
                mode = 'fix'
                break
            elif ch in (ord('p'), ord('P')):
                mode = 'physical'
                break
        
        args = [
            os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3"),
            os.path.join(os.path.dirname(__file__), "find_duplicate_tasks.py"),
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
        self.run_interactive(args, title="Duplication Finder")
        self.status = "Ready"

    def do_update_all(self):
        self.do_collect_obsidian()
        self.do_collect_reminders()
        self.do_build_links()

    def do_settings(self):
        # Simple inline adjusters
        self.status = "Settings: +/- score, </> tol, d toggle done, i toggle ignore, [/] prune- days, p toggle prune"
        while True:
            self.draw()
            ch = self.stdscr.getch()
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

    def loop(self):
        while True:
            try:
                self.draw()
            except curses.error as e:
                # If drawing fails completely, try to recover
                try:
                    self.height, self.width = self.stdscr.getmaxyx()
                    self.stdscr.clear()
                    if self.height > 0 and self.width > 20:
                        self.stdscr.addstr(0, 0, f"Display error: {e}")
                        self.stdscr.addstr(1, 0, "Press q to quit")
                    self.stdscr.refresh()
                except curses.error:
                    pass  # Terminal is too broken, just continue
            
            try:
                ch = self.stdscr.getch()
            except curses.error:
                # If we can't get input, the terminal is broken
                time.sleep(0.1)
                continue
            if ch in (ord("q"), 27):
                break
            elif ch in (curses.KEY_DOWN, ord("j")):
                self.selected = (self.selected + 1) % len(self.menu)
            elif ch in (curses.KEY_UP, ord("k")):
                self.selected = (self.selected - 1) % len(self.menu)
            elif ch in (10, 13):
                item = self.menu[self.selected]
                if item == "Update All":
                    self.do_update_all()
                elif item == "Discover Vaults":
                    self.do_discover_vaults()
                elif item == "Collect Obsidian":
                    self.do_collect_obsidian()
                elif item == "Discover Reminders":
                    self.do_discover_reminders()
                elif item == "Collect Reminders":
                    self.do_collect_reminders()
                elif item == "Build Links":
                    self.do_build_links()
                elif item == "Link Review":
                    self.do_link_review()
                elif item == "Sync Links":
                    self.do_sync_links()
                elif item == "Duplication Finder":
                    self.do_duplication_finder()
                elif item == "Fix Block IDs":
                    self.do_fix_block_ids_interactive()
                elif item == "Restore Last Fix":
                    self.do_restore_last_fix()
                elif item == "Reset (dangerous)":
                    self.do_reset_interactive()
                elif item == "Settings":
                    self.do_settings()
                elif item == "Quit":
                    break
            elif ch == ord("s"):
                self.do_settings()

    # Helpers
    def _count_tasks(self, path: str) -> int:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return len(data.get("tasks", {}) or {})
        except Exception:
            return 0

    def _count_links(self, path: str) -> int:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return len(data.get("links", []) or [])
        except Exception:
            return 0

    def _count_active_tasks(self, path: str) -> int:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            tasks = data.get("tasks", {}) or {}
            return sum(1 for rec in tasks.values() if not rec.get("deleted"))
        except Exception:
            return 0

    # Link Review
    def do_link_review(self):
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

        self._show_paged(lines, title="Link Review — press q to close, PgUp/PgDn to scroll")

    # Block ID fixer
    def do_fix_block_ids_interactive(self):
        prompt = "Fix Block IDs: press d for dry-run, a to apply (with backups), q to cancel"
        self.status = prompt
        while True:
            self.draw()
            ch = self.stdscr.getch()
            if ch in (ord('q'), 27):
                self.status = "Ready"
                return
            elif ch in (ord('d'), ord('D')):
                args = [
                    os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3"),
                    os.path.join(os.path.dirname(__file__), "obs_tools.py"),
                    "obs", "fix-block-ids", "--use-config", "--ignore-common",
                ]
                self.run_cmd(args)
                self.status = "Ready"
                return
            elif ch in (ord('a'), ord('A')):
                # Build changeset path
                base = os.path.expanduser("~/.config/obs-tools/backups")
                os.makedirs(base, exist_ok=True)
                ts = time.strftime("%Y%m%d_%H%M%S")
                changes = os.path.join(base, f"block_id_fix_{ts}.json")
                args = [
                    os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3"),
                    os.path.join(os.path.dirname(__file__), "obs_tools.py"),
                    "obs", "fix-block-ids", "--use-config", "--ignore-common", "--apply",
                    "--changes-out", changes,
                ]
                self.run_cmd(args)
                self.status = "Ready"
                return

    def do_restore_last_fix(self):
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
        args = [
            os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3"),
            os.path.join(os.path.dirname(__file__), "fix_obsidian_block_ids.py"),
            "--restore", latest,
        ]
        self.run_cmd(args)

    def _show_paged(self, lines, title=""):
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

    def do_reset_interactive(self):
        options = [
            ("All (configs, indices, links, prefs, backups)", ["--all"]),
            ("Configs only", ["--configs"]),
            ("Indices only", ["--indices"]),
            ("Links only", ["--links"]),
            ("Prefs only", ["--prefs"]),
            ("Backups only", ["--backups"]),
            ("Cancel", None),
        ]
        sel = 0
        while True:
            # Draw menu overlay
            self.stdscr.clear()
            title = "Reset — select target and press Enter"
            self.stdscr.addstr(0, 2, title, curses.A_BOLD)
            self.stdscr.addstr(2, 2, "This will delete selected files/directories under ~/.config.")
            for i, (label, _) in enumerate(options):
                attr = curses.A_REVERSE if i == sel else curses.A_NORMAL
                self.stdscr.addstr(4 + i, 4, label, attr)
            self.stdscr.addstr(4 + len(options) + 1, 2, "↑/↓: move  Enter: confirm  q: cancel")
            self.stdscr.refresh()

            ch = self.stdscr.getch()
            if ch in (ord('q'), 27):
                self.status = "Ready"
                return
            elif ch in (curses.KEY_DOWN, ord('j')):
                sel = (sel + 1) % len(options)
            elif ch in (curses.KEY_UP, ord('k')):
                sel = (sel - 1) % len(options)
            elif ch in (10, 13):
                label, flags = options[sel]
                if flags is None:  # Cancel
                    self.status = "Ready"
                    return
                args = [
                    os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3"),
                    os.path.join(os.path.dirname(__file__), "obs_tools.py"),
                    "reset", "run", "--yes",
                ] + flags
                self.run_cmd(args)
                # Provide an explicit confirmation line in the log
                self.log_line(f"Reset run for: {label}")
                self.status = "Ready"
                return

    def _load_index(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except Exception:
            return {"meta": {}, "tasks": {}}

    def _digest_obs(self, rec: dict):
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
        return (
            rec.get("status"),
            rec.get("description"),
            rec.get("due"),
            rec.get("start"),
            rec.get("done"),
            rec.get("priority"),
        )

    def _diff_index(self, prev: dict, curr: dict, system: str):
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

    def _load_links(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("links", []) or []
        except Exception:
            return []

    def _diff_links(self, prev_list: list, curr_list: list):
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


def main() -> int:
    def _run(stdscr):
        app = App(stdscr)
        app.loop()

    curses.wrapper(_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
