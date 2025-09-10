#!/usr/bin/env python3
"""
Add block IDs (caret anchors) to Obsidian task lines missing them.

Behavior:
  - Finds task lines "- [ ] ..." / "- [x] ..." in .md files.
  - If a task line has no trailing block ID (e.g., "^abc123"), append one.
  - ID format: "^t-<12 hex>" derived from uuid4 (random), low collision risk.
  - Dry-run by default; use --apply to write changes.

Changeset backup (JSON):
  - You can write a centralized JSON changeset with --changes-out FILE
    that records each edit for later restore.
  - To restore, run with --restore FILE; it will attempt to put the original
    lines back safely.

Scope:
  - Uses saved vaults from discover_obsidian_vaults.py (via --use-config),
    or explicit --root paths. Skips typical noisy/backup directories when
    --ignore-common is set.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import uuid
from typing import Iterable, List, Set, Tuple, Dict, Any
import hashlib
import json
from datetime import datetime, timezone


TASK_RE = re.compile(r"^(?P<indent>\s*)[-*]\s+\[(?P<status>[ xX])\]\s+(?P<rest>.*)$")
BLOCK_ID_RE = re.compile(r"\^(?P<bid>[A-Za-z0-9\-]+)\s*$")


def iter_md_files(root: str, ignore_dirs: Set[str]) -> Iterable[str]:
    for dirpath, dirnames, filenames in os.walk(root):
        for d in list(dirnames):
            if d in ignore_dirs:
                dirnames.remove(d)
        for fn in filenames:
            if fn.lower().endswith(".md"):
                yield os.path.join(dirpath, fn)


def _sha(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def add_block_ids_in_file(path: str, apply: bool, collect_edits: bool) -> Tuple[int, int, List[Dict[str, Any]]]:
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    changed = False
    modified = 0
    tasks_total = 0
    out_lines: List[str] = []
    edits: List[Dict[str, Any]] = []

    for idx, line in enumerate(lines, start=1):
        m = TASK_RE.match(line)
        if not m:
            out_lines.append(line)
            continue
        tasks_total += 1
        rest = m.group("rest")
        if BLOCK_ID_RE.search(rest):
            out_lines.append(line)
            continue
        # Append a new block ID
        new_id = f"^t-{uuid.uuid4().hex[:12]}"
        newline = line.rstrip() + " " + new_id
        out_lines.append(newline)
        modified += 1
        changed = True
        if collect_edits:
            edits.append({
                "file": path,
                "line": idx,
                "original": line,
                "new": newline,
                "block_id": new_id,
                "sha_before": _sha(line),
                "sha_after": _sha(newline),
            })

    if changed and apply:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(out_lines) + "\n")

    return tasks_total, modified, edits


def write_changeset(edits: List[Dict[str, Any]], out_path: str) -> None:
    payload = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "edit_count": len(edits),
        },
        "edits": edits,
    }
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def restore_changeset(changes_file: str) -> Tuple[int, int, int]:
    with open(os.path.expanduser(changes_file), "r", encoding="utf-8") as f:
        data = json.load(f)
    edits = data.get("edits", []) or []
    restored = 0
    skipped = 0
    files_touched = set()
    for e in edits:
        path = e.get("file")
        new = e.get("new", "")
        original = e.get("original", "")
        line_no = int(e.get("line", 0) or 0)
        if not path or not os.path.isfile(path):
            skipped += 1
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
        except Exception:
            skipped += 1
            continue

        changed = False
        # Prefer replacing at recorded line number if matches
        if 1 <= line_no <= len(lines) and lines[line_no - 1] == new:
            lines[line_no - 1] = original
            changed = True
        else:
            # Search for unique match of 'new'
            matches = [i for i, ln in enumerate(lines) if ln == new]
            if len(matches) == 1:
                lines[matches[0]] = original
                changed = True

        if changed:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
                restored += 1
                files_touched.add(path)
            except Exception:
                skipped += 1
        else:
            skipped += 1

    return restored, skipped, len(files_touched)


def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(description="Add block IDs to Obsidian tasks that lack them.")
    p.add_argument("--use-config", action="store_true", help="Use saved vaults from discover_obsidian_vaults.py")
    p.add_argument("--config", default=os.path.expanduser("~/.config/obsidian_vaults.json"))
    p.add_argument("--root", action="append", help="Additional root(s) to include")
    p.add_argument("--ignore-common", action="store_true", help="Ignore .obsidian, .recovery_backups, .trash and VCS")
    p.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    p.add_argument("--changes-out", help="Write JSON changeset describing edits for restore")
    p.add_argument("--restore", help="Restore from a prior JSON changeset (skips scanning roots)")
    args = p.parse_args(argv)

    # Restore mode
    if args.restore:
        restored, skipped, files = restore_changeset(args.restore)
        print(f"Restore: {restored} edit(s) applied across {files} file(s); skipped {skipped}.")
        return 0

    roots: List[str] = []
    if args.use_config:
        try:
            import json
            with open(os.path.expanduser(args.config), "r", encoding="utf-8") as f:
                data = json.load(f)
            for d in data:
                if isinstance(d, dict) and d.get("path") and os.path.isdir(os.path.expanduser(d["path"])):
                    roots.append(os.path.abspath(os.path.expanduser(d["path"])))
        except Exception as e:
            print(f"Failed to load config: {e}")
    for r in (args.root or []):
        ap = os.path.abspath(os.path.expanduser(r))
        if os.path.isdir(ap):
            roots.append(ap)

    if not roots:
        roots = [os.getcwd()]

    ignore: Set[str] = {".git", ".hg", ".svn"}
    if args.ignore_common:
        ignore.update({".obsidian", ".recovery_backups", ".trash"})

    grand_tasks = 0
    grand_added = 0
    all_edits: List[Dict[str, Any]] = []
    for root in roots:
        for path in iter_md_files(root, ignore):
            tasks, added, edits = add_block_ids_in_file(path, apply=args.apply, collect_edits=bool(args.changes_out))
            if added:
                action = "updated" if args.apply else "would update"
                print(f"{path}: +{added} block-id(s) ({tasks} tasks) -> {action}")
            if edits:
                all_edits.extend(edits)
            grand_tasks += tasks
            grand_added += added

    if all_edits and args.changes_out:
        write_changeset(all_edits, os.path.expanduser(args.changes_out))
        print(f"Changeset written: {os.path.expanduser(args.changes_out)} ({len(all_edits)} edit(s))")
    print(f"Total tasks scanned: {grand_tasks}")
    print(f"Total block IDs {'added' if args.apply else 'to add'}: {grand_added}")
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"Summary: mode={mode} scanned={grand_tasks} missing_ids={grand_added}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
