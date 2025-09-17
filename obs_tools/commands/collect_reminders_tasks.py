#!/usr/bin/env python3
"""
Collect Apple Reminders tasks (via EventKit) into a unified JSON index.

Reads lists from the discovery config created by discover_reminders_lists.py
(~/.config/reminders_lists.json by default). For each reminder in those lists,
extracts rich metadata and writes to a JSON file keyed by stable UUIDs.

Record shape (mirrors collect_obsidian_tasks.py where practical):
  uuid, source_key, list{...}, status, description, notes, url,
  priority, due, start, done, recurrence, alarms[], created_at, updated_at,
  item_created_at, item_modified_at

Default output: ~/.config/reminders_tasks_index.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from uuid import uuid4
import time
import hashlib
from dataclasses import dataclass
import re

# Import utilities and configuration
try:
    # When run as a module from obs_tools
    from lib.safe_io import (
        safe_write_json_with_lock,
        generate_run_id,
        ensure_run_id_in_meta,
        check_concurrent_access
    )
    from lib.observability import get_logger
    from lib.hybrid_reminders_collector import HybridRemindersCollector
    from lib.reminders_domain import RemindersDataAdapter
    from app_config import get_path, load_app_config
    from reminders_gateway import (
        RemindersGateway, RemindersError, AuthorizationError, EventKitImportError,
        to_iso_dt, components_to_iso, reminder_priority_to_text, rrule_to_text, alarm_to_dict
    )
except ImportError:
    # Fallback for direct script execution (deprecated - use obs_tools.py instead)
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from lib.safe_io import (
        safe_write_json_with_lock,
        generate_run_id,
        ensure_run_id_in_meta,
        check_concurrent_access
    )
    from lib.observability import get_logger
    from lib.hybrid_reminders_collector import HybridRemindersCollector
    from lib.reminders_domain import RemindersDataAdapter
    from app_config import get_path, load_app_config
    from reminders_gateway import (
        RemindersGateway, RemindersError, AuthorizationError, EventKitImportError,
        to_iso_dt, components_to_iso, reminder_priority_to_text, rrule_to_text, alarm_to_dict
    )


@dataclass
class ReminderSnapshot:
    """Lightweight snapshot of a reminder for change detection."""
    item_id: str
    external_id: Optional[str]
    title: str
    notes: Optional[str]
    completed: bool
    completion_date: Optional[str]
    due_date: Optional[str]
    start_date: Optional[str]
    priority: Optional[str]
    recurrence: Optional[str] 
    item_created_at: Optional[str]
    item_modified_at: Optional[str]
    content_hash: str  # Hash of all content fields for fast comparison


@dataclass
class SnapshotCache:
    """Cache of reminder snapshots for incremental collection."""
    schema_version: int
    created_at: str
    last_updated: str
    snapshots: Dict[str, ReminderSnapshot]  # item_id -> ReminderSnapshot


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_text_for_similarity(s: Optional[str]) -> List[str]:
    """Normalize text for similarity matching and return tokenized words."""
    if not s:
        return []

    s = s.lower()
    s = re.sub(r"https?://\S+", " ", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    words = [w for w in s.split(" ") if w]
    return words


# Note: to_iso_dt, components_to_iso are now imported from reminders_gateway

def nscolor_to_hex(color) -> Optional[str]:
    """Convert NSColor to hex string. Kept local as it's used in calendar caching."""
    try:
        c = color.colorUsingColorSpaceName_("NSCalibratedRGBColorSpace")
        if c is None:
            return None
        r = int(round(c.redComponent() * 255))
        g = int(round(c.greenComponent() * 255))
        b = int(round(c.blueComponent() * 255))
        return f"#{r:02X}{g:02X}{b:02X}"
    except Exception:
        return None


