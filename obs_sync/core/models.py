"""
Domain models for obs-sync.

This module contains the core data structures used throughout the
simplified obs-sync architecture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4
import os
import json
from .paths import get_path_manager


def _normalize_path(path: str) -> str:
    """Expand user and convert to absolute path."""
    return os.path.abspath(os.path.expanduser(path))


def normalize_vault_path(path: str) -> str:
    """Normalize vault path for consistent identification across all components.

    Handles:
    - User home expansion (~)
    - Conversion to absolute path
    - Symlink resolution
    - Trailing slash removal (except for root)
    - Case normalization on case-insensitive filesystems

    Args:
        path: Vault path to normalize

    Returns:
        Normalized absolute path suitable for vault identification
    """
    if not path:
        raise ValueError("Path cannot be empty")

    # Expand user home directory
    expanded = os.path.expanduser(path)

    # Convert to absolute path
    absolute = os.path.abspath(expanded)

    # Resolve symlinks to get the real path
    try:
        resolved = os.path.realpath(absolute)
    except (OSError, AttributeError):
        # If realpath fails, use absolute path as fallback
        resolved = absolute

    # Remove trailing slashes except for root directory
    if resolved != os.sep and resolved.endswith(os.sep):
        resolved = resolved.rstrip(os.sep)

    # On case-insensitive filesystems (like macOS default), normalize case
    # This ensures consistent identification even if path case varies
    try:
        # Check if filesystem is case-insensitive by comparing paths
        if os.path.exists(resolved):
            # Get the actual case from the filesystem
            # This works by resolving the path through the filesystem
            resolved = os.path.realpath(resolved)
    except (OSError, AttributeError):
        pass

    return resolved


def deterministic_vault_id(normalized_path: str) -> str:
    """Generate a deterministic vault ID from a normalized path.

    Uses SHA256 hashing to create a stable, unique identifier based on the
    vault's normalized path. This ensures the same vault always gets the
    same ID, even across different sessions or machines.

    Args:
        normalized_path: Already normalized vault path (from normalize_vault_path)

    Returns:
        Deterministic vault ID in format "vault-{hash[:12]}"
    """
    if not normalized_path:
        raise ValueError("Normalized path cannot be empty")

    import hashlib

    # Create SHA256 hash of the normalized path
    path_hash = hashlib.sha256(normalized_path.encode('utf-8')).hexdigest()

    # Use first 12 characters of hash for a compact but unique ID
    # This gives us 48 bits of entropy, which is plenty for vault identification
    vault_id = f"vault-{path_hash[:12]}"

    return vault_id


def _date_to_iso(value: Optional[date]) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat()


def _iso_to_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


class TaskStatus(Enum):
    """Task completion status."""

    TODO = "todo"
    DONE = "done"


class Priority(Enum):
    """Task priority levels."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Vault:
    """Represents an Obsidian vault."""

    name: str
    path: str
    vault_id: str = field(default_factory=lambda: str(uuid4()))
    is_default: bool = False

    def __post_init__(self) -> None:
        # Normalize the vault path using the new comprehensive normalizer
        self.path = normalize_vault_path(self.path)

        # Check if vault_id looks like a legacy UUID (36 chars with dashes)
        if self.vault_id and len(self.vault_id) == 36 and '-' in self.vault_id:
            # This appears to be a legacy UUID - preserve it for backward compatibility
            # Legacy UUIDs have format: XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX
            pass  # Keep the existing vault_id
        elif not self.vault_id or self.vault_id == str(uuid4()):
            # No ID provided or default factory UUID - generate deterministic ID
            # Pass the already normalized path to deterministic_vault_id
            self.vault_id = deterministic_vault_id(self.path)
        # else: Keep whatever custom vault_id was provided


@dataclass
class RemindersList:
    """Represents an Apple Reminders list."""

    name: str
    identifier: str
    source_name: Optional[str] = None
    source_type: Optional[str] = None
    color: Optional[str] = None
    allows_modification: bool = True


