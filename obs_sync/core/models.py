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


def _normalize_path(path: str) -> str:
    """Expand user and convert to absolute path."""
    return os.path.abspath(os.path.expanduser(path))


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
        self.path = _normalize_path(self.path)


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
    notes: Optional[str] = None
    created_at: Optional[str] = None
    modified_at: Optional[str] = None

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
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.modified_at,
        }

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

        return cls(
            uuid=data.get("uuid", str(uuid4())),
            item_id=external_ids.get("item", ""),
            calendar_id=external_ids.get("calendar", ""),
            list_name=list_info.get("name", ""),
            status=status,
            title=data.get("description", ""),
            due_date=_iso_to_date(data.get("due")),
            priority=priority,
            notes=data.get("notes"),
            created_at=data.get("created_at"),
            modified_at=data.get("updated_at"),
        )


@dataclass
class SyncLink:
    """Represents a sync link between Obsidian and Reminders tasks."""

    obs_uuid: str
    rem_uuid: str
    score: float
    last_synced: Optional[str] = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "obs_uuid": self.obs_uuid,
            "rem_uuid": self.rem_uuid,
            "score": self.score,
            "last_synced": self.last_synced,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SyncLink:
        return cls(
            obs_uuid=data["obs_uuid"],
            rem_uuid=data["rem_uuid"],
            score=float(data.get("score", 0.0)),
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
    min_score: float = 0.75
    days_tolerance: int = 1
    include_completed: bool = False
    obsidian_inbox_path: str = "AppleRemindersInbox.md"
    obsidian_index_path: str = "~/.config/obsidian_tasks_index.json"
    reminders_index_path: str = "~/.config/reminders_tasks_index.json"
    links_path: str = "~/.config/sync_links.json"

    def __post_init__(self) -> None:
        self.obsidian_index_path = _normalize_path(self.obsidian_index_path)
        self.reminders_index_path = _normalize_path(self.reminders_index_path)
        self.links_path = _normalize_path(self.links_path)

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
            vaults.append(
                Vault(
                    name=entry.get("name", ""),
                    path=entry.get("path", ""),
                    vault_id=entry.get("vault_id", str(uuid4())),
                    is_default=entry.get("is_default", False),
                )
            )

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

        sync_settings = data.get("sync", {})
        min_score = sync_settings.get("min_score", data.get("min_score", 0.75))
        days_tolerance = sync_settings.get(
            "days_tolerance", data.get("days_tolerance", 1)
        )
        include_completed = sync_settings.get(
            "include_completed", data.get("include_completed", False)
        )

        paths = data.get("paths", {})

        config = cls(
            vaults=vaults,
            default_vault_id=data.get("default_vault_id"),
            reminders_lists=reminders_lists,
            default_calendar_id=data.get("default_calendar_id"),
            calendar_ids=data.get("calendar_ids", []),
            min_score=min_score,
            days_tolerance=days_tolerance,
            include_completed=include_completed,
            obsidian_inbox_path=sync_settings.get(
                "obsidian_inbox_path", data.get("obsidian_inbox_path", "AppleRemindersInbox.md")
            ),
            obsidian_index_path=paths.get(
                "obsidian_index", data.get("obsidian_index_path", cls.obsidian_index_path)
            ),
            reminders_index_path=paths.get(
                "reminders_index", data.get("reminders_index_path", cls.reminders_index_path)
            ),
            links_path=paths.get(
                "links", data.get("links_path", cls.links_path)
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
            "sync": {
                "min_score": self.min_score,
                "days_tolerance": self.days_tolerance,
                "include_completed": self.include_completed,
                "obsidian_inbox_path": self.obsidian_inbox_path,
            },
            "paths": {
                "obsidian_index": self.obsidian_index_path,
                "reminders_index": self.reminders_index_path,
                "links": self.links_path,
            },
        }

        with open(config_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)