#!/usr/bin/env python3
"""
Ensure Anchors For Plan

Add Obsidian block IDs ("^t-…") only for the specific Obsidian tasks
referenced in a create-missing plan JSON produced by create_missing_counterparts.

Behavior
- Reads a plan JSON (with obs_to_rem and rem_to_obs arrays).
- For each obs_to_rem item, if obs_task has no block_id, append one to the
  exact Markdown line (by absolute path + line number).
- Dry-run by default; with --apply, writes changes and emits a JSON changeset
  for audit/rollback.

Safety
- Only edits the exact targeted line when it still matches a task pattern.
- Writes atomically by rewriting whole file if changed.
- Produces a structured changeset in the configured backups directory when
  --changes-out is provided.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import uuid
from typing import Dict, List, Any, Tuple


TASK_RE = re.compile(r"^(?P<indent>\s*)[-*]\s+\[(?P<status>[ xX])\]\s+(?P<rest>.*)$")
BLOCK_ID_RE = re.compile(r"\^(?P<bid>[A-Za-z0-9\-]+)\s*$")


def append_block_id_to_line(line: str) -> Tuple[str, str]:
    """Return (new_line, new_block_id). If line already has ID, returns original line and ''."""
    m = TASK_RE.match(line.rstrip("\n"))
    if not m:
        return line, ""
    rest = m.group("rest")
    if BLOCK_ID_RE.search(rest):
        return line, ""
    new_id = f"^t-{uuid.uuid4().hex[:12]}"
    return line.rstrip() + " " + new_id, new_id


def ensure_anchor(file_path: str, line_num: int) -> Dict[str, Any] | None:
    """Ensure anchor at 1-based line_num in file_path. Returns edit record or None."""
    if not os.path.isfile(file_path):
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except Exception:
        return None
    if line_num < 1 or line_num > len(lines):
        return None
    original = lines[line_num - 1]
    new_line, new_id = append_block_id_to_line(original)
    if not new_id:
        return None  # already has ID or not a task
    lines[line_num - 1] = new_line
    return {
        "file": file_path,
        "line": line_num,
        "original": original,
        "new": new_line,
        "block_id": new_id,
        "_updated_lines": lines,
    }


def write_changes(edits: List[Dict[str, Any]]):
    by_file: Dict[str, List[Dict[str, Any]]] = {}
    for e in edits:
        by_file.setdefault(e["file"], []).append(e)
    for path, file_edits in by_file.items():
        # Each edit contains the full updated lines array; use last one
        lines = file_edits[-1]["_updated_lines"]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Ensure block IDs for tasks in a creation plan")
    ap.add_argument("--plan", required=True, help="Path to plan JSON from create_missing_counterparts --plan-out")
    ap.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    ap.add_argument("--changes-out", help="Write JSON changeset describing edits")
    args = ap.parse_args(argv)

    try:
        with open(os.path.expanduser(args.plan), "r", encoding="utf-8") as f:
            plan = json.load(f)
    except Exception as e:
        print(f"Failed to load plan: {e}")
        return 1

    obs_items = plan.get("obs_to_rem") or []
    total = 0
    added = 0
    edits: List[Dict[str, Any]] = []

    for item in obs_items:
        obs_task = item.get("obs_task") or {}
        # Skip if already has block_id
        if obs_task.get("block_id"):
            continue
        file_info = obs_task.get("file") or {}
        # Prefer absolute path if present
        abs_path = file_info.get("absolute_path") or file_info.get("relative_path")
        line_no = int(file_info.get("line") or 0)
        if not abs_path or not line_no:
            continue
        total += 1
        edit = ensure_anchor(os.path.expanduser(abs_path), line_no)
        if edit:
            edits.append(edit)
            added += 1

    if not edits:
        print(f"Nothing to do. Candidates: {total}, to_add: 0")
        return 0

    print(f"Ensure anchors: candidates={total}, to_add={added}")
    if args.apply:
        write_changes(edits)
        print(f"Applied {added} anchor(s) across {len(set(e['file'] for e in edits))} file(s)")
    else:
        print("Dry-run mode; no changes written")

    if args.changes_out and edits:
        payload = {
            "meta": {
                "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                "edit_count": len(edits),
                "plan": os.path.abspath(os.path.expanduser(args.plan)),
            },
            "edits": [
                {k: v for k, v in e.items() if not k.startswith("_")}
                for e in edits
            ],
        }
        os.makedirs(os.path.dirname(os.path.abspath(args.changes_out)), exist_ok=True)
        with open(os.path.expanduser(args.changes_out), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"Changeset written: {os.path.expanduser(args.changes_out)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

