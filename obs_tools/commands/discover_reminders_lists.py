#!/usr/bin/env python3
"""
Discover Apple Reminders lists via EventKit, confirm with the user,
and save to a config file. On subsequent runs, confirm the saved
list or reset and re-discover.

Config file location:
  - Default: ~/.config/reminders_lists.json
  - Override with: --config /path/to/file.json

Notes:
  - Uses EventKit (via PyObjC) to enumerate Reminders calendars.
  - You'll be prompted for Reminders access on first run.
  - No deep search options (EventKit returns all lists).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from dataclasses import dataclass
from typing import List, Optional

# Import centralized path configuration
from app_config import get_path


@dataclass(frozen=True)
class RemindersList:
    name: str
    identifier: str
    source_name: Optional[str]
    source_type: Optional[str]
    calendar_type: Optional[str]
    allows_modification: Optional[bool]
    color: Optional[str]


def nscolor_to_hex(color) -> Optional[str]:
    try:
        # Try to extract RGBA components if possible
        # Works when AppKit is available; otherwise returns a fallback string
        c = color.colorUsingColorSpaceName_("NSCalibratedRGBColorSpace")
        if c is None:
            return None
        r = int(round(c.redComponent() * 255))
        g = int(round(c.greenComponent() * 255))
        b = int(round(c.blueComponent() * 255))
        return f"#{r:02X}{g:02X}{b:02X}"
    except Exception:
        try:
            return str(color)
        except Exception:
            return None


def ek_discover_lists() -> List[RemindersList]:
    try:
        import objc  # type: ignore
        from EventKit import (
            EKEventStore,
            EKEntityTypeReminder,
            EKAuthorizationStatusAuthorized,
            EKCalendarTypeLocal,
            EKCalendarTypeCalDAV,
            EKCalendarTypeExchange,
            EKCalendarTypeSubscription,
            EKCalendarTypeBirthday,
        )  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "EventKit is not available. Install PyObjC:\n"
            "  pip3 install pyobjc-framework-EventKit pyobjc\n"
            f"Import error: {e}"
        )

    cal_type_map = {
        int(EKCalendarTypeLocal): "local",
        int(EKCalendarTypeCalDAV): "caldav",
        int(EKCalendarTypeExchange): "exchange",
        int(EKCalendarTypeSubscription): "subscription",
        int(EKCalendarTypeBirthday): "birthday",
    }

    store = EKEventStore.alloc().init()

    # Request access if needed (async completion)
    # Class method to check authorization for Reminders entity
    status = EKEventStore.authorizationStatusForEntityType_(EKEntityTypeReminder)
    if int(status) != int(EKAuthorizationStatusAuthorized):
        done = threading.Event()
        result = {"granted": False}

        def completion(granted, error):  # noqa: ANN001
            try:
                result["granted"] = bool(granted)
            finally:
                done.set()

        store.requestAccessToEntityType_completion_(EKEntityTypeReminder, completion)
        # Wait up to 60s for user to respond to the permission dialog
        done.wait(60)
        if not result["granted"]:
            raise PermissionError("Reminders access not granted. Please allow access and retry.")

    calendars = store.calendarsForEntityType_(EKEntityTypeReminder) or []
    out: List[RemindersList] = []
    for cal in calendars:
        try:
            name = str(cal.title())
        except Exception:
            name = "(unnamed)"
        try:
            identifier = str(cal.calendarIdentifier())
        except Exception:
            identifier = ""

        # Source info
        src = None
        try:
            src = cal.source()
        except Exception:
            pass
        source_name = None
        source_type_num = None
        if src is not None:
            try:
                source_name = str(src.title())
            except Exception:
                source_name = None
            try:
                source_type_num = int(src.sourceType())
            except Exception:
                source_type_num = None
        source_type = None
        if source_type_num is not None:
            # Best-effort mapping; EventKit SourceType constants overlap with calendar types
            #  Local(0), Exchange(1), CalDAV(2), MobileMe(3), Subscribed(4), Birthdays(5)
            source_type = {
                0: "local",
                1: "exchange",
                2: "caldav",
                3: "mobileme",
                4: "subscribed",
                5: "birthdays",
            }.get(source_type_num, str(source_type_num))

        # Calendar type + modifiability
        try:
            cal_type = cal_type_map.get(int(cal.type()), str(int(cal.type())))
        except Exception:
            cal_type = None
        try:
            allows_mod = bool(cal.allowsContentModifications())
        except Exception:
            allows_mod = None

        # Color (hex if possible)
        try:
            color_hex = nscolor_to_hex(cal.color())
        except Exception:
            color_hex = None

        out.append(
            RemindersList(
                name=name,
                identifier=identifier,
                source_name=source_name,
                source_type=source_type,
                calendar_type=cal_type,
                allows_modification=allows_mod,
                color=color_hex,
            )
        )
    return out


def human_list(items: List[RemindersList]) -> str:
    if not items:
        return "(none)"
    lines = []
    for i, it in enumerate(items, 1):
        src = it.source_name or "(no source)"
        lines.append(f"{i}. {it.name}  —  {src}  —  {it.identifier}")
    return "\n".join(lines)


def save_config(items: List[RemindersList], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = [
        {
            "name": it.name,
            "identifier": it.identifier,
            "source": {"name": it.source_name, "type": it.source_type},
            "calendar_type": it.calendar_type,
            "allows_modification": it.allows_modification,
            "color": it.color,
        }
        for it in items
    ]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(items)} list(s) to {path}")


def load_config(path: str) -> Optional[List[RemindersList]]:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        out: List[RemindersList] = []
        for d in data:
            out.append(
                RemindersList(
                    name=str(d.get("name", "")),
                    identifier=str(d.get("identifier", "")),
                    source_name=(d.get("source") or {}).get("name"),
                    source_type=(d.get("source") or {}).get("type"),
                    calendar_type=d.get("calendar_type"),
                    allows_modification=d.get("allows_modification"),
                    color=d.get("color"),
                )
            )
        return out
    except Exception as e:
        print(f"Warning: failed to read config {path}: {e}")
        return None


def prompt(msg: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    try:
        val = input(f"{msg}{suffix}: ").strip()
    except EOFError:
        print("\nInput stream closed. Exiting.")
        sys.exit(1)
    if not val and default is not None:
        return default
    return val


def confirm_saved(items: List[RemindersList]) -> bool:
    print("Found saved Reminders lists:")
    print(human_list(items))
    ans = prompt("Use these lists? (Y)es/(N)o", default="Y").lower()
    return ans in ("y", "yes", "")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Discover Apple Reminders lists via EventKit and save to a config file.")
    ap.add_argument("--config", default=get_path("reminders_lists"), help="Config JSON file path (default: ~/.config/reminders_lists.json)")
    args = ap.parse_args(argv)

    cfg = os.path.abspath(os.path.expanduser(args.config))

    existing = load_config(cfg)
    if existing:
        if confirm_saved(existing):
            print("Confirmed. Nothing to do.")
            return 0
        else:
            try:
                os.remove(cfg)
            except OSError:
                pass
            print("Cleared saved config. Discovering lists…")

    try:
        lists = ek_discover_lists()
    except Exception as e:
        print(f"Error: {e}")
        return 1

    if not lists:
        print("No Reminders lists found.")
        return 0

    print("Discovered Reminders lists:")
    print(human_list(lists))
    ans = prompt("Save these? (Y)es/(N)o", default="Y").lower()
    if ans not in ("y", "yes", ""):
        print("Aborted by user; nothing saved.")
        return 0

    save_config(lists, cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
