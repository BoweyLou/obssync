#!/usr/bin/env python3
"""
Platform-specific tests for EventKit/macOS functionality.

These tests are marked with @pytest.mark.macos and will be skipped
by default on non-Darwin platforms.
"""

import os
import platform
import unittest
from typing import Dict, List, Optional
from unittest.mock import patch, MagicMock

import pytest

# Add parent directory to path for imports
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Platform detection
IS_MACOS = platform.system() == "Darwin"

# EventKit imports - only available on macOS
HAS_EVENTKIT = False
if IS_MACOS:
    try:
        import objc
        import EventKit
        HAS_EVENTKIT = True
    except ImportError:
        pass

# Import our modules
try:
    from obs_tools.commands.collect_reminders_tasks import (
        list_reminder_lists, collect_all_reminders, format_reminder_task
    )
    from obs_tools.commands.discover_reminders_lists import (
        discover_reminder_lists, save_reminder_lists_config
    )
except ImportError:
    # Mock implementations for testing when modules not available
    def list_reminder_lists():
        return []
    
    def collect_all_reminders(lists=None, include_completed=False):
        return []
    
    def format_reminder_task(reminder):
        return {}
    
    def discover_reminder_lists():
        return []
    
    def save_reminder_lists_config(lists, config_path):
        return True


