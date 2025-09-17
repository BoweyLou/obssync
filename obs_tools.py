#!/usr/bin/env python3
"""
obs_tools.py — Unified launcher with an auto-managed user venv (Option B).

Purpose:
  - Provide a single entrypoint that ensures a dedicated virtualenv exists
    and contains any needed third-party deps, then runs the requested tool.

Venv location (overridable via OBS_TOOLS_HOME):
  - macOS:   ~/Library/Application Support/obs-tools/venv
  - others:  ~/.local/share/obs-tools/venv

Supported tools:
  - reminders discover  -> discover_reminders_lists.py  (needs: pyobjc, pyobjc-framework-EventKit)
  - reminders collect   -> collect_reminders_tasks.py   (needs: pyobjc, pyobjc-framework-EventKit)
  - vaults discover     -> discover_obsidian_vaults.py  (stdlib)
  - ids remove          -> remove_obsidian_ids.py       (stdlib)
  - tasks collect       -> collect_obsidian_tasks.py    (stdlib)
  - sync suggest        -> build_sync_links.py          (stdlib)
  - sync update         -> update_indices_and_links.py  (stdlib)
  - app tui             -> app_tui.py                  (stdlib)
  - obs fix-block-ids   -> fix_obsidian_block_ids.py    (stdlib)
  - duplicates find     -> find_duplicate_tasks.py     (stdlib)
  - operations delete   -> task_operations.py          (stdlib)
  - reset                -> reset_obs_tools.py           (stdlib)

Usage examples:
  python3 obs_tools.py reminders discover --config ~/.config/reminders_lists.json
  python3 obs_tools.py vaults discover
  python3 obs_tools.py ids remove --use-config --ignore-common --apply
  python3 obs_tools.py tasks collect --use-config --ignore-common --output ./index.json
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from typing import List

# Import command modules
from obs_tools.commands import (
    collect_obsidian_tasks,
    collect_reminders_tasks,
    collect_calendar_events,
    sync_calendar_to_daily_note,
    build_sync_links,
    sync_links_apply,
    create_missing_counterparts,
    discover_obsidian_vaults,
    discover_reminders_lists,
    find_duplicate_tasks,
    task_operations,
    update_indices_and_links,
    fix_obsidian_block_ids,
    reset_obs_tools,
    app_tui,
    setup,
    test_db_reader,
    vault_setup,
)

# Import configuration utilities
from app_config import get_path


def default_home() -> str:
    home = os.path.expanduser("~")
    if platform.system() == "Darwin":
        base = os.path.join(home, "Library", "Application Support", "obs-tools")
    else:
        base = os.path.join(home, ".local", "share", "obs-tools")
    return base


def venv_paths() -> tuple[str, str]:
    root = os.environ.get("OBS_TOOLS_HOME", default_home())
    venv_dir = os.path.join(root, "venv")
    python_bin = os.path.join(venv_dir, "bin", "python3") if platform.system() != "Windows" else os.path.join(venv_dir, "Scripts", "python.exe")
    return venv_dir, python_bin


def create_venv(venv_dir: str) -> None:
    os.makedirs(venv_dir, exist_ok=True)
    # If already looks like a venv, skip
    if os.path.exists(os.path.join(venv_dir, "pyvenv.cfg")):
        return
    import venv

    venv.EnvBuilder(with_pip=True).create(venv_dir)


def run_in_venv(python_bin: str, args: List[str]) -> int:
    """Legacy function - now unused but kept for compatibility."""
    proc = subprocess.run([python_bin] + args)
    return proc.returncode


def run_command_module(command_func, args: List[str]) -> int:
    """Run a command module function directly."""
    try:
        return command_func(args)
    except Exception as e:
        print(f"Command failed with error: {e}", file=sys.stderr)
        return 1


def ensure_eventkit(python_bin: str) -> None:
    # Try to import EventKit via PyObjC
    res = subprocess.run(
        [python_bin, "-c", "import objc, EventKit; print('OK')"], capture_output=True, text=True
    )
    if res.stdout.strip() == "OK":
        return
    print("Setting up EventKit dependencies in managed venv…")
    # Avoid failing hard on network-restricted environments; best-effort install
    subprocess.run([python_bin, "-m", "pip", "install", "--upgrade", "pip"], check=False)
    subprocess.run([python_bin, "-m", "pip", "install", "pyobjc", "pyobjc-framework-EventKit"], check=False)


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="obs-tools launcher with auto-managed venv")
    subparsers = parser.add_subparsers(dest="tool")

    # reminders discover
    sp_rem = subparsers.add_parser("reminders", help="Reminders tools")
    sp_rem_sub = sp_rem.add_subparsers(dest="action")
    sp_rem_disc = sp_rem_sub.add_parser("discover", help="Discover Apple Reminders lists")
    sp_rem_disc.add_argument("--config", default=os.path.expanduser("~/.config/reminders_lists.json"))
    sp_rem_coll = sp_rem_sub.add_parser("collect", help="Collect Apple Reminders tasks")
    sp_rem_coll.add_argument("--config", default=os.path.expanduser("~/.config/reminders_lists.json"))
    sp_rem_coll.add_argument("--output", default=os.path.expanduser("~/.config/reminders_tasks_index.json"))

    # vaults discover
    sp_vaults = subparsers.add_parser("vaults", help="Vault tools")
    sp_vaults_sub = sp_vaults.add_subparsers(dest="action")
    sp_vaults_disc = sp_vaults_sub.add_parser("discover", help="Discover Obsidian vaults")
    sp_vaults_disc.add_argument("--config", default=os.path.expanduser("~/.config/obsidian_vaults.json"))
    sp_vaults_disc.add_argument("--depth", type=int, default=2)

    # ids remove
    sp_ids = subparsers.add_parser("ids", help="ID tools")
    sp_ids_sub = sp_ids.add_subparsers(dest="action")
    sp_ids_remove = sp_ids_sub.add_parser("remove", help="Remove [id::UUID] from Markdown")
    sp_ids_remove.add_argument("--use-config", action="store_true")
    sp_ids_remove.add_argument("--config", default=os.path.expanduser("~/.config/obsidian_vaults.json"))
    sp_ids_remove.add_argument("--root", action="append")
    sp_ids_remove.add_argument("--apply", action="store_true")
    sp_ids_remove.add_argument("--backup", action="store_true")
    sp_ids_remove.add_argument("--ignore", action="append")
    sp_ids_remove.add_argument("--ignore-common", action="store_true")

    # tasks collect
    sp_tasks = subparsers.add_parser("tasks", help="Task tools")
    sp_tasks_sub = sp_tasks.add_subparsers(dest="action")
    sp_tasks_collect = sp_tasks_sub.add_parser("collect", help="Collect tasks across vaults")
    sp_tasks_collect.add_argument("--use-config", action="store_true")
    sp_tasks_collect.add_argument("--config", default=os.path.expanduser("~/.config/obsidian_vaults.json"))
    sp_tasks_collect.add_argument("--root", action="append")
    sp_tasks_collect.add_argument("--output", default=os.path.expanduser("~/.config/obsidian_tasks_index.json"))
    sp_tasks_collect.add_argument("--ignore-common", action="store_true")

    # calendar tools
    sp_calendar = subparsers.add_parser("calendar", help="Calendar tools")
    sp_calendar_sub = sp_calendar.add_subparsers(dest="action")
    sp_calendar_collect = sp_calendar_sub.add_parser("collect", help="Collect calendar events")
    sp_calendar_collect.add_argument("--date", help="Date to collect events for (YYYY-MM-DD, default: today)")
    sp_calendar_collect.add_argument("--calendars", nargs="*", help="Calendar IDs to include")
    sp_calendar_collect.add_argument("--output", help="Output file for events JSON")
    sp_calendar_collect.add_argument("--format", choices=["json", "markdown"], default="markdown")
    sp_calendar_collect.add_argument("--list-calendars", action="store_true", help="List available calendars")
    sp_calendar_collect.add_argument("--verbose", "-v", action="store_true")

    sp_calendar_sync = sp_calendar_sub.add_parser("sync", help="Sync calendar events to daily note")
    sp_calendar_sync.add_argument("--date", help="Date to sync events for (YYYY-MM-DD, default: today)")
    sp_calendar_sync.add_argument("--vault-path", help="Path to Obsidian vault (auto-detected if not specified)")
    sp_calendar_sync.add_argument("--calendars", nargs="*", help="Calendar IDs to include")
    sp_calendar_sync.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    sp_calendar_sync.add_argument("--verbose", "-v", action="store_true")

    # app tui (TUI launcher)
    sp_app = subparsers.add_parser("app", help="Application UI")
    sp_app_sub = sp_app.add_subparsers(dest="action")
    sp_app_tui = sp_app_sub.add_parser("tui", help="Launch curses-based TUI")

    # obs fix-block-ids
    sp_obs = subparsers.add_parser("obs", help="Obsidian tools")
    sp_obs_sub = sp_obs.add_subparsers(dest="action")
    sp_obs_fix = sp_obs_sub.add_parser("fix-block-ids", help="Add block IDs to task lines")
    sp_obs_fix.add_argument("--use-config", action="store_true")
    sp_obs_fix.add_argument("--config", default=os.path.expanduser("~/.config/obsidian_vaults.json"))
    sp_obs_fix.add_argument("--root", action="append")
    sp_obs_fix.add_argument("--ignore-common", action="store_true")
    sp_obs_fix.add_argument("--apply", action="store_true")
    sp_obs_fix.add_argument("--backup", action="store_true")

    # duplicates find
    sp_dup = subparsers.add_parser("duplicates", help="Duplicate task tools")
    sp_dup_sub = sp_dup.add_subparsers(dest="action")
    sp_dup_find = sp_dup_sub.add_parser("find", help="Find and remove duplicate tasks")
    sp_dup_find.add_argument("--obs", default=os.path.expanduser("~/.config/obsidian_tasks_index.json"))
    sp_dup_find.add_argument("--rem", default=os.path.expanduser("~/.config/reminders_tasks_index.json"))
    sp_dup_find.add_argument("--links", default=os.path.expanduser("~/.config/sync_links.json"))
    sp_dup_find.add_argument("--similarity", type=float, default=0.85)
    sp_dup_find.add_argument("--dry-run", action="store_true")
    sp_dup_find.add_argument("--auto-remove-unsynced", action="store_true")
    sp_dup_find.add_argument("--yes", action="store_true")
    sp_dup_find.add_argument("--physical-remove", action="store_true")

    # operations tools
    sp_ops = subparsers.add_parser("operations", help="Task operations tools")
    sp_ops_sub = sp_ops.add_subparsers(dest="action")
    sp_ops_delete = sp_ops_sub.add_parser("delete-duplicates", help="Physically delete duplicate tasks")
    sp_ops_delete.add_argument("--obs", default=os.path.expanduser("~/.config/obsidian_tasks_index.json"))
    sp_ops_delete.add_argument("--rem", default=os.path.expanduser("~/.config/reminders_tasks_index.json"))
    sp_ops_delete.add_argument("--similarity", type=float, default=1.0)
    sp_ops_delete.add_argument("--dry-run", action="store_true")
    sp_ops_delete.add_argument("--verbose", action="store_true")

    # reset
    sp_reset = subparsers.add_parser("reset", help="Reset configs and JSON outputs")
    sp_reset_sub = sp_reset.add_subparsers(dest="action")
    sp_reset_run = sp_reset_sub.add_parser("run", help="Run reset")
    sp_reset_run.add_argument("--all", action="store_true")
    sp_reset_run.add_argument("--configs", action="store_true")
    sp_reset_run.add_argument("--indices", action="store_true")
    sp_reset_run.add_argument("--links", action="store_true")
    sp_reset_run.add_argument("--prefs", action="store_true")
    sp_reset_run.add_argument("--backups", action="store_true")
    sp_reset_run.add_argument("--yes", action="store_true")

    # setup
    sp_setup = subparsers.add_parser("setup", help="Install optional dependencies")
    sp_setup.add_argument("--list", action="store_true", help="List available dependency groups")
    sp_setup.add_argument("--group", help="Install specific dependency group")
    sp_setup.add_argument("--all", action="store_true", help="Install all applicable dependency groups")
    sp_setup.add_argument("--test", help="Test if a dependency group is installed")
    sp_setup.add_argument("--interactive", action="store_true", help="Run interactive setup (default)")

    # test-db-reader
    sp_test_db = subparsers.add_parser("test-db-reader", help="Test SQLite database reader functionality")
    sp_test_db.add_argument("--test", choices=["discovery", "connection", "performance", "hybrid", "config", "all"], default="all", help="Which test to run")
    sp_test_db.add_argument("--output-json", help="Output results to JSON file")

    # sync suggest
    sp_sync = subparsers.add_parser("sync", help="Sync tools")
    sp_sync_sub = sp_sync.add_subparsers(dest="action")
    sp_sync_suggest = sp_sync_sub.add_parser("suggest", help="Suggest obs<->rem links")
    sp_sync_suggest.add_argument("--obs", default=os.path.expanduser("~/.config/obsidian_tasks_index.json"))
    sp_sync_suggest.add_argument("--rem", default=os.path.expanduser("~/.config/reminders_tasks_index.json"))
    sp_sync_suggest.add_argument("--output", default=os.path.expanduser("~/.config/sync_links.json"))
    sp_sync_suggest.add_argument("--min-score", type=float, default=0.75)
    sp_sync_suggest.add_argument("--days-tol", type=int, default=1)
    sp_sync_suggest.add_argument("--include-done", action="store_true")

    sp_sync_update = sp_sync_sub.add_parser("update", help="Refresh indices then rebuild links")
    sp_sync_update.add_argument("--obs-config", default=os.path.expanduser("~/.config/obsidian_vaults.json"))
    sp_sync_update.add_argument("--rem-config", default=os.path.expanduser("~/.config/reminders_lists.json"))
    sp_sync_update.add_argument("--obs-output", default=os.path.expanduser("~/.config/obsidian_tasks_index.json"))
    sp_sync_update.add_argument("--rem-output", default=os.path.expanduser("~/.config/reminders_tasks_index.json"))
    sp_sync_update.add_argument("--links-output", default=os.path.expanduser("~/.config/sync_links.json"))
    sp_sync_update.add_argument("--skip-obs", action="store_true")
    sp_sync_update.add_argument("--skip-rem", action="store_true")
    sp_sync_update.add_argument("--skip-links", action="store_true")
    sp_sync_update.add_argument("--ignore-common", action="store_true")
    sp_sync_update.add_argument("--min-score", type=float, default=0.75)
    sp_sync_update.add_argument("--days-tol", type=int, default=1)
    sp_sync_update.add_argument("--include-done", action="store_true")
    sp_sync_update.add_argument("--prune-days", type=int, default=-1)

    sp_sync_apply = sp_sync_sub.add_parser("apply", help="Apply field-level sync for linked tasks")
    sp_sync_apply.add_argument("--obs", default=os.path.expanduser("~/.config/obsidian_tasks_index.json"))
    sp_sync_apply.add_argument("--rem", default=os.path.expanduser("~/.config/reminders_tasks_index.json"))
    sp_sync_apply.add_argument("--links", default=os.path.expanduser("~/.config/sync_links.json"))
    sp_sync_apply.add_argument("--apply", action="store_true")
    sp_sync_apply.add_argument("--verbose", action="store_true", help="Print detailed EventKit operations and sync information")
    sp_sync_apply.add_argument("--changes-out", default=os.path.expanduser("~/.config/obs-tools/backups/sync_changeset.json"))
    sp_sync_apply.add_argument("--refresh", action="store_true", help="Run sync update (refresh indices + links) before applying")
    sp_sync_apply.add_argument("--ignore-common", action="store_true", help="Ignore common dirs (.obsidian, .recovery_backups, .trash) during refresh")

    sp_sync_create = sp_sync_sub.add_parser("create", help="Create missing counterpart tasks")
    sp_sync_create.add_argument("--obs", default=get_path("obsidian_index"))
    sp_sync_create.add_argument("--rem", default=get_path("reminders_index"))
    sp_sync_create.add_argument("--links", default=get_path("links"))
    sp_sync_create.add_argument("--apply", action="store_true", help="Actually create counterparts (default: dry-run)")
    sp_sync_create.add_argument("--direction", choices=["both", "obs-to-rem", "rem-to-obs"], default="both", help="Direction of counterpart creation")
    sp_sync_create.add_argument("--include-done", action="store_true", help="Include completed tasks")
    sp_sync_create.add_argument("--since", type=int, metavar="DAYS", help="Only process tasks modified within N days")
    sp_sync_create.add_argument("--max", type=int, metavar="N", help="Maximum number of counterparts to create")
    sp_sync_create.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    sp_sync_create.add_argument("--plan-out", help="Save creation plan to JSON file")

    # vault - Vault-based organization
    sp_vault = subparsers.add_parser("vault", help="Vault-based organization tools")
    sp_vault_sub = sp_vault.add_subparsers(dest="action")

    sp_vault_setup = sp_vault_sub.add_parser("setup", help="Interactive vault organization setup")

    sp_vault_analyze = sp_vault_sub.add_parser("analyze", help="Analyze vault organization opportunities")

    sp_vault_migrate = sp_vault_sub.add_parser("migrate", help="Migrate to vault-based organization")
    sp_vault_migrate.add_argument("--apply", action="store_true", help="Apply changes (default: dry-run)")
    sp_vault_migrate.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args, passthrough = parser.parse_known_args(argv)

    if not args.tool:
        parser.print_help()
        return 2

    venv_dir, pybin = venv_paths()
    create_venv(venv_dir)

    # Determine packages for the selected tool
    if args.tool == "reminders":
        if platform.system() != "Darwin":
            print("The Reminders tool requires macOS (EventKit).")
            return 1
        ensure_eventkit(pybin)
    # Calendar tools also need EventKit
    if args.tool == "calendar":
        if platform.system() != "Darwin":
            print("The Calendar tool requires macOS (EventKit).")
            return 1
        ensure_eventkit(pybin)
    # Sync apply and create also need EventKit for Reminders writes
    if args.tool == "sync" and getattr(args, 'action', None) in ("apply", "create"):
        if platform.system() == "Darwin":
            ensure_eventkit(pybin)

    # Run commands directly
    if args.tool == "reminders" and args.action == "discover":
        return run_command_module(discover_reminders_lists.main, ["--config", args.config])
    elif args.tool == "reminders" and args.action == "collect":
        return run_command_module(collect_reminders_tasks.main, ["--use-config", "--config", args.config, "--output", args.output])
    elif args.tool == "vaults" and args.action == "discover":
        return run_command_module(discover_obsidian_vaults.main, ["--config", args.config, "--depth", str(args.depth)])
    elif args.tool == "ids" and args.action == "remove":
        # Note: remove_obsidian_ids.py doesn't exist, skipping for now
        print("IDs remove command not yet implemented.")
        return 1
    elif args.tool == "tasks" and args.action == "collect":
        cmd_args = []
        if args.use_config:
            cmd_args.append("--use-config")
        if args.config:
            cmd_args.extend(["--config", args.config])
        for r in (args.root or []):
            cmd_args.extend(["--root", r])
        if args.output:
            cmd_args.extend(["--output", args.output])
        if args.ignore_common:
            cmd_args.append("--ignore-common")
        return run_command_module(collect_obsidian_tasks.main, cmd_args)
    elif args.tool == "calendar" and args.action == "collect":
        cmd_args = []
        if args.date:
            cmd_args.extend(["--date", args.date])
        if args.calendars:
            cmd_args.extend(["--calendars"] + args.calendars)
        if args.output:
            cmd_args.extend(["--output", args.output])
        if args.format:
            cmd_args.extend(["--format", args.format])
        if args.list_calendars:
            cmd_args.append("--list-calendars")
        if args.verbose:
            cmd_args.append("--verbose")
        return run_command_module(collect_calendar_events.main, cmd_args)
    elif args.tool == "calendar" and args.action == "sync":
        cmd_args = []
        if args.date:
            cmd_args.extend(["--date", args.date])
        if args.vault_path:
            cmd_args.extend(["--vault-path", args.vault_path])
        if args.calendars:
            cmd_args.extend(["--calendars"] + args.calendars)
        if args.dry_run:
            cmd_args.append("--dry-run")
        if args.verbose:
            cmd_args.append("--verbose")
        return run_command_module(sync_calendar_to_daily_note.main, cmd_args)
    elif args.tool == "sync" and args.action == "suggest":
        cmd_args = ["--obs", args.obs, "--rem", args.rem, "--output", args.output, "--min-score", str(args.min_score), "--days-tol", str(args.days_tol)]
        if args.include_done:
            cmd_args.append("--include-done")
        return run_command_module(build_sync_links.main, cmd_args)
    elif args.tool == "sync" and args.action == "update":
        cmd_args = [
            "--obs-config", args.obs_config,
            "--rem-config", args.rem_config,
            "--obs-output", args.obs_output,
            "--rem-output", args.rem_output,
            "--links-output", args.links_output,
            "--min-score", str(args.min_score),
            "--days-tol", str(args.days_tol),
            "--prune-days", str(args.prune_days),
        ]
        if args.skip_obs:
            cmd_args.append("--skip-obs")
        if args.skip_rem:
            cmd_args.append("--skip-rem")
        if args.skip_links:
            cmd_args.append("--skip-links")
        if args.ignore_common:
            cmd_args.append("--ignore-common")
        if args.include_done:
            cmd_args.append("--include-done")
        return run_command_module(update_indices_and_links.main, cmd_args)
    elif args.tool == "app" and args.action == "tui":
        return run_command_module(app_tui.main, [])
    elif args.tool == "obs" and args.action == "fix-block-ids":
        cmd_args = []
        if args.use_config:
            cmd_args.append("--use-config")
        if args.config:
            cmd_args.extend(["--config", args.config])
        for r in (args.root or []):
            cmd_args.extend(["--root", r])
        if args.ignore_common:
            cmd_args.append("--ignore-common")
        if args.apply:
            cmd_args.append("--apply")
        if args.backup:
            cmd_args.append("--backup")
        return run_command_module(fix_obsidian_block_ids.main, cmd_args)
    elif args.tool == "duplicates" and args.action == "find":
        cmd_args = ["--obs", args.obs, "--rem", args.rem, "--links", args.links, "--similarity", str(args.similarity)]
        if args.dry_run:
            cmd_args.append("--dry-run")
        if args.auto_remove_unsynced:
            cmd_args.append("--auto-remove-unsynced")
        if args.yes:
            cmd_args.append("--yes")
        if args.physical_remove:
            cmd_args.append("--physical-remove")
        return run_command_module(find_duplicate_tasks.main, cmd_args)
    elif args.tool == "operations" and args.action == "delete-duplicates":
        cmd_args = ["delete-duplicates", "--obs", args.obs, "--rem", args.rem, "--similarity", str(args.similarity)]
        if args.dry_run:
            cmd_args.append("--dry-run")
        if args.verbose:
            cmd_args.append("--verbose")
        return run_command_module(task_operations.main, cmd_args)
    elif args.tool == "reset" and args.action == "run":
        cmd_args = []
        if args.all:
            cmd_args.append("--all")
        if args.configs:
            cmd_args.append("--configs")
        if args.indices:
            cmd_args.append("--indices")
        if args.links:
            cmd_args.append("--links")
        if args.prefs:
            cmd_args.append("--prefs")
        if args.backups:
            cmd_args.append("--backups")
        if args.yes:
            cmd_args.append("--yes")
        return run_command_module(reset_obs_tools.main, cmd_args)
    elif args.tool == "sync" and args.action == "apply":
        # Optional pre-step: refresh indices + links to repair missing identifiers
        if getattr(args, "refresh", False):
            pre_cmd_args = [
                "--obs-output", args.obs,
                "--rem-output", args.rem,
                "--links-output", args.links,
            ]
            if getattr(args, "ignore_common", False):
                pre_cmd_args.append("--ignore-common")
            result = run_command_module(update_indices_and_links.main, pre_cmd_args)
            if result != 0:
                return result
        
        cmd_args = ["--obs", args.obs, "--rem", args.rem, "--links", args.links]
        if args.apply:
            cmd_args.append("--apply")
        if getattr(args, 'verbose', False):
            cmd_args.append("--verbose")
        if args.changes_out:
            cmd_args.extend(["--changes-out", args.changes_out])
        return run_command_module(sync_links_apply.main, cmd_args)
    elif args.tool == "sync" and args.action == "create":
        cmd_args = ["--obs", args.obs, "--rem", args.rem, "--links", args.links, "--direction", args.direction]
        if args.apply:
            cmd_args.append("--apply")
        if args.include_done:
            cmd_args.append("--include-done")
        if args.since:
            cmd_args.extend(["--since", str(args.since)])
        if getattr(args, 'max', None):
            cmd_args.extend(["--max", str(args.max)])
        if args.verbose:
            cmd_args.append("--verbose")
        if args.plan_out:
            cmd_args.extend(["--plan-out", args.plan_out])
        return run_command_module(create_missing_counterparts.main, cmd_args)
    elif args.tool == "setup":
        cmd_args = []
        if args.list:
            cmd_args.append("--list")
        if args.group:
            cmd_args.extend(["--group", args.group])
        if args.all:
            cmd_args.append("--all")
        if args.test:
            cmd_args.extend(["--test", args.test])
        if args.interactive:
            cmd_args.append("--interactive")
        return run_command_module(setup.main, cmd_args)
    elif args.tool == "test-db-reader":
        cmd_args = ["--test", args.test]
        if args.output_json:
            cmd_args.extend(["--output-json", args.output_json])
        return run_command_module(test_db_reader.main, cmd_args)
    elif args.tool == "vault":
        if args.action == "setup":
            return run_command_module(vault_setup.main, ["setup"])
        elif args.action == "analyze":
            return run_command_module(vault_setup.main, ["analyze"])
        elif args.action == "migrate":
            cmd_args = ["migrate"]
            if args.apply:
                cmd_args.append("--apply")
            if args.verbose:
                cmd_args.append("--verbose")
            return run_command_module(vault_setup.main, cmd_args)
        else:
            print("Unknown vault action. See --help.")
            return 2
    else:
        print("Unknown action. See --help.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
