#!/usr/bin/env python3
"""Test proper PyObjC error handling for EventKit"""

try:
    from EventKit import EKEventStore, EKEntityTypeReminder
    from Foundation import NSError
    import objc
    
    print("EventKit imported successfully")
    
    # Check how to properly handle NSError with PyObjC
    print("\nPyObjC error handling pattern:")
    print("- For methods ending in 'error:', PyObjC uses a special pattern")
    print("- The method returns a tuple: (success, error)")
    print("- You don't pass None for error, you omit it or handle the tuple return")
    
    # The correct pattern is:
    # success, error = store.saveReminder_commit_error_(reminder, True, None)
    # OR just:
    # success = store.saveReminder_commit_error_(reminder, True, None)
    # But it depends on the method signature
    
except ImportError as e:
    print(f"EventKit not available: {e}")