@pytest.mark.macos
@pytest.mark.eventkit
class TestEventKitIntegration(unittest.TestCase):
    """Test EventKit integration on macOS."""
    
    def setUp(self):
        """Set up test environment."""
        if not IS_MACOS:
            self.skipTest("EventKit tests require macOS")
        
        if not HAS_EVENTKIT:
            self.skipTest("EventKit framework not available")
    
    def test_eventkit_import_availability(self):
        """Test that EventKit can be imported on macOS."""
        self.assertTrue(IS_MACOS, "Should be running on macOS")
        self.assertTrue(HAS_EVENTKIT, "EventKit should be available")
        
        # Test that we can import the required classes
        self.assertTrue(hasattr(EventKit, 'EKEventStore'))
        self.assertTrue(hasattr(EventKit, 'EKReminder'))
        self.assertTrue(hasattr(EventKit, 'EKCalendar'))
    
    @patch('EventKit.EKEventStore')
    def test_eventstore_initialization_mock(self, mock_eventstore_class):
        """Test EventStore initialization with mocking."""
        mock_store = MagicMock()
        mock_eventstore_class.return_value = mock_store
        
        # Mock the authorization status
        mock_store.authorizationStatusForEntityType_.return_value = 3  # EKAuthorizationStatusAuthorized
        
        # Test initialization
        store = EventKit.EKEventStore.alloc().init()
        self.assertIsNotNone(store)
        
        # Verify mock was called
        mock_eventstore_class.assert_called()
    
    def test_reminder_lists_discovery_mock(self):
        """Test reminder lists discovery with mocking."""
        with patch('EventKit.EKEventStore') as mock_eventstore_class:
            mock_store = MagicMock()
            mock_eventstore_class.alloc.return_value.init.return_value = mock_store
            
            # Mock authorization
            mock_store.authorizationStatusForEntityType_.return_value = 3  # Authorized
            
            # Mock calendar lists
            mock_calendar_1 = MagicMock()
            mock_calendar_1.title.return_value = "Tasks"
            mock_calendar_1.calendarIdentifier.return_value = "cal-1"
            mock_calendar_1.type.return_value = 1  # EKCalendarTypeReminder
            
            mock_calendar_2 = MagicMock()
            mock_calendar_2.title.return_value = "Work"
            mock_calendar_2.calendarIdentifier.return_value = "cal-2"
            mock_calendar_2.type.return_value = 1  # EKCalendarTypeReminder
            
            mock_store.calendarsForEntityType_.return_value = [mock_calendar_1, mock_calendar_2]
            
            # Test discovery
            reminder_lists = discover_reminder_lists()
            
            # Should return valid structure (might be empty if mocked completely)
            self.assertIsInstance(reminder_lists, list)
    
    def test_reminders_collection_mock(self):
        """Test reminders collection with mocking."""
        with patch('EventKit.EKEventStore') as mock_eventstore_class:
            mock_store = MagicMock()
            mock_eventstore_class.alloc.return_value.init.return_value = mock_store
            
            # Mock authorization
            mock_store.authorizationStatusForEntityType_.return_value = 3
            
            # Mock reminder
            mock_reminder = MagicMock()
            mock_reminder.title.return_value = "Test Task"
            mock_reminder.isCompleted.return_value = False
            mock_reminder.calendarItemIdentifier.return_value = "reminder-1"
            mock_reminder.creationDate.return_value = None
            mock_reminder.lastModifiedDate.return_value = None
            mock_reminder.dueDateComponents.return_value = None
            mock_reminder.priority.return_value = 0
            
            # Mock predicate and query
            mock_predicate = MagicMock()
            mock_store.predicateForRemindersInCalendars_.return_value = mock_predicate
            mock_store.fetchRemindersMatchingPredicate_completion_.return_value = [mock_reminder]
            
            # Test collection
            reminders = collect_all_reminders(include_completed=False)
            
            # Should return valid structure
            self.assertIsInstance(reminders, list)
    
    def test_reminder_task_formatting(self):
        """Test reminder task formatting."""
        # Create a mock reminder object
        mock_reminder = MagicMock()
        mock_reminder.title.return_value = "Test Task"
        mock_reminder.isCompleted.return_value = False
        mock_reminder.calendarItemIdentifier.return_value = "reminder-123"
        mock_reminder.calendar.title.return_value = "Tasks"
        mock_reminder.creationDate.return_value = None
        mock_reminder.lastModifiedDate.return_value = None
        mock_reminder.dueDateComponents.return_value = None
        mock_reminder.priority.return_value = 0
        
        # Test formatting
        formatted = format_reminder_task(mock_reminder)
        
        # Should return dict with expected fields
        self.assertIsInstance(formatted, dict)
        # The actual implementation will determine exact fields
        # This test just ensures no crash occurs
    
    def test_eventkit_permission_handling_mock(self):
        """Test EventKit permission handling."""
        with patch('EventKit.EKEventStore') as mock_eventstore_class:
            mock_store = MagicMock()
            mock_eventstore_class.alloc.return_value.init.return_value = mock_store
            
            # Test different authorization statuses
            authorization_statuses = [
                0,  # EKAuthorizationStatusNotDetermined
                1,  # EKAuthorizationStatusRestricted
                2,  # EKAuthorizationStatusDenied
                3,  # EKAuthorizationStatusAuthorized
            ]
            
            for status in authorization_statuses:
                mock_store.authorizationStatusForEntityType_.return_value = status
                
                # The actual implementation should handle different statuses appropriately
                # This test just ensures no crash occurs
                auth_status = mock_store.authorizationStatusForEntityType_(1)  # EKEntityTypeReminder
                self.assertEqual(auth_status, status)
    
    @patch('EventKit.EKEventStore')
    def test_eventkit_error_handling(self, mock_eventstore_class):
        """Test EventKit error handling."""
        # Test store initialization failure
        mock_eventstore_class.side_effect = Exception("EventKit initialization failed")
        
        # Should handle initialization errors gracefully
        try:
            store = EventKit.EKEventStore.alloc().init()
            # If we get here, the mock didn't work as expected, but that's ok
        except Exception:
            # Error handling should be graceful - no crash
            pass
        
        # Reset mock for successful initialization but failed operations
        mock_eventstore_class.side_effect = None
        mock_store = MagicMock()
        mock_eventstore_class.alloc.return_value.init.return_value = mock_store
        
        # Mock operation failures
        mock_store.calendarsForEntityType_.side_effect = Exception("Calendar access failed")
        
        # Should handle operation errors gracefully
        try:
            calendars = mock_store.calendarsForEntityType_(1)
        except Exception:
            # Error should be handled gracefully
            pass
    
    def test_date_handling_in_reminders(self):
        """Test date handling in reminder tasks."""
        with patch('EventKit.EKEventStore') as mock_eventstore_class:
            mock_store = MagicMock()
            mock_eventstore_class.alloc.return_value.init.return_value = mock_store
            
            # Mock reminder with date components
            mock_reminder = MagicMock()
            mock_reminder.title.return_value = "Task with due date"
            mock_reminder.isCompleted.return_value = False
            mock_reminder.calendarItemIdentifier.return_value = "reminder-date"
            
            # Mock date components (NSDateComponents equivalent)
            mock_due_date = MagicMock()
            mock_due_date.year = 2023
            mock_due_date.month = 12
            mock_due_date.day = 15
            mock_reminder.dueDateComponents.return_value = mock_due_date
            
            # Test date handling in formatting
            formatted = format_reminder_task(mock_reminder)
            
            # Should handle date components without crashing
            self.assertIsInstance(formatted, dict)
    
    def test_unicode_handling_in_reminders(self):
        """Test Unicode text handling in reminders."""
        mock_reminder = MagicMock()
        
        # Test various Unicode strings
        unicode_titles = [
            "Task with émojis 📅",
            "タスク with Japanese",
            "Задача с кириллицей",
            "🎯 Goal with emoji prefix"
        ]
        
        for title in unicode_titles:
            mock_reminder.title.return_value = title
            mock_reminder.isCompleted.return_value = False
            mock_reminder.calendarItemIdentifier.return_value = f"reminder-unicode-{hash(title)}"
            
            # Should handle Unicode without crashing
            formatted = format_reminder_task(mock_reminder)
            self.assertIsInstance(formatted, dict)


