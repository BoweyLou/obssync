#!/usr/bin/env python3
"""
Apple Calendar Gateway - Unified EventKit boundary for all Calendar operations.

This module provides a single, consistent interface for all Apple Calendar access,
following the same patterns as the RemindersGateway but for calendar events.

Key responsibilities:
- One-time EventKit store initialization and authorization
- Unified error handling with detailed diagnostics
- Fetch calendar events with filtering and caching
- Thread-safe EventKit operations with proper lifecycle management

Usage:
    gateway = CalendarGateway()

    # Fetch operations
    calendars = gateway.get_calendars()
    events = gateway.get_events_for_date(date_obj)
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from datetime import datetime, timezone, date, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass


class CalendarError(Exception):
    """Base exception for all Calendar Gateway errors."""
    pass


class AuthorizationError(CalendarError):
    """Raised when EventKit authorization fails or is denied."""
    pass


class EventKitImportError(CalendarError):
    """Raised when EventKit/PyObjC dependencies are not available."""
    pass


class CalendarNotFoundError(CalendarError):
    """Raised when a specific calendar cannot be found."""
    pass


class AuthorizationStatus(Enum):
    """EventKit authorization status enumeration."""
    NOT_DETERMINED = 0
    RESTRICTED = 1
    DENIED = 2
    AUTHORIZED = 3


@dataclass
class CalendarEvent:
    """Represents a calendar event with all relevant details."""
    event_id: str
    title: str
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    location: Optional[str]
    notes: Optional[str]
    is_all_day: bool
    calendar_name: str
    calendar_id: str
    created_date: Optional[datetime]
    modified_date: Optional[datetime]


@dataclass
class GatewayStats:
    """Statistics for gateway operations."""
    store_initializations: int = 0
    authorization_attempts: int = 0
    calendars_fetched: int = 0
    events_fetched: int = 0
    errors_encountered: int = 0


class CalendarGateway:
    """
    Unified gateway for Apple Calendar (EventKit) operations.

    Provides thread-safe access to calendar events with proper authorization
    handling and error management.
    """

    def __init__(self, timeout_seconds: float = 30.0):
        """
        Initialize the Calendar Gateway.

        Args:
            timeout_seconds: Timeout for EventKit operations
        """
        self.timeout_seconds = timeout_seconds
        self.stats = GatewayStats()
        self._store = None
        self._store_lock = threading.Lock()
        self._auth_status = None
        self._logger = logging.getLogger(__name__)

        # Try to import EventKit dependencies
        try:
            import objc
            import EventKit
            self._EventKit = EventKit
            self._objc = objc
        except ImportError as e:
            raise EventKitImportError(
                f"EventKit/PyObjC not available: {e}. "
                "Run: pip install pyobjc pyobjc-framework-EventKit"
            ) from e

    def _get_store(self) -> Any:
        """Get or create the EventKit store with thread safety."""
        with self._store_lock:
            if self._store is None:
                self._store = self._EventKit.EKEventStore.alloc().init()
                self.stats.store_initializations += 1
            return self._store

    def _check_authorization(self) -> AuthorizationStatus:
        """Check current authorization status."""
        # Use class method, not instance method (following reminders_gateway.py pattern)
        status = self._EventKit.EKEventStore.authorizationStatusForEntityType_(self._EventKit.EKEntityTypeEvent)

        # Map to our enum
        status_map = {
            0: AuthorizationStatus.NOT_DETERMINED,
            1: AuthorizationStatus.RESTRICTED,
            2: AuthorizationStatus.DENIED,
            3: AuthorizationStatus.AUTHORIZED
        }

        return status_map.get(status, AuthorizationStatus.NOT_DETERMINED)

    def request_authorization(self) -> bool:
        """
        Request authorization to access calendars.

        Returns:
            True if authorized, False otherwise

        Raises:
            AuthorizationError: If authorization is denied or restricted
        """
        self.stats.authorization_attempts += 1

        current_status = self._check_authorization()

        if current_status == AuthorizationStatus.AUTHORIZED:
            return True

        if current_status in (AuthorizationStatus.RESTRICTED, AuthorizationStatus.DENIED):
            raise AuthorizationError(
                f"Calendar access {current_status.name.lower()}. "
                "Please grant calendar permissions in System Settings."
            )

        # Request permission
        store = self._get_store()
        authorization_granted = threading.Event()
        auth_result = [False]

        def completion_handler(granted, error):
            auth_result[0] = granted
            if error:
                self._logger.error(f"Authorization error: {error}")
            authorization_granted.set()

        store.requestAccessToEntityType_completion_(
            self._EventKit.EKEntityTypeEvent,
            completion_handler
        )

        # Wait for response with timeout
        if not authorization_granted.wait(timeout=self.timeout_seconds):
            raise AuthorizationError("Authorization request timed out")

        if not auth_result[0]:
            raise AuthorizationError("Calendar access denied by user")

        self._auth_status = AuthorizationStatus.AUTHORIZED
        return True

    def get_calendars(self) -> List[Dict[str, Any]]:
        """
        Get all available calendars.

        Returns:
            List of calendar dictionaries with id, title, color, etc.

        Raises:
            CalendarError: If fetching calendars fails
        """
        if not self.request_authorization():
            raise AuthorizationError("Not authorized to access calendars")

        try:
            store = self._get_store()
            calendars = store.calendarsForEntityType_(self._EventKit.EKEntityTypeEvent)

            result = []
            for cal in calendars:
                try:
                    cal_dict = {
                        'identifier': str(cal.calendarIdentifier()),
                        'title': str(cal.title() or 'Untitled'),
                        'type': str(cal.type()),
                        'allowsContentModifications': bool(cal.allowsContentModifications()),
                    }

                    # Try to get color
                    try:
                        color = cal.color()
                        if color:
                            cal_dict['color'] = self._nscolor_to_hex(color)
                    except Exception:
                        pass

                    result.append(cal_dict)

                except Exception as e:
                    self._logger.warning(f"Error processing calendar: {e}")
                    continue

            self.stats.calendars_fetched += len(result)
            return result

        except Exception as e:
            self.stats.errors_encountered += 1
            raise CalendarError(f"Failed to fetch calendars: {e}") from e

    def get_events_for_date(self, target_date: date, calendar_ids: Optional[List[str]] = None) -> List[CalendarEvent]:
        """
        Get all events for a specific date.

        Args:
            target_date: The date to fetch events for
            calendar_ids: Optional list of calendar IDs to filter by

        Returns:
            List of CalendarEvent objects

        Raises:
            CalendarError: If fetching events fails
        """
        if not self.request_authorization():
            raise AuthorizationError("Not authorized to access calendars")

        try:
            store = self._get_store()

            # Create date range for the entire day
            start_date = datetime.combine(target_date, datetime.min.time())
            end_date = start_date + timedelta(days=1)

            # Get calendars to search
            if calendar_ids:
                calendars = []
                all_calendars = store.calendarsForEntityType_(self._EventKit.EKEntityTypeEvent)
                for cal in all_calendars:
                    if str(cal.calendarIdentifier()) in calendar_ids:
                        calendars.append(cal)
            else:
                calendars = store.calendarsForEntityType_(self._EventKit.EKEntityTypeEvent)

            # Create predicate for the date range
            predicate = store.predicateForEventsWithStartDate_endDate_calendars_(
                start_date, end_date, calendars
            )

            # Fetch events
            events = store.eventsMatchingPredicate_(predicate)

            result = []
            for event in events:
                try:
                    calendar_event = self._convert_event_to_calendar_event(event)
                    result.append(calendar_event)
                except Exception as e:
                    self._logger.warning(f"Error processing event: {e}")
                    continue

            # Sort events by start time
            result.sort(key=lambda e: e.start_time or datetime.min.replace(tzinfo=timezone.utc))

            self.stats.events_fetched += len(result)
            return result

        except Exception as e:
            self.stats.errors_encountered += 1
            raise CalendarError(f"Failed to fetch events for {target_date}: {e}") from e

    def _convert_event_to_calendar_event(self, event) -> CalendarEvent:
        """Convert an EventKit event to our CalendarEvent dataclass."""
        try:
            # Get basic properties
            event_id = str(event.eventIdentifier() or '')
            title = str(event.title() or 'Untitled')

            # Get dates
            start_time = None
            end_time = None
            if event.startDate():
                start_time = self._nsdate_to_datetime(event.startDate())
            if event.endDate():
                end_time = self._nsdate_to_datetime(event.endDate())

            # Get other properties
            location = None
            if event.location():
                location = str(event.location())

            notes = None
            if event.notes():
                notes = str(event.notes())

            is_all_day = bool(event.isAllDay())

            # Get calendar info
            calendar = event.calendar()
            calendar_name = str(calendar.title() or 'Unknown') if calendar else 'Unknown'
            calendar_id = str(calendar.calendarIdentifier()) if calendar else ''

            # Get creation/modification dates
            created_date = None
            if hasattr(event, 'creationDate') and event.creationDate():
                created_date = self._nsdate_to_datetime(event.creationDate())

            modified_date = None
            if hasattr(event, 'lastModifiedDate') and event.lastModifiedDate():
                modified_date = self._nsdate_to_datetime(event.lastModifiedDate())

            return CalendarEvent(
                event_id=event_id,
                title=title,
                start_time=start_time,
                end_time=end_time,
                location=location,
                notes=notes,
                is_all_day=is_all_day,
                calendar_name=calendar_name,
                calendar_id=calendar_id,
                created_date=created_date,
                modified_date=modified_date
            )

        except Exception as e:
            raise CalendarError(f"Failed to convert event: {e}") from e

    def _nsdate_to_datetime(self, nsdate) -> datetime:
        """Convert NSDate to Python datetime."""
        timestamp = nsdate.timeIntervalSince1970()
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)

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

    def get_stats(self) -> GatewayStats:
        """Get gateway operation statistics."""
        return self.stats


# Convenience functions for direct usage
def get_todays_events(calendar_ids: Optional[List[str]] = None) -> List[CalendarEvent]:
    """
    Convenience function to get today's events.

    Args:
        calendar_ids: Optional list of calendar IDs to filter by

    Returns:
        List of today's CalendarEvent objects
    """
    gateway = CalendarGateway()
    today = date.today()
    return gateway.get_events_for_date(today, calendar_ids)


def format_event_time(event: CalendarEvent) -> str:
    """
    Format event time for display.

    Args:
        event: CalendarEvent to format

    Returns:
        Formatted time string (e.g., "09:00", "All Day", "09:00 - 10:30")
    """
    if event.is_all_day:
        return "All Day"

    if not event.start_time:
        return "Unknown Time"

    # Convert to local time for display
    local_start = event.start_time.astimezone()

    if event.end_time:
        local_end = event.end_time.astimezone()
        # Only show end time if it's different and not just 1 minute later (common for all-day events)
        if (local_end - local_start).total_seconds() > 60:
            return f"{local_start.strftime('%H:%M')} - {local_end.strftime('%H:%M')}"

    return local_start.strftime('%H:%M')


def format_event_for_markdown(event: CalendarEvent) -> str:
    """
    Format a calendar event for markdown display.

    Args:
        event: CalendarEvent to format

    Returns:
        Formatted markdown string
    """
    time_str = format_event_time(event)
    title = event.title

    # Add location if available
    if event.location:
        title += f" ({event.location})"

    return f"- {time_str} - {title}"