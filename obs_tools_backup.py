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
    proc = subprocess.run([python_bin] + args)
    return proc.returncode


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
    # Sync apply also needs EventKit for Reminders writes
    if args.tool == "sync" and getattr(args, 'action', None) == "apply":
        if platform.system() == "Darwin":
            ensure_eventkit(pybin)

    # Build command
    here = os.path.dirname(os.path.abspath(__file__))
    if args.tool == "reminders" and args.action == "discover":
        cmd = [os.path.join(here, "discover_reminders_lists.py"), "--config", args.config]
    elif args.tool == "reminders" and args.action == "collect":
        cmd = [os.path.join(here, "collect_reminders_tasks.py"), "--use-config", "--config", args.config, "--output", args.output]
    elif args.tool == "vaults" and args.action == "discover":
        cmd = [os.path.join(here, "discover_obsidian_vaults.py"), "--config", args.config, "--depth", str(args.depth)]
    elif args.tool == "ids" and args.action == "remove":
        cmd = [os.path.join(here, "remove_obsidian_ids.py")]
        if args.use_config:
            cmd.append("--use-config")
        if args.config:
            cmd.extend(["--config", args.config])
        for r in (args.root or []):
            cmd.extend(["--root", r])
        if args.apply:
            cmd.append("--apply")
        if args.backup:
            cmd.append("--backup")
        for ig in (args.ignore or []):
            cmd.extend(["--ignore", ig])
        if args.ignore_common:
            cmd.append("--ignore-common")
    elif args.tool == "tasks" and args.action == "collect":
        cmd = [os.path.join(here, "collect_obsidian_tasks.py")]
        if args.use_config:
            cmd.append("--use-config")
        if args.config:
            cmd.extend(["--config", args.config])
        for r in (args.root or []):
            cmd.extend(["--root", r])
        if args.output:
            cmd.extend(["--output", args.output])
        if args.ignore_common:
            cmd.append("--ignore-common")
    elif args.tool == "sync" and args.action == "suggest":
        cmd = [os.path.join(here, "build_sync_links.py"), "--obs", args.obs, "--rem", args.rem, "--output", args.output, "--min-score", str(args.min_score), "--days-tol", str(args.days_tol)]
        if args.include_done:
            cmd.append("--include-done")
    elif args.tool == "sync" and args.action == "update":
        cmd = [
            os.path.join(here, "update_indices_and_links.py"),
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
            cmd.append("--skip-obs")
        if args.skip_rem:
            cmd.append("--skip-rem")
        if args.skip_links:
            cmd.append("--skip-links")
        if args.ignore_common:
            cmd.append("--ignore-common")
        if args.include_done:
            cmd.append("--include-done")
    elif args.tool == "app" and args.action == "tui":
        cmd = [os.path.join(here, "app_tui.py")]
    elif args.tool == "obs" and args.action == "fix-block-ids":
        cmd = [os.path.join(here, "fix_obsidian_block_ids.py")]
        if args.use_config:
            cmd.append("--use-config")
        if args.config:
            cmd.extend(["--config", args.config])
        for r in (args.root or []):
            cmd.extend(["--root", r])
        if args.ignore_common:
            cmd.append("--ignore-common")
        if args.apply:
            cmd.append("--apply")
        if args.backup:
            cmd.append("--backup")
    elif args.tool == "duplicates" and args.action == "find":
        cmd = [os.path.join(here, "find_duplicate_tasks.py")]
        cmd.extend(["--obs", args.obs])
        cmd.extend(["--rem", args.rem]) 
        cmd.extend(["--links", args.links])
        cmd.extend(["--similarity", str(args.similarity)])
        if args.dry_run:
            cmd.append("--dry-run")
        if args.auto_remove_unsynced:
            cmd.append("--auto-remove-unsynced")
        if args.yes:
            cmd.append("--yes")
        if args.physical_remove:
            cmd.append("--physical-remove")
    elif args.tool == "operations" and args.action == "delete-duplicates":
        cmd = [os.path.join(here, "task_operations.py")]
        cmd.extend(["delete-duplicates"])
        cmd.extend(["--obs", args.obs])
        cmd.extend(["--rem", args.rem])
        cmd.extend(["--similarity", str(args.similarity)])
        if args.dry_run:
            cmd.append("--dry-run")
        if args.verbose:
            cmd.append("--verbose")
    elif args.tool == "reset" and args.action == "run":
        cmd = [os.path.join(here, "reset_obs_tools.py")]
        if args.all:
            cmd.append("--all")
        if args.configs:
            cmd.append("--configs")
        if args.indices:
            cmd.append("--indices")
        if args.links:
            cmd.append("--links")
        if args.prefs:
            cmd.append("--prefs")
        if args.backups:
            cmd.append("--backups")
        if args.yes:
            cmd.append("--yes")
    elif args.tool == "sync" and args.action == "apply":
        # Optional pre-step: refresh indices + links to repair missing identifiers
        if getattr(args, "refresh", False):
            pre_cmd = [
                os.path.join(here, "update_indices_and_links.py"),
                "--obs-output", args.obs,
                "--rem-output", args.rem,
                "--links-output", args.links,
            ]
            if getattr(args, "ignore_common", False):
                pre_cmd.append("--ignore-common")
            run_in_venv(pybin, pre_cmd)
        cmd = [os.path.join(here, "sync_links_apply.py"), "--obs", args.obs, "--rem", args.rem, "--links", args.links]
        if args.apply:
            cmd.append("--apply")
        if getattr(args, 'verbose', False):
            cmd.append("--verbose")
        if args.changes_out:
            cmd.extend(["--changes-out", args.changes_out])
    else:
        print("Unknown action. See --help.")
        return 2

    # Pass through any additional args verbatim (future-proofing)
    cmd.extend(passthrough)

    # Run the tool inside the venv
    return run_in_venv(pybin, cmd)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
