#!/usr/bin/env python3
"""Test EventKit save method signature"""

from EventKit import EKEventStore, EKEntityTypeReminder
import inspect

store = EKEventStore.alloc().init()

# Check the method signature
method = store.saveReminder_commit_error_
print(f"Method: {method}")
print(f"Method type: {type(method)}")

# Try to get more info
import objc
print("\nChecking PyObjC method info:")
try:
    # PyObjC methods have special attributes
    print(f"Selector: {method.selector}")
except:
    pass

# The actual signature in Objective-C is:
# - (BOOL)saveReminder:(EKReminder *)reminder commit:(BOOL)commit error:(NSError **)error
# In PyObjC, methods with NSError ** typically return a tuple
print("\nBased on Objective-C signature, PyObjC should return:")
print("(success_bool, error_or_none) = store.saveReminder_commit_error_(reminder, commit_bool)")
