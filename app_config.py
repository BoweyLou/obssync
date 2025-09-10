#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, asdict
from typing import Optional

# Import safe I/O utilities
from lib.safe_io import safe_write_json_with_lock


def _expand(p: str) -> str:
    return os.path.abspath(os.path.expanduser(p))


def default_paths() -> dict:
    """Centralized path configuration for all obs-tools scripts.
    
    This is the single source of truth for file locations.
    All other scripts should import and use these paths.
    """
    return {
        # Configuration files
        "obsidian_vaults": _expand("~/.config/obsidian_vaults.json"),
        "reminders_lists": _expand("~/.config/reminders_lists.json"),
        
        # Index files (data)
        "obsidian_index": _expand("~/.config/obsidian_tasks_index.json"),
        "reminders_index": _expand("~/.config/reminders_tasks_index.json"),
        
        # Cache files (for performance)
        "obsidian_cache": _expand("~/.config/obsidian_tasks_cache.json"),
        "reminders_snapshot_cache": _expand("~/.config/reminders_snapshot_cache.json"),
        
        # Sync files
        "links": _expand("~/.config/sync_links.json"),
        
        # Application configuration
        "app_config": _expand("~/.config/obs-tools/app.json"),
        
        # Directories
        "logs_dir": _expand("~/.config/obs-tools/logs"),
        "backups_dir": _expand("~/.config/obs-tools/backups"),
        
        # Backup-specific files (commonly used)
        "sync_changeset": _expand("~/.config/obs-tools/backups/sync_changeset.json"),
        "task_operations_backup": _expand("~/.config/obs-tools/backups/task_operations.json"),
        "duplicate_removal_backup": _expand("~/.config/obs-tools/backups/duplicate_removal.json"),
    }


def get_path(key: str) -> str:
    """Get a specific path by key. Raises KeyError if key doesn't exist."""
    paths = default_paths()
    if key not in paths:
        available = ', '.join(sorted(paths.keys()))
        raise KeyError(f"Unknown path key '{key}'. Available keys: {available}")
    return paths[key]


def validate_paths() -> list[str]:
    """Validate that all configured directories can be created.
    
    Returns list of errors, empty if all paths are valid.
    """
    errors = []
    paths = default_paths()
    
    # Check that we can create parent directories for files
    file_paths = ["obsidian_vaults", "reminders_lists", "obsidian_index", 
                  "reminders_index", "obsidian_cache", "reminders_snapshot_cache",
                  "links", "app_config", "sync_changeset",
                  "task_operations_backup", "duplicate_removal_backup"]
    
    for key in file_paths:
        try:
            parent_dir = os.path.dirname(paths[key])
            os.makedirs(parent_dir, exist_ok=True)
        except (OSError, PermissionError) as e:
            errors.append(f"Cannot create directory for {key} ({paths[key]}): {e}")
    
    # Check that we can create directories
    dir_paths = ["logs_dir", "backups_dir"]
    for key in dir_paths:
        try:
            os.makedirs(paths[key], exist_ok=True)
        except (OSError, PermissionError) as e:
            errors.append(f"Cannot create directory {key} ({paths[key]}): {e}")
    
    return errors


def print_paths_debug() -> None:
    """Debug utility to print all configured paths."""
    paths = default_paths()
    print("=== obs-tools Path Configuration ===", file=sys.stderr)
    for key, path in sorted(paths.items()):
        exists = "✓" if os.path.exists(path) else "✗"
        print(f"{exists} {key}: {path}", file=sys.stderr)
    print("", file=sys.stderr)


def ensure_dirs(cfg_path: str = None) -> None:
    """Ensure all required directories exist.
    
    Args:
        cfg_path: Optional additional config path to ensure (for backward compatibility)
    """
    if cfg_path:
        os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
    
    errors = validate_paths()
    if errors:
        raise OSError(f"Path validation failed:\n" + "\n".join(errors))


@dataclass
class AppPreferences:
    min_score: float = 0.75
    days_tolerance: int = 1
    include_done: bool = False
    ignore_common: bool = True
    prune_days: int = -1  # <0 disables lifecycle prune
    last_summary: str = ""


def load_app_config() -> tuple[AppPreferences, dict]:
    paths = default_paths()
    cfg_path = paths["app_config"]
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        prefs = AppPreferences(
            min_score=float(data.get("min_score", 0.75)),
            days_tolerance=int(data.get("days_tolerance", 1)),
            include_done=bool(data.get("include_done", False)),
            ignore_common=bool(data.get("ignore_common", True)),
            prune_days=int(data.get("prune_days", -1)),
            last_summary=str(data.get("last_summary", "")),
        )
        return prefs, paths
    except Exception:
        return AppPreferences(), paths


def save_app_config(prefs: AppPreferences) -> None:
    paths = default_paths()
    cfg_path = paths["app_config"]
    ensure_dirs(cfg_path)
    payload = {
        "min_score": prefs.min_score,
        "days_tolerance": prefs.days_tolerance,
        "include_done": prefs.include_done,
        "ignore_common": prefs.ignore_common,
        "prune_days": prefs.prune_days,
        "last_summary": prefs.last_summary,
    }
    try:
        # Use safe write with locking for app config
        safe_write_json_with_lock(
            cfg_path,
            payload,
            indent=2,
            timeout=10.0  # Shorter timeout for config writes
        )
    except Exception as e:
        # Fall back to direct write if safe write fails
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
