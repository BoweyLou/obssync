#!/usr/bin/env python3
"""
Sync Apple Calendar events to Obsidian daily notes.

This module integrates calendar events with Obsidian daily notes by:
1. Fetching today's calendar events
2. Finding or creating today's daily note
3. Adding/updating an "On Today" section with the events

The module preserves existing content and safely updates only the calendar section.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional, Tuple

# Add the project root to the path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# Import safe I/O utilities
from lib.safe_io import safe_write_json_with_lock
from lib.observability import get_logger

# Import centralized path configuration
from app_config import get_path

# Import calendar collection
from obs_tools.commands.collect_calendar_events import collect_events_for_date, format_events_for_obsidian
from calendar_gateway import CalendarError, AuthorizationError, EventKitImportError


def find_obsidian_vault_path(preferred_vault_name: Optional[str] = None) -> Optional[str]:
    """
    Find the default Obsidian vault path from configuration.

    Args:
        preferred_vault_name: Name of preferred vault from app settings

    Tries to find the vault in this order:
    1. Vault matching preferred_vault_name (if provided)
    2. Vault marked as default
    3. Vault that contains the current working directory
    4. First vault in the list

    Returns:
        Path to the Obsidian vault, or None if not found
    """
    logger = get_logger(__name__)

    try:
        # Try to read vault configuration
        vaults_config_path = get_path("obsidian_vaults")
        if not os.path.exists(vaults_config_path):
            logger.warning(f"Obsidian vaults config not found at {vaults_config_path}")
            return None

        import json
        with open(vaults_config_path, 'r', encoding='utf-8') as f:
            vaults_data = json.load(f)

        # Get current working directory to try to match vault
        current_dir = os.getcwd()

        # Find vault by priority order
        preferred_vault = None
        default_vault = None
        current_dir_vault = None
        first_vault = None

        for vault in vaults_data:
            if isinstance(vault, dict) and 'path' in vault:
                vault_path = vault['path']
                vault_name = vault.get('name', '')

                if first_vault is None:
                    first_vault = vault_path

                # Check if this is the preferred vault
                if preferred_vault_name and vault_name == preferred_vault_name:
                    preferred_vault = vault_path

                # Check if this vault is marked as default
                if vault.get('is_default', False):
                    default_vault = vault_path

                # Check if current directory is within this vault
                if current_dir.startswith(vault_path):
                    current_dir_vault = vault_path

        # Priority: preferred > default > current directory > first
        vault_path = preferred_vault or default_vault or current_dir_vault or first_vault

        if vault_path:
            logger.info(f"Using Obsidian vault: {vault_path}")
            return vault_path
        else:
            logger.warning("No valid Obsidian vault found in configuration")
            return None

    except Exception as e:
        logger.error(f"Error finding Obsidian vault: {e}")
        return None


def get_daily_note_path(vault_path: str, target_date: date) -> str:
    """
    Get the path to the daily note for a specific date.

    Args:
        vault_path: Path to the Obsidian vault
        target_date: Date for the daily note

    Returns:
        Full path to the daily note file
    """
    date_str = target_date.strftime("%Y-%m-%d")
    daily_notes_dir = os.path.join(vault_path, "01-Daily-Notes")
    return os.path.join(daily_notes_dir, f"{date_str}.md")


def read_daily_note(file_path: str) -> str:
    """
    Read the content of a daily note file.

    Args:
        file_path: Path to the daily note file

    Returns:
        Content of the file, or empty string if file doesn't exist
    """
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    return ""


def create_new_daily_note(target_date: date) -> str:
    """
    Create content for a new daily note.

    Args:
        target_date: Date for the daily note

    Returns:
        Content for the new daily note
    """
    date_str = target_date.strftime("%Y-%m-%d")

    return f"""# {date_str}

## 🎯 Today's Focus
**Primary Context**: Project / Admin / Strategy
**Top 3 priorities**:
1.
2.
3.

---

## 📝 Brain Dump
*Write everything here - tag with #work #phd #life #project-name as you go*



---

## ✅ Tasks by Context
*Tasks auto-link to project pages via hashtags*

### 💼 Work Tasks

### 📋 Quick Tasks (Other)


### 🎓 PhD Tasks


### 🏠 Life Tasks


---

## 🌙 End of Day Reflection
**Accomplished**:

**Tomorrow's focus**:

**Context for tomorrow**:

---

## 🎯 Quick Context Switch
- [[../System/Current Work Dashboard|🎯 Current Work]] - What am I working on right now?
- [[../System/Work Dashboard|💼 Work Mode]] - Focus on #work only
- [[../System/Today Dashboard|📅 All Contexts]] - See everything
- [[../System/Weekly Focus Dashboard|📅 Weekly Focus]] - This week's priorities

---
*ADHD-Friendly: All content starts here, organize later via hashtags*"""


def parse_daily_note_sections(content: str) -> Tuple[str, str, str]:
    """
    Parse daily note content into sections.

    Args:
        content: Content of the daily note

    Returns:
        Tuple of (before_calendar, calendar_section, after_calendar)
    """
    # Look for existing "On Today" section
    on_today_pattern = r'^## On Today\s*\n(.*?)(?=^## |\Z)'
    match = re.search(on_today_pattern, content, re.MULTILINE | re.DOTALL)

    if match:
        # Found existing section - split around it
        start_pos = match.start()
        end_pos = match.end()

        before_calendar = content[:start_pos].rstrip()
        calendar_section = match.group(0)
        after_calendar = content[end_pos:].lstrip()

        return before_calendar, calendar_section, after_calendar
    else:
        # No existing section - find insertion point after title
        title_pattern = r'^# \d{4}-\d{2}-\d{2}\s*\n'
        title_match = re.search(title_pattern, content, re.MULTILINE)

        if title_match:
            # Insert after title
            insertion_point = title_match.end()
            before_calendar = content[:insertion_point].rstrip()
            after_calendar = content[insertion_point:].lstrip()
        else:
            # No title found - insert at beginning
            before_calendar = ""
            after_calendar = content.lstrip()

        return before_calendar, "", after_calendar


def create_calendar_section(events_markdown: str) -> str:
    """
    Create the "On Today" calendar section.

    Args:
        events_markdown: Formatted events in markdown

    Returns:
        Complete calendar section
    """
    return f"""## On Today
{events_markdown}

