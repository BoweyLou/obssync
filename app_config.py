#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import glob
from dataclasses import dataclass, asdict
from typing import Optional, List, Tuple

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

    # SQLite DB Reader settings
    enable_db_reader: bool = False  # Feature flag for DB access
    db_fallback_enabled: bool = True  # Allow EventKit fallback when DB fails
    db_read_timeout: float = 10.0  # SQLite connection timeout in seconds
    schema_validation_level: str = "warning"  # "strict", "warning", or "disabled"
    db_query_complexity: str = "standard"  # "minimal", "standard", "enhanced", "complete"

    # Vault-based organization settings
    vault_organization_enabled: bool = False  # Feature flag for vault-based organization
    default_vault_id: Optional[str] = None  # Primary vault for catch-all file
    catch_all_filename: str = "OtherAppleReminders.md"  # Name of catch-all file
    auto_create_vault_lists: bool = True  # Automatically create lists for vaults
    cleanup_legacy_mappings: bool = False  # Feature flag for cleanup phase
    list_naming_template: str = "{vault_name}"  # Template for auto-created lists
    preserve_list_colors: bool = True  # Keep colors when creating lists
    max_lists_per_cleanup: int = 5  # Safety limit for bulk cleanup operations

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
            # DB Reader settings
            enable_db_reader=bool(data.get("enable_db_reader", False)),
            db_fallback_enabled=bool(data.get("db_fallback_enabled", True)),
            db_read_timeout=float(data.get("db_read_timeout", 10.0)),
            schema_validation_level=str(data.get("schema_validation_level", "warning")),
            db_query_complexity=str(data.get("db_query_complexity", "standard")),
            # Vault-based organization settings
            vault_organization_enabled=bool(data.get("vault_organization_enabled", False)),
            default_vault_id=data.get("default_vault_id"),
            catch_all_filename=str(data.get("catch_all_filename", "OtherAppleReminders.md")),
            auto_create_vault_lists=bool(data.get("auto_create_vault_lists", True)),
            cleanup_legacy_mappings=bool(data.get("cleanup_legacy_mappings", False)),
            list_naming_template=str(data.get("list_naming_template", "{vault_name}")),
            preserve_list_colors=bool(data.get("preserve_list_colors", True)),
            max_lists_per_cleanup=int(data.get("max_lists_per_cleanup", 5)),
            # Creation settings
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
        # DB Reader settings
        "enable_db_reader": prefs.enable_db_reader,
        "db_fallback_enabled": prefs.db_fallback_enabled,
        "db_read_timeout": prefs.db_read_timeout,
        "schema_validation_level": prefs.schema_validation_level,
        "db_query_complexity": prefs.db_query_complexity,
        # Vault-based organization settings
        "vault_organization_enabled": prefs.vault_organization_enabled,
        "default_vault_id": prefs.default_vault_id,
        "catch_all_filename": prefs.catch_all_filename,
        "auto_create_vault_lists": prefs.auto_create_vault_lists,
        "cleanup_legacy_mappings": prefs.cleanup_legacy_mappings,
        "list_naming_template": prefs.list_naming_template,
        "preserve_list_colors": prefs.preserve_list_colors,
        "max_lists_per_cleanup": prefs.max_lists_per_cleanup,
        # Creation settings
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