def load_lists(config_path: str) -> List[dict]:
    cfg = os.path.abspath(os.path.expanduser(config_path))
    if not os.path.isfile(cfg):
        raise FileNotFoundError(f"Reminders lists config not found: {cfg}")
    with open(cfg, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        entries = data.get("lists", [])
    else:
        entries = data

    lists: List[dict] = []
    for item in entries:
        if isinstance(item, dict) and item.get("identifier"):
            lists.append(item)
    return lists


def _key_for(rem) -> str:
    """Generate a stable key for a reminder object."""
    try:
        external_id = rem.calendarItemExternalIdentifier()
        if external_id:
            return f"ext:{external_id}"
    except Exception:
        pass
    cal_id = ""
    try:
        c = rem.calendar()
        if c is not None:
            cal_id = str(c.calendarIdentifier())
    except Exception:
        pass
    try:
        item_id = str(rem.calendarItemIdentifier())
    except Exception:
        item_id = ""
    return f"cid:{cal_id}|iid:{item_id}"


def reminders_from_lists_hybrid(lists: List[dict], logger, force_eventkit: bool = False) -> Tuple[Dict[str, dict], Dict[str, str], Dict[str, dict]]:
    """
    Fetch reminders using the hybrid collector (DB + EventKit).

    Returns:
        Tuple of (tasks_by_uuid, source_key_to_uuid, calendar_cache)
    """
    try:
        # Initialize hybrid collector
        collector = HybridRemindersCollector(logger=logger)

        # Convert list format for collector
        list_configs = [{'identifier': str(d['identifier'])} for d in lists]

        # Collect using optimal method
        snapshot = collector.collect_reminders_data(list_configs, force_eventkit=force_eventkit)

        # Convert snapshot to legacy format for backward compatibility
        tasks_by_uuid = {}
        source_key_to_uuid = {}
        calendar_cache = {}

        for uuid, reminder in snapshot.reminders.items():
            # Convert to schema v2 dict format
            task_dict = RemindersDataAdapter.to_schema_v2_dict(reminder)
            tasks_by_uuid[uuid] = task_dict

            # Build source key mapping
            if reminder.source_key:
                source_key_to_uuid[reminder.source_key] = uuid

        # Build calendar cache from lists
        for list_id, list_info in snapshot.lists.items():
            calendar_cache[list_id] = {
                "name": list_info.name,
                "identifier": list_info.identifier,
                "source_name": list_info.source_name,
                "source_type": list_info.source_type,
                "color": list_info.color
            }

        # Log collection statistics
        stats = collector.get_collection_stats()
        logger.info(
            f"Hybrid collection completed: mode={stats.mode_used.value}, "
            f"items={stats.items_collected}, time={stats.collection_time_ms:.1f}ms, "
            f"db_enrichment={stats.db_enrichment_rate:.1%}"
        )

        if stats.fallback_triggered:
            logger.warning(f"Fallback triggered: {stats.fallback_reason}")

        return tasks_by_uuid, source_key_to_uuid, calendar_cache

    except Exception as e:
        logger.error(f"Hybrid collection failed: {e}")
        # Fall back to legacy EventKit-only collection
        logger.info("Falling back to legacy EventKit collection")
        return reminders_from_lists_legacy(lists)


def reminders_from_lists_legacy(lists: List[dict]) -> Tuple[List[object], Dict[str, dict], Dict[str, dict]]:
    """Legacy fetch reminders using EventKit gateway only."""
    gateway = RemindersGateway()

    try:
        # Convert list format for gateway
        list_configs = [{'identifier': str(d['identifier'])} for d in lists]

        # Fetch reminders and calendar cache
        reminders, calendar_cache = gateway.get_reminders_from_lists(list_configs)

        # Create id_to_meta mapping for backward compatibility
        id_to_meta = {str(d["identifier"]): d for d in lists}

        return reminders, id_to_meta, calendar_cache

    except (RemindersError, AuthorizationError, EventKitImportError) as e:
        raise RuntimeError(str(e)) from e


def reminders_from_lists(lists: List[dict]) -> Tuple[List[object], Dict[str, dict], Dict[str, dict]]:
    """Fetch reminders using the RemindersGateway (maintained for backward compatibility)."""
    return reminders_from_lists_legacy(lists)


# Note: reminder_priority_to_text, rrule_to_text, alarm_to_dict are now imported from reminders_gateway


def load_existing(output_path: str) -> Tuple[Dict[str, dict], Dict[str, str]]:
    if not os.path.isfile(output_path):
        return {}, {}
    try:
        with open(output_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        tasks = data.get("tasks", {}) or {}
        by_source: Dict[str, str] = {}
        for uid, rec in tasks.items():
            sk = rec.get("source_key")
            if sk:
                by_source[sk] = uid
            for alias in rec.get("aliases", []) or []:
                if alias and alias not in by_source:
                    by_source[alias] = uid
        return tasks, by_source
    except Exception:
        return {}, {}


def create_reminder_snapshot(reminder) -> ReminderSnapshot:
    """Create a snapshot of a reminder for change detection."""
    try:
        title = str(reminder.title() or "").strip()
    except Exception:
        title = ""
    
    try:
        notes = str(reminder.notes()) if reminder.notes() is not None else None
    except Exception:
        notes = None
        
    try:
        completed = bool(reminder.isCompleted())
    except Exception:
        completed = False
        
    try:
        completion_dt = to_iso_dt(reminder.completionDate()) if reminder.completionDate() is not None else None
    except Exception:
        completion_dt = None
        
    try:
        due = components_to_iso(reminder.dueDateComponents()) if reminder.dueDateComponents() is not None else None
    except Exception:
        due = None
        
    try:
        start = components_to_iso(reminder.startDateComponents()) if reminder.startDateComponents() is not None else None
    except Exception:
        start = None
        
    try:
        prio = reminder_priority_to_text(int(reminder.priority()))
    except Exception:
        prio = None
        
    try:
        rec_rules = reminder.recurrenceRules() or []
        recurrence = rrule_to_text(rec_rules[0]) if rec_rules else None
    except Exception:
        recurrence = None
        
    try:
        created_at_item = to_iso_dt(reminder.creationDate()) if reminder.creationDate() is not None else None
    except Exception:
        created_at_item = None
        
    try:
        modified_at_item = to_iso_dt(reminder.lastModifiedDate()) if reminder.lastModifiedDate() is not None else None
    except Exception:
        modified_at_item = None
        
    try:
        item_id = str(reminder.calendarItemIdentifier())
    except Exception:
        item_id = ""
        
    try:
        external_id = str(reminder.calendarItemExternalIdentifier())
    except Exception:
        external_id = None
    
    # Create content hash for fast comparison
    content_fields = [
        title, notes or "", str(completed), completion_dt or "",
        due or "", start or "", prio or "", recurrence or "",
        created_at_item or "", modified_at_item or ""
    ]
    content_hash = hashlib.sha256("|".join(content_fields).encode("utf-8")).hexdigest()[:16]
    
    return ReminderSnapshot(
        item_id=item_id,
        external_id=external_id,
        title=title,
        notes=notes,
        completed=completed,
        completion_date=completion_dt,
        due_date=due,
        start_date=start,
        priority=prio,
        recurrence=recurrence,
        item_created_at=created_at_item,
        item_modified_at=modified_at_item,
        content_hash=content_hash
    )


def load_snapshot_cache(cache_path: str) -> Optional[SnapshotCache]:
    """Load snapshot cache from disk, return None if invalid or missing."""
    if not os.path.isfile(cache_path):
        return None
    
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Validate cache structure and schema version
        if not isinstance(data, dict):
            print(f"Warning: Snapshot cache file corrupted (not a dict): {cache_path}")
            return None
            
        if data.get("schema_version") != 2:
            print(f"Warning: Snapshot cache schema version mismatch, expected 2, got {data.get('schema_version')}")
            return None
        
        # Validate and recover snapshot entries
        snapshots = {}
        corrupted_entries = 0
        for item_id, snap_data in (data.get("snapshots") or {}).items():
            try:
                if not isinstance(snap_data, dict):
                    corrupted_entries += 1
                    continue
                
                # Validate required fields
                if not snap_data.get("item_id") or not isinstance(snap_data.get("title"), str):
                    corrupted_entries += 1
                    continue
                    
                # Validate content hash
                content_hash = snap_data.get("content_hash", "")
                if not content_hash or len(content_hash) != 16:
                    corrupted_entries += 1
                    continue
                
                snapshots[item_id] = ReminderSnapshot(
                    item_id=snap_data.get("item_id", ""),
                    external_id=snap_data.get("external_id"),
                    title=snap_data.get("title", ""),
                    notes=snap_data.get("notes"),
                    completed=bool(snap_data.get("completed", False)),
                    completion_date=snap_data.get("completion_date"),
                    due_date=snap_data.get("due_date"),
                    start_date=snap_data.get("start_date"),
                    priority=snap_data.get("priority"),
                    recurrence=snap_data.get("recurrence"),
                    item_created_at=snap_data.get("item_created_at"),
                    item_modified_at=snap_data.get("item_modified_at"),
                    content_hash=content_hash
                )
            except Exception:
                corrupted_entries += 1
                continue
        
        if corrupted_entries > 0:
            print(f"Warning: Recovered snapshot cache with {corrupted_entries} corrupted entries removed")
        
        return SnapshotCache(
            schema_version=data.get("schema_version", 2),
            created_at=data.get("created_at", now_iso()),
            last_updated=data.get("last_updated", now_iso()),
            snapshots=snapshots
        )
    except json.JSONDecodeError as e:
        print(f"Warning: Snapshot cache file corrupted (JSON decode error): {cache_path}: {e}")
        return None
    except Exception as e:
        print(f"Warning: Failed to load snapshot cache from {cache_path}: {e}")
        return None


def save_snapshot_cache(cache: SnapshotCache, cache_path: str) -> bool:
    """Save snapshot cache to disk with atomic write and validation."""
    import tempfile
    
    try:
        # Convert to JSON-serializable format with validation
        snapshots_data = {}
        for item_id, snapshot in cache.snapshots.items():
            # Validate snapshot before saving
            if not snapshot.item_id or not isinstance(snapshot.title, str):
                continue
            if not snapshot.content_hash or len(snapshot.content_hash) != 16:
                continue
                
            snapshots_data[item_id] = {
                "item_id": snapshot.item_id,
                "external_id": snapshot.external_id,
                "title": snapshot.title,
                "notes": snapshot.notes,
                "completed": snapshot.completed,
                "completion_date": snapshot.completion_date,
                "due_date": snapshot.due_date,
                "start_date": snapshot.start_date,
                "priority": snapshot.priority,
                "recurrence": snapshot.recurrence,
                "item_created_at": snapshot.item_created_at,
                "item_modified_at": snapshot.item_modified_at,
                "content_hash": snapshot.content_hash
            }
        
        data = {
            "schema_version": cache.schema_version,
            "created_at": cache.created_at,
            "last_updated": cache.last_updated,
            "snapshots": snapshots_data
        }
        
        # Ensure directory exists
        cache_dir = os.path.dirname(os.path.abspath(cache_path))
        os.makedirs(cache_dir, exist_ok=True)
        
        # Atomic write: write to temp file, then rename
        with tempfile.NamedTemporaryFile(
            mode="w", 
            dir=cache_dir,
            prefix=".tmp_snapshot_",
            suffix=".json",
            delete=False,
            encoding="utf-8"
        ) as f:
            temp_path = f.name
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        
        # Verify written file is valid
        try:
            with open(temp_path, "r", encoding="utf-8") as f:
                json.load(f)  # Just validate it's parseable
        except Exception as e:
            os.unlink(temp_path)
            raise Exception(f"Snapshot cache validation failed after write: {e}")
        
        # Atomic rename
        if os.name == 'nt':  # Windows
            if os.path.exists(cache_path):
                os.unlink(cache_path)
        os.rename(temp_path, cache_path)
        
        return True
        
    except Exception as e:
        print(f"Warning: Failed to save snapshot cache to {cache_path}: {e}")
        # Clean up temp file if it exists
        try:
            if 'temp_path' in locals() and os.path.exists(temp_path):
                os.unlink(temp_path)
        except Exception:
            pass
        return False


def collect_reminders_incremental(lists: List[dict], cache: Optional[SnapshotCache]) -> Tuple[List[object], SnapshotCache, Dict[str, int]]:
    """
    Collect reminders using incremental fetching with snapshot-based change detection.
    
    Returns:
        - List of reminder objects (only changed/new items in incremental mode)
        - Updated cache
        - Performance metrics dict
    """
    start_time = time.time()
    
    # Initialize new cache if none provided
    if cache is None:
        cache = SnapshotCache(
            schema_version=2,
            created_at=now_iso(),
            last_updated=now_iso(),
            snapshots={}
        )
    
    # Always fetch all reminders (EventKit doesn't support efficient deltas)
    # But we'll only process those that have changed
    reminders, id_to_meta, calendar_cache = reminders_from_lists(lists)
    
    changed_reminders = []
    new_snapshots = {}
    reminders_checked = 0
    reminders_changed = 0
    reminders_unchanged = 0
    
    for reminder in reminders:
        reminders_checked += 1
        
        # Create current snapshot
        try:
            current_snapshot = create_reminder_snapshot(reminder)
            item_id = current_snapshot.item_id
            
            if not item_id:
                continue  # Skip items without IDs
            
            # Compare with cached snapshot
            cached_snapshot = cache.snapshots.get(item_id)
            
            if cached_snapshot is None or cached_snapshot.content_hash != current_snapshot.content_hash:
                # New or changed reminder
                changed_reminders.append(reminder)
                reminders_changed += 1
            else:
                # Unchanged reminder
                reminders_unchanged += 1
            
            # Update snapshot cache
            new_snapshots[item_id] = current_snapshot
            
        except Exception as e:
            print(f"Warning: Failed to process reminder snapshot: {e}")
            continue
    
    # Update cache
    cache.snapshots = new_snapshots
    cache.last_updated = now_iso()
    
    metrics = {
        "total_time_ms": int((time.time() - start_time) * 1000),
        "reminders_checked": reminders_checked,
        "reminders_changed": reminders_changed,
        "reminders_unchanged": reminders_unchanged,
        "change_rate": reminders_changed / reminders_checked if reminders_checked > 0 else 0.0
    }
    
    return changed_reminders, cache, metrics


def collect_with_hybrid(args, logger, lists: List[dict]) -> int:
    """
    Collection using the hybrid DB+EventKit collector.

    This provides a streamlined collection path that leverages the new
    hybrid collector while maintaining full schema v2 compatibility.
    """
    logger.info("Using hybrid collector for reminders collection")

    try:
        # Use hybrid collector to get reminders data
        tasks_by_uuid, source_to_uuid, calendar_cache = reminders_from_lists_hybrid(
            lists, logger, force_eventkit=args.force_eventkit
        )

        # Build final index structure
        now = now_iso()

        # Load existing tasks for lifecycle management
        existing_tasks, existing_source_to_uuid = load_existing(args.output)

        # Merge with existing lifecycle data
        final_tasks = {}
        for uuid, task in tasks_by_uuid.items():
            if uuid in existing_tasks:
                # Preserve lifecycle fields from existing task
                existing_task = existing_tasks[uuid]
                task["created_at"] = existing_task.get("created_at", now)
                task["updated_at"] = now
                task["last_seen"] = now
                task["missing_since"] = None  # Reset since we found it
                task["deleted"] = False
            else:
                # New task
                task["created_at"] = now
                task["updated_at"] = now
                task["last_seen"] = now
                task["missing_since"] = None
                task["deleted"] = False

            final_tasks[uuid] = task

        # Mark tasks that are no longer present as missing
        for uuid, existing_task in existing_tasks.items():
            if uuid not in final_tasks:
                missing_task = existing_task.copy()
                missing_task["last_seen"] = existing_task.get("last_seen", now)
                missing_task["missing_since"] = now
                missing_task["updated_at"] = now
                final_tasks[uuid] = missing_task

        # Prepare output structure
        output_data = {
            "meta": {
                "schema": 2,
                "generated_at": now,
                "collector_type": "hybrid",
                "run_id": logger.run_id
            },
            "tasks": final_tasks
        }

        # Add run ID to meta for tracking
        output_data = ensure_run_id_in_meta(output_data, logger.run_id)

        # Write output
        safe_write_json_with_lock(args.output, output_data, indent=2)

        logger.info("Collection completed successfully",
                   total_tasks=len(final_tasks),
                   new_tasks=len([t for t in final_tasks.values() if t.get("created_at") == now]),
                   output_path=args.output)

        print(f"Collected {len(final_tasks)} tasks and wrote to {args.output}")

        # End run tracking
        logger.end_run(True, f"Successfully collected {len(final_tasks)} tasks using hybrid collector")
        return 0

    except Exception as e:
        logger.error("Hybrid collection failed", error=str(e))
        logger.end_run(False, str(e))
        print(f"Error during hybrid collection: {e}")
        return 1


def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(description="Collect Apple Reminders tasks into a single JSON index (schema v2).")
    p.add_argument("--use-config", action="store_true", help="Use saved lists from discover_reminders_lists.py")
    p.add_argument("--config", default=get_path("reminders_lists"), help="Reminders lists config JSON path")
    p.add_argument("--output", default=get_path("reminders_index"), help="Output JSON index path")
    p.add_argument("--cache", default=get_path("reminders_snapshot_cache"), help="Snapshot cache JSON path")
    p.add_argument("--no-cache", action="store_true", help="Disable incremental caching (full rescan)")
    p.add_argument("--clear-cache", action="store_true", help="Clear cache before running")
    p.add_argument("--use-hybrid", action="store_true", help="Use hybrid DB+EventKit collector (experimental)")
    p.add_argument("--force-eventkit", action="store_true", help="Force EventKit-only collection even with hybrid mode")
    args = p.parse_args(argv)
    
    # Initialize logger and start run tracking
    logger = get_logger("collect_reminders")
    run_id = logger.start_run("collect_reminders", {
        "use_config": args.use_config,
        "no_cache": args.no_cache,
        "clear_cache": args.clear_cache,
        "use_hybrid": args.use_hybrid,
        "force_eventkit": args.force_eventkit,
        "config": args.config,
        "output": args.output,
        "cache": args.cache
    })

    if not args.use_config:
        logger.error("No config specified, --use-config is required")
        logger.end_run(False, "Please provide --use-config to load lists from the discovery config.")
        print("Please provide --use-config to load lists from the discovery config.")
        return 2

    try:
        lists = load_lists(args.config)
        logger.info(f"Loaded {len(lists)} reminder lists from config", config_path=args.config)
    except FileNotFoundError as e:
        logger.error(f"Reminders lists config not found: {args.config}", error=str(e))
        logger.end_run(False, str(e))
        print(str(e))
        return 1

    if not lists:
        logger.error("No lists to scan")
        logger.end_run(False, "No lists to scan. Run discover_reminders_lists.py first.")
        print("No lists to scan. Run discover_reminders_lists.py first.")
        return 1

    # Load or initialize snapshot cache
    snapshot_cache = None
    if not args.no_cache:
        if args.clear_cache and os.path.exists(args.cache):
            logger.info("Clearing snapshot cache", cache_path=args.cache)
            print(f"Clearing snapshot cache: {args.cache}")
            os.remove(args.cache)
        snapshot_cache = load_snapshot_cache(args.cache)
        if snapshot_cache:
            cached_reminders = len(snapshot_cache.snapshots)
            logger.info("Loaded snapshot cache", 
                       cached_reminders=cached_reminders,
                       cache_path=args.cache)
            print(f"Loaded snapshot cache with {cached_reminders} reminders")
        else:
            logger.info("No valid snapshot cache found, performing full scan")
            print("No valid snapshot cache found, performing full scan")

    # Check if hybrid collector should be used
    use_hybrid_collector = args.use_hybrid
    if not use_hybrid_collector:
        # Check configuration for automatic hybrid mode
        try:
            prefs, _ = load_app_config()
            use_hybrid_collector = prefs.enable_db_reader
            if use_hybrid_collector:
                logger.info("Hybrid collector enabled via configuration")
                print("Using hybrid DB+EventKit collector (enabled in config)")
        except Exception:
            pass

    if use_hybrid_collector:
        return collect_with_hybrid(args, logger, lists)

    # Legacy collection path
    existing_tasks, source_to_uuid = load_existing(args.output)
    out_tasks: Dict[str, dict] = {}
    now = now_iso()

    # Use incremental collection
    if args.no_cache:
        logger.info("Cache disabled, performing full reminder fetch")
        print("Cache disabled, performing full reminder fetch...")
        try:
            reminders, id_to_meta, calendar_cache = reminders_from_lists(lists)
            metrics = {"total_time_ms": 0, "reminders_checked": len(reminders), "reminders_changed": len(reminders), "reminders_unchanged": 0, "change_rate": 1.0}
        except Exception as e:
            logger.error("Failed to fetch reminders", error=str(e))
            logger.end_run(False, str(e))
            print(f"Error fetching reminders: {e}")
            return 1
    else:
        logger.info("Using incremental reminder collection")
        print("Using incremental reminder collection...")
        try:
            # For incremental mode, we need to handle both changed and unchanged items
            # The challenge is that we still need the full dataset for the index
            # So we'll fetch all, but only process changed ones for performance optimization of record generation
            all_reminders, id_to_meta, calendar_cache = reminders_from_lists(lists)
            changed_reminders, snapshot_cache, metrics = collect_reminders_incremental(lists, snapshot_cache)
            
            # Log cache performance metrics
            logger.update_metrics({
                "change_rate": metrics["change_rate"],
                "processing_rate_reminders_per_sec": metrics["reminders_checked"] / (metrics["total_time_ms"] / 1000) if metrics["total_time_ms"] > 0 else 0
            })
            
            # Save updated cache
            if save_snapshot_cache(snapshot_cache, args.cache):
                logger.info("Snapshot cache saved successfully", cache_path=args.cache)
                print(f"Snapshot cache saved to {args.cache}")
            else:
                logger.warning("Failed to save snapshot cache", cache_path=args.cache)
            
            # Print performance metrics
            logger.info("Collection performance", **metrics)
            print(f"Performance: {metrics['total_time_ms']}ms, "
                  f"reminders checked: {metrics['reminders_checked']}, "
                  f"changed: {metrics['reminders_changed']}, "
                  f"unchanged: {metrics['reminders_unchanged']}, "
                  f"change rate: {metrics['change_rate']:.1%}")
            
            # For now, process all reminders (we could optimize this further by only processing changed ones
            # and carrying forward unchanged records from the existing index)
            reminders = all_reminders
            
        except Exception as e:
            logger.error("Failed during incremental collection", error=str(e))
            logger.end_run(False, str(e))
            print(f"Error during incremental collection: {e}")
            return 1

    logger.info("Processing reminders", total_reminders=len(reminders))
    processed_reminders = 0
    
    for r in reminders:
        try:
            title = str(r.title() or "").strip()
        except Exception:
            title = ""
        try:
            notes = str(r.notes()) if r.notes() is not None else None
        except Exception:
            notes = None
        try:
            url = str(r.URL().absoluteString()) if r.URL() is not None else None
        except Exception:
            url = None
        try:
            completed = bool(r.isCompleted())
        except Exception:
            completed = False
        try:
            completion_dt = to_iso_dt(r.completionDate()) if r.completionDate() is not None else None
        except Exception:
            completion_dt = None
        try:
            due = components_to_iso(r.dueDateComponents()) if r.dueDateComponents() is not None else None
        except Exception:
            due = None
        try:
            start = components_to_iso(r.startDateComponents()) if r.startDateComponents() is not None else None
        except Exception:
            start = None
        try:
            prio = reminder_priority_to_text(int(r.priority()))
        except Exception:
            prio = None
        try:
            rec_rules = r.recurrenceRules() or []
            recurrence = rrule_to_text(rec_rules[0]) if rec_rules else None
        except Exception:
            recurrence = None
        try:
            alarms = [alarm_to_dict(a) for a in (r.alarms() or [])]
        except Exception:
            alarms = []
        try:
            created_at_item = to_iso_dt(r.creationDate()) if r.creationDate() is not None else None
        except Exception:
            created_at_item = None
        try:
            modified_at_item = to_iso_dt(r.lastModifiedDate()) if r.lastModifiedDate() is not None else None
        except Exception:
            modified_at_item = None

        # Use cached calendar information instead of r.calendar() which can be None
        try:
            key = _key_for(r)
            debug_title = str(r.title() or "Unknown")[:30]
            cached_cal = calendar_cache.get(key, {})
            
            cal_id = cached_cal.get("identifier", "")
            cal_name = cached_cal.get("name", None)
            src_name = cached_cal.get("source_name", None)
            src_type = cached_cal.get("source_type", None)
            color_hex = cached_cal.get("color", None)
            
        except Exception as e:
            debug_title = str(r.title()) if r.title() else "Unknown"
            print(f"Warning: Calendar cache access failed for '{debug_title}': {e}")
            cal_id = ""
            cal_name = None
            src_name = None
            src_type = None
            color_hex = None

        # Stable key: calendarItemIdentifier + calendar identifier
        try:
            item_id = str(r.calendarItemIdentifier())
        except Exception:
            item_id = None
        try:
            external_id = str(r.calendarItemExternalIdentifier())
        except Exception:
            external_id = None
        if not item_id:
            # Skip items without an identifier (should be rare)
            continue

        # Prefer external id as source key if present
        preferred_key = f"rem:{external_id}" if external_id else None
        fallback_key = f"reminder:{cal_id}:{item_id}"
        candidate_keys = [k for k in (preferred_key, fallback_key) if k]

        # Resolve UUID via any candidate key (source_key or aliases)
        uid = None
        for k in candidate_keys:
            uid = source_to_uuid.get(k)
            if uid:
                break
        if uid:
            prev = existing_tasks.get(uid, {})
            created_at_index = prev.get("created_at", now)
            prev_aliases = set(prev.get("aliases", []) or [])
        else:
            uid = str(uuid4())
            created_at_index = now
            prev_aliases = set()

        # Build aliases (all candidate keys + previous)
        aliases = set(prev_aliases)
        for k in candidate_keys:
            aliases.add(k)
        prev_source = existing_tasks.get(uid, {}).get("source_key") if uid in existing_tasks else None
        if prev_source:
            aliases.add(prev_source)

        # Cache tokenized title for performance optimization
        title_tokens = normalize_text_for_similarity(title)
        title_tokens_hash = hashlib.sha1("|".join(title_tokens).encode("utf-8")).hexdigest()[:8] if title_tokens else ""
        
        # Fingerprint from title+notes hash+due/start/done
        import hashlib as _h
        title_norm = (title or "").strip().lower()
        notes_hash = _h.sha1(((notes or "").strip()).encode("utf-8")).hexdigest()[:16]
        date_pack = f"{due or ''}|{start or ''}|{completion_dt or ''}"
        fingerprint = _h.sha1(f"{title_norm}|{notes_hash}|{date_pack}".encode("utf-8")).hexdigest()

        rec = {
            "uuid": uid,
            "source_key": preferred_key or fallback_key,
            "aliases": sorted(aliases),
            "list": {
                "name": cal_name,
                "identifier": cal_id,
                "source": {"name": src_name, "type": src_type},
                "color": color_hex,
            },
            "status": "done" if completed else "todo",
            "description": title,
            "notes": notes,
            "url": url,
            "priority": prio,
            "due": due,
            "start": start,
            "done": completion_dt,
            "recurrence": recurrence,
            "alarms": alarms,
            "item_created_at": created_at_item,
            "item_modified_at": modified_at_item,
            "external_ids": {"external": external_id, "item": item_id, "calendar": cal_id},
            "fingerprint": fingerprint,
            "created_at": created_at_index,
            "updated_at": now,
            "last_seen": now,
            # Performance optimization fields
            "cached_tokens": title_tokens,
            "title_hash": title_tokens_hash,
        }
        out_tasks[uid] = rec
        processed_reminders += 1

    # Note: Instead of carrying forward all missing tasks (which preserves deleted reminders),
    # we now treat reminders not returned by EventKit as permanently deleted.
    # This fixes the issue where deleted reminders were being preserved indefinitely
    # in the index because the carry-forward logic assumed missing = temporarily unavailable.
    # 
    # The previous logic was:
    # - Carry forward tasks not seen this run
    # - for uid, prev in existing_tasks.items():
    #     if uid in out_tasks:
    #         continue
    #     out_tasks[uid] = prev
    #
    # Now we simply don't carry forward missing reminders, treating them as deleted.

    # Sort tasks by UUID for deterministic output
    tasks_sorted = {uid: out_tasks[uid] for uid in sorted(out_tasks)}
    new_reminders = len([t for t in tasks_sorted.values() if t.get("created_at") == now])
    carried_forward = 0  # No longer carrying forward, so this is always 0
    deleted_reminders = len(existing_tasks) - len(tasks_sorted) + new_reminders
    
    logger.update_counts(
        input_counts={
            "lists": len(lists),
            "reminders_fetched": len(reminders)
        },
        output_counts={
            "reminders_processed": processed_reminders,
            "reminders_indexed": len(tasks_sorted),
            "new_reminders": new_reminders,
            "carried_forward": max(0, carried_forward),
            "deleted_reminders": max(0, deleted_reminders)
        }
    )

    out = {
        "meta": {
            "schema": 2,
            "generated_at": now,
            "list_count": len(lists),
        },
        "tasks": tasks_sorted,
    }
    
    # Add run_id to meta for concurrent write detection
    out = ensure_run_id_in_meta(out, run_id)
    
    # Check for concurrent access before writing
    if check_concurrent_access(args.output, run_id):
        print(f"Warning: Concurrent access detected to {args.output}, proceeding with caution")
    
    # Write with locking and atomic operations
    try:
        # Create deterministic JSON for comparison
        new_json = json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True)
        
        # Check if file exists and content has changed
        changed = True
        if os.path.isfile(args.output):
            try:
                with open(args.output, "r", encoding="utf-8") as f:
                    old_json = f.read()
                # Compare content ignoring generated_at and run_id for change detection
                try:
                    import copy
                    old_obj = json.loads(old_json)
                    new_obj = copy.deepcopy(out)
                    old_obj.get("meta", {}).pop("generated_at", None)
                    new_obj.get("meta", {}).pop("generated_at", None)
                    old_obj.get("meta", {}).pop("run_id", None)
                    new_obj.get("meta", {}).pop("run_id", None)
                    if json.dumps(old_obj, sort_keys=True) == json.dumps(new_obj, sort_keys=True):
                        changed = False
                except Exception:
                    # Fall back to simple string comparison
                    if old_json == new_json:
                        changed = False
            except Exception:
                pass  # Assume changed if we can't read the old file
        
        if not changed:
            logger.info("No changes detected, skipping write", 
                       output_path=args.output, 
                       task_count=len(tasks_sorted))
            summary_path = logger.end_run(True)
            print(f"No changes for {args.output} (tasks={len(tasks_sorted)})")
            return 0
        
        # Write safely with file locking
        safe_write_json_with_lock(
            args.output, 
            out, 
            run_id=run_id,
            indent=2,
            timeout=30.0
        )
        
        logger.info("Successfully wrote reminder index", 
                   output_path=args.output, 
                   task_count=len(tasks_sorted))
        summary_path = logger.end_run(True)
        if deleted_reminders > 0:
            print(f"Wrote {len(tasks_sorted)} reminder task(s) to {args.output} (deleted {deleted_reminders} from index)")
        else:
            print(f"Wrote {len(tasks_sorted)} reminder task(s) to {args.output}")
        return 0
        
    except Exception as e:
        logger.error("Failed to write reminder index", 
                    output_path=args.output, 
                    error=str(e))
        logger.end_run(False, str(e))
        print(f"Error writing to {args.output}: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
