#!/usr/bin/env python3
"""Verify if the save persisted"""

from EventKit import EKEventStore, EKEntityTypeReminder
from Foundation import NSRunLoop, NSDate
import threading
import time

store = EKEventStore.alloc().init()

# Get fresh reminders
all_cals = store.calendarsForEntityType_(EKEntityTypeReminder) or []
pred = store.predicateForRemindersInCalendars_(all_cals)
bucket = []
done = threading.Event()

def completion(reminders):
    bucket.extend(list(reminders or []))
    done.set()

store.fetchRemindersMatchingPredicate_completion_(pred, completion)
deadline = time.time() + 5
while not done.is_set() and time.time() < deadline:
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.1))

# Find test reminder
for r in bucket:
    if "Mechanised" in str(r.title()):
        print(f"Reminder: {r.title()}")
        due = r.dueDateComponents()
        if due:
            print(f"Due date: Year={due.year()}, Month={due.month()}, Day={due.day()}")
        else:
            print("Due date: None")
        break