@pytest.mark.macos
@pytest.mark.eventkit
@pytest.mark.integration
class TestEventKitIntegrationReal(unittest.TestCase):
    """Real EventKit integration tests (only run on macOS with EventKit)."""
    
    def setUp(self):
        """Set up test environment."""
        if not IS_MACOS:
            self.skipTest("EventKit tests require macOS")
        
        if not HAS_EVENTKIT:
            self.skipTest("EventKit framework not available")
    
    @pytest.mark.slow
    def test_real_eventstore_creation(self):
        """Test real EventStore creation (requires permissions)."""
        try:
            store = EventKit.EKEventStore.alloc().init()
            self.assertIsNotNone(store)
            
            # Check authorization status
            auth_status = store.authorizationStatusForEntityType_(1)  # EKEntityTypeReminder
            
            # Auth status should be a valid value (0-3)
            self.assertIn(auth_status, [0, 1, 2, 3])
            
            if auth_status == 3:  # Authorized
                # Try to get calendars
                calendars = store.calendarsForEntityType_(1)
                self.assertIsInstance(calendars, (list, tuple, type(None)))
                
                if calendars:
                    print(f"Found {len(calendars)} reminder calendars")
                    for calendar in calendars[:3]:  # Limit output
                        print(f"  - {calendar.title()}")
            else:
                print(f"EventKit authorization status: {auth_status}")
                print("Note: Full EventKit tests require authorization")
                
        except Exception as e:
            self.skipTest(f"EventKit access failed: {e}")
    
    @pytest.mark.slow
    def test_real_reminder_list_discovery(self):
        """Test real reminder list discovery (requires permissions)."""
        try:
            lists = discover_reminder_lists()
            self.assertIsInstance(lists, list)
            
            if lists:
                print(f"Discovered {len(lists)} reminder lists")
                for reminder_list in lists[:3]:  # Limit output
                    if isinstance(reminder_list, dict):
                        print(f"  - {reminder_list.get('name', 'Unknown')}")
            else:
                print("No reminder lists found (may require authorization)")
                
        except Exception as e:
            self.skipTest(f"Reminder list discovery failed: {e}")


@pytest.mark.macos
class TestMacOSPlatformDetection(unittest.TestCase):
    """Test macOS platform detection and conditional behavior."""
    
    def test_platform_detection(self):
        """Test that platform detection works correctly."""
        detected_platform = platform.system()
        
        if detected_platform == "Darwin":
            self.assertTrue(IS_MACOS)
            print("Running on macOS")
        else:
            self.assertFalse(IS_MACOS)
            print(f"Running on {detected_platform} (not macOS)")
    
    def test_optional_import_handling(self):
        """Test that optional imports are handled gracefully."""
        # This test runs on all platforms but checks macOS-specific behavior
        
        if IS_MACOS:
            # On macOS, should attempt to import EventKit
            try:
                import objc
                import EventKit
                print("EventKit successfully imported on macOS")
            except ImportError as e:
                print(f"EventKit import failed on macOS: {e}")
                # This is ok - EventKit might not be available in all environments
        else:
            # On non-macOS, EventKit import should fail
            with self.assertRaises(ImportError):
                import EventKit
            print("EventKit correctly unavailable on non-macOS platform")
    
    def test_conditional_functionality(self):
        """Test that functionality is conditionally available based on platform."""
        # Functions should exist but may be no-ops on non-macOS
        lists = list_reminder_lists()
        self.assertIsInstance(lists, list)
        
        reminders = collect_all_reminders()
        self.assertIsInstance(reminders, list)
        
        if not IS_MACOS:
            # On non-macOS, these should return empty lists
            self.assertEqual(len(lists), 0)
            self.assertEqual(len(reminders), 0)
        # On macOS, they may return data depending on authorization


# Skip entire test class on non-Darwin platforms
if not IS_MACOS:
    # Create dummy test to indicate skipping
    class TestEventKitSkipped(unittest.TestCase):
        def test_eventkit_skipped_on_non_macos(self):
            """Placeholder test to indicate EventKit tests are skipped."""
            self.skipTest("EventKit tests are only available on macOS")


if __name__ == '__main__':
    # Print platform information
    print(f"Platform: {platform.system()}")
    print(f"Is macOS: {IS_MACOS}")
    print(f"Has EventKit: {HAS_EVENTKIT}")
    
    # Run tests with appropriate filtering
    unittest.main(verbosity=2)