def discover_reminders_sqlite_stores() -> List[Tuple[str, str]]:
    """
    Discover Apple Reminders SQLite database stores on macOS.

    Returns:
        List of (store_path, description) tuples for discovered stores
    """
    stores = []

    # Reminders CoreData stores (introduced with tags/groups metadata)
    reminders_base = _expand("~/Library/Reminders")
    if os.path.isdir(reminders_base):
        # CoreData container hierarchy looks like Container_v*/Stores/Data-<uuid>-<random>.sqlite
        coredata_patterns = [
            "Container_v*/Stores/Data-*.sqlite",
            "Container_v*/Stores/*/Data-*.sqlite",  # nested variant seen on newer macOS
        ]
        for pattern in coredata_patterns:
            full_pattern = os.path.join(reminders_base, pattern)
            for match in glob.glob(full_pattern):
                if os.path.isfile(match):
                    stores.append((match, "Reminders CoreData Store"))

    # Historical Calendar stores kept as a fallback for older releases
    calendar_dir = _expand("~/Library/Calendars")
    if os.path.isdir(calendar_dir):
        calendar_db = os.path.join(calendar_dir, "Calendar.sqlitedb")
        if os.path.isfile(calendar_db):
            stores.append((calendar_db, "Legacy Calendar Store"))

    containers_base = _expand("~/Library/Containers")
    if os.path.isdir(containers_base):
        calendar_patterns = [
            "com.apple.CalendarAgent/Data/Library/Calendars/Calendar.sqlitedb",
            "com.apple.remindd/Data/Library/Calendars/Calendar.sqlitedb",
            "com.apple.calendar/Data/Library/Calendars/Calendar.sqlitedb",
        ]

        for pattern in calendar_patterns:
            full_pattern = os.path.join(containers_base, pattern)
            for match in glob.glob(full_pattern):
                if os.path.isfile(match):
                    container_name = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(match))))
                    stores.append((match, f"Legacy Container Store ({container_name})"))

    group_containers = _expand("~/Library/Group Containers")
    if os.path.isdir(group_containers):
        group_patterns = [
            "*/Library/Calendars/Calendar.sqlitedb",
            "*/*.sqlitedb",
        ]

        for pattern in group_patterns:
            full_pattern = os.path.join(group_containers, pattern)
            for match in glob.glob(full_pattern):
                if os.path.isfile(match) and "Calendar" in os.path.basename(match):
                    group_name = os.path.basename(os.path.dirname(os.path.dirname(match)))
                    stores.append((match, f"Legacy Group Container ({group_name})"))

    # Sort by modification time (most recently modified first)
    stores_with_mtime = []
    for store_path, description in stores:
        try:
            mtime = os.path.getmtime(store_path)
            stores_with_mtime.append((store_path, description, mtime))
        except OSError:
            # Skip stores we can't access
            continue

    stores_with_mtime.sort(key=lambda x: x[2], reverse=True)
    return [(path, desc) for path, desc, _ in stores_with_mtime]


def get_primary_reminders_store() -> Optional[str]:
    """
    Get the path to the primary Apple Reminders SQLite store.

    Returns:
        Path to the most likely active store, or None if not found
    """
    stores = discover_reminders_sqlite_stores()
    if not stores:
        return None

    # Return the most recently modified store (likely the active one)
    return stores[0][0]


def validate_reminders_store(store_path: str) -> Tuple[bool, str]:
    """
    Validate that a SQLite store looks like a valid Reminders database.

    Args:
        store_path: Path to SQLite database file

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not os.path.isfile(store_path):
        return False, f"Store file does not exist: {store_path}"

    try:
        import sqlite3

        with sqlite3.connect(f"file:{store_path}?mode=ro", uri=True, timeout=5.0) as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name IN (
                    'ZREMCDREMINDER',
                    'ZREMCDLIST',
                    'ZREMCDACCOUNT'
                )
                """
            )
            tables = {row[0] for row in cursor.fetchall()}

            if {'ZREMCDREMINDER', 'ZREMCDLIST'}.issubset(tables):
                return True, "Valid Reminders CoreData store"

            # Fall back to legacy Calendar store detection
            cursor.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name IN ('CalendarItem', 'Calendar', 'Store')
                """
            )
            legacy_tables = {row[0] for row in cursor.fetchall()}
            if {'CalendarItem', 'Calendar'}.issubset(legacy_tables):
                return True, "Valid legacy Calendar store"

            return False, "Missing required Reminders tables"

    except Exception as e:
        return False, f"Error validating store: {e}"