"""


def update_daily_note_with_events(content: str, events_markdown: str) -> str:
    """
    Update daily note content with calendar events.

    Args:
        content: Current daily note content
        events_markdown: Formatted events in markdown

    Returns:
        Updated daily note content
    """
    before, _, after = parse_daily_note_sections(content)
    new_calendar_section = create_calendar_section(events_markdown)

    # Reconstruct the note
    if before and after:
        return f"{before}\n\n{new_calendar_section}{after}"
    elif before:
        return f"{before}\n\n{new_calendar_section}"
    elif after:
        return f"{new_calendar_section}{after}"
    else:
        return new_calendar_section


def sync_calendar_to_daily_note(
    target_date: date,
    vault_path: Optional[str] = None,
    calendar_ids: Optional[List[str]] = None,
    dry_run: bool = False,
    preferred_vault_name: Optional[str] = None
) -> bool:
    """
    Sync calendar events to daily note.

    Args:
        target_date: Date to sync events for
        vault_path: Path to Obsidian vault (auto-detected if None)
        calendar_ids: Calendar IDs to include (all if None)
        dry_run: If True, don't actually write files

    Returns:
        True if successful, False otherwise
    """
    logger = get_logger(__name__)

    try:
        # Find vault path if not provided
        if not vault_path:
            vault_path = find_obsidian_vault_path(preferred_vault_name)
            if not vault_path:
                logger.error("Could not find Obsidian vault path")
                return False

        # Ensure vault path exists
        if not os.path.exists(vault_path):
            logger.error(f"Obsidian vault path does not exist: {vault_path}")
            return False

        # Ensure daily notes directory exists
        daily_notes_dir = os.path.join(vault_path, "01-Daily-Notes")
        os.makedirs(daily_notes_dir, exist_ok=True)

        # Get daily note path
        note_path = get_daily_note_path(vault_path, target_date)

        # Read existing content or create new
        existing_content = read_daily_note(note_path)
        if not existing_content:
            logger.info(f"Creating new daily note for {target_date}")
            existing_content = create_new_daily_note(target_date)

        # Collect calendar events
        logger.info(f"Collecting calendar events for {target_date}")
        events = collect_events_for_date(target_date, calendar_ids)
        events_markdown = format_events_for_obsidian(events)

        # Update content
        updated_content = update_daily_note_with_events(existing_content, events_markdown)

        # Write file (if not dry run)
        if dry_run:
            logger.info(f"DRY RUN: Would update {note_path}")
            logger.info(f"Calendar section content:\n{events_markdown}")
        else:
            with open(note_path, 'w', encoding='utf-8') as f:
                f.write(updated_content)
            logger.info(f"Updated daily note: {note_path}")
            logger.info(f"Added {len(events)} calendar events")

        return True

    except EventKitImportError as e:
        logger.error(f"EventKit not available: {e}")
        return False
    except AuthorizationError as e:
        logger.error(f"Calendar authorization failed: {e}")
        return False
    except CalendarError as e:
        logger.error(f"Calendar error: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during sync: {e}")
        return False


def main(argv: Optional[List[str]] = None) -> int:
    """
    Main entry point for calendar to daily note sync.

    Args:
        argv: Command line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    parser = argparse.ArgumentParser(
        description="Sync Apple Calendar events to Obsidian daily notes"
    )

    parser.add_argument(
        "--date",
        type=str,
        help="Date to sync events for (YYYY-MM-DD format, default: today)"
    )

    parser.add_argument(
        "--vault-path",
        type=str,
        help="Path to Obsidian vault (auto-detected if not specified)"
    )

    parser.add_argument(
        "--calendars",
        type=str,
        nargs="*",
        help="Calendar IDs to include (default: all calendars)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
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
        # Parse target date
        if args.date:
            try:
                target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
            except ValueError:
                print(f"Error: Invalid date format '{args.date}'. Use YYYY-MM-DD format.")
                return 1
        else:
            target_date = date.today()

        # Load app preferences to get preferred vault
        preferred_vault_name = None
        try:
            import app_config
            prefs, _ = app_config.load_app_config()
            preferred_vault_name = prefs.calendar_vault_name if prefs.calendar_vault_name else None
        except Exception:
            # If we can't load preferences, continue with None
            pass

        # Perform sync
        success = sync_calendar_to_daily_note(
            target_date=target_date,
            vault_path=args.vault_path,
            calendar_ids=args.calendars,
            dry_run=args.dry_run,
            preferred_vault_name=preferred_vault_name
        )

        if success:
            action = "Would update" if args.dry_run else "Updated"
            print(f"{action} daily note for {target_date}")
            return 0
        else:
            print("Failed to sync calendar events to daily note")
            return 1

    except EventKitImportError:
        print("Error: EventKit framework not available. This tool requires macOS with EventKit support.")
        return 1

    except AuthorizationError as e:
        print(f"Error: Calendar access denied. {e}")
        print("Please grant calendar permissions in System Settings > Privacy & Security > Calendars.")
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