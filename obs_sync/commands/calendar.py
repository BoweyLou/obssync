"""Calendar sync command - integrate calendar events with daily notes."""

import os
from datetime import date, datetime
from typing import Optional, List
from ..calendar.gateway import CalendarGateway
from ..calendar.daily_notes import DailyNoteManager
from ..core.config import SyncConfig
import logging


class CalendarCommand:
    """Command for syncing calendar events to daily notes."""
    
    def __init__(self, config: SyncConfig, verbose: bool = False):
        self.config = config
        self.verbose = verbose
        self.logger = logging.getLogger(__name__)
        if verbose:
            self.logger.setLevel(logging.DEBUG)
    
    def run(self, date_str: Optional[str] = None, dry_run: bool = True) -> bool:
        """Run the calendar sync command."""
        try:
            target_date = None
            if date_str:
                target_date = datetime.strptime(date_str, "%Y-%m-%d").date()

            vault_path = self.config.default_vault_path
            if not vault_path:
                print("No Obsidian vault is configured. Run 'obs-sync setup' before syncing calendar events.")
                return False

            return calendar_sync_command(
                target_date=target_date,
                vault_path=vault_path,
                calendar_ids=self.config.calendar_ids or None,
                dry_run=dry_run,
            )
        except Exception as exc:  # pragma: no cover - defensive
            self.logger.error("Calendar command failed: %s", exc)
            if self.verbose:
                import traceback

                traceback.print_exc()
            return False


def calendar_sync_command(target_date: Optional[date] = None,
                        vault_path: Optional[str] = None,
                        calendar_ids: Optional[List[str]] = None,
                        dry_run: bool = True) -> bool:
    """
    Sync calendar events to Obsidian daily note.
    
    Args:
        target_date: Date to sync (default: today)
        vault_path: Path to Obsidian vault
        calendar_ids: Optional list of calendar IDs to include
        dry_run: If True, only preview changes
    
    Returns:
        True for success, False for failure
    """
    logger = logging.getLogger(__name__)
    
    # Default to today
    if not target_date:
        target_date = date.today()
    
    # Find vault if not specified
    if not vault_path:
        # Try to find from environment or config
        vault_path = os.environ.get('OBSIDIAN_VAULT')
        if not vault_path:
            print("Error: No vault path specified. Use --vault-path or set OBSIDIAN_VAULT.")
            return False
    
    if not os.path.exists(vault_path):
        print(f"Error: Vault not found at {vault_path}.")
        return False
    
    try:
        # Initialize components
        gateway = CalendarGateway()
        note_manager = DailyNoteManager(vault_path)
        
        # Get calendar events
        logger.info(f"Fetching calendar events for {target_date}")
        events = gateway.get_events_for_date(target_date, calendar_ids)
        
        print(f"Found {len(events)} calendar events for {target_date}.")
        
        # Update daily note
        if dry_run:
            print("\nEvents that will be added to the daily note:")
            for event in events:
                time_str = "All Day" if event.is_all_day else event.start_time.strftime("%H:%M")
                print(f"  - {time_str}: {event.title}")
                if event.location:
                    print(f"    Location — {event.location}")
        else:
            note_path = note_manager.update_daily_note(target_date, events)
            print(f"\nUpdated daily note saved to: {note_path}")
            print(f"Added {len(events)} calendar events.")
        
        return True
        
    except Exception as e:
        logger.error(f"Calendar sync failed: {e}")
        print(f"Error: Calendar sync failed — {e}")
        return False