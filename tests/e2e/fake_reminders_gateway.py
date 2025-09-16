#!/usr/bin/env python3
"""
Fake Reminders Gateway and EventKit-like objects for end-to-end testing.

This provides a minimal, in-memory implementation of the interfaces used by:
- obs_tools.commands.collect_reminders_tasks (reads raw reminder object attrs)
- obs_tools.commands.sync_links_apply (calls RemindersGateway.update_reminder)
- obs_tools.commands.create_missing_counterparts (calls RemindersGateway.create_reminder)

It intentionally mimics the subset of EventKit object API accessed by the
collectors and updaters. It allows tests to verify actual mutations happen
"on the platform" by asserting state in this fake store.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import hashlib


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class _FakeURL:
    def __init__(self, url: Optional[str]):
        self._url = url

    def absoluteString(self) -> Optional[str]:
        return self._url


class _FakeDateComponents:
    def __init__(self, year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0):
        self._y, self._m, self._d = year, month, day
        self._h, self._min, self._s = hour, minute, second

    def year(self) -> int:
        return self._y

    def month(self) -> int:
        return self._m

    def day(self) -> int:
        return self._d

    def hour(self) -> int:
        return self._h

    def minute(self) -> int:
        return self._min

    def second(self) -> int:
        return self._s


class _FakeCalendar:
    def __init__(self, identifier: str, title: str = "Test", source_title: str = "Local"):
        self._id = identifier
        self._title = title
        self._source_title = source_title

    # Methods used indirectly (via caching in collector)
    def calendarIdentifier(self) -> str:
        return self._id

    def title(self) -> str:
        return self._title

    def source(self):
        class _Src:
            def __init__(self, title: str):
                self._title = title

            def title(self):
                return self._title

            def sourceType(self):
                return 0  # local

        return _Src(self._source_title)

    def color(self):  # not used in assertions
        class _C:
            def colorUsingColorSpaceName_(self, *_):
                return self

            def redComponent(self):
                return 0.1

            def greenComponent(self):
                return 0.6

            def blueComponent(self):
                return 0.9

        return _C()


class FakeReminder:
    def __init__(self, *,
                 title: str,
                 calendar_id: str,
                 item_id: str,
                 external_id: Optional[str] = None,
                 completed: bool = False,
                 due_date: Optional[str] = None,
                 priority: Optional[int] = None,
                 notes: Optional[str] = None,
                 url: Optional[str] = None,
                 created_at: Optional[str] = None,
                 modified_at: Optional[str] = None):
        self._title = title
        self._completed = bool(completed)
        self._due = None
        if due_date:
            y, m, d = map(int, due_date[:10].split("-"))
            self._due = _FakeDateComponents(y, m, d)
        self._priority = int(priority) if priority is not None else 0
        self._notes = notes
        self._url = _FakeURL(url) if url else None
        self._created = created_at or now_iso()
        self._modified = modified_at or self._created
        self._calendar = _FakeCalendar(calendar_id)
        self._item_id = item_id
        self._external_id = external_id

    # Getters used by collector
    def title(self) -> str:
        return self._title

    def notes(self) -> Optional[str]:
        return self._notes

    def URL(self):
        return self._url

    def isCompleted(self) -> bool:
        return self._completed

    def completionDate(self):
        return None

    def dueDateComponents(self):
        return self._due

    def startDateComponents(self):
        return None

    def priority(self) -> int:
        return self._priority

    def recurrenceRules(self):
        return []

    def alarms(self):
        return []

    def creationDate(self):
        return None

    def lastModifiedDate(self):
        return None

    def calendarItemIdentifier(self) -> str:
        return self._item_id

    def calendarItemExternalIdentifier(self) -> Optional[str]:
        return self._external_id

    def calendar(self) -> _FakeCalendar:
        return self._calendar

    # Setters used by gateway.update_reminder
    def setTitle_(self, value: str) -> None:
        self._title = value

    def setCompleted_(self, val: bool) -> None:
        self._completed = bool(val)

    def setDueDateComponents_(self, comps: Optional[_FakeDateComponents]) -> None:
        self._due = comps

    def setPriority_(self, val: int) -> None:
        self._priority = int(val)


class FakeRemindersGateway:
    """In-memory fake store keyed by calendar_id and item_id."""
    def __init__(self, logger=None, timeout: int = 30):
        self.logger = logger
        self.timeout = timeout
        self._lists: Dict[str, List[FakeReminder]] = {}
        # Pre-seed data can be injected by tests via methods below

    # Test helper API
    def seed_list(self, calendar_id: str, items: List[FakeReminder]) -> None:
        self._lists[calendar_id] = list(items)

    def all_items(self) -> List[FakeReminder]:
        return [item for items in self._lists.values() for item in items]

    # API used by commands
    def get_reminders_from_lists(self, list_configs: List[Dict[str, str]], **_) -> Tuple[List[FakeReminder], Dict[str, Dict[str, Any]]]:
        wanted = {c["identifier"] for c in list_configs}
        result: List[FakeReminder] = []
        cal_cache: Dict[str, Dict[str, Any]] = {}
        for cal_id, items in self._lists.items():
            if cal_id not in wanted:
                continue
            for r in items:
                result.append(r)
                key = self._key_for(r)
                cal_cache[key] = {
                    "name": "Test",
                    "identifier": cal_id,
                    "source_name": "Local",
                    "source_type": "local",
                    "color": "#00A0E6",
                }
        return result, cal_cache

    def _key_for(self, r: FakeReminder) -> str:
        ext = r.calendarItemExternalIdentifier()
        if ext:
            return f"ext:{ext}"
        return f"cid:{r.calendar().calendarIdentifier()}|iid:{r.calendarItemIdentifier()}"

    def find_reminder_by_id(self, item_id: str, calendar_id: Optional[str] = None) -> Optional[FakeReminder]:
        if calendar_id and calendar_id in self._lists:
            for r in self._lists[calendar_id]:
                if r.calendarItemIdentifier() == item_id:
                    return r
            return None
        for items in self._lists.values():
            for r in items:
                if r.calendarItemIdentifier() == item_id:
                    return r
        return None

    def update_reminder(self, reminder_dict: Dict[str, Any], fields: Dict[str, Any], dry_run: bool = False):
        # Emulate reminders_gateway.UpdateResult shape
        class Change:
            def __init__(self, field, old, new):
                self.field = field
                self.old_value = old
                self.new_value = new

        changes = []
        errors: List[str] = []
        ids = reminder_dict.get("external_ids", {})
        item_id = ids.get("item")
        cal_id = ids.get("calendar")
        if not item_id:
            return type("Res", (), {"success": False, "changes_applied": [], "errors": ["no id"], "reminder_id": None})
        r = self.find_reminder_by_id(item_id, cal_id)
        if not r:
            return type("Res", (), {"success": False, "changes_applied": [], "errors": ["not found"], "reminder_id": item_id})

        # Title
        if fields.get("title_to_rem"):
            new_title = fields.get("title_value")
            if new_title is not None and new_title != r.title():
                changes.append(Change("title", r.title(), new_title))
                if not dry_run:
                    r.setTitle_(new_title)
        # Status
        if fields.get("status_to_rem"):
            new_status = reminder_dict.get("status") == "done"
            if new_status != bool(r.isCompleted()):
                changes.append(Change("status", "done" if r.isCompleted() else "todo", "done" if new_status else "todo"))
                if not dry_run:
                    r.setCompleted_(new_status)
        # Due
        if fields.get("due_to_rem"):
            new_due = reminder_dict.get("due")
            old_due = r.dueDateComponents()
            old_str = f"{old_due.year()}-{old_due.month():02d}-{old_due.day():02d}" if old_due else None
            new_str = new_due[:10] if new_due else None
            if new_str != old_str:
                changes.append(Change("due", old_str, new_str))
                if not dry_run:
                    if new_due:
                        y, m, d = map(int, new_due[:10].split("-"))
                        r.setDueDateComponents_(_FakeDateComponents(y, m, d))
                    else:
                        r.setDueDateComponents_(None)
        # Priority
        if fields.get("priority_to_rem"):
            pr_map = {"high": 1, "medium": 5, "low": 9}
            new_text = reminder_dict.get("priority")
            new_val = pr_map.get(new_text, 0)
            if new_val != r.priority():
                changes.append(Change("priority", r.priority(), new_text))
                if not dry_run:
                    r.setPriority_(new_val)

        return type("Res", (), {"success": True, "changes_applied": changes, "errors": errors, "reminder_id": item_id})

    def create_reminder(self, title: str, calendar_id: Optional[str] = None, properties: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        cal_id = calendar_id or next(iter(self._lists.keys()), "test-cal")
        if cal_id not in self._lists:
            self._lists[cal_id] = []
        item_id = f"fake-{len(self._lists[cal_id]) + 1}"
        due = properties.get("due_date")[:10] if properties and properties.get("due_date") else None
        prio = properties.get("priority") if properties else None
        r = FakeReminder(title=title or "Untitled Task", calendar_id=cal_id, item_id=item_id, due_date=due, priority=prio)
        self._lists[cal_id].append(r)
        uid = hashlib.sha1(f"{cal_id}:{item_id}".encode("utf-8")).hexdigest()[:12]
        return {
            "uuid": f"rem-{uid}",
            "calendar_id": cal_id,
            "created_at": now_iso(),
            "external_ids": {"calendar": cal_id, "item": item_id}
        }

