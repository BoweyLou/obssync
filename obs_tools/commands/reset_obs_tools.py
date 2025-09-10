#!/usr/bin/env python3
"""
Reset tool for Obsidian ↔ Reminders Task Sync.

Clears JSON indices, configs, links, app prefs, and/or backups in a safe, explicit way.

Defaults:
  - If no target flags are provided, resets EVERYTHING (configs, indices, links, prefs, backups).
  - Dry-run by default; pass --yes to actually delete.

Examples:
  - Dry-run of full reset:  python3 reset_obs_tools.py
  - Delete indices + links only:  python3 reset_obs_tools.py --indices --links --yes
  - Delete everything without prompt:  python3 reset_obs_tools.py --all --yes
"""

from __future__ import annotations

import argparse
import os
import shutil
from typing import List, Tuple

import app_config as cfg


def existing(path: str) -> bool:
    return os.path.exists(os.path.expanduser(path))


def gather_targets(args) -> Tuple[List[str], List[str]]:
    paths = cfg.default_paths()

    files: List[str] = []
    dirs: List[str] = []

    want_all = args.all or not any([args.configs, args.indices, args.links, args.prefs, args.backups])

    if want_all or args.configs:
        files += [paths["obsidian_vaults"], paths["reminders_lists"]]
    if want_all or args.indices:
        files += [paths["obsidian_index"], paths["reminders_index"]]
    if want_all or args.links:
        files += [paths["links"]]
    if want_all or args.prefs:
        files += [paths["app_config"]]
    if want_all or args.backups:
        dirs += [os.path.join(os.path.expanduser("~/.config/obs-tools"), "backups")]

    # Dedupe while preserving order
    seen = set()
    files = [p for p in files if not (p in seen or seen.add(p))]
    seen = set()
    dirs = [p for p in dirs if not (p in seen or seen.add(p))]

    # Filter to only existing
    files = [p for p in files if existing(p)]
    dirs = [p for p in dirs if existing(p)]
    return files, dirs


def delete_targets(files: List[str], dirs: List[str]) -> Tuple[int, int]:
    fcnt = 0
    dcnt = 0
    for p in files:
        try:
            os.remove(os.path.expanduser(p))
            fcnt += 1
        except FileNotFoundError:
            pass
    for d in dirs:
        try:
            shutil.rmtree(os.path.expanduser(d))
            dcnt += 1
        except FileNotFoundError:
            pass
    return fcnt, dcnt


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Reset obs-tools configs and JSON outputs.")
    ap.add_argument("--all", action="store_true", help="Reset everything (default if no flags provided)")
    ap.add_argument("--configs", action="store_true", help="Reset discovery configs (vaults/lists)")
    ap.add_argument("--indices", action="store_true", help="Reset task indices (Obsidian/Reminders)")
    ap.add_argument("--links", action="store_true", help="Reset sync links")
    ap.add_argument("--prefs", action="store_true", help="Reset app preferences")
    ap.add_argument("--backups", action="store_true", help="Delete changeset backups directory")
    ap.add_argument("--yes", action="store_true", help="Proceed without interactive confirmation")
    args = ap.parse_args(argv)

    files, dirs = gather_targets(args)

    if not files and not dirs:
        print("Nothing to reset (no matching files/directories exist).")
        return 0

    print("Reset plan:")
    for p in files:
        print(f" - file: {p}")
    for d in dirs:
        print(f" - dir:  {d}")

    if not args.yes:
        try:
            ans = input("Proceed to delete these? Type 'RESET' to confirm: ").strip()
        except EOFError:
            print("Aborted (no input).")
            return 1
        if ans != "RESET":
            print("Aborted. Nothing deleted.")
            return 1

    fcnt, dcnt = delete_targets(files, dirs)
    print(f"Deleted {fcnt} file(s) and {dcnt} directorie(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(os.sys.argv[1:]))

