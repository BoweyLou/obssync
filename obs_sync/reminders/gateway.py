"""Simplified Apple Reminders gateway using EventKit."""

import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import logging

from obs_sync.core.exceptions import (
    RemindersError,
    AuthorizationError,
    EventKitImportError
)
from obs_sync.utils.tags import decode_tags_from_notes, encode_tags_in_notes


@dataclass
class ReminderData:
    """Simplified reminder data structure."""
    uuid: str
    title: str
    completed: bool
    due_date: Optional[str] = None
    priority: Optional[str] = None
    notes: Optional[str] = None
    tags: List[str] = field(default_factory=list)  # Added tags field
    list_id: Optional[str] = None
    list_name: Optional[str] = None
    created_at: Optional[str] = None
    modified_at: Optional[str] = None


class RemindersGateway:
    """Simplified gateway for Apple Reminders via EventKit."""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self._store = None
        self._authorized = False
        
    def _ensure_eventkit(self):
        """Import and initialize EventKit with specific error handling."""
        try:
            import objc
            from EventKit import (
                EKEventStore, EKEntityTypeReminder,
                EKAuthorizationStatusAuthorized
            )
            from Foundation import NSRunLoop, NSDate

            self._EKEventStore = EKEventStore
            self._EKEntityTypeReminder = EKEntityTypeReminder
            self._EKAuthorizationStatusAuthorized = EKAuthorizationStatusAuthorized
            self._NSRunLoop = NSRunLoop
            self._NSDate = NSDate

        except ImportError as e:
            # Provide specific, actionable error message for import failures
            self.logger.error(f"EventKit import failed: {e}")
            raise EventKitImportError(
                "EventKit not available. Please install PyObjC framework:\n"
                "  pip install pyobjc pyobjc-framework-EventKit\n"
                f"Import error details: {e}"
            )
        except Exception as e:
            # Catch any other unexpected errors during import
            self.logger.error(f"Unexpected error importing EventKit: {e}")
            raise EventKitImportError(
                f"Failed to import EventKit framework: {e}\n"
                "This may indicate a corrupted PyObjC installation."
            )
    
    def _get_store(self):
        """Get or create EventKit store with detailed error reporting."""
        if self._store:
            return self._store

        # Ensure EventKit is available (will raise EventKitImportError if not)
        self._ensure_eventkit()

        # Create EventKit store
        try:
            self._store = self._EKEventStore.alloc().init()
            self.logger.debug("EventKit store created successfully")
        except Exception as e:
            self.logger.error(f"Failed to create EventKit store: {e}")
            raise RemindersError(
                f"Failed to initialize EventKit store: {e}\n"
                "This may indicate a system-level EventKit issue."
            )

        # Check current authorization status
        try:
            status = self._EKEventStore.authorizationStatusForEntityType_(
                self._EKEntityTypeReminder
            )
            status_int = int(status)
            authorized_int = int(self._EKAuthorizationStatusAuthorized)

            if status_int == authorized_int:
                self.logger.debug("EventKit already authorized for reminders")
                self._authorized = True
                return self._store

            # Map status codes to meaningful messages
            status_messages = {
                0: "Not Determined - Authorization has not been requested yet",
                1: "Restricted - System policy prevents access to reminders",
                2: "Denied - User has explicitly denied access to reminders",
                3: "Authorized - Access is granted"
            }

            current_status_msg = status_messages.get(status_int, f"Unknown status: {status_int}")
            self.logger.info(f"Current authorization status: {current_status_msg}")

            # If explicitly denied or restricted, fail fast
            if status_int == 1:  # Restricted
                raise AuthorizationError(
                    "Access to Reminders is restricted by system policy.\n"
                    "This may be due to parental controls or device management profiles."
                )
            elif status_int == 2:  # Denied
                raise AuthorizationError(
                    "Access to Reminders was previously denied.\n"
                    "To fix this:\n"
                    "  1. Open System Preferences > Security & Privacy > Privacy\n"
                    "  2. Select 'Reminders' from the left sidebar\n"
                    "  3. Check the box next to this application\n"
                    "  4. Restart the application"
                )

        except (AuthorizationError, RemindersError):
            raise
        except Exception as e:
            self.logger.error(f"Failed to check authorization status: {e}")
            raise RemindersError(f"Failed to check EventKit authorization status: {e}")

        # Request authorization if needed
        self.logger.info("Requesting EventKit authorization for reminders...")
        done = threading.Event()
        result = {'granted': False, 'error': None}

        def completion(granted, error):
            result['granted'] = granted
            result['error'] = error
            done.set()

        try:
            self._store.requestAccessToEntityType_completion_(
                self._EKEntityTypeReminder, completion
            )

            # Wait for authorization with timeout
            timeout_seconds = 30
            start_time = time.time()

            while not done.is_set():
                if time.time() - start_time > timeout_seconds:
                    raise AuthorizationError(
                        f"Authorization request timed out after {timeout_seconds} seconds.\n"
                        "The system may be showing an authorization dialog.\n"
                        "Please check for any system prompts and try again."
                    )

                # Run the event loop briefly
                self._NSRunLoop.currentRunLoop().runUntilDate_(
                    self._NSDate.dateWithTimeIntervalSinceNow_(0.1)
                )

            # Check the authorization result
            if not result['granted']:
                error_msg = "User denied access to Reminders"
                if result['error']:
                    try:
                        # Try to extract error details
                        error_desc = str(result['error'])
                        if hasattr(result['error'], 'localizedDescription'):
                            error_desc = result['error'].localizedDescription()
                        error_msg = f"{error_msg}: {error_desc}"
                    except:
                        pass

                raise AuthorizationError(
                    f"{error_msg}\n"
                    "To grant access:\n"
                    "  1. When prompted, click 'OK' to allow access\n"
                    "  2. Or go to System Preferences > Security & Privacy > Privacy > Reminders\n"
                    "  3. Enable access for this application"
                )

            # Verify final authorization status
            final_status = self._EKEventStore.authorizationStatusForEntityType_(
                self._EKEntityTypeReminder
            )
            if int(final_status) != int(self._EKAuthorizationStatusAuthorized):
                raise AuthorizationError(
                    "Authorization was granted but final status check failed.\n"
                    "This may indicate a system-level issue with EventKit.\n"
                    "Try restarting the application or rebooting your system."
                )

            self._authorized = True
            self.logger.info("EventKit authorization granted successfully")

        except (AuthorizationError, RemindersError):
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error during authorization: {e}")
            raise AuthorizationError(
                f"Failed to request EventKit authorization: {e}\n"
                "This may indicate a problem with the EventKit framework."
            )

        return self._store
    
    def get_lists(self) -> List[Dict[str, str]]:
        """Get all reminder lists."""
        try:
            store = self._get_store()
        except (EventKitImportError, AuthorizationError, RemindersError) as e:
            # Propagate specific exceptions with context
            self.logger.error(f"Failed to get store for lists: {e}")
            raise

        try:
            calendars = store.calendarsForEntityType_(self._EKEntityTypeReminder) or []

            lists = []
            for cal in calendars:
                lists.append({
                    'id': str(cal.calendarIdentifier()),
                    'name': str(cal.title() or 'Untitled'),
                })

            return lists

        except Exception as e:
            self.logger.error(f"Failed to fetch reminder lists: {e}")
            raise RemindersError(
                f"Failed to retrieve reminder lists: {e}\n"
                "The EventKit store may be in an invalid state."
            )
    
    def get_reminders(self, list_ids: Optional[List[str]] = None) -> List[ReminderData]:
        """Get reminders from specified lists."""
        try:
            store = self._get_store()
        except (EventKitImportError, AuthorizationError, RemindersError) as e:
            self.logger.error(f"Failed to get store for reminders: {e}")
            raise

        # Get calendars
        try:
            all_cals = store.calendarsForEntityType_(self._EKEntityTypeReminder) or []
            if list_ids:
                calendars = [c for c in all_cals if str(c.calendarIdentifier()) in list_ids]
            else:
                calendars = all_cals

            if not calendars:
                self.logger.warning(f"No calendars found for list_ids: {list_ids}")
                return []

            # Create predicate
            predicate = store.predicateForRemindersInCalendars_(calendars)

        except Exception as e:
            self.logger.error(f"Failed to create reminders predicate: {e}")
            raise RemindersError(
                f"Failed to prepare reminder fetch: {e}\n"
                "The specified lists may not exist or be accessible."
            )

        # Fetch reminders
        reminders = []
        done = threading.Event()

        def completion(fetched_reminders):
            if fetched_reminders:
                reminders.extend(list(fetched_reminders))
            done.set()

        try:
            store.fetchRemindersMatchingPredicate_completion_(predicate, completion)

            # Wait for completion with timeout and better progress indication
            timeout_seconds = 30
            start_time = time.time()

            while not done.is_set():
                elapsed = time.time() - start_time
                if elapsed > timeout_seconds:
                    raise RemindersError(
                        f"Reminder fetch timed out after {timeout_seconds} seconds.\n"
                        "This may indicate:\n"
                        "  - A large number of reminders causing slow retrieval\n"
                        "  - EventKit framework issues\n"
                        "  - System resource constraints\n"
                        "Try reducing the number of lists being synced."
                    )

                self._NSRunLoop.currentRunLoop().runUntilDate_(
                    self._NSDate.dateWithTimeIntervalSinceNow_(0.1)
                )

        except RemindersError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to fetch reminders: {e}")
            raise RemindersError(
                f"Failed to fetch reminders: {e}\n"
                "The EventKit fetch operation encountered an unexpected error."
            )
        
        # Convert to ReminderData
        result = []
        for rem in reminders:
            try:
                # Extract data
                uuid = str(rem.calendarItemIdentifier())
                title = str(rem.title() or '')
                completed = bool(rem.isCompleted())
                
                # Due date
                due_date = None
                due_components = rem.dueDateComponents()
                if due_components:
                    try:
                        year = due_components.year()
                        month = due_components.month()
                        day = due_components.day()
                        if year and month and day:
                            due_date = f"{year:04d}-{month:02d}-{day:02d}"
                    except:
                        pass
                
                # Priority
                priority = None
                try:
                    prio_num = int(rem.priority())
                    if prio_num == 0:
                        priority = None  # No priority set
                    elif prio_num == 1:
                        priority = "high"
                    elif prio_num <= 5:
                        priority = "medium"
                    elif prio_num >= 9:
                        priority = "low"
                except:
                    pass
                
                # Notes and Tags
                notes = None
                tags = []
                try:
                    if rem.notes():
                        raw_notes = str(rem.notes())
                        # Decode tags from notes field
                        notes, tags = decode_tags_from_notes(raw_notes)
                except:
                    pass
                
                # List info
                list_id = None
                list_name = None
                try:
                    cal = rem.calendar()
                    if cal:
                        list_id = str(cal.calendarIdentifier())
                        list_name = str(cal.title() or 'Untitled')
                except:
                    pass
                
                # Timestamps
                created_at = None
                modified_at = None
                try:
                    if rem.creationDate():
                        created_at = datetime.fromtimestamp(
                            rem.creationDate().timeIntervalSince1970(),
                            tz=timezone.utc
                        ).isoformat()
                except:
                    pass
                
                try:
                    if rem.lastModifiedDate():
                        modified_at = datetime.fromtimestamp(
                            rem.lastModifiedDate().timeIntervalSince1970(),
                            tz=timezone.utc
                        ).isoformat()
                except:
                    pass
                
                result.append(ReminderData(
                    uuid=uuid,
                    title=title,
                    completed=completed,
                    due_date=due_date,
                    priority=priority,
                    notes=notes,
                    tags=tags,  # Include decoded tags
                    list_id=list_id,
                    list_name=list_name,
                    created_at=created_at,
                    modified_at=modified_at
                ))
                
            except Exception as e:
                self.logger.warning(f"Failed to process reminder: {e}")
                continue
        
        return result
    
    def create_reminder(self, title: str, list_id: Optional[str] = None,
                       **properties) -> Optional[str]:
        """Create a new reminder."""
        try:
            from EventKit import EKReminder
            from Foundation import NSDateComponents
            
            store = self._get_store()
            reminder = EKReminder.reminderWithEventStore_(store)
            reminder.setTitle_(title)
            
            # Set calendar/list
            calendar_set = False
            if list_id:
                all_cals = store.calendarsForEntityType_(self._EKEntityTypeReminder) or []
                self.logger.debug(f"Looking for calendar with ID: {list_id}")
                self.logger.debug(f"Available calendars: {[(cal.title(), str(cal.calendarIdentifier())) for cal in all_cals]}")
                for cal in all_cals:
                    if str(cal.calendarIdentifier()) == list_id:
                        reminder.setCalendar_(cal)
                        calendar_set = True
                        self.logger.debug(f"Set calendar to: {cal.title()}")
                        break
                
                if not calendar_set:
                    self.logger.error(f"Calendar with ID '{list_id}' not found among available calendars")
                    return None
            else:
                self.logger.warning("No list_id provided, will use default calendar")
            
            # Set properties
            if properties.get('due_date'):
                try:
                    parts = properties['due_date'].split('-')
                    if len(parts) == 3:
                        components = NSDateComponents.alloc().init()
                        components.setYear_(int(parts[0]))
                        components.setMonth_(int(parts[1]))
                        components.setDay_(int(parts[2]))
                        reminder.setDueDateComponents_(components)
                except:
                    pass
            
            if properties.get('priority'):
                priority_map = {'high': 1, 'medium': 5, 'low': 9}
                reminder.setPriority_(priority_map.get(properties['priority'], 0))
            
            # Handle notes and tags
            notes = properties.get('notes')
            tags = properties.get('tags', [])
            encoded_notes = encode_tags_in_notes(notes, tags)
            if encoded_notes:
                reminder.setNotes_(encoded_notes)
            
            # Save
            success, error = store.saveReminder_commit_error_(reminder, True, None)
            self.logger.debug(f"saveReminder result: success={success}, error={error}")
            if success:
                uuid_result = str(reminder.calendarItemIdentifier())
                self.logger.debug(f"Created reminder with UUID: {uuid_result}")
                return uuid_result
            else:
                self.logger.error(f"Failed to save reminder '{title}': error={error}")
            
        except Exception as e:
            self.logger.error(f"Failed to create reminder '{title}': {e}")
            import traceback
            self.logger.debug(traceback.format_exc())
        
        return None
    
    def update_reminder(self, uuid: str, **updates) -> bool:
        """Update an existing reminder."""
        try:
            from Foundation import NSDateComponents
            
            store = self._get_store()
            
            # Find the reminder
            all_cals = store.calendarsForEntityType_(self._EKEntityTypeReminder) or []
            predicate = store.predicateForRemindersInCalendars_(all_cals)
            
            reminders = []
            done = threading.Event()
            
            def completion(fetched):
                if fetched:
                    reminders.extend(list(fetched))
                done.set()
            
            store.fetchRemindersMatchingPredicate_completion_(predicate, completion)
            
            deadline = time.time() + 10
            while not done.is_set() and time.time() < deadline:
                self._NSRunLoop.currentRunLoop().runUntilDate_(
                    self._NSDate.dateWithTimeIntervalSinceNow_(0.1)
                )
            
            # Find our reminder
            reminder = None
            for rem in reminders:
                if str(rem.calendarItemIdentifier()) == uuid:
                    reminder = rem
                    break
            
            if not reminder:
                return False
            
            # Apply updates
            if 'title' in updates:
                reminder.setTitle_(updates['title'])
            
            if 'completed' in updates:
                reminder.setCompleted_(bool(updates['completed']))
            
            if 'due_date' in updates:
                if updates['due_date']:
                    parts = updates['due_date'].split('-')
                    if len(parts) == 3:
                        components = NSDateComponents.alloc().init()
                        components.setYear_(int(parts[0]))
                        components.setMonth_(int(parts[1]))
                        components.setDay_(int(parts[2]))
                        reminder.setDueDateComponents_(components)
                else:
                    reminder.setDueDateComponents_(None)
            
            if 'priority' in updates:
                priority_map = {'high': 1, 'medium': 5, 'low': 9}
                reminder.setPriority_(priority_map.get(updates['priority'], 0))
            
            # Handle calendar/list change
            if 'calendar_id' in updates:
                new_calendar_id = updates['calendar_id']
                if new_calendar_id:
                    all_cals = store.calendarsForEntityType_(self._EKEntityTypeReminder) or []
                    for cal in all_cals:
                        if str(cal.calendarIdentifier()) == new_calendar_id:
                            reminder.setCalendar_(cal)
                            break
            
            # Handle notes and tags updates
            if 'notes' in updates or 'tags' in updates:
                # Get current notes and tags if we're only updating one
                current_notes = None
                current_tags = []
                if reminder.notes():
                    current_notes, current_tags = decode_tags_from_notes(str(reminder.notes()))
                
                # Use updated values or keep current ones
                new_notes = updates.get('notes', current_notes)
                new_tags = updates.get('tags', current_tags)
                
                # Encode and set
                encoded_notes = encode_tags_in_notes(new_notes, new_tags)
                reminder.setNotes_(encoded_notes if encoded_notes else None)
            
            # Save
            success, error = store.saveReminder_commit_error_(reminder, True, None)
            return bool(success)
            
        except Exception as e:
            self.logger.error(f"Failed to update reminder: {e}")
            return False
    
    def delete_reminder(self, uuid: str) -> bool:
        """Delete a reminder."""
        try:
            store = self._get_store()
            
            # Find the reminder (similar to update)
            all_cals = store.calendarsForEntityType_(self._EKEntityTypeReminder) or []
            predicate = store.predicateForRemindersInCalendars_(all_cals)
            
            reminders = []
            done = threading.Event()
            
            def completion(fetched):
                if fetched:
                    reminders.extend(list(fetched))
                done.set()
            
            store.fetchRemindersMatchingPredicate_completion_(predicate, completion)
            
            deadline = time.time() + 10
            while not done.is_set() and time.time() < deadline:
                self._NSRunLoop.currentRunLoop().runUntilDate_(
                    self._NSDate.dateWithTimeIntervalSinceNow_(0.1)
                )
            
            # Find and delete
            for rem in reminders:
                if str(rem.calendarItemIdentifier()) == uuid:
                    success, error = store.removeReminder_commit_error_(rem, True, None)
                    return bool(success)
            
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to delete reminder: {e}")
            return False