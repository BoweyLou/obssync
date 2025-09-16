#!/usr/bin/env python3
"""
Debug version of sync_links_apply.py to identify EventKit issues.
"""

import json
import os
from obs_tools.commands.sync_links_apply import load_json, DEFAULT_OBS, DEFAULT_REM, DEFAULT_LINKS

def debug_update_reminder(rem_task: dict) -> dict:
    """Debug version that reports exactly what fails."""
    result = {
        "task_id": rem_task.get("uuid"),
        "task_title": rem_task.get("description", "")[:50],
        "has_external_ids": bool(rem_task.get("external_ids")),
        "item_id": None,
        "cal_id": None,
        "eventkit_available": False,
        "store_created": False,
        "calendars_found": 0,
        "reminder_found": False,
        "error": None
    }
    
    # Extract identifiers
    ids = rem_task.get("external_ids") or {}
    item_id = ids.get("item")
    cal_id = ids.get("calendar") or ""
    
    result["item_id"] = item_id
    result["cal_id"] = cal_id
    
    if not item_id:
        result["error"] = "No item_id found"
        return result
    
    # Test EventKit import
    try:
        from EventKit import EKEventStore, EKEntityTypeReminder
        from Foundation import NSRunLoop, NSDate
        result["eventkit_available"] = True
    except Exception as e:
        result["error"] = f"EventKit import failed: {e}"
        return result
    
    # Try to create store
    try:
        store = EKEventStore.alloc().init()
        result["store_created"] = True
    except Exception as e:
        result["error"] = f"Store creation failed: {e}"
        return result
    
    # Try to get calendars
    try:
        all_cals = store.calendarsForEntityType_(EKEntityTypeReminder) or []
        result["calendars_found"] = len(all_cals)
        
        if cal_id:
            cals = [c for c in all_cals if str(c.calendarIdentifier()) == cal_id]
            if not cals:
                result["error"] = f"Calendar {cal_id} not found among {len(all_cals)} calendars"
                return result
        else:
            cals = list(all_cals)
            
    except Exception as e:
        result["error"] = f"Calendar access failed: {e}"
        return result
    
    # Try to fetch reminders
    try:
        pred = store.predicateForRemindersInCalendars_(cals)
        bucket = []
        import threading, time
        done = threading.Event()
        
        def completion(reminders):
            try:
                bucket.extend(list(reminders or []))
            finally:
                done.set()
                
        store.fetchRemindersMatchingPredicate_completion_(pred, completion)
        deadline = time.time() + 10  # Shorter timeout for debugging
        
        while (not done.is_set()) and time.time() < deadline:
            NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.1))
            
        if not done.is_set():
            result["error"] = "Timeout waiting for reminders"
            return result
            
    except Exception as e:
        result["error"] = f"Reminder fetch failed: {e}"
        return result
    
    # Try to find specific reminder
    target = None
    for r in bucket:
        try:
            rid = str(r.calendarItemIdentifier())
        except Exception:
            rid = ""
        if rid and rid == item_id:
            target = r
            break
            
    result["reminder_found"] = target is not None
    if not target:
        result["error"] = f"Reminder with ID {item_id} not found among {len(bucket)} reminders"
    
    return result

def main():
    obs = load_json(DEFAULT_OBS)
    rem = load_json(DEFAULT_REM)
    links = load_json(DEFAULT_LINKS)
    
    obs_tasks = obs.get("tasks", {}) or {}
    rem_tasks = rem.get("tasks", {}) or {}
    link_list = links.get("links", []) or []
    
    print("Debugging EventKit issues...")
    print(f"Found {len(link_list)} links to test")
    
    issues = []
    success_count = 0
    
    for i, lk in enumerate(link_list[:5]):  # Test first 5 links
        ru = lk.get("rem_uuid")
        if not ru:
            continue
            
        rt = rem_tasks.get(ru)
        if not rt:
            continue
            
        print(f"\nTesting reminder {i+1}: {rt.get('description', '')[:50]}...")
        result = debug_update_reminder(rt)
        
        if result["error"]:
            issues.append(result)
            print(f"  ❌ FAILED: {result['error']}")
        else:
            success_count += 1
            print(f"  ✅ SUCCESS: Reminder found and accessible")
    
    print(f"\n--- SUMMARY ---")
    print(f"Successful: {success_count}")
    print(f"Failed: {len(issues)}")
    
    if issues:
        print("\n--- FAILURE DETAILS ---")
        for issue in issues:
            print(f"Task: {issue['task_title']}")
            print(f"  Error: {issue['error']}")
            print(f"  Has IDs: {issue['has_external_ids']}")
            print(f"  Item ID: {issue['item_id']}")
            print(f"  Cal ID: {issue['cal_id']}")
            print(f"  EventKit: {issue['eventkit_available']}")
            print()

if __name__ == "__main__":
    main()