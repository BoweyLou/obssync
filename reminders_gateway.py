#!/usr/bin/env python3
"""
Apple Reminders Gateway - Unified EventKit boundary for all Reminders operations.

This module provides a single, consistent interface for all Apple Reminders access,
eliminating code duplication and providing standardized error handling across
the entire task sync system.

Key responsibilities:
- One-time EventKit store initialization and authorization
- Unified error handling with detailed diagnostics
- Fetch operations with filtering and caching
- Update operations with dry-run support
- Thread-safe EventKit operations with proper lifecycle management

Usage:
    gateway = RemindersGateway()
    
    # Fetch operations
    lists = gateway.get_reminder_lists()
    reminders = gateway.get_reminders_from_lists(lists)
    
    # Update operations
    success = gateway.update_reminder(reminder_dict, changes, dry_run=False)
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass


class RemindersError(Exception):
    """Base exception for all Reminders Gateway errors."""
    pass


class AuthorizationError(RemindersError):
    """Raised when EventKit authorization fails or is denied."""
    pass


class EventKitImportError(RemindersError):
    """Raised when EventKit/PyObjC dependencies are not available."""
    pass


class ReminderNotFoundError(RemindersError):
    """Raised when a specific reminder cannot be found."""
    pass


class SaveError(RemindersError):
    """Raised when saving reminder changes fails."""
    pass


class AuthorizationStatus(Enum):
    """EventKit authorization status enumeration."""
    NOT_DETERMINED = 0
    RESTRICTED = 1
    DENIED = 2
    AUTHORIZED = 3


@dataclass
class ReminderChange:
    """Represents a change to be applied to a reminder."""
    field: str
    old_value: Any
    new_value: Any


@dataclass
class UpdateResult:
    """Result of an update operation."""
    success: bool
    changes_applied: List[ReminderChange]
    errors: List[str]
    reminder_id: Optional[str] = None


@dataclass
class GatewayStats:
    """Statistics for gateway operations."""
    store_initializations: int = 0
    authorization_requests: int = 0
    authorization_successes: int = 0
    authorization_failures: int = 0
    fetch_operations: int = 0
    update_operations: int = 0
    save_successes: int = 0
    save_failures: int = 0
    errors_by_type: Dict[str, int] = None
    
    def __post_init__(self):
        if self.errors_by_type is None:
            self.errors_by_type = {}


class RemindersGateway:
    """
    Unified gateway for all Apple Reminders operations via EventKit.
    
    Provides thread-safe, cached access to EventKit with comprehensive
    error handling and logging. Supports dry-run operations for testing.
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None, timeout: int = 30):
        """
        Initialize the Reminders Gateway.
        
        Args:
            logger: Optional logger for operation tracking
            timeout: Timeout in seconds for EventKit operations
        """
        self.logger = logger or logging.getLogger(__name__)
        self.timeout = timeout
        self.stats = GatewayStats()
        self._lock = threading.Lock()
        self._store = None
        self._calendars_cache = None
        self._reminders_cache: Dict[str, List] = {}
        self._cache_timestamp = None
        self._cache_ttl = 300  # 5 minutes
        
        # EventKit classes (will be set on first use)
        self._eventkit_available = None
        self._EKEventStore = None
        self._EKEntityTypeReminder = None
        self._EKAuthorizationStatusAuthorized = None
        self._NSRunLoop = None
        self._NSDate = None
        self._NSCalendar = None
        self._NSDateComponents = None
    
    def _ensure_eventkit_imports(self) -> None:
        """Ensure EventKit is imported and available."""
        if self._eventkit_available is not None:
            return
            
        try:
            # Import EventKit and Foundation frameworks
            from EventKit import (
                EKEventStore, EKEntityTypeReminder, EKAuthorizationStatusAuthorized
            )
            from Foundation import NSRunLoop, NSDate, NSCalendar, NSDateComponents
            
            # Store classes for later use
            self._EKEventStore = EKEventStore
            self._EKEntityTypeReminder = EKEntityTypeReminder
            self._EKAuthorizationStatusAuthorized = EKAuthorizationStatusAuthorized
            self._NSRunLoop = NSRunLoop
            self._NSDate = NSDate
            self._NSCalendar = NSCalendar
            self._NSDateComponents = NSDateComponents
            
            self._eventkit_available = True
            self.logger.debug("EventKit imported successfully")
            
        except ImportError as e:
            self._eventkit_available = False
            self.stats.errors_by_type['import_error'] = self.stats.errors_by_type.get('import_error', 0) + 1
            raise EventKitImportError(
                f"EventKit not available. Please install PyObjC framework: "
                f"pip install pyobjc pyobjc-framework-EventKit. Error: {e}"
            ) from e
        except Exception as e:
            self._eventkit_available = False
            self.stats.errors_by_type['import_error'] = self.stats.errors_by_type.get('import_error', 0) + 1
            raise EventKitImportError(f"Failed to import EventKit: {e}") from e
    
    def _get_store(self) -> Any:
        """Get or create the EventKit store with proper authorization."""
        with self._lock:
            if self._store is not None:
                return self._store
                
            self._ensure_eventkit_imports()
            
            # Create EventKit store
            try:
                self._store = self._EKEventStore.alloc().init()
                self.stats.store_initializations += 1
                self.logger.debug("EventKit store created")
            except Exception as e:
                self.stats.errors_by_type['store_creation'] = self.stats.errors_by_type.get('store_creation', 0) + 1
                raise RemindersError(f"Failed to create EventKit store: {e}") from e
            
            # Check authorization status
            status = self._EKEventStore.authorizationStatusForEntityType_(self._EKEntityTypeReminder)
            if int(status) == int(self._EKAuthorizationStatusAuthorized):
                self.logger.debug("EventKit already authorized")
                return self._store
            
            # Request authorization
            self.logger.info("Requesting EventKit authorization for reminders...")
            self.stats.authorization_requests += 1
            
            done_auth = threading.Event()
            auth_result = {'granted': False, 'error': None}
            
            def completion_auth(granted, error):
                auth_result['granted'] = granted
                auth_result['error'] = error
                done_auth.set()
            
            try:
                self._store.requestAccessToEntityType_completion_(
                    self._EKEntityTypeReminder, completion_auth
                )
                
                # Wait for authorization with timeout
                deadline = time.time() + self.timeout
                while not done_auth.is_set() and time.time() < deadline:
                    self._NSRunLoop.currentRunLoop().runUntilDate_(
                        self._NSDate.dateWithTimeIntervalSinceNow_(0.1)
                    )
                
                if not done_auth.is_set():
                    self.stats.authorization_failures += 1
                    self.stats.errors_by_type['auth_timeout'] = self.stats.errors_by_type.get('auth_timeout', 0) + 1
                    raise AuthorizationError(
                        f"EventKit authorization request timed out after {self.timeout} seconds. "
                        "Please check System Preferences > Security & Privacy > Privacy > Reminders"
                    )
                
                # Check final authorization status
                final_status = self._EKEventStore.authorizationStatusForEntityType_(self._EKEntityTypeReminder)
                if int(final_status) != int(self._EKAuthorizationStatusAuthorized):
                    self.stats.authorization_failures += 1
                    self.stats.errors_by_type['auth_denied'] = self.stats.errors_by_type.get('auth_denied', 0) + 1
                    error_details = f"(granted: {auth_result['granted']}, error: {auth_result['error']})" if auth_result['error'] else f"(granted: {auth_result['granted']})"
                    raise AuthorizationError(
                        f"EventKit authorization denied for reminders. "
                        f"Final status: {final_status} {error_details}. "
                        "Please enable access in System Preferences > Security & Privacy > Privacy > Reminders"
                    )
                
                self.stats.authorization_successes += 1
                self.logger.info("EventKit authorization granted successfully")
                
            except Exception as e:
                if isinstance(e, AuthorizationError):
                    raise
                self.stats.authorization_failures += 1
                self.stats.errors_by_type['auth_error'] = self.stats.errors_by_type.get('auth_error', 0) + 1
                raise AuthorizationError(f"EventKit authorization failed: {e}") from e
            
            return self._store
    
    def _is_cache_valid(self) -> bool:
        """Check if the current cache is still valid."""
        if self._cache_timestamp is None:
            return False
        return time.time() - self._cache_timestamp < self._cache_ttl
    
    def _cache_calendar_info(self, reminder) -> Dict[str, Any]:
        """Extract and cache calendar information from a reminder."""
        try:
            cal = reminder.calendar()
            if cal is None:
                return {}
            
            cal_info = {
                "name": str(cal.title()) if cal.title() is not None else None,
                "identifier": str(cal.calendarIdentifier()),
                "source_name": None,
                "source_type": None,
                "color": None
            }
            
            try:
                src = cal.source()
                if src is not None:
                    cal_info["source_name"] = str(src.title()) if src.title() is not None else None
                    cal_info["source_type"] = str(int(src.sourceType()))
            except Exception:
                pass
                
            try:
                cal_info["color"] = self._nscolor_to_hex(cal.color())
            except Exception:
                pass
                
            return cal_info
        except Exception as e:
            self.logger.debug(f"Failed to cache calendar info: {e}")
            return {}
    
    def _nscolor_to_hex(self, color) -> Optional[str]:
        """Convert NSColor to hex string."""
        try:
            c = color.colorUsingColorSpaceName_("NSCalibratedRGBColorSpace")
            if c is None:
                return None
            r = int(round(c.redComponent() * 255))
            g = int(round(c.greenComponent() * 255))
            b = int(round(c.blueComponent() * 255))
            return f"#{r:02X}{g:02X}{b:02X}"
        except Exception:
            return None
    
    def get_reminder_lists(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Get all available reminder lists/calendars.
        
        Args:
            force_refresh: If True, bypass cache and fetch fresh data
            
        Returns:
            List of reminder lists with metadata
            
        Raises:
            RemindersError: If fetching lists fails
        """
        if not force_refresh and self._calendars_cache is not None and self._is_cache_valid():
            return self._calendars_cache
        
        try:
            store = self._get_store()
            calendars = store.calendarsForEntityType_(self._EKEntityTypeReminder) or []
            
            result = []
            for cal in calendars:
                try:
                    list_info = {
                        "name": str(cal.title()) if cal.title() is not None else "(unnamed)",
                        "identifier": str(cal.calendarIdentifier()),
                        "source_name": None,
                        "source_type": None,
                        "calendar_type": None,
                        "allows_modification": None,
                        "color": None,
                    }
                    
                    # Source info
                    try:
                        src = cal.source()
                        if src is not None:
                            list_info["source_name"] = str(src.title()) if src.title() is not None else None
                            source_type_num = int(src.sourceType())
                            source_type_map = {
                                0: "local", 1: "exchange", 2: "caldav", 
                                3: "mobileme", 4: "subscribed", 5: "birthdays"
                            }
                            list_info["source_type"] = source_type_map.get(source_type_num, str(source_type_num))
                    except Exception:
                        pass
                    
                    # Calendar type and modifiability
                    try:
                        cal_type_map = {0: "local", 1: "caldav", 2: "exchange", 3: "subscription", 4: "birthday"}
                        list_info["calendar_type"] = cal_type_map.get(int(cal.type()), str(int(cal.type())))
                    except Exception:
                        pass
                        
                    try:
                        list_info["allows_modification"] = bool(cal.allowsContentModifications())
                    except Exception:
                        pass
                    
                    # Color
                    try:
                        list_info["color"] = self._nscolor_to_hex(cal.color())
                    except Exception:
                        pass
                    
                    result.append(list_info)
                    
                except Exception as e:
                    self.logger.warning(f"Failed to process calendar: {e}")
                    continue
            
            # Cache the results
            self._calendars_cache = result
            self._cache_timestamp = time.time()
            self.stats.fetch_operations += 1
            
            self.logger.debug(f"Fetched {len(result)} reminder lists")
            return result
            
        except Exception as e:
            if isinstance(e, (RemindersError, AuthorizationError, ImportError)):
                raise
            self.stats.errors_by_type['fetch_lists'] = self.stats.errors_by_type.get('fetch_lists', 0) + 1
            raise RemindersError(f"Failed to fetch reminder lists: {e}") from e
    
    def get_reminders_from_lists(
        self, 
        list_configs: List[Dict[str, str]], 
        force_refresh: bool = False,
        date_start: Optional[datetime] = None,
        date_end: Optional[datetime] = None,
        completed_only: bool = False,
        incomplete_only: bool = False
    ) -> Tuple[List[Any], Dict[str, Dict[str, Any]]]:
        """
        Get reminders from specified lists with optional filtering.
        
        Args:
            list_configs: List configurations with 'identifier' keys
            force_refresh: If True, bypass cache and fetch fresh data
            date_start: Optional start date for filtering
            date_end: Optional end date for filtering
            completed_only: If True, only return completed reminders
            incomplete_only: If True, only return incomplete reminders
            
        Returns:
            Tuple of (reminders_list, calendar_info_cache)
            
        Raises:
            RemindersError: If fetching reminders fails
        """
        # Create cache key based on parameters
        cache_key = self._create_cache_key(list_configs, date_start, date_end, completed_only, incomplete_only)
        
        if not force_refresh and cache_key in self._reminders_cache and self._is_cache_valid():
            return self._reminders_cache[cache_key]
        
        try:
            store = self._get_store()
            
            # Resolve calendars by identifier
            wanted_ids = {str(config["identifier"]) for config in list_configs}
            all_cals = store.calendarsForEntityType_(self._EKEntityTypeReminder) or []
            calendars = [c for c in all_cals if str(c.calendarIdentifier()) in wanted_ids]
            
            if not calendars:
                self.logger.warning(f"No calendars found for identifiers: {wanted_ids}")
                return [], {}
            
            # Build predicates based on filtering options
            predicates = []
            
            if completed_only:
                try:
                    predicates.append(
                        store.predicateForCompletedRemindersWithCompletionDateStarting_ending_calendars_(
                            self._datetime_to_nsdate(date_start) if date_start else None,
                            self._datetime_to_nsdate(date_end) if date_end else None,
                            calendars
                        )
                    )
                except Exception:
                    pass
            elif incomplete_only:
                try:
                    predicates.append(
                        store.predicateForIncompleteRemindersWithDueDateStarting_ending_calendars_(
                            self._datetime_to_nsdate(date_start) if date_start else None,
                            self._datetime_to_nsdate(date_end) if date_end else None,
                            calendars
                        )
                    )
                except Exception:
                    pass
            else:
                # Generic predicate for all reminders
                try:
                    predicates.append(store.predicateForRemindersInCalendars_(calendars))
                except Exception:
                    pass
            
            # Fetch reminders asynchronously
            items_by_key = {}
            calendar_cache = {}
            
            for pred in [p for p in predicates if p is not None]:
                done = threading.Event()
                
                def completion(reminders):
                    try:
                        for reminder in list(reminders or []):
                            # Cache calendar info immediately while available
                            key = self._key_for_reminder(reminder)
                            calendar_cache[key] = self._cache_calendar_info(reminder)
                            items_by_key[key] = reminder
                    finally:
                        done.set()
                
                store.fetchRemindersMatchingPredicate_completion_(pred, completion)
                deadline = time.time() + self.timeout
                while not done.is_set() and time.time() < deadline:
                    self._NSRunLoop.currentRunLoop().runUntilDate_(
                        self._NSDate.dateWithTimeIntervalSinceNow_(0.1)
                    )
                
                if not done.is_set():
                    raise RemindersError(f"Reminder fetch timed out after {self.timeout} seconds")
            
            reminders_list = list(items_by_key.values())
            result = (reminders_list, calendar_cache)
            
            # Cache the results
            self._reminders_cache[cache_key] = result
            self._cache_timestamp = time.time()
            self.stats.fetch_operations += 1
            
            self.logger.debug(f"Fetched {len(reminders_list)} reminders from {len(calendars)} calendars")
            return result
            
        except Exception as e:
            if isinstance(e, (RemindersError, AuthorizationError, ImportError)):
                raise
            self.stats.errors_by_type['fetch_reminders'] = self.stats.errors_by_type.get('fetch_reminders', 0) + 1
            raise RemindersError(f"Failed to fetch reminders: {e}") from e
    
    def find_reminder_by_id(self, item_id: str, calendar_id: Optional[str] = None) -> Optional[Any]:
        """
        Find a specific reminder by its identifier.
        
        Args:
            item_id: The reminder's calendar item identifier
            calendar_id: Optional calendar identifier to narrow search
            
        Returns:
            Reminder object if found, None otherwise
            
        Raises:
            RemindersError: If search operation fails
        """
        try:
            store = self._get_store()
            
            # Determine search scope
            if calendar_id:
                all_cals = store.calendarsForEntityType_(self._EKEntityTypeReminder) or []
                calendars = [c for c in all_cals if str(c.calendarIdentifier()) == calendar_id]
                if not calendars:
                    return None
            else:
                calendars = store.calendarsForEntityType_(self._EKEntityTypeReminder) or []
            
            # Search for the reminder
            predicate = store.predicateForRemindersInCalendars_(calendars)
            bucket = []
            done = threading.Event()
            
            def completion(reminders):
                try:
                    bucket.extend(list(reminders or []))
                finally:
                    done.set()
            
            store.fetchRemindersMatchingPredicate_completion_(predicate, completion)
            deadline = time.time() + self.timeout
            while not done.is_set() and time.time() < deadline:
                self._NSRunLoop.currentRunLoop().runUntilDate_(
                    self._NSDate.dateWithTimeIntervalSinceNow_(0.1)
                )
            
            # Find by ID
            for reminder in bucket:
                try:
                    if str(reminder.calendarItemIdentifier()) == item_id:
                        return reminder
                except Exception:
                    continue
            
            return None
            
        except Exception as e:
            if isinstance(e, (RemindersError, AuthorizationError, ImportError)):
                raise
            self.stats.errors_by_type['find_reminder'] = self.stats.errors_by_type.get('find_reminder', 0) + 1
            raise RemindersError(f"Failed to find reminder {item_id}: {e}") from e
    
    def update_reminder(
        self, 
        reminder_dict: Dict[str, Any], 
        fields: Dict[str, Any], 
        dry_run: bool = False
    ) -> UpdateResult:
        """
        Update a reminder with specified field changes.
        
        Args:
            reminder_dict: Dictionary with reminder metadata including external_ids
            fields: Dictionary of field updates (title_to_rem, status_to_rem, etc.)
            dry_run: If True, don't actually save changes
            
        Returns:
            UpdateResult with success status and applied changes
            
        Raises:
            ReminderNotFoundError: If reminder cannot be found
            RemindersError: If update operation fails
        """
        # Extract identifiers
        ids = reminder_dict.get("external_ids", {})
        item_id = ids.get("item")
        calendar_id = ids.get("calendar", "")
        
        if not item_id:
            raise ReminderNotFoundError("No item identifier provided for reminder update")
        
        # Find the reminder
        reminder = self.find_reminder_by_id(item_id, calendar_id if calendar_id else None)
        if not reminder:
            self.stats.errors_by_type['reminder_not_found'] = self.stats.errors_by_type.get('reminder_not_found', 0) + 1
            raise ReminderNotFoundError(f"Reminder with ID {item_id} not found")
        
        changes_applied = []
        errors = []
        
        try:
            # Title update
            if fields.get("title_to_rem"):
                title_value = fields.get("title_value") or reminder_dict.get("description", "")
                old_title = str(reminder.title() or "")
                if old_title != title_value:
                    changes_applied.append(ReminderChange("title", old_title, title_value))
                    if not dry_run:
                        reminder.setTitle_(title_value)
            
            # Status update
            if fields.get("status_to_rem"):
                new_status = reminder_dict.get("status") == "done"
                old_status = bool(reminder.isCompleted())
                if old_status != new_status:
                    status_str = "done" if new_status else "todo"
                    old_status_str = "done" if old_status else "todo"
                    changes_applied.append(ReminderChange("status", old_status_str, status_str))
                    if not dry_run:
                        reminder.setCompleted_(new_status)
            
            # Due date update
            if fields.get("due_to_rem"):
                due_date = reminder_dict.get("due")
                old_due = reminder.dueDateComponents()
                old_due_str = None
                if old_due:
                    try:
                        old_due_str = f"{old_due.year()}-{old_due.month():02d}-{old_due.day():02d}"
                    except Exception:
                        old_due_str = "invalid"
                
                new_due_str = due_date[:10] if due_date else None
                
                if old_due_str != new_due_str:
                    changes_applied.append(ReminderChange("due", old_due_str, new_due_str))
                    if not dry_run:
                        if due_date:
                            try:
                                y, m, d = map(int, due_date[:10].split("-"))
                                components = self._NSDateComponents.alloc().init()
                                components.setYear_(y)
                                components.setMonth_(m)
                                components.setDay_(d)
                                reminder.setDueDateComponents_(components)
                            except Exception as e:
                                errors.append(f"Due date update failed: {e}")
                        else:
                            reminder.setDueDateComponents_(None)
            
            # Priority update
            if fields.get("priority_to_rem"):
                priority = reminder_dict.get("priority")
                priority_map = {"high": 9, "medium": 5, "low": 1}
                new_priority_val = priority_map.get(priority, 0)
                
                old_priority_val = reminder.priority()
                old_priority = ("high" if old_priority_val >= 6 
                              else "medium" if old_priority_val == 5 
                              else "low" if old_priority_val >= 1 
                              else None)
                
                if old_priority != priority:
                    changes_applied.append(ReminderChange("priority", old_priority, priority))
                    if not dry_run:
                        reminder.setPriority_(new_priority_val)
            
            # Save changes if not dry run and changes were made
            if not dry_run and changes_applied:
                success = self._save_reminder(reminder)
                if not success:
                    return UpdateResult(False, changes_applied, ["Save operation failed"], item_id)
            
            self.stats.update_operations += 1
            return UpdateResult(True, changes_applied, errors, item_id)
            
        except Exception as e:
            self.stats.errors_by_type['update_error'] = self.stats.errors_by_type.get('update_error', 0) + 1
            return UpdateResult(False, changes_applied, [str(e)], item_id)
    
    def _save_reminder(self, reminder) -> bool:
        """
        Save reminder changes with proper error handling.
        
        Args:
            reminder: EventKit reminder object
            
        Returns:
            True if save successful, False otherwise
        """
        try:
            store = self._get_store()
            
            # PyObjC method signature handling for saveReminder:commit:error:
            result = store.saveReminder_commit_error_(reminder, True, None)
            
            # Handle different PyObjC return patterns
            if isinstance(result, tuple) and len(result) == 2:
                success, error = result
            elif isinstance(result, bool):
                success = result
                error = None
            else:
                success = bool(result)
                error = None
            
            if success and not error:
                self.stats.save_successes += 1
                return True
            else:
                self.stats.save_failures += 1
                error_msg = "Unknown save error"
                if error:
                    if hasattr(error, 'localizedDescription'):
                        error_msg = error.localizedDescription()
                    elif hasattr(error, 'description'):
                        error_msg = error.description()
                    else:
                        error_msg = str(error)
                
                self.logger.error(f"Reminder save failed: {error_msg}")
                return False
                
        except Exception as e:
            self.stats.save_failures += 1
            self.stats.errors_by_type['save_exception'] = self.stats.errors_by_type.get('save_exception', 0) + 1
            self.logger.error(f"Reminder save exception: {e}")
            return False
    
    def _create_cache_key(
        self, 
        list_configs: List[Dict[str, str]], 
        date_start: Optional[datetime],
        date_end: Optional[datetime], 
        completed_only: bool, 
        incomplete_only: bool
    ) -> str:
        """Create a cache key for reminder fetch parameters."""
        key_parts = [
            "|".join(sorted(config["identifier"] for config in list_configs)),
            str(date_start.isoformat() if date_start else ""),
            str(date_end.isoformat() if date_end else ""),
            str(completed_only),
            str(incomplete_only)
        ]
        return hashlib.sha256("|".join(key_parts).encode()).hexdigest()[:16]
    
    def _key_for_reminder(self, reminder) -> str:
        """Generate a stable key for a reminder object."""
        try:
            external_id = reminder.calendarItemExternalIdentifier()
            if external_id:
                return f"ext:{external_id}"
        except Exception:
            pass
            
        cal_id = ""
        try:
            cal = reminder.calendar()
            if cal is not None:
                cal_id = str(cal.calendarIdentifier())
        except Exception:
            pass
            
        try:
            item_id = str(reminder.calendarItemIdentifier())
        except Exception:
            item_id = ""
            
        return f"cid:{cal_id}|iid:{item_id}"
    
    def _datetime_to_nsdate(self, dt: datetime) -> Optional[Any]:
        """Convert Python datetime to NSDate."""
        if dt is None:
            return None
        try:
            epoch = dt.timestamp()
            return self._NSDate.dateWithTimeIntervalSince1970_(epoch)
        except Exception:
            return None
    
    def clear_cache(self) -> None:
        """Clear all cached data."""
        with self._lock:
            self._calendars_cache = None
            self._reminders_cache.clear()
            self._cache_timestamp = None
            self.logger.debug("Gateway cache cleared")
    
    def get_stats(self) -> GatewayStats:
        """Get current gateway statistics."""
        return self.stats
    
    def is_available(self) -> bool:
        """Check if EventKit is available without throwing exceptions."""
        try:
            self._ensure_eventkit_imports()
            return True
        except Exception:
            return False


# Convenience functions for backward compatibility

def to_iso_dt(nsdate) -> Optional[str]:
    """Convert NSDate to ISO string."""
    if nsdate is None:
        return None
    try:
        epoch = nsdate.timeIntervalSince1970()
        return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
    except Exception:
        return None


def components_to_iso(components) -> Optional[str]:
    """Convert NSDateComponents to ISO string."""
    if components is None:
        return None
    try:
        from Foundation import NSCalendar
        cal = NSCalendar.currentCalendar()
        dt = cal.dateFromComponents_(components)
        if dt is None:
            return None
        return to_iso_dt(dt)
    except Exception:
        # Fallback: attempt to compose manually
        try:
            y = components.year()
            m = components.month()
            d = components.day()
            if y and m and d:
                hh = components.hour() or 0
                mm = components.minute() or 0
                ss = components.second() or 0
                return datetime(y, m, d, hh, mm, ss, tzinfo=timezone.utc).isoformat()
        except Exception:
            pass
        return None


def reminder_priority_to_text(priority_num: int) -> Optional[str]:
    """Convert EventKit priority number to text."""
    try:
        num = int(priority_num)
    except Exception:
        return None
    if num == 0:
        return None
    if num <= 1:
        return "high"
    if num <= 5:
        return "medium"
    return "low"


def rrule_to_text(rule) -> Optional[str]:
    """Convert EventKit recurrence rule to text."""
    try:
        freq_map = {
            0: "daily", 1: "weekly", 2: "monthly", 3: "yearly",
            4: "hourly", 5: "minutely", 6: "secondly"
        }
        freq = freq_map.get(int(rule.frequency()), str(int(rule.frequency())))
        interval = int(rule.interval()) if rule.interval() else 1
        return f"every {interval} {freq}"
    except Exception:
        return None


def alarm_to_dict(alarm) -> dict:
    """Convert EventKit alarm to dictionary."""
    out = {}
    try:
        ad = alarm.absoluteDate()
        if ad is not None:
            out["absolute_date"] = to_iso_dt(ad)
    except Exception:
        pass
        
    try:
        ro = alarm.relativeOffset()
        if ro is not None:
            out["relative_offset_seconds"] = float(ro)
    except Exception:
        pass
        
    try:
        loc = alarm.structuredLocation()
        if loc is not None:
            try:
                out["location_title"] = str(loc.title())
            except Exception:
                pass
            try:
                geo = loc.geoLocation()
                if geo is not None:
                    out["location_lat"] = float(geo.coordinate().latitude)
                    out["location_lng"] = float(geo.coordinate().longitude)
            except Exception:
                pass
    except Exception:
        pass
        
    return out