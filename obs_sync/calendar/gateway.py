"""Simplified Apple Calendar gateway using EventKit."""

import threading
import time
from datetime import date, datetime, timezone, timedelta
from typing import List, Optional
from dataclasses import dataclass
import logging


@dataclass
class CalendarEvent:
    """Calendar event data."""
    event_id: str
    title: str
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    location: Optional[str]
    notes: Optional[str]
    is_all_day: bool
    calendar_name: str


class CalendarGateway:
    """Gateway for Apple Calendar via EventKit."""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self._store = None
        
    def _ensure_eventkit(self):
        """Import EventKit."""
        try:
            import objc
            from EventKit import (
                EKEventStore, EKEntityTypeEvent,
                EKAuthorizationStatusAuthorized
            )
            from Foundation import NSRunLoop, NSDate
            
            self._EKEventStore = EKEventStore
            self._EKEntityTypeEvent = EKEntityTypeEvent
            self._EKAuthorizationStatusAuthorized = EKAuthorizationStatusAuthorized
            self._NSRunLoop = NSRunLoop
            self._NSDate = NSDate
            
        except ImportError as e:
            raise RuntimeError(f"EventKit not available: {e}")
    
    def _get_store(self):
        """Get EventKit store."""
        if self._store:
            return self._store
            
        self._ensure_eventkit()
        self._store = self._EKEventStore.alloc().init()
        
        # Check authorization
        status = self._EKEventStore.authorizationStatusForEntityType_(
            self._EKEntityTypeEvent
        )
        
        if int(status) != int(self._EKAuthorizationStatusAuthorized):
            # Request authorization
            done = threading.Event()
            result = {'granted': False}
            
            def completion(granted, error):
                result['granted'] = granted
                done.set()
            
            self._store.requestAccessToEntityType_completion_(
                self._EKEntityTypeEvent, completion
            )
            
            done.wait(30)
            
            if not result['granted']:
                raise RuntimeError("Calendar access not granted")
                
        return self._store
    
    def get_events_for_date(self, target_date: date,
                           calendar_ids: Optional[List[str]] = None) -> List[CalendarEvent]:
        """Get calendar events for a specific date."""
        store = self._get_store()

        # Get system local timezone for proper time display
        local_tz = datetime.now().astimezone().tzinfo

        # Create date range
        start = datetime.combine(target_date, datetime.min.time())
        end = start + timedelta(days=1)

        # Get calendars
        all_cals = store.calendarsForEntityType_(self._EKEntityTypeEvent) or []
        if calendar_ids:
            calendars = [c for c in all_cals
                        if str(c.calendarIdentifier()) in calendar_ids]
        else:
            calendars = all_cals

        # Create predicate
        from Foundation import NSDate
        start_ns = NSDate.dateWithTimeIntervalSince1970_(start.timestamp())
        end_ns = NSDate.dateWithTimeIntervalSince1970_(end.timestamp())

        predicate = store.predicateForEventsWithStartDate_endDate_calendars_(
            start_ns, end_ns, calendars
        )

        # Fetch events
        events = store.eventsMatchingPredicate_(predicate) or []

        # Convert to CalendarEvent
        result = []
        for event in events:
            try:
                # Extract data
                event_id = str(event.eventIdentifier())
                title = str(event.title() or 'Untitled')

                # Times - use local timezone for proper display
                start_time = None
                end_time = None
                if event.startDate():
                    start_time = datetime.fromtimestamp(
                        event.startDate().timeIntervalSince1970(),
                        tz=local_tz
                    )
                if event.endDate():
                    end_time = datetime.fromtimestamp(
                        event.endDate().timeIntervalSince1970(),
                        tz=local_tz
                    )

                # Other fields
                location = str(event.location()) if event.location() else None
                notes = str(event.notes()) if event.notes() else None
                is_all_day = bool(event.isAllDay())

                # Calendar name
                cal = event.calendar()
                calendar_name = str(cal.title()) if cal else 'Unknown'

                result.append(CalendarEvent(
                    event_id=event_id,
                    title=title,
                    start_time=start_time,
                    end_time=end_time,
                    location=location,
                    notes=notes,
                    is_all_day=is_all_day,
                    calendar_name=calendar_name
                ))

            except Exception as e:
                self.logger.warning(f"Failed to process event: {e}")
                continue

        # Sort by start time (use local timezone for comparison)
        result.sort(key=lambda e: e.start_time or datetime.min.replace(tzinfo=local_tz))

        return result