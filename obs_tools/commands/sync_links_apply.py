#!/usr/bin/env python3
"""
Phase 1 sync: Apply field-level changes between linked Obsidian and Reminders tasks.

Behavior
- Reads: obsidian index (schema v2), reminders index (schema v2), links json
- For each link obs_uuid <-> rem_uuid:
  - Skip if either task is missing or deleted
  - Field-level compare: status, due, priority, title/description (title only to Reminders for now)
  - Winner-by-freshness per field using updated_at (tie: skip field)
  - Writes (when --apply):
    - Obsidian: update status/due/priority on the Markdown line if block_id present, via safe in-place edit; record a JSON changeset when --changes-out is given
    - Reminders: update via EventKit; if EventKit unavailable, downgrade to dry-run and log
- Updates links.json: last_synced (ISO) + snapshot of key fields; write-only-if-changed

Safety
- Dry-run by default; use --apply to write
- Only edits lines with a block_id; others are logged as skipped
- Skips tasks marked deleted or with missing_since
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

# Import the new reminders gateway
from reminders_gateway import RemindersGateway, RemindersError, AuthorizationError, EventKitImportError

# Import safe I/O utilities
from lib.safe_io import (
    file_lock, 
    safe_write_json_with_lock, 
    generate_run_id, 
    ensure_run_id_in_meta, 
    check_concurrent_access
)

# Import observability utilities
from lib.observability import get_logger


# Import centralized path configuration
try:
    from app_config import get_path
    DEFAULT_OBS = get_path("obsidian_index")
    DEFAULT_REM = get_path("reminders_index") 
    DEFAULT_LINKS = get_path("links")
    DEFAULT_CHANGESET = get_path("sync_changeset")
except ImportError:
    # Fallback for standalone execution
    import os
    DEFAULT_OBS = os.path.expanduser("~/.config/obsidian_tasks_index.json")
    DEFAULT_REM = os.path.expanduser("~/.config/reminders_tasks_index.json")
    DEFAULT_LINKS = os.path.expanduser("~/.config/sync_links.json")
    DEFAULT_CHANGESET = os.path.expanduser("~/.config/obs-tools/backups/sync_changeset.json")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: str) -> dict:
    with open(os.path.expanduser(path), "r", encoding="utf-8") as f:
        return json.load(f)


def safe_write_if_changed(path: str, payload: dict, run_id: str) -> bool:
    """
    Write JSON payload to path using safe I/O with file locking.
    Returns True if file was written (changed), False if no changes.
    """
    # Add run_id to payload meta
    payload = ensure_run_id_in_meta(payload, run_id)
    
    # Check for concurrent access
    if check_concurrent_access(path, run_id):
        print(f"Warning: Concurrent access detected to {path}, proceeding with caution")
    
    # Create deterministic JSON for comparison
    new_json = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    
    # Check if file exists and content has changed
    changed = True
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                old_json = f.read()
            # Compare ignoring meta.generated_at timestamp
            try:
                import copy
                old_obj = json.loads(old_json)
                new_obj = copy.deepcopy(payload)
                old_obj.get("meta", {}).pop("generated_at", None)
                new_obj.get("meta", {}).pop("generated_at", None)
                # Also ignore run_id differences for change detection
                old_obj.get("meta", {}).pop("run_id", None)
                new_obj.get("meta", {}).pop("run_id", None)
                if json.dumps(old_obj, sort_keys=True) == json.dumps(new_obj, sort_keys=True):
                    changed = False
            except Exception:
                if old_json == new_json:
                    changed = False
        except Exception:
            pass  # Assume changed if we can't read the old file
    
    if not changed:
        return False
    
    try:
        # Write safely with file locking
        safe_write_json_with_lock(
            path, 
            payload, 
            run_id=run_id,
            indent=2,
            timeout=30.0
        )
        return True
    except Exception as e:
        print(f"Error writing to {path}: {e}")
        return False


TASK_LINE_RE = re.compile(r"^(?P<prefix>\s*[-*]\s+\[)(?P<status>[ xX])(\])(\s+)(?P<body>.*)$")
END_BLOCK_RE = re.compile(r"\s+\^[A-Za-z0-9\-]+\s*$")
# Match any 📅 YYYY-M-D or YYYY-MM-DD occurrence (no word boundary, emoji breaks \b)
DATE_ICON_RE = re.compile(r"📅\s*\d{4}-\d{1,2}-\d{1,2}")
# Also strip Tasks plugin style "(due: YYYY-MM-DD)" with lenient month/day
DUE_PAREN_RE = re.compile(r"\(\s*due\s*:\s*\d{4}-\d{1,2}-\d{1,2}\s*\)")
PRIORITY_RE = re.compile(r"[⏫🔼🔽]")


def _pad_date(iso_date: Optional[str]) -> Optional[str]:
    if not iso_date:
        return None
    try:
        # Accept YYYY-M-D or YYYY-MM-DD and return YYYY-MM-DD
        parts = iso_date.strip().split("T")[0].split("-")
        if len(parts) != 3:
            return iso_date[:10]
        y = parts[0]
        m = parts[1].zfill(2)
        d = parts[2].zfill(2)
        return f"{y}-{m}-{d}"
    except Exception:
        return iso_date[:10]


def edit_task_line(raw: str, new_status: Optional[str], new_due: Optional[str], new_priority: Optional[str]) -> str:
    """Return edited line with requested changes. Only minimal tokens are changed.
    new_status: "todo" or "done" or None
    new_due: ISO date YYYY-MM-DD or None
    new_priority: high|medium|low or None
    """
    m = TASK_LINE_RE.match(raw.rstrip("\n"))
    if not m:
        return raw
    status_char = "x" if (new_status == "done") else " " if (new_status == "todo") else m.group("status")
    prefix = m.group("prefix")
    body = m.group("body")
    # Separate trailing block id if present
    block_tail = ""
    mb = END_BLOCK_RE.search(body)
    if mb:
        block_tail = body[mb.start():]
        body = body[: mb.start()].rstrip()

    # Remove existing due tokens and priority
    body = DATE_ICON_RE.sub("", body)
    body = DUE_PAREN_RE.sub("", body)
    body = PRIORITY_RE.sub("", body)
    body = re.sub(r"\s+", " ", body).strip()

    # Append priority
    if new_priority:
        sym = {"high": "⏫", "medium": "🔼", "low": "🔽"}.get(new_priority)
        if sym:
            body = f"{body} {sym}".strip()
    # Append due date
    if new_due:
        body = f"{body} 📅 {_pad_date(new_due)}".strip()

    return f"{prefix}{status_char}] {body}{block_tail}"


def update_obsidian_line(task: dict, apply: bool, changes: list) -> Tuple[bool, Optional[str], bool]:
    """Apply minimal edits to an Obsidian task line identified by block_id.
    Returns True if a change was applied.
    """
    block_id = task.get("block_id")
    if not block_id:
        # Derive block_id from raw line if present
        raw = (task.get("raw") or "").rstrip("\n")
        mb = END_BLOCK_RE.search(raw)
        if mb:
            tail = raw[mb.start():]
            m2 = re.search(r"\^([A-Za-z0-9\-]+)\s*$", tail)
            if m2:
                block_id = m2.group(1)
    file_abs = (task.get("file") or {}).get("absolute_path")
    if not block_id or not os.path.isfile(file_abs):
        return False, None, True
    try:
        with open(file_abs, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except Exception:
        return False, None, True

    # Find the line by exact raw match first; fallback to searching for \^{block_id}
    line_no = None
    for i, ln in enumerate(lines):
        if ln.strip() == (task.get("raw") or "").strip():
            line_no = i
            break
    if line_no is None:
        for i, ln in enumerate(lines):
            if ln.rstrip().endswith(f"^{block_id}"):
                line_no = i
                break
    if line_no is None:
        return False, None, True

    raw = lines[line_no]
    new_line = edit_task_line(
        raw,
        new_status=task.get("_apply_status"),
        new_due=task.get("_apply_due"),
        new_priority=task.get("_apply_priority"),
    )

    if new_line != raw:
        if apply:
            lines[line_no] = new_line
            try:
                with open(file_abs, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
            except Exception:
                return False, None, False
        changes.append({
            "file": file_abs,
            "line": line_no + 1,
            "original": raw,
            "new": new_line,
            "block_id": block_id,
        })
        return True, new_line, False
    return False, None, False


def resolve_obsidian_current(ot: dict) -> bool:
    """Refresh ot['raw'] and file.line by locating the current line via block_id.
    Also re-derive status, due (date-only), and priority from the raw line so planning reflects reality.
    Returns True if the task line was found, False otherwise.
    """
    block_id = ot.get("block_id")
    file_abs = (ot.get("file") or {}).get("absolute_path")
    if not block_id or not file_abs or not os.path.isfile(file_abs):
        return False
    try:
        with open(file_abs, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except Exception:
        return False
    line_no = None
    for i, ln in enumerate(lines):
        if ln.rstrip().endswith(f"^{block_id}"):
            line_no = i
            break
    if line_no is None:
        return False
    raw = lines[line_no]
    # Update location and raw
    (ot.setdefault("file", {}))["line"] = line_no + 1
    ot["raw"] = raw
    # Re-parse status
    mm = TASK_LINE_RE.match(raw)
    if mm:
        ot["status"] = "done" if mm.group("status").lower() == "x" else "todo"
    # Extract due date if present
    # Prefer date-only regardless of time in source
    due = None
    m1 = DATE_ICON_RE.search(raw)
    if m1:
        due = m1.group(0).split()[-1]
    else:
        m2 = DUE_PAREN_RE.search(raw)
        if m2:
            # Find YYYY-MM-DD inside the parentheses
            mdate = re.search(r"\d{4}-\d{2}-\d{2}", m2.group(0))
            if mdate:
                due = mdate.group(0)
    ot["due"] = due
    # Extract priority symbol
    pr = None
    mprio = PRIORITY_RE.search(raw)
    if mprio:
        pr = {"⏫": "high", "🔼": "medium", "🔽": "low"}.get(mprio.group(0))
    ot["priority"] = pr
    return True


def update_reminder(rem_task: dict, apply: bool, fields: dict, ek_cache: dict, verbose: bool = False) -> bool:
    """Update reminder using the RemindersGateway. Returns True if any change planned/applied."""
    # Get or create gateway instance from cache for session reuse
    gateway = ek_cache.get("gateway")
    if not gateway:
        gateway = RemindersGateway()
        ek_cache["gateway"] = gateway
    
    try:
        # Perform the update using the gateway
        result = gateway.update_reminder(rem_task, fields, dry_run=not apply)
        
        # Update statistics cache for reporting
        if result.success:
            if result.changes_applied:
                if apply:
                    ek_cache.setdefault('save_successes', 0)
                    ek_cache['save_successes'] += 1
                
                if verbose:
                    task_desc = rem_task.get('description', '(no description)')[:40]
                    changes_str = ", ".join([f"{c.field}: {c.old_value} -> {c.new_value}" for c in result.changes_applied])
                    if apply:
                        print(f"  EventKit updated '{task_desc}': {changes_str}")
                    else:
                        print(f"  EventKit would update '{task_desc}': {changes_str} (dry-run)")
                
                return True
            else:
                # No changes needed
                return False
        else:
            # Update failed
            if result.errors:
                for error in result.errors:
                    if "not found" in error.lower():
                        ek_cache.setdefault('reminder_not_found', 0)
                        ek_cache['reminder_not_found'] += 1
                    else:
                        ek_cache.setdefault('save_failures', 0)
                        ek_cache['save_failures'] += 1
                
                if verbose or apply:  # Always show errors in apply mode
                    task_desc = rem_task.get('description', '(no description)')[:50]
                    print(f"EventKit update failed for '{task_desc}': {'; '.join(result.errors)}")
            
            return False
    
    except EventKitImportError as e:
        # EventKit not available
        if apply:
            print(f"EventKit unavailable (missing PyObjC framework): {e}")
            print("  To fix: pip install pyobjc pyobjc-framework-EventKit")
            ek_cache.setdefault('import_failures', 0)
            ek_cache['import_failures'] += 1
            return False
        else:
            # In dry-run mode, we can show what would be done
            if verbose:
                print(f"EventKit unavailable (dry-run mode): {e}")
            return True
    
    except AuthorizationError as e:
        # Authorization failed
        if apply:
            print(f"EventKit authorization failed: {e}")
            ek_cache.setdefault('auth_denied', 0)
            ek_cache['auth_denied'] += 1
            return False
        else:
            # In dry-run mode, we can show what would be done
            if verbose:
                print(f"EventKit authorization failed (dry-run mode): {e}")
            return True
    
    except RemindersError as e:
        # Other reminders error
        if apply:
            print(f"EventKit error: {e}")
            ek_cache.setdefault('save_failures', 0)
            ek_cache['save_failures'] += 1
            return False
        else:
            # In dry-run mode, we can show what would be done
            if verbose:
                print(f"EventKit error (dry-run mode): {e}")
            return True


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Sync linked tasks between Obsidian and Reminders (Phase 1)")
    ap.add_argument("--obs", default=DEFAULT_OBS)
    ap.add_argument("--rem", default=DEFAULT_REM)
    ap.add_argument("--links", default=DEFAULT_LINKS)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--verbose", action="store_true", help="Print per-link planned/applied changes")
    ap.add_argument("--changes-out", default=DEFAULT_CHANGESET, help="Write Obsidian changeset JSON when applying")
    ap.add_argument("--plan-out", help="Write verbose plan (text) to this file when --verbose is set")
    args = ap.parse_args(argv)
    
    # Initialize logger and start run tracking
    logger = get_logger("sync_links_apply")
    run_id = logger.start_run("sync_links_apply", {
        "obs_path": args.obs,
        "rem_path": args.rem,
        "links_path": args.links,
        "apply_changes": args.apply,
        "verbose": args.verbose,
        "changes_out": args.changes_out
    })

    try:
        obs = load_json(args.obs)
        rem = load_json(args.rem)
        links = load_json(args.links)
        obs_tasks: Dict[str, dict] = obs.get("tasks", {}) or {}
        rem_tasks: Dict[str, dict] = rem.get("tasks", {}) or {}
        link_list: List[dict] = links.get("links", []) or []
        
        logger.info("Loaded sync data", 
                   obs_tasks_count=len(obs_tasks),
                   rem_tasks_count=len(rem_tasks),
                   links_count=len(link_list),
                   apply_mode=args.apply)
    except Exception as e:
        logger.error("Failed to load sync data", error=str(e))
        logger.end_run(False, str(e))
        print(f"Error loading sync data: {e}")
        return 1

    # Build quick maps
    changed_obs = 0
    changed_rem = 0
    skipped = 0
    skipped_missing_block_id = 0
    skipped_file_not_found = 0
    changeset: List[dict] = []
    ek_cache: dict = {}
    per_link_results = []
    # Track if any task state changed (for index updates)
    any_obs_task_modified = False
    any_rem_task_modified = False
    # Track links that were successfully synced for last_synced updates
    synced_links = {}
    # Verbose plan buffers
    verbose_lines: List[str] = []
    summary_counts = {
        "obs_status": 0, "obs_due": 0, "obs_priority": 0,
        "rem_status": 0, "rem_due": 0, "rem_title": 0,
        "links_changed": 0,
    }

    for lk in link_list:
        ou = lk.get("obs_uuid"); ru = lk.get("rem_uuid")
        if not ou or not ru:
            continue
        ot = obs_tasks.get(ou); rt = rem_tasks.get(ru)
        if not ot or not rt:
            skipped += 1
            continue
        if ot.get("deleted") or ot.get("missing_since") or rt.get("deleted") or rt.get("missing_since"):
            skipped += 1
            continue
            
        # Mark that this link was processed (even if no changes needed)
        link_processed = True

        # Refresh Obsidian current state by block_id so planning reflects the file
        resolved = resolve_obsidian_current(ot)
        # Normalize Reminders due to date-only for comparison
        if isinstance(rt.get("due"), str):
            rt["due"] = rt["due"][:10]

        # Compare fields and decide per-field direction
        def newer(a: Optional[str], b: Optional[str]) -> int:
            # return 1 if a newer, -1 if b newer, 0 if tie/unknown
            try:
                if a == b:
                    return 0
                da = datetime.fromisoformat((a or "").replace("Z", "+00:00")) if a else None
                db = datetime.fromisoformat((b or "").replace("Z", "+00:00")) if b else None
                if da and db:
                    return 1 if da > db else -1 if db > da else 0
            except Exception:
                pass
            return 0

        def field_dir(key_obs: str, key_rem: str) -> str:
            o = ot.get(key_obs); r = rt.get(key_rem)
            # Normalize due dates to date-only for comparison
            if key_obs == 'due' and isinstance(o, str):
                o = o[:10]
            if key_rem == 'due' and isinstance(r, str):
                r = r[:10]
            if o == r:
                return "none"
            # Winner by field freshness: prefer item/file modified timestamps when available
            o_fresh = (ot.get("file") or {}).get("modified_at") or ot.get("updated_at")
            r_fresh = rt.get("item_modified_at") or rt.get("updated_at")
            n = newer(o_fresh, r_fresh)
            if n > 0:
                return "to_rem"
            elif n < 0:
                return "to_obs"
            return "none"

        # Decide fields
        dir_status = field_dir("status", "status")
        dir_due = field_dir("due", "due")
        dir_prio = field_dir("priority", "priority")
        dir_title = field_dir("description", "description")

        # Plan and apply
        any_change = False
        # Obsidian changes
        if dir_status == "to_obs" or dir_due == "to_obs" or dir_prio == "to_obs":
            # Set transient markers for edit_task_line
            if not ot.get("block_id"):
                skipped += 1
                skipped_missing_block_id += 1
                if args.verbose:
                    task_desc = ot.get('description', '(no description)')[:50]
                    file_path = (ot.get('file') or {}).get('relative_path', 'unknown')
                    print(f"  Skipped Obsidian update for '{task_desc}' in {file_path}: no block_id present")
            else:
                ot["_apply_status"] = rt.get("status") if dir_status == "to_obs" else None
                ot["_apply_due"] = (rt.get("due")[:10] if rt.get("due") else None) if dir_due == "to_obs" else None
                ot["_apply_priority"] = rt.get("priority") if dir_prio == "to_obs" else None
                changed, new_line, not_found = update_obsidian_line(ot, apply=args.apply, changes=changeset)
                if not_found:
                    skipped += 1
                    skipped_file_not_found += 1
                    if args.verbose:
                        task_desc = ot.get('description', '(no description)')[:50]
                        file_path = (ot.get('file') or {}).get('relative_path', 'unknown')
                        print(f"  Skipped Obsidian update for '{task_desc}': task not found in {file_path}")
                if changed:
                    changed_obs += 1
                    any_change = True
                    # Reflect changes into obs task record only when applying, to keep dry-run pure
                    if args.apply:
                        any_obs_task_modified = True
                        if new_line:
                            ot["raw"] = new_line
                        if dir_status == "to_obs":
                            ot["status"] = rt.get("status")
                        if dir_due == "to_obs":
                            ot["due"] = (rt.get("due")[:10] if rt.get("due") else None)
                        if dir_prio == "to_obs":
                            ot["priority"] = rt.get("priority")
                        ot["updated_at"] = now_iso()
            # Cleanup transient
            for k in ("_apply_status", "_apply_due", "_apply_priority"):
                ot.pop(k, None)

        # Reminders changes
        rem_fields = {
            "status_to_rem": dir_status == "to_rem",
            "due_to_rem": dir_due == "to_rem",
            "priority_to_rem": dir_prio == "to_rem",
            # Title pushed to Reminders if it won; Obsidian title updates deferred for safety
            "title_to_rem": dir_title == "to_rem",
            "title_value": ot.get("description") if dir_title == "to_rem" else None,
        }
        if any(rem_fields.values()):
            reminder_updated = update_reminder(rt, apply=args.apply, fields=rem_fields, ek_cache=ek_cache, verbose=args.verbose)
            if reminder_updated:
                changed_rem += 1
                any_change = True
                # Reflect changes into rem task record ONLY when EventKit operation succeeded
                if args.apply:
                    any_rem_task_modified = True
                    if dir_status == "to_rem":
                        rt["status"] = ot.get("status")
                    if dir_due == "to_rem":
                        rt["due"] = ot.get("due")
                    if dir_prio == "to_rem":
                        rt["priority"] = ot.get("priority")
                    if dir_title == "to_rem":
                        rt["description"] = ot.get("description")
                    rt["updated_at"] = now_iso()

        per_link_results.append({
            "obs_uuid": ou,
            "rem_uuid": ru,
            "changed_obs": dir_status == "to_obs" or dir_due == "to_obs" or dir_prio == "to_obs",
            "changed_rem": any(rem_fields.values()),
        })
        
        # Track processed links for last_synced updates
        # Mark as synced if:
        # 1. Any change occurred (successful sync)
        # 2. Link was processed but no changes needed (successful check)
        sync_occurred = False
        needs_field_refresh = False
        
        if any_change:
            # Had actual changes - always update last_synced and refresh fields
            sync_occurred = True
            needs_field_refresh = True
        elif link_processed:
            # No changes needed but link was fully processed - light update
            sync_occurred = True
            needs_field_refresh = False
            
        if sync_occurred:
            synced_links[ou] = {
                "timestamp": now_iso(),
                "obs_task": ot,
                "rem_task": rt,
                "had_obs_change": dir_status == "to_obs" or dir_due == "to_obs" or dir_prio == "to_obs",
                "had_rem_change": any(rem_fields.values()),
                "needs_field_refresh": needs_field_refresh
            }
        if args.verbose:
            def val(v: Optional[str]) -> str:
                return v if (v is not None and v != "") else "-"
            def date_only(v: Optional[str]) -> str:
                if not v:
                    return "-"
                return v[:10] if len(v) >= 10 else v
            # Only prepare header if there is at least one actionable change to show
            any_action = (
                dir_status in ("to_obs", "to_rem") or
                dir_due in ("to_obs", "to_rem") or
                dir_prio in ("to_obs", "to_rem") or
                dir_title == "to_rem"
            )
            if any_action:
                obs_loc = f"{(ot.get('file') or {}).get('relative_path','?')}:{(ot.get('file') or {}).get('line','?')}"
                list_name = (rt.get('list') or {}).get('name')
                if list_name:
                    rem_loc = list_name
                else:
                    # Fall back to calendar ID or generic message
                    cal_id = (rt.get('external_ids') or {}).get('calendar', '')
                    if cal_id:
                        rem_loc = f"Calendar[{cal_id[:8]}...]"
                    else:
                        rem_loc = "Reminders"  # Generic fallback
                title = (ot.get('description') or rt.get('description') or '').strip()
                if len(title) > 80:
                    title = title[:77] + '…'
                title_display = f'"{title}"' if title else '"(untitled)"'
                verbose_lines.append(f"Task {title_display} — Obsidian[{obs_loc}] ↔ Reminders[{rem_loc}]")
                summary_counts['links_changed'] += 1
                # If Obsidian change requested but not actionable due to missing block_id, note it
                if (dir_status == 'to_obs' or dir_due == 'to_obs' or dir_prio == 'to_obs') and not ot.get('block_id'):
                    verbose_lines.append("  Skipped Obsidian update: no block_id present")
                if dir_status == "to_obs":
                    verbose_lines.append(f"  Update Obsidian status: {val(ot.get('status'))} -> {val(rt.get('status'))}")
                    summary_counts['obs_status'] += 1
                elif dir_status == "to_rem":
                    verbose_lines.append(f"  Update Reminders status: {val(rt.get('status'))} -> {val(ot.get('status'))}")
                    summary_counts['rem_status'] += 1
                if dir_due == "to_obs":
                    verbose_lines.append(f"  Update Obsidian due: {date_only(ot.get('due'))} -> {date_only(rt.get('due'))}")
                    summary_counts['obs_due'] += 1
                elif dir_due == "to_rem":
                    verbose_lines.append(f"  Update Reminders due: {date_only(rt.get('due'))} -> {date_only(ot.get('due'))}")
                    summary_counts['rem_due'] += 1
                if dir_prio == "to_obs":
                    verbose_lines.append(f"  Update Obsidian priority: {val(ot.get('priority'))} -> {val(rt.get('priority'))}")
                    summary_counts['obs_priority'] += 1
                elif dir_prio == "to_rem":
                    verbose_lines.append(f"  Update Reminders priority: {val(rt.get('priority'))} -> {val(ot.get('priority'))}")
                    summary_counts['rem_priority'] = summary_counts.get('rem_priority', 0) + 1
                if dir_title == "to_rem":
                    verbose_lines.append(f"  Update Reminders title: {val(rt.get('description'))} -> {val(ot.get('description'))}")
                    summary_counts['rem_title'] += 1

    # Update links with last_synced timestamps and field snapshots for processed links
    # Performance optimization: only process links that need updates
    updated_links = []
    sync_updates_count = 0
    field_refreshes_count = 0
    
    for link in link_list:
        obs_uuid = link.get("obs_uuid")
        if obs_uuid in synced_links:
            # Create updated link with last_synced timestamp
            sync_info = synced_links[obs_uuid]
            updated_link = link.copy()
            updated_link["last_synced"] = sync_info["timestamp"]
            sync_updates_count += 1
            
            # Only refresh field snapshot if there were actual changes
            if sync_info.get("needs_field_refresh", False):
                obs_task = sync_info["obs_task"]
                rem_task = sync_info["rem_task"]
                
                # Build updated field snapshot reflecting post-sync state
                updated_fields = {
                    "obs_title": obs_task.get("description"),
                    "rem_title": rem_task.get("description"),
                    "obs_due": obs_task.get("due"),
                    "rem_due": rem_task.get("due"),
                    "obs_status": obs_task.get("status"),
                    "rem_status": rem_task.get("status"),
                    "obs_priority": obs_task.get("priority"),
                    "rem_priority": rem_task.get("priority"),
                    # Preserve computed fields from original
                    "title_similarity": link.get("fields", {}).get("title_similarity"),
                    "due_equal": link.get("fields", {}).get("due_equal"),
                    "date_distance_days": link.get("fields", {}).get("date_distance_days"),
                }
                updated_link["fields"] = updated_fields
                field_refreshes_count += 1
            # else: keep original fields unchanged for light updates
            
            updated_links.append(updated_link)
        else:
            # Keep original link unchanged
            updated_links.append(link)
    
    links_out = {
        "meta": {"schema": links.get("meta", {}).get("schema", 1), "generated_at": now_iso()},
        "links": updated_links,
    }
    wrote = safe_write_if_changed(args.links, links_out, run_id)

    # Keep indices idempotent after apply by writing updated records back
    # Always write indices back if any task state was modified (regardless of EventKit success)
    if args.apply and any_obs_task_modified:
        obs_out = {"meta": {"schema": obs.get("meta", {}).get("schema", 2), "generated_at": now_iso()}, "tasks": obs_tasks}
        safe_write_if_changed(args.obs, obs_out, run_id)
    if args.apply and any_rem_task_modified:
        rem_out = {"meta": {"schema": rem.get("meta", {}).get("schema", 2), "generated_at": now_iso()}, "tasks": rem_tasks}
        safe_write_if_changed(args.rem, rem_out, run_id)

    # EventKit operation summary
    eventkit_summary = []
    if ek_cache:
        successes = ek_cache.get('save_successes', 0)
        failures = ek_cache.get('save_failures', 0)
        exceptions = ek_cache.get('save_exceptions', 0)
        not_found = ek_cache.get('reminder_not_found', 0)
        field_errors = ek_cache.get('field_update_errors', 0)
        import_failures = ek_cache.get('import_failures', 0)
        auth_denied = ek_cache.get('auth_denied', 0)
        auth_timeouts = ek_cache.get('auth_timeouts', 0)
        
        # Log EventKit operation details
        logger.info("EventKit gateway stats",
                   save_successes=successes,
                   save_failures=failures,
                   save_exceptions=exceptions,
                   reminder_not_found=not_found,
                   field_update_errors=field_errors,
                   import_failures=import_failures,
                   auth_denied=auth_denied,
                   auth_timeouts=auth_timeouts)
        
        if successes > 0 or failures > 0 or exceptions > 0:
            eventkit_summary.append(f"EventKit operations: {successes} successful, {failures + exceptions} failed")
        if not_found > 0:
            eventkit_summary.append(f"EventKit: {not_found} reminders not found")
        if field_errors > 0:
            eventkit_summary.append(f"EventKit: {field_errors} field update errors")
        if import_failures > 0:
            eventkit_summary.append(f"EventKit: {import_failures} import failures (missing PyObjC)")
        if auth_denied > 0:
            eventkit_summary.append(f"EventKit: {auth_denied} authorization denied")
        if auth_timeouts > 0:
            eventkit_summary.append(f"EventKit: {auth_timeouts} authorization timeouts")

    # Verbose plan summary (print before final summary so it appears at top of log)
    if args.verbose and verbose_lines:
        print("Plan summary:")
        print(f"  Links with actions: {summary_counts['links_changed']}")
        print(f"  Obsidian updates: status={summary_counts['obs_status']}, due={summary_counts['obs_due']}, priority={summary_counts['obs_priority']}")
        print(f"  Reminders updates: status={summary_counts['rem_status']}, due={summary_counts['rem_due']}, title={summary_counts.get('rem_title',0)}")
        if eventkit_summary:
            print(f"  {' | '.join(eventkit_summary)}")
        print("")
        for ln in verbose_lines:
            print(ln)
        # Optional: write plan to file for paging in TUI
        if args.plan_out:
            try:
                os.makedirs(os.path.dirname(os.path.abspath(args.plan_out)), exist_ok=True)
                with open(args.plan_out, "w", encoding="utf-8") as f:
                    f.write("Plan summary:\n")
                    f.write(f"  Links with actions: {summary_counts['links_changed']}\n")
                    f.write(f"  Obsidian updates: status={summary_counts['obs_status']}, due={summary_counts['obs_due']}, priority={summary_counts['obs_priority']}\n")
                    f.write(f"  Reminders updates: status={summary_counts['rem_status']}, due={summary_counts['rem_due']}, title={summary_counts.get('rem_title',0)}\n")
                    if eventkit_summary:
                        f.write(f"  {' | '.join(eventkit_summary)}\n")
                    f.write("\n")
                    for ln in verbose_lines:
                        f.write(ln + "\n")
            except Exception:
                pass

    # Write changeset if requested and applied
    if args.apply and changeset:
        changeset_data = {
            "meta": {"generated_at": now_iso(), "edit_count": len(changeset)}, 
            "edits": changeset
        }
        try:
            safe_write_json_with_lock(
                args.changes_out,
                changeset_data,
                run_id=run_id,
                indent=2,
                timeout=30.0
            )
        except Exception as e:
            print(f"Warning: Failed to write changeset to {args.changes_out}: {e}")

    # Log comprehensive sync metrics
    logger.update_counts(
        input_counts={
            "obs_tasks": len(obs_tasks),
            "rem_tasks": len(rem_tasks),
            "links_to_sync": len(link_list)
        },
        output_counts={
            "obs_changed": changed_obs,
            "rem_changed": changed_rem,
            "skipped": skipped,
            "sync_updates": sync_updates_count,
            "field_refreshes": field_refreshes_count,
            "changeset_edits": len(changeset) if args.apply else 0
        }
    )
    
    # Log per-field change counts
    field_changes = {
        "obs_status_changes": summary_counts['obs_status'],
        "obs_due_changes": summary_counts['obs_due'], 
        "obs_priority_changes": summary_counts['obs_priority'],
        "rem_status_changes": summary_counts['rem_status'],
        "rem_due_changes": summary_counts['rem_due'],
        "rem_title_changes": summary_counts.get('rem_title', 0)
    }
    
    # Log EventKit metrics if available
    eventkit_metrics = {}
    if ek_cache:
        eventkit_metrics.update({
            "save_success_rate": successes / (successes + failures + exceptions) if (successes + failures + exceptions) > 0 else 0.0,
            "auth_failure_rate": (auth_denied + auth_timeouts) / len(link_list) if link_list else 0.0
        })
    
    logger.update_metrics({
        **field_changes,
        **eventkit_metrics,
        "links_write_success": wrote,
        "block_id_issues_rate": (skipped_missing_block_id + skipped_file_not_found) / len(link_list) if link_list else 0.0
    })
    
    mode = "APPLY" if args.apply else "DRY-RUN"
    sync_tracking_info = f" sync_tracked={sync_updates_count} fields_refreshed={field_refreshes_count}" if sync_updates_count > 0 else ""
    
    logger.info("Sync operation completed",
               mode=mode,
               obs_changed=changed_obs,
               rem_changed=changed_rem,
               skipped=skipped,
               links_written=wrote,
               **field_changes)
    
    print(f"Sync summary: mode={mode} obs_changed={changed_obs} rem_changed={changed_rem} skipped={skipped} links_written={'yes' if wrote else 'no'}{sync_tracking_info}")
    
    # Provide guidance for block_id issues
    if skipped_missing_block_id > 0 or skipped_file_not_found > 0:
        logger.warning("Block ID issues detected", 
                      missing_block_ids=skipped_missing_block_id,
                      file_not_found=skipped_file_not_found)
        print(f"Block ID issues: {skipped_missing_block_id} tasks missing block_id, {skipped_file_not_found} tasks not found in files")
        if skipped_missing_block_id > 0:
            print("  → Fix missing block IDs: python3 obs_tools.py obs fix-block-ids --use-config --apply")
        if skipped_file_not_found > 0:
            print("  → Refresh task index: python3 obs_tools.py sync update")
    
    # Always show EventKit summary if there were operations
    if eventkit_summary:
        print(f"EventKit summary: {' | '.join(eventkit_summary)}")
    
    # Repeat plan summary at the end so it's visible even with limited logs
    if args.verbose and verbose_lines:
        print(f"Plan links={summary_counts['links_changed']} obs(status={summary_counts['obs_status']},due={summary_counts['obs_due']},prio={summary_counts['obs_priority']}) rem(status={summary_counts['rem_status']},due={summary_counts['rem_due']},title={summary_counts.get('rem_title',0)})")
    
    summary_path = logger.end_run(True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(os.sys.argv[1:]))