@dataclass
class ObsidianTask:
    """Represents a task parsed from Obsidian."""

    uuid: str
    vault_id: str
    vault_name: str
    vault_path: str
    file_path: str
    line_number: int
    block_id: Optional[str]
    status: TaskStatus
    description: str
    raw_line: str
    due_date: Optional[date] = None
    completion_date: Optional[date] = None
    priority: Optional[Priority] = None
    tags: List[str] = field(default_factory=list)
    created_at: Optional[str] = None
    modified_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "vault": {
                "vault_id": self.vault_id,
                "name": self.vault_name,
                "path": self.vault_path,
            },
            "file": {
                "relative_path": self.file_path,
                "line": self.line_number,
            },
            "block_id": self.block_id,
            "status": self.status.value,
            "description": self.description,
            "raw": self.raw_line,
            "due": _date_to_iso(self.due_date),
            "completion_date": _date_to_iso(self.completion_date),
            "priority": self.priority.value if self.priority else None,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.modified_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ObsidianTask:
        vault_info = data.get("vault", {})
        file_info = data.get("file", {})
        status = TaskStatus(data.get("status", "todo"))

        priority_value = data.get("priority")
        priority = None
        if priority_value:
            try:
                priority = Priority(priority_value.lower())
            except ValueError:
                priority = None

        return cls(
            uuid=data.get("uuid", f"obs-{uuid4().hex[:8]}"),
            vault_id=vault_info.get("vault_id", ""),
            vault_name=vault_info.get("name", ""),
            vault_path=vault_info.get("path", ""),
            file_path=file_info.get("relative_path", ""),
            line_number=file_info.get("line", 0),
            block_id=data.get("block_id"),
            status=status,
            description=data.get("description", ""),
            raw_line=data.get("raw", ""),
            due_date=_iso_to_date(data.get("due")),
            completion_date=_iso_to_date(data.get("completion_date")),
            priority=priority,
            tags=data.get("tags", []),
            created_at=data.get("created_at"),
            modified_at=data.get("updated_at"),
        )


@dataclass
class RemindersTask:
    """Represents a task from Apple Reminders."""

    uuid: str
    item_id: str
    calendar_id: str
    list_name: str
    status: TaskStatus
    title: str
    due_date: Optional[date] = None
    priority: Optional[Priority] = None
    url: Optional[str] = None
    notes: Optional[str] = None
    tags: List[str] = field(default_factory=list)  # Added tags field
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    completion_date: Optional[date] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "external_ids": {
                "item": self.item_id,
                "calendar": self.calendar_id,
            },
            "list": {
                "name": self.list_name,
            },
            "status": self.status.value,
            "description": self.title,
            "due": _date_to_iso(self.due_date),
            "priority": self.priority.value if self.priority else None,
            "url": self.url,
            "notes": self.notes,
            "tags": self.tags,  # Added tags to serialization
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.modified_at.isoformat() if self.modified_at else None,
            "completion_date": _date_to_iso(self.completion_date),
        }

    def display_title(self) -> str:
        """Compose a display-friendly title including the reminder URL when present."""
        parts: List[str] = []
        if self.title and self.title.strip():
            parts.append(self.title.strip())
        url_str = (self.url or "").strip() if self.url else None
        if url_str:
            base = parts[0] if parts else ""
            if url_str not in base:
                parts.append(url_str)
        return " ".join(part for part in parts if part).strip()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RemindersTask:
        status_value = data.get("status", "todo")
        status = TaskStatus.DONE if status_value == "done" else TaskStatus.TODO

        priority_value = data.get("priority")
        priority = None
        if priority_value:
            try:
                priority = Priority(priority_value.lower())
            except ValueError:
                priority = None

        external_ids = data.get("external_ids", {})
        list_info = data.get("list", {})
        
        # Parse timestamps from ISO strings to datetime objects
        created_at = None
        if data.get("created_at"):
            try:
                if isinstance(data["created_at"], str):
                    created_at = datetime.fromisoformat(data["created_at"])
                elif isinstance(data["created_at"], datetime):
                    created_at = data["created_at"]
            except (ValueError, TypeError):
                pass
        
        modified_at = None
        if data.get("updated_at"):
            try:
                if isinstance(data["updated_at"], str):
                    modified_at = datetime.fromisoformat(data["updated_at"])
                elif isinstance(data["updated_at"], datetime):
                    modified_at = data["updated_at"]
            except (ValueError, TypeError):
                pass

        return cls(
            uuid=data.get("uuid", str(uuid4())),
            item_id=external_ids.get("item", ""),
            calendar_id=external_ids.get("calendar", ""),
            list_name=list_info.get("name", ""),
            status=status,
            title=data.get("description", ""),
            due_date=_iso_to_date(data.get("due")),
            priority=priority,
            url=data.get("url"),
            notes=data.get("notes"),
            tags=data.get("tags", []),
            created_at=created_at,
            modified_at=modified_at,
            completion_date=_iso_to_date(data.get("completion_date")),
        )


