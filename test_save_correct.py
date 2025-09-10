#!/usr/bin/env python3
"""Test correct EventKit save operation"""

from EventKit import EKEventStore, EKEntityTypeReminder
from Foundation import NSRunLoop, NSDate, NSDateComponents
import threading
import time
import objc

store = EKEventStore.alloc().init()

# Get reminders
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
target = None
for r in bucket:
    if "Mechanised" in str(r.title()):
        target = r
        break

if target:
    print(f"Found reminder: {target.title()}")
    print(f"Current due date: {target.dueDateComponents()}")
    
    # Set due date
    comps = NSDateComponents.alloc().init()
    comps.setYear_(2025)
    comps.setMonth_(8) 
    comps.setDay_(22)
    target.setDueDateComponents_(comps)
    
    # Try different save patterns
    print("\nTrying save with None for error:")
    try:
        result = store.saveReminder_commit_error_(target, True, None)
        print(f"Result: {result} (type: {type(result)})")
        
        # Check if the save actually worked
        if result:
            print("Save reported success!")
            # Verify the change
            print(f"Due date after save: {target.dueDateComponents()}")
        else:
            print("Save reported failure")
    except Exception as e:
        print(f"Exception: {e}")
    
    # Try with objc.nil
    print("\nTrying save with objc.nil:")
    try:
        result = store.saveReminder_commit_error_(target, True, objc.nil)
        print(f"Result: {result}")
    except Exception as e:
        print(f"Exception: {e}")
