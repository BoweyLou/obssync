#!/usr/bin/env python3
"""
Collect Apple Calendar events for a specific date.

This module fetches calendar events using the CalendarGateway and formats them
for integration with Obsidian daily notes. It provides both command-line
interface and programmatic access to calendar events.

Default behavior fetches today's events, but can be configured for any date.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import asdict

# Add the project root to the path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# Import observability utilities
from lib.observability import get_logger

# Import the calendar gateway
from calendar_gateway import (
    CalendarGateway, CalendarError, AuthorizationError, EventKitImportError,
    CalendarEvent, format_event_for_markdown, get_todays_events
)


def collect_events_for_date(target_date: date, calendar_ids: Optional[List[str]] = None) -> List[CalendarEvent]:
    """
    Collect calendar events for a specific date.

    Args:
        target_date: The date to collect events for
        calendar_ids: Optional list of calendar IDs to filter by

    Returns:
        List of CalendarEvent objects for the date

    Raises:
        CalendarError: If fetching events fails
    """
    logger = get_logger(__name__)

    try:
        gateway = CalendarGateway()
        events = gateway.get_events_for_date(target_date, calendar_ids)

        logger.info(f"Collected {len(events)} events for {target_date}")
        return events

    except EventKitImportError as e:
        logger.error(f"EventKit not available: {e}")
        raise
    except AuthorizationError as e:
        logger.error(f"Calendar authorization failed: {e}")
        raise
    except CalendarError as e:
        logger.error(f"Failed to collect calendar events: {e}")
        raise


def format_events_for_obsidian(events: List[CalendarEvent]) -> str:
    """
    Format calendar events for Obsidian daily note integration.

    Args:
        events: List of CalendarEvent objects

    Returns:
        Formatted markdown string ready for insertion into daily note
    """
    if not events:
        return "- No events scheduled"

    lines = []
    for event in events:
        formatted_event = format_event_for_markdown(event)
        lines.append(formatted_event)

    return "\n".join(lines)


def get_available_calendars() -> List[Dict[str, str]]:
    """
    Get list of available calendars for configuration.

    Returns:
        List of calendar dictionaries with id and title

    Raises:
        CalendarError: If fetching calendars fails
    """
    logger = get_logger(__name__)

    try:
        gateway = CalendarGateway()
        calendars = gateway.get_calendars()

        logger.info(f"Found {len(calendars)} calendars")
        return calendars

    except EventKitImportError as e:
        logger.error(f"EventKit not available: {e}")
        raise
    except AuthorizationError as e:
        logger.error(f"Calendar authorization failed: {e}")
        raise
    except CalendarError as e:
        logger.error(f"Failed to fetch calendars: {e}")
        raise


def main(argv: Optional[List[str]] = None) -> int:
    """
    Main entry point for calendar event collection.

    Args:
        argv: Command line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    parser = argparse.ArgumentParser(
        description="Collect Apple Calendar events for integration with Obsidian"
    )

    parser.add_argument(
        "--date",
        type=str,
        help="Date to collect events for (YYYY-MM-DD format, default: today)"
    )

    parser.add_argument(
        "--calendars",
        type=str,
        nargs="*",
        help="Calendar IDs to include (default: all calendars)"
    )

    parser.add_argument(
        "--output",
        type=str,
        help="Output file for events JSON (optional)"
    )

    parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="markdown",
        help="Output format (default: markdown)"
    )

    parser.add_argument(
        "--list-calendars",
        action="store_true",
        help="List available calendars and exit"
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args(argv)

    # Set up logging
    logger = get_logger(__name__)

    try:
        # Handle list calendars request
        if args.list_calendars:
            calendars = get_available_calendars()
            print("Available calendars:")
            for cal in calendars:
                print(f"  {cal['identifier']}: {cal['title']}")
            return 0

        # Parse target date
        if args.date:
            try:
                target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
            except ValueError:
                print(f"Error: Invalid date format '{args.date}'. Use YYYY-MM-DD format.")
                return 1
        else:
            target_date = date.today()

        # Collect events
        events = collect_events_for_date(target_date, args.calendars)

        # Format output
        if args.format == "json":
            # Convert events to JSON-serializable format
            events_data = {
                "date": target_date.isoformat(),
                "event_count": len(events),
                "events": [asdict(event) for event in events]
            }

            # Convert datetime objects to ISO strings for JSON serialization
            for event_dict in events_data["events"]:
                for key, value in event_dict.items():
                    if isinstance(value, datetime):
                        event_dict[key] = value.isoformat()

            output_text = json.dumps(events_data, indent=2, default=str)
        else:
            # Markdown format
            output_text = format_events_for_obsidian(events)

        # Output results
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output_text)
            print(f"Events written to {args.output}")
        else:
            print(output_text)

        if args.verbose:
            print(f"\nCollected {len(events)} events for {target_date}")

        return 0

    except EventKitImportError:
        print("Error: EventKit framework not available. This tool requires macOS with EventKit support.")
        return 1

    except AuthorizationError as e:
        print(f"Error: Calendar access denied. {e}")
        print("Please grant calendar permissions in System Settings > Privacy & Security > Calendars.")
        return 1

    except CalendarError as e:
        print(f"Error: Failed to collect calendar events. {e}")
        return 1

    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        return 130

    except Exception as e:
        logger.error(f"Unexpected error occurred: {e}")
        print(f"Error: Unexpected error occurred: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))