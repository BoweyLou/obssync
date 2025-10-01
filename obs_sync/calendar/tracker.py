"""Calendar import tracking for daily sync runs."""

import json
from datetime import date
from pathlib import Path
from typing import Dict, Optional
from ..core.paths import get_path_manager
from ..utils.io import safe_read_json, safe_write_json


class CalendarImportTracker:
    """Tracks calendar import timestamps to ensure once-per-day execution."""
    
    def __init__(self):
        self.path_manager = get_path_manager()
        self.tracker_file = Path(self.path_manager.log_dir) / "calendar_imports.json"
    
    def has_run_today(self, vault_id: str) -> bool:
        """Check if calendar import has already run today for the given vault."""
        today = date.today().isoformat()
        data = self._load_tracker_data()
        
        last_run = data.get(vault_id)
        return last_run == today
    
    def mark_run_today(self, vault_id: str) -> None:
        """Mark that calendar import has run today for the given vault."""
        today = date.today().isoformat()
        data = self._load_tracker_data()
        data[vault_id] = today
        self._save_tracker_data(data)
    
    def _load_tracker_data(self) -> Dict[str, str]:
        """Load tracker data from file."""
        return safe_read_json(str(self.tracker_file), default={})
    
    def _save_tracker_data(self, data: Dict[str, str]) -> None:
        """Save tracker data to file."""
        # Ensure log directory exists
        self.path_manager.ensure_directories()
        safe_write_json(str(self.tracker_file), data)