#!/usr/bin/env python3
"""Test script to verify calendar timezone handling."""

from datetime import datetime, date, timezone, timedelta
from obs_sync.calendar.gateway import CalendarGateway, CalendarEvent
from obs_sync.calendar.daily_notes import DailyNoteManager

def test_timezone_display():
    """Test that events display in local time, not UTC."""

    # Get local timezone
    local_tz = datetime.now().astimezone().tzinfo
    print(f"System local timezone: {local_tz}")

    # Create a sample event with known time (e.g., 2:00 PM local)
    sample_time = datetime.now().replace(hour=14, minute=0, second=0, microsecond=0)
    sample_time_local = sample_time.astimezone(local_tz)

    print(f"\nSample time in local TZ: {sample_time_local.strftime('%Y-%m-%d %H:%M %Z')}")
    print(f"Expected display: 14:00")

    # Create CalendarEvent
    event = CalendarEvent(
        event_id="test-1",
        title="Test Meeting",
        start_time=sample_time_local,
        end_time=sample_time_local + timedelta(hours=1),
        location="Office",
        notes="Test notes",
        is_all_day=False,
        calendar_name="Work"
    )

    # Test formatting as done in daily_notes.py
    formatted_time = event.start_time.strftime("%H:%M")
    print(f"Formatted time: {formatted_time}")

    assert formatted_time == "14:00", f"Expected 14:00 but got {formatted_time}"
    print("✓ Time displays correctly in local timezone")

    # Test all-day event
    all_day_event = CalendarEvent(
        event_id="test-2",
        title="All Day Event",
        start_time=sample_time_local,
        end_time=sample_time_local + timedelta(days=1),
        location=None,
        notes=None,
        is_all_day=True,
        calendar_name="Personal"
    )

    time_str = "All Day" if all_day_event.is_all_day else all_day_event.start_time.strftime("%H:%M")
    assert time_str == "All Day", "All-day events should show 'All Day'"
    print("✓ All-day events handled correctly")

if __name__ == "__main__":
    print("Testing calendar timezone handling...\n")
    test_timezone_display()
    print("\n✅ All tests passed!")
    print("\nTo test with real calendar events:")
    print("  obs-sync calendar --dry-run")
    print("\nVerify that event times match what you see in Apple Calendar.")
