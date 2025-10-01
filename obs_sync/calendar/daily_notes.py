"""Daily note management for calendar integration."""

import os
import re
from datetime import date
from typing import List, Optional
from .gateway import CalendarEvent


class DailyNoteManager:
    """Manages daily notes in Obsidian."""
    
    def __init__(self, vault_path: str):
        self.vault_path = vault_path
        self.daily_notes_dir = self._find_daily_notes_dir()
    
    def _find_daily_notes_dir(self) -> str:
        """Find the daily notes directory by looking for common patterns."""
        possible_dirs = [
            "01-Daily-Notes",  # Common PARA method naming
            "Daily Notes",     # Default Obsidian
            "daily-notes",     # Lowercase variant
            "Daily",           # Short version
            "Journal",         # Alternative naming
            "00-Daily",        # Another PARA variant
        ]
        
        for dir_name in possible_dirs:
            dir_path = os.path.join(self.vault_path, dir_name)
            if os.path.exists(dir_path) and os.path.isdir(dir_path):
                return dir_name
        
        # If none found, use the first option and create it if needed
        return possible_dirs[0]
    
    def get_daily_note_path(self, target_date: date) -> str:
        """Get path to daily note for a date."""
        date_str = target_date.strftime("%Y-%m-%d")
        dir_path = os.path.join(self.vault_path, self.daily_notes_dir)
        return os.path.join(dir_path, f"{date_str}.md")
    
    def update_daily_note(self, target_date: date,
                         events: List[CalendarEvent]) -> str:
        """Update daily note with calendar events."""
        note_path = self.get_daily_note_path(target_date)
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(note_path), exist_ok=True)
        
        # Read existing content or create new
        if os.path.exists(note_path):
            with open(note_path, 'r', encoding='utf-8') as f:
                content = f.read()
        else:
            content = self._create_new_daily_note(target_date)
        
        # Update with events
        updated = self._insert_calendar_section(content, events)
        
        # Write back
        with open(note_path, 'w', encoding='utf-8') as f:
            f.write(updated)
        
        return note_path
    
    def _create_new_daily_note(self, target_date: date) -> str:
        """Create content for a new daily note."""
        date_str = target_date.strftime("%Y-%m-%d")
        weekday = target_date.strftime("%A")
        
        return f"""# {date_str} {weekday}

## Calendar

## Tasks
- [ ]

## Notes

## Daily Review
- **What went well:**
- **What could be improved:**
- **Key learnings:**
"""
    
    def _insert_calendar_section(self, content: str,
                                events: List[CalendarEvent]) -> str:
        """Insert calendar events at the top of the note."""
        if not events:
            return content  # No events to insert
        
        # Format events for insertion at top
        lines = ["## Today's Calendar Events"]
        for event in events:
            if event.is_all_day:
                time_str = "All Day"
            elif event.start_time:
                time_str = event.start_time.strftime("%H:%M")
            else:
                time_str = ""
            
            line = f"- **{time_str}**: {event.title}"
            if event.location:
                line += f" @ {event.location}"
            lines.append(line)
        
        events_section = "\n".join(lines) + "\n\n"
        
        # Insert at the top of the content after the title
        lines = content.split('\n')
        if lines and lines[0].startswith('# '):
            # Insert after title
            result = [lines[0], '', events_section] + lines[1:]
            return '\n'.join(result)
        else:
            # Insert at very beginning
            return events_section + content