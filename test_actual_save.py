#!/usr/bin/env python3
"""Test if we can actually save changes to a reminder"""

from EventKit import EKEventStore, EKEntityTypeReminder, EKAuthorizationStatusAuthorized
from Foundation import NSRunLoop, NSDate, NSDateComponents, NSCalendar
import threading
import time

store = EKEventStore.alloc().init()

# Check authorization
status = EKEventStore.authorizationStatusForEntityType_(EKEntityTypeReminder)
print(f"Authorization status: {status} (Authorized = {EKAuthorizationStatusAuthorized})")

if int(status) != int(EKAuthorizationStatusAuthorized):
    print("Not authorized, requesting...")
    done = threading.Event()
    def completion(granted, error):
        print(f"Authorization granted: {granted}")
        done.set()
    store.requestAccessToEntityType_completion_(EKEntityTypeReminder, completion)
    deadline = time.time() + 10
    while not done.is_set() and time.time() < deadline:
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.1))

# Get all calendars
all_cals = store.calendarsForEntityType_(EKEntityTypeReminder) or []
print(f"\nFound {len(all_cals)} calendars")

# Find a test reminder
pred = store.predicateForRemindersInCalendars_(all_cals)
bucket = []
done = threading.Event()

def completion(reminders):
    bucket.extend(list(reminders or []))
    done.set()

store.fetchRemindersMatchingPredicate_completion_(pred, completion)
deadline = time.time() + 10
while not done.is_set() and time.time() < deadline:
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.1))

print(f"Found {len(bucket)} reminders")

# Find the "Mechanised find out" reminder
target = None
for r in bucket:
    if "Mechanised" in str(r.title()):
        target = r
        break

if target:
    print(f"\nFound reminder: {target.title()}")
    print(f"Current due date: {target.dueDateComponents()}")
    
    # Try to set a due date
    print("\nAttempting to set due date to 2025-08-22...")
    comps = NSDateComponents.alloc().init()
    comps.setYear_(2025)
    comps.setMonth_(8)
    comps.setDay_(22)
    target.setDueDateComponents_(comps)
    
    # Save with correct PyObjC pattern
    print("Saving...")
    result = store.saveReminder_commit_error_(target, True)
    
    # Check the result type
    print(f"Result type: {type(result)}")
    print(f"Result value: {result}")
    
    if isinstance(result, tuple):
        success, error = result
        print(f"Success: {success}, Error: {error}")
    else:
        print(f"Unexpected result type - might be just boolean: {result}")
else:
    print("Could not find test reminder")