@dataclass
class SyncLink:
    """Represents a sync link between Obsidian and Reminders tasks."""

    obs_uuid: str
    rem_uuid: str
    score: float
    vault_id: Optional[str] = None
    last_synced: Optional[str] = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "obs_uuid": self.obs_uuid,
            "rem_uuid": self.rem_uuid,
            "score": self.score,
            "vault_id": self.vault_id,
            "last_synced": self.last_synced,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SyncLink:
        return cls(
            obs_uuid=data["obs_uuid"],
            rem_uuid=data["rem_uuid"],
            score=float(data.get("score", 0.0)),
            vault_id=data.get("vault_id"),
            last_synced=data.get("last_synced"),
            created_at=data.get(
                "created_at",
                datetime.now(timezone.utc).isoformat(),
            ),
        )


@dataclass
class SyncConfig:
    """Configuration for sync operations."""

    vaults: List[Vault] = field(default_factory=list)
    default_vault_id: Optional[str] = None
    reminders_lists: List[RemindersList] = field(default_factory=list)
    default_calendar_id: Optional[str] = None
    calendar_ids: List[str] = field(default_factory=list)
    vault_mappings: List[Dict[str, str]] = field(default_factory=list)
    tag_routes: List[Dict[str, str]] = field(default_factory=list)
    min_score: float = 0.75
    days_tolerance: int = 1
    include_completed: bool = False
    obsidian_inbox_path: str = "AppleRemindersInbox.md"
    obsidian_index_path: Optional[str] = None
    reminders_index_path: Optional[str] = None
    links_path: Optional[str] = None
    # Deduplication settings
    enable_deduplication: bool = True
    dedup_auto_apply: bool = False
    # Calendar integration settings
    sync_calendar_events: bool = False
    # Automation settings (macOS LaunchAgent)
    automation_enabled: bool = False
    automation_interval: int = 3600  # Default: hourly
    # Update settings
    update_channel: str = "stable"  # "stable" or "beta"
    # Insights and analytics settings
    enable_insights: bool = True
    enable_streak_tracking: bool = True
    insights_in_daily_notes: bool = True
    # Hygiene assistant settings
    enable_hygiene_assistant: bool = True
    hygiene_stagnant_threshold: int = 14  # Days before a task is considered stagnant

    def __post_init__(self) -> None:
        # Get the path manager
        manager = get_path_manager()

        # Set default paths using PathManager if not provided
        if self.obsidian_index_path is None:
            self.obsidian_index_path = str(manager.obsidian_index_path)
        else:
            self.obsidian_index_path = _normalize_path(self.obsidian_index_path)

        if self.reminders_index_path is None:
            self.reminders_index_path = str(manager.reminders_index_path)
        else:
            self.reminders_index_path = _normalize_path(self.reminders_index_path)

        if self.links_path is None:
            self.links_path = str(manager.sync_links_path)
        else:
            self.links_path = _normalize_path(self.links_path)

        self._normalize_tag_routes()

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------
    @property
    def default_vault(self) -> Optional[Vault]:
        if not self.vaults:
            return None
        for vault in self.vaults:
            if vault.is_default:
                return vault
        if self.default_vault_id:
            for vault in self.vaults:
                if vault.vault_id == self.default_vault_id:
                    return vault
        return self.vaults[0]

    @property
    def default_vault_path(self) -> Optional[str]:
        vault = self.default_vault
        return vault.path if vault else None

    @property
    def reminder_list_ids(self) -> List[str]:
        return [lst.identifier for lst in self.reminders_lists if lst.identifier]

    @property
    def has_vaults(self) -> bool:
        return bool(self.vaults)

    @property
    def has_reminder_lists(self) -> bool:
        return bool(self.reminders_lists)

    def get_vault_mapping(self, vault_id: str) -> Optional[str]:
        """Get calendar ID mapped to a specific vault.

        Args:
            vault_id: The vault ID to look up

        Returns:
            Calendar ID if mapped, None otherwise
        """
        for mapping in self.vault_mappings:
            if mapping.get("vault_id") == vault_id:
                return mapping.get("calendar_id")
        return None

    def set_vault_mapping(self, vault_id: str, calendar_id: str) -> None:
        """Set or update vault to calendar mapping.

        Args:
            vault_id: The vault ID to map
            calendar_id: The calendar ID to map to
        """
        # Remove any existing mapping for this vault
        self.vault_mappings = [
            m for m in self.vault_mappings
            if m.get("vault_id") != vault_id
        ]
        # Add the new mapping
        self.vault_mappings.append({
            "vault_id": vault_id,
            "calendar_id": calendar_id
        })

    def get_all_vault_mappings(self) -> List[tuple[Vault, str]]:
        """Get all vault to calendar mappings as tuples.

        Returns:
            List of (Vault, calendar_id) tuples for configured mappings
        """
        result = []
        for mapping in self.vault_mappings:
            vault_id = mapping.get("vault_id")
            calendar_id = mapping.get("calendar_id")
            if vault_id and calendar_id:
                # Find the vault object
                for vault in self.vaults:
                    if vault.vault_id == vault_id:
                        result.append((vault, calendar_id))
                        break
        return result

    def get_tag_routes_for_vault(self, vault_id: str) -> List[Dict[str, str]]:
        """Return configured tag routing rules for a vault."""
        if not vault_id:
            return []
        return [route.copy() for route in self.tag_routes if route.get("vault_id") == vault_id]

    def get_tag_route(self, vault_id: str, tag: str) -> Optional[str]:
        """Look up calendar mapping for a specific tag within a vault."""
        normalized_tag = self._normalize_tag_value(tag)
        if not vault_id or not normalized_tag:
            return None
        for route in self.tag_routes:
            if route.get("vault_id") == vault_id and route.get("tag") == normalized_tag:
                return route.get("calendar_id")
        return None

    def set_tag_route(self, vault_id: str, tag: str, calendar_id: str, import_mode: str = "existing_only") -> None:
        """Create or update a tag routing rule for a vault."""
        normalized_tag = self._normalize_tag_value(tag)
        if not vault_id or not normalized_tag or not calendar_id:
            return
        if import_mode not in ["existing_only", "full_import"]:
            import_mode = "existing_only"
        self.tag_routes = [
            route
            for route in self.tag_routes
            if not (
                route.get("vault_id") == vault_id and route.get("tag") == normalized_tag
            )
        ]
        self.tag_routes.append(
            {
                "vault_id": vault_id,
                "tag": normalized_tag,
                "calendar_id": calendar_id,
                "import_mode": import_mode,
            }
        )

    def remove_tag_route(self, vault_id: str, tag: str) -> None:
        """Remove an existing tag routing rule for a vault."""
        normalized_tag = self._normalize_tag_value(tag)
        if not vault_id or not normalized_tag:
            return
        self.tag_routes = [
            route
            for route in self.tag_routes
            if not (
                route.get("vault_id") == vault_id and route.get("tag") == normalized_tag
            )
        ]

    def get_tag_route_import_mode(self, vault_id: str, tag: str) -> str:
        """Get the import mode for a tag route, defaults to 'existing_only'."""
        normalized_tag = self._normalize_tag_value(tag)
        if not vault_id or not normalized_tag:
            return "existing_only"
        for route in self.tag_routes:
            if route.get("vault_id") == vault_id and route.get("tag") == normalized_tag:
                return route.get("import_mode", "existing_only")
        return "existing_only"

    def set_tag_route_import_mode(self, vault_id: str, tag: str, import_mode: str) -> None:
        """Update the import mode for an existing tag route."""
        normalized_tag = self._normalize_tag_value(tag)
        if not vault_id or not normalized_tag:
            return
        if import_mode not in ["existing_only", "full_import"]:
            import_mode = "existing_only"
        for route in self.tag_routes:
            if route.get("vault_id") == vault_id and route.get("tag") == normalized_tag:
                route["import_mode"] = import_mode
                break

    def remove_vault(self, vault_id: str) -> bool:
        """Remove a vault and all its associated data.
        
        Args:
            vault_id: The vault ID to remove
            
        Returns:
            True if vault was found and removed, False otherwise
        """
        if not vault_id:
            return False
            
        # Find the vault to remove
        vault_to_remove = None
        for vault in self.vaults:
            if vault.vault_id == vault_id:
                vault_to_remove = vault
                break
                
        if not vault_to_remove:
            return False
            
        # Remove the vault from the list
        self.vaults = [v for v in self.vaults if v.vault_id != vault_id]
        
        # Clear vault mappings
        self.vault_mappings = [
            m for m in self.vault_mappings
            if m.get("vault_id") != vault_id
        ]
        
        # Clear tag routes for this vault
        self.tag_routes = [
            route for route in self.tag_routes
            if route.get("vault_id") != vault_id
        ]
        
        # Handle default vault changes
        if self.default_vault_id == vault_id:
            self.default_vault_id = None
            # Set first remaining vault as default if any exist
            if self.vaults:
                self.vaults[0].is_default = True
                self.default_vault_id = self.vaults[0].vault_id
                
        # Update is_default flags for remaining vaults
        for vault in self.vaults:
            vault.is_default = (vault.vault_id == self.default_vault_id)
            
        return True

    def remove_reminders_list(self, list_id: str) -> bool:
        """Remove a Reminders list and all its associated data.
        
        Args:
            list_id: The list identifier to remove
            
        Returns:
            True if list was found and removed, False otherwise
        """
        if not list_id:
            return False
            
        # Find the list to remove
        list_to_remove = None
        for lst in self.reminders_lists:
            if lst.identifier == list_id:
                list_to_remove = lst
                break
                
        if not list_to_remove:
            return False
            
        # Remove the list from the list
        self.reminders_lists = [
            lst for lst in self.reminders_lists
            if lst.identifier != list_id
        ]
        
        # Remove from calendar_ids
        if list_id in self.calendar_ids:
            self.calendar_ids.remove(list_id)
            
        # Clear vault mappings that reference this list
        self.vault_mappings = [
            m for m in self.vault_mappings
            if m.get("calendar_id") != list_id
        ]
        
        # Clear tag routes that reference this list
        self.tag_routes = [
            route for route in self.tag_routes
            if route.get("calendar_id") != list_id
        ]
        
        # Handle default calendar changes
        if self.default_calendar_id == list_id:
            self.default_calendar_id = None
            # Set first remaining list as default if any exist
            if self.reminders_lists:
                self.default_calendar_id = self.reminders_lists[0].identifier
                
        return True

    def get_vault_removal_impact(self, vault_id: str) -> Dict[str, Any]:
        """Get summary of what would be affected by removing a vault.
        
        Args:
            vault_id: The vault ID to analyze
            
        Returns:
            Dictionary with impact summary
        """
        impact = {
            "vault_found": False,
            "vault_name": None,
            "is_default": False,
            "mappings_cleared": 0,
            "tag_routes_cleared": 0,
            "tag_routes": []
        }
        
        # Find the vault
        for vault in self.vaults:
            if vault.vault_id == vault_id:
                impact["vault_found"] = True
                impact["vault_name"] = vault.name
                impact["is_default"] = vault.is_default
                break
                
        if not impact["vault_found"]:
            return impact
            
        # Count mappings
        impact["mappings_cleared"] = len([
            m for m in self.vault_mappings
            if m.get("vault_id") == vault_id
        ])
        
        # Collect tag routes
        tag_routes = [
            route for route in self.tag_routes
            if route.get("vault_id") == vault_id
        ]
        impact["tag_routes_cleared"] = len(tag_routes)
        impact["tag_routes"] = tag_routes
        
        return impact

    def get_list_removal_impact(self, list_id: str) -> Dict[str, Any]:
        """Get summary of what would be affected by removing a Reminders list.
        
        Args:
            list_id: The list identifier to analyze
            
        Returns:
            Dictionary with impact summary
        """
        impact = {
            "list_found": False,
            "list_name": None,
            "is_default": False,
            "mappings_cleared": 0,
            "tag_routes_cleared": 0,
            "affected_vaults": []
        }
        
        # Find the list
        for lst in self.reminders_lists:
            if lst.identifier == list_id:
                impact["list_found"] = True
                impact["list_name"] = lst.name
                impact["is_default"] = (lst.identifier == self.default_calendar_id)
                break
                
        if not impact["list_found"]:
            return impact
            
        # Count mappings
        mappings = [
            m for m in self.vault_mappings
            if m.get("calendar_id") == list_id
        ]
        impact["mappings_cleared"] = len(mappings)
        
        # Find affected vaults
        for mapping in mappings:
            vault_id = mapping.get("vault_id")
            for vault in self.vaults:
                if vault.vault_id == vault_id:
                    impact["affected_vaults"].append(vault.name)
                    break
        
        # Count tag routes
        impact["tag_routes_cleared"] = len([
            route for route in self.tag_routes
            if route.get("calendar_id") == list_id
        ])
        
        return impact

    def get_route_tag_for_calendar(self, vault_id: str, calendar_id: str) -> Optional[str]:
        """Return the configured tag for a vault/calendar combination if present."""
        if not vault_id or not calendar_id:
            return None
        for route in self.tag_routes:
            if (
                route.get("vault_id") == vault_id
                and route.get("calendar_id") == calendar_id
            ):
                return route.get("tag")
        return None

    @staticmethod
    def _normalize_tag_value(tag: Optional[str]) -> Optional[str]:
        if not tag:
            return None
        normalized = tag.strip()
        if not normalized:
            return None
        if not normalized.startswith("#"):
            normalized = f"#{normalized}"
        return normalized.lower()

    def _normalize_tag_routes(self) -> None:
        if not self.tag_routes:
            self.tag_routes = []
            return

        normalized_routes: List[Dict[str, str]] = []
        index_map: Dict[tuple[str, str], int] = {}
        for route in self.tag_routes:
            vault_id = route.get("vault_id")
            tag = self._normalize_tag_value(route.get("tag"))
            calendar_id = route.get("calendar_id")
            import_mode = route.get("import_mode", "existing_only")
            if not vault_id or not tag or not calendar_id:
                continue
            key = (vault_id, tag)
            normalized_entry = {
                "vault_id": vault_id,
                "tag": tag,
                "calendar_id": calendar_id,
                "import_mode": import_mode,
            }
            if key in index_map:
                normalized_routes[index_map[key]] = normalized_entry
            else:
                index_map[key] = len(normalized_routes)
                normalized_routes.append(normalized_entry)

        self.tag_routes = normalized_routes

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    @classmethod
    def load_from_file(cls, config_path: str) -> SyncConfig:
        config_path = _normalize_path(config_path)
        if not os.path.exists(config_path):
            return cls()

        try:
            with open(config_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError:
            return cls()

        # Parse vaults
        vaults: List[Vault] = []
        for entry in data.get("vaults", []):
            vault = Vault(
                name=entry.get("name", ""),
                path=entry.get("path", ""),
                vault_id=entry.get("vault_id", str(uuid4())),
                is_default=entry.get("is_default", False),
            )

            # Migrate old random UUIDs to deterministic ones if needed
            stored_id = entry.get("vault_id", "")
            if stored_id and len(stored_id) == 36:  # Looks like an old UUID
                # Keep the old ID to maintain compatibility
                vault.vault_id = stored_id

            vaults.append(vault)

        # Parse reminders lists
        reminders_lists: List[RemindersList] = []
        for entry in data.get("reminders_lists", []):
            reminders_lists.append(
                RemindersList(
                    name=entry.get("name", ""),
                    identifier=entry.get("identifier", ""),
                    source_name=entry.get("source_name"),
                    source_type=entry.get("source_type"),
                    color=entry.get("color"),
                    allows_modification=entry.get("allows_modification", True),
                )
            )

        # Parse vault mappings
        vault_mappings = data.get("vault_mappings", [])

        sync_settings = data.get("sync", {})
        min_score = sync_settings.get("min_score", data.get("min_score", 0.75))
        days_tolerance = sync_settings.get(
            "days_tolerance", data.get("days_tolerance", 1)
        )
        include_completed = sync_settings.get(
            "include_completed", data.get("include_completed", False)
        )

        paths = data.get("paths", {})

        # Pass None for paths not in config to use PathManager defaults
        config = cls(
            vaults=vaults,
            default_vault_id=data.get("default_vault_id"),
            reminders_lists=reminders_lists,
            default_calendar_id=data.get("default_calendar_id"),
            calendar_ids=data.get("calendar_ids", []),
            vault_mappings=vault_mappings,
            tag_routes=data.get("tag_routes", []),
            min_score=min_score,
            days_tolerance=days_tolerance,
            include_completed=include_completed,
            obsidian_inbox_path=sync_settings.get(
                "obsidian_inbox_path", data.get("obsidian_inbox_path", "AppleRemindersInbox.md")
            ),
            sync_calendar_events=sync_settings.get("sync_calendar_events", False),
            automation_enabled=sync_settings.get("automation_enabled", False),
            automation_interval=sync_settings.get("automation_interval", 3600),
            update_channel=sync_settings.get("update_channel", "stable"),
            obsidian_index_path=paths.get(
                "obsidian_index", data.get("obsidian_index_path", None)
            ),
            reminders_index_path=paths.get(
                "reminders_index", data.get("reminders_index_path", None)
            ),
            links_path=paths.get(
                "links", data.get("links_path", None)
            ),
        )

        # Ensure a default vault id is recorded if one is marked.
        if config.default_vault is not None:
            config.default_vault_id = config.default_vault.vault_id

        return config

    def save_to_file(self, config_path: str) -> None:
        config_path = _normalize_path(config_path)
        os.makedirs(os.path.dirname(config_path), exist_ok=True)

        # Synchronise default markers
        if self.default_vault_id and self.vaults:
            for vault in self.vaults:
                vault.is_default = vault.vault_id == self.default_vault_id
        elif self.vaults:
            # Ensure exactly one default by picking the first if none selected
            self.vaults[0].is_default = True
            self.default_vault_id = self.vaults[0].vault_id

        data = {
            "vaults": [
                {
                    "name": v.name,
                    "path": v.path,
                    "vault_id": v.vault_id,
                    "is_default": v.is_default,
                }
                for v in self.vaults
            ],
            "default_vault_id": self.default_vault_id,
            "reminders_lists": [
                {
                    "name": lst.name,
                    "identifier": lst.identifier,
                    "source_name": lst.source_name,
                    "source_type": lst.source_type,
                    "color": lst.color,
                    "allows_modification": lst.allows_modification,
                }
                for lst in self.reminders_lists
            ],
            "default_calendar_id": self.default_calendar_id,
            "calendar_ids": self.calendar_ids,
            "vault_mappings": self.vault_mappings,
            "tag_routes": self.tag_routes,
            "sync": {
                "min_score": self.min_score,
                "days_tolerance": self.days_tolerance,
                "include_completed": self.include_completed,
                "obsidian_inbox_path": self.obsidian_inbox_path,
                "sync_calendar_events": self.sync_calendar_events,
                "automation_enabled": self.automation_enabled,
                "automation_interval": self.automation_interval,
                "update_channel": self.update_channel,
            },
            "paths": {
                "obsidian_index": self.obsidian_index_path,
                "reminders_index": self.reminders_index_path,
                "links": self.links_path,
            },
        }

        with open(config_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
