#!/usr/bin/env python3
"""
Update pipeline: refresh Obsidian + Reminders task indices, then rebuild links.

Steps (config-driven):
  1) Collect Obsidian tasks to obsidian_tasks_index.json (schema v2)
  2) Collect Reminders tasks to reminders_tasks_index.json (schema v2)
  3) Suggest/update links into sync_links.json

This script orchestrates the three steps and prints a concise summary of changes.
For Reminders, it delegates to the obs_tools launcher to ensure EventKit deps.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from typing import Dict, Tuple
from datetime import datetime, timezone

# Import configuration and modules
# This module should be run via obs_tools.py launcher, not directly
try:
    # Package-relative imports when run as a module
    from . import collect_obsidian_tasks as cot
    from . import build_sync_links as bsl
    from . import collect_reminders_tasks as crt
except ImportError:
    # Fallback for direct script execution (deprecated - use obs_tools.py instead)
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    import obs_tools.commands.collect_obsidian_tasks as cot
    import obs_tools.commands.build_sync_links as bsl
    import obs_tools.commands.collect_reminders_tasks as crt

# Import centralized path configuration
from app_config import get_path


def count_tasks(path: str) -> int:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return len(data.get("tasks", {}) or {})
    except Exception:
        return 0


def load_links(path: str) -> int:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return len(data.get("links", []) or [])
    except Exception:
        return 0


def run_obsidian_collect(obs_cfg: str, obs_out: str, ignore_common: bool) -> int:
    args = ["--use-config", "--config", obs_cfg, "--output", obs_out]
    if ignore_common:
        args.append("--ignore-common")
    return cot.main(args)


def run_reminders_collect(rem_cfg: str, rem_out: str) -> int:
    """Run the Reminders collector directly as a function call.

    Note: EventKit dependencies must be available. When running via obs_tools.py,
    these are automatically installed in the managed venv.
    """
    args = ["--use-config", "--config", rem_cfg, "--output", rem_out]
    try:
        return crt.main(args)
    except ImportError as e:
        # If EventKit is not available, provide helpful error message
        if "EventKit" in str(e) or "objc" in str(e):
            print(f"Error: EventKit dependencies not available: {e}", file=sys.stderr)
            print("Please run via 'python3 obs_tools.py' to ensure dependencies are installed.", file=sys.stderr)
            return 1
        raise


def run_links_build(obs_out: str, rem_out: str, links_out: str, min_score: float, days_tol: int, include_done: bool) -> int:
    args = [
        "--obs",
        obs_out,
        "--rem",
        rem_out,
        "--output",
        links_out,
        "--min-score",
        str(min_score),
        "--days-tol",
        str(days_tol),
    ]
    if include_done:
        args.append("--include-done")
    return bsl.main(args)


def _parse_iso(s: str) -> datetime:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


def apply_lifecycle(index_path: str, prune_days: int) -> Tuple[int, int, int]:
    """Mark missing tasks and prune to deleted after N days. Returns (total, marked_missing, marked_deleted)."""
    if prune_days is None or prune_days < 0:
        return (0, 0, 0)
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return (0, 0, 0)

    tasks = data.get("tasks", {}) or {}
    meta = data.get("meta", {}) or {}
    run_ts = _parse_iso(meta.get("generated_at") or datetime.now(timezone.utc).isoformat())
    now = datetime.now(timezone.utc)

    total = len(tasks)
    marked_missing = 0
    marked_deleted = 0

    changed = False
    for uid, rec in tasks.items():
        last_seen = rec.get("last_seen")
        last_seen_ts = _parse_iso(last_seen) if last_seen else None
        seen_this_run = (last_seen_ts == run_ts)

        if seen_this_run:
            if rec.get("missing_since"):
                rec.pop("missing_since", None)
                changed = True
            if rec.get("deleted"):
                # Resurrect if it reappeared
                rec["deleted"] = False
                rec.pop("deleted_at", None)
                changed = True
            continue

        # Not seen this run
        if not rec.get("missing_since"):
            rec["missing_since"] = run_ts.isoformat()
            marked_missing += 1
            changed = True
        # Check for prune threshold
        try:
            ms = _parse_iso(rec.get("missing_since"))
            days = (now.date() - ms.date()).days
        except Exception:
            days = 0
        if days >= prune_days:
            if not rec.get("deleted"):
                rec["deleted"] = True
                rec["deleted_at"] = now.isoformat()
                marked_deleted += 1
                changed = True

    if changed:
        # Deterministic write
        tasks_sorted = {uid: tasks[uid] for uid in sorted(tasks)}
        data["tasks"] = tasks_sorted
        new_json = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(new_json)

    return total, marked_missing, marked_deleted


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Refresh Obsidian + Reminders indices, then rebuild links.")
    ap.add_argument("--obs-config", default=get_path("obsidian_vaults"))
    ap.add_argument("--rem-config", default=get_path("reminders_lists"))
    ap.add_argument("--obs-output", default=get_path("obsidian_index"))
    ap.add_argument("--rem-output", default=get_path("reminders_index"))
    ap.add_argument("--links-output", default=get_path("links"))
    ap.add_argument("--skip-obs", action="store_true", help="Skip Obsidian collection")
    ap.add_argument("--skip-rem", action="store_true", help="Skip Reminders collection")
    ap.add_argument("--skip-links", action="store_true", help="Skip link building")
    ap.add_argument("--ignore-common", action="store_true", help="Ignore backup/config dirs for Obsidian")
    ap.add_argument("--min-score", type=float, default=0.75)
    ap.add_argument("--days-tol", type=int, default=1)
    ap.add_argument("--include-done", action="store_true")
    ap.add_argument("--prune-days", type=int, default=-1, help="Mark deleted after N days missing; negative disables")
    args = ap.parse_args(argv)

    # Baselines
    pre_obs = count_tasks(args.obs_output)
    pre_rem = count_tasks(args.rem_output)
    pre_links = load_links(args.links_output)

    # 1) Obsidian
    if not args.skip_obs:
        rc = run_obsidian_collect(args.obs_config, args.obs_output, args.ignore_common)
        if rc != 0:
            print("Obsidian collection failed with code", rc)

    # 2) Reminders
    if not args.skip_rem:
        if platform.system() != "Darwin":
            print("Skipping Reminders collection (requires macOS)")
        else:
            rc = run_reminders_collect(args.rem_config, args.rem_output)
            if rc != 0:
                print("Reminders collection failed with code", rc)

    # Mark missing/deleted based on prune policy
    if args.prune_days is not None and args.prune_days >= 0:
        o_tot, o_miss, o_del = apply_lifecycle(args.obs_output, args.prune_days)
        r_tot, r_miss, r_del = apply_lifecycle(args.rem_output, args.prune_days)
        if o_tot:
            print(f"Obsidian lifecycle: missing+{o_miss}, deleted+{o_del}")
        if r_tot:
            print(f"Reminders lifecycle: missing+{r_miss}, deleted+{r_del}")

    # 3) Links
    if not args.skip_links:
        rc = run_links_build(args.obs_output, args.rem_output, args.links_output, args.min_score, args.days_tol, args.include_done)
        if rc != 0:
            print("Link building failed with code", rc)

    # Summary
    post_obs = count_tasks(args.obs_output)
    post_rem = count_tasks(args.rem_output)
    post_links = load_links(args.links_output)

    print("Update summary:")
    print(f"- Obsidian tasks: {pre_obs} -> {post_obs} ({post_obs - pre_obs:+d})")
    print(f"- Reminders tasks: {pre_rem} -> {post_rem} ({post_rem - pre_rem:+d})")
    print(f"- Links: {pre_links} -> {post_links} ({post_links - pre_links:+d})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(os.sys.argv[1:]))
