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
class CreationDefaults:
    """Default settings for creating missing counterparts."""
    obs_inbox_file: str = "~/Documents/Obsidian/Default/Tasks.md"
    rem_default_calendar_id: Optional[str] = None
    max_creates_per_run: int = 50
    since_days: int = 30
    include_done: bool = False


@dataclass
class CreationRule:
    """Mapping rule for creating counterparts."""
    pass


@dataclass
class ObsToRemRule(CreationRule):
    """Rule for creating Reminders from Obsidian tasks."""
    tag: str  # Obsidian tag like "#work"
    calendar_id: str  # Target Reminders calendar ID


@dataclass
class RemToObsRule(CreationRule):
    """Rule for creating Obsidian tasks from Reminders."""
    list_name: str  # Reminders list name
    target_file: str  # Target Obsidian file path
    heading: Optional[str] = None  # Optional heading within file


@dataclass
class AppPreferences:
    min_score: float = 0.75
    days_tolerance: int = 1
    include_done: bool = False
    ignore_common: bool = True
    prune_days: int = -1  # <0 disables lifecycle prune
    last_summary: str = ""

    # Calendar settings
    calendar_vault_name: str = ""  # Selected vault for calendar sync (empty = auto-detect)

    # Creation settings
    creation_defaults: CreationDefaults = None
    obs_to_rem_rules: list = None  # List[ObsToRemRule]
    rem_to_obs_rules: list = None  # List[RemToObsRule]
    
    def __post_init__(self):
        if self.creation_defaults is None:
            self.creation_defaults = CreationDefaults()
        if self.obs_to_rem_rules is None:
            self.obs_to_rem_rules = []
        if self.rem_to_obs_rules is None:
            self.rem_to_obs_rules = []


def load_app_config() -> tuple[AppPreferences, dict]:
    paths = default_paths()
    cfg_path = paths["app_config"]
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Load creation defaults
        creation_defaults_data = data.get("creation_defaults", {})
        creation_defaults = CreationDefaults(
            obs_inbox_file=creation_defaults_data.get("obs_inbox_file", "~/Documents/Obsidian/Default/Tasks.md"),
            rem_default_calendar_id=creation_defaults_data.get("rem_default_calendar_id"),
            max_creates_per_run=creation_defaults_data.get("max_creates_per_run", 50),
            since_days=creation_defaults_data.get("since_days", 30),
            include_done=creation_defaults_data.get("include_done", False),
        )
        
        # Load creation rules
        obs_to_rem_rules = []
        for rule_data in data.get("obs_to_rem_rules", []):
            obs_to_rem_rules.append(ObsToRemRule(
                tag=rule_data["tag"],
                calendar_id=rule_data["calendar_id"]
            ))
        
        rem_to_obs_rules = []
        for rule_data in data.get("rem_to_obs_rules", []):
            rem_to_obs_rules.append(RemToObsRule(
                list_name=rule_data["list_name"],
                target_file=rule_data["target_file"],
                heading=rule_data.get("heading")
            ))
        
        prefs = AppPreferences(
            min_score=float(data.get("min_score", 0.75)),
            days_tolerance=int(data.get("days_tolerance", 1)),
            include_done=bool(data.get("include_done", False)),
            ignore_common=bool(data.get("ignore_common", True)),
            prune_days=int(data.get("prune_days", -1)),
            last_summary=str(data.get("last_summary", "")),
            calendar_vault_name=str(data.get("calendar_vault_name", "")),
            creation_defaults=creation_defaults,
            obs_to_rem_rules=obs_to_rem_rules,
            rem_to_obs_rules=rem_to_obs_rules,
        )
        return prefs, paths
    except Exception:
        return AppPreferences(), paths


def save_app_config(prefs: AppPreferences) -> None:
    paths = default_paths()
    cfg_path = paths["app_config"]
    ensure_dirs(cfg_path)
    
    # Convert creation rules to serializable format
    obs_to_rem_rules_data = []
    for rule in prefs.obs_to_rem_rules:
        obs_to_rem_rules_data.append({
            "tag": rule.tag,
            "calendar_id": rule.calendar_id
        })
    
    rem_to_obs_rules_data = []
    for rule in prefs.rem_to_obs_rules:
        rule_data = {
            "list_name": rule.list_name,
            "target_file": rule.target_file
        }
        if rule.heading:
            rule_data["heading"] = rule.heading
        rem_to_obs_rules_data.append(rule_data)
    
    payload = {
        "min_score": prefs.min_score,
        "days_tolerance": prefs.days_tolerance,
        "include_done": prefs.include_done,
        "ignore_common": prefs.ignore_common,
        "prune_days": prefs.prune_days,
        "last_summary": prefs.last_summary,
        "calendar_vault_name": prefs.calendar_vault_name,
        "creation_defaults": {
            "obs_inbox_file": prefs.creation_defaults.obs_inbox_file,
            "rem_default_calendar_id": prefs.creation_defaults.rem_default_calendar_id,
            "max_creates_per_run": prefs.creation_defaults.max_creates_per_run,
            "since_days": prefs.creation_defaults.since_days,
            "include_done": prefs.creation_defaults.include_done,
        },
        "obs_to_rem_rules": obs_to_rem_rules_data,
        "rem_to_obs_rules": rem_to_obs_rules_data,
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
