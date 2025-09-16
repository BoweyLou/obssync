#!/usr/bin/env python3
"""
Test script to verify the RemindersGateway integration works correctly.
"""

import sys
import json
from reminders_gateway import RemindersGateway, RemindersError, AuthorizationError, EventKitImportError


def test_gateway_basic():
    """Test basic gateway functionality."""
    print("Testing RemindersGateway basic functionality...")
    
    gateway = RemindersGateway()
    
    # Test if EventKit is available
    print(f"EventKit available: {gateway.is_available()}")
    
    if not gateway.is_available():
        print("EventKit not available - this is expected in environments without PyObjC")
        return True
    
    try:
        # Test getting reminder lists
        print("Fetching reminder lists...")
        lists = gateway.get_reminder_lists()
        print(f"Found {len(lists)} reminder lists:")
        for lst in lists:
            print(f"  - {lst['name']} ({lst['identifier']})")
        
        if lists:
            # Test getting reminders from first list
            print(f"\nFetching reminders from first list: {lists[0]['name']}")
            reminders, calendar_cache = gateway.get_reminders_from_lists([lists[0]])
            print(f"Found {len(reminders)} reminders")
            
            # Show first few reminders
            for i, reminder in enumerate(reminders[:3]):
                try:
                    title = str(reminder.title() or "(no title)")
                    completed = bool(reminder.isCompleted())
                    print(f"  {i+1}. {title} ({'completed' if completed else 'pending'})")
                except Exception as e:
                    print(f"  {i+1}. Error reading reminder: {e}")
        
        print("\nGateway basic test completed successfully!")
        return True
        
    except EventKitImportError as e:
        print(f"EventKit import error: {e}")
        return False
    except AuthorizationError as e:
        print(f"Authorization error: {e}")
        return False
    except RemindersError as e:
        print(f"Reminders error: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False


def test_collect_reminders_integration():
    """Test the updated collect_reminders_tasks.py integration."""
    print("\nTesting collect_reminders_tasks.py integration...")
    
    # Check if reminders lists config exists
    import os
    config_path = os.path.expanduser("~/.config/reminders_lists.json")
    if not os.path.exists(config_path):
        print(f"Reminders lists config not found at {config_path}")
        print("Run: python3 obs_tools.py reminders discover")
        return False
    
    try:
        # Import the updated function
        from collect_reminders_tasks import reminders_from_lists, load_lists
        
        # Load lists
        lists = load_lists(config_path)
        print(f"Loaded {len(lists)} lists from config")
        
        # Test the updated function
        reminders, id_to_meta, calendar_cache = reminders_from_lists(lists)
        print(f"Successfully fetched {len(reminders)} reminders")
        print(f"Calendar cache contains {len(calendar_cache)} entries")
        
        print("collect_reminders_tasks.py integration test passed!")
        return True
        
    except Exception as e:
        print(f"collect_reminders_tasks.py integration test failed: {e}")
        return False


def test_sync_apply_integration():
    """Test the updated sync_links_apply.py integration.""" 
    print("\nTesting sync_links_apply.py integration...")
    
    try:
        # Import the updated function
        from obs_tools.commands.sync_links_apply import update_reminder
        
        # Create a mock reminder task for testing
        mock_reminder = {
            "description": "Test reminder",
            "external_ids": {
                "item": "test-item-id",
                "calendar": "test-calendar-id"
            },
            "status": "todo",
            "due": None,
            "priority": None
        }
        
        # Create mock fields (no actual changes)
        mock_fields = {
            "title_to_rem": False,
            "status_to_rem": False, 
            "due_to_rem": False,
            "priority_to_rem": False
        }
        
        # Test in dry-run mode
        ek_cache = {}
        result = update_reminder(mock_reminder, apply=False, fields=mock_fields, ek_cache=ek_cache, verbose=True)
        
        print(f"sync_links_apply.py dry-run test completed (result: {result})")
        print("sync_links_apply.py integration test passed!")
        return True
        
    except Exception as e:
        print(f"sync_links_apply.py integration test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("=== RemindersGateway Integration Tests ===\n")
    
    tests = [
        test_gateway_basic,
        test_collect_reminders_integration,
        test_sync_apply_integration
    ]
    
    results = []
    for test_func in tests:
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            print(f"Test {test_func.__name__} failed with exception: {e}")
            results.append(False)
        print("-" * 60)
    
    print(f"\n=== Test Results ===")
    print(f"Passed: {sum(results)}/{len(results)}")
    
    if all(results):
        print("All tests passed! RemindersGateway integration is working correctly.")
        return 0
    else:
        print("Some tests failed. Check the output above for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())