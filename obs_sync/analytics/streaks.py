"""
Streak tracking for task completions by tag and list.

Maintains daily completion counts and calculates current/best streaks
for each tag and reminder list across vaults.
"""

import json
import os
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path


class StreakTracker:
    """
    Tracks and persists task completion streaks.
    
    Streak data is keyed by vault_id -> tag/list -> dates with completion counts.
    Streaks are calculated on-demand to determine current and best runs.
    """
    
    def __init__(self, data_path: Optional[str] = None):
        """
        Initialize streak tracker.
        
        Args:
            data_path: Path to JSON file for persisting streak data.
                      Defaults to ~/.config/obs-tools/streaks.json
        """
        if data_path is None:
            config_dir = Path.home() / ".config" / "obs-tools"
            config_dir.mkdir(parents=True, exist_ok=True)
            data_path = str(config_dir / "streaks.json")
        
        self.data_path = data_path
        self.data = self._load()
    
    def _load(self) -> Dict[str, Any]:
        """Load streak data from disk."""
        if not os.path.exists(self.data_path):
            return {}
        
        try:
            with open(self.data_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    
    def _save(self) -> None:
        """Persist streak data to disk."""
        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
        with open(self.data_path, 'w') as f:
            json.dump(self.data, f, indent=2)
    
    def record_completions(
        self,
        vault_id: str,
        target_date: date,
        by_tag: Dict[str, int],
        by_list: Dict[str, int]
    ) -> None:
        """
        Record completion counts for a given date.
        
        Args:
            vault_id: Vault identifier
            target_date: Date of completions
            by_tag: Dict mapping tag names to completion counts
            by_list: Dict mapping list names to completion counts
        """
        if vault_id not in self.data:
            self.data[vault_id] = {"tags": {}, "lists": {}}
        
        date_str = target_date.isoformat()
        
        # Record tag completions
        for tag, count in by_tag.items():
            if tag not in self.data[vault_id]["tags"]:
                self.data[vault_id]["tags"][tag] = {}
            self.data[vault_id]["tags"][tag][date_str] = count
        
        # Record list completions
        for list_name, count in by_list.items():
            if list_name not in self.data[vault_id]["lists"]:
                self.data[vault_id]["lists"][list_name] = {}
            self.data[vault_id]["lists"][list_name][date_str] = count
        
        self._save()
    
    def get_streak(
        self,
        vault_id: str,
        key: str,
        category: str = "tags"
    ) -> Dict[str, int]:
        """
        Calculate current and best streak for a tag or list.
        
        Args:
            vault_id: Vault identifier
            key: Tag name or list name
            category: "tags" or "lists"
        
        Returns:
            Dict with "current" and "best" streak counts in days
        """
        if vault_id not in self.data:
            return {"current": 0, "best": 0}
        
        if key not in self.data[vault_id].get(category, {}):
            return {"current": 0, "best": 0}
        
        completion_dates = self.data[vault_id][category][key]
        if not completion_dates:
            return {"current": 0, "best": 0}
        
        # Sort dates and calculate streaks
        dates = sorted([date.fromisoformat(d) for d in completion_dates.keys()])
        
        current_streak = 0
        best_streak = 0
        temp_streak = 0
        
        today = date.today()
        
        # Calculate current streak (working backwards from today)
        for i in range(len(dates) - 1, -1, -1):
            check_date = today - timedelta(days=len(dates) - 1 - i)
            if dates[i] == check_date:
                current_streak += 1
            else:
                break
        
        # Calculate best streak
        for i, d in enumerate(dates):
            if i == 0:
                temp_streak = 1
            else:
                # Check if consecutive day
                if (d - dates[i-1]).days == 1:
                    temp_streak += 1
                else:
                    temp_streak = 1
            
            best_streak = max(best_streak, temp_streak)
        
        return {
            "current": current_streak,
            "best": best_streak
        }
    
    def get_all_streaks(
        self,
        vault_id: str,
        min_current: int = 1
    ) -> Dict[str, Dict[str, int]]:
        """
        Get all active streaks for a vault.
        
        Args:
            vault_id: Vault identifier
            min_current: Minimum current streak to include
        
        Returns:
            Dict mapping "tag:name" or "list:name" to streak info
        """
        streaks = {}
        
        if vault_id not in self.data:
            return streaks
        
        # Process tags
        for tag, _ in self.data[vault_id].get("tags", {}).items():
            streak_info = self.get_streak(vault_id, tag, "tags")
            if streak_info["current"] >= min_current:
                streaks[f"tag:{tag}"] = streak_info
        
        # Process lists
        for list_name, _ in self.data[vault_id].get("lists", {}).items():
            streak_info = self.get_streak(vault_id, list_name, "lists")
            if streak_info["current"] >= min_current:
                streaks[f"list:{list_name}"] = streak_info
        
        return streaks
    
    def cleanup_old_data(self, days_to_keep: int = 365) -> None:
        """
        Remove streak data older than specified days.
        
        Args:
            days_to_keep: Number of days of history to retain
        """
        cutoff_date = date.today() - timedelta(days=days_to_keep)
        cutoff_str = cutoff_date.isoformat()
        
        for vault_id in self.data:
            # Clean tags
            for tag in list(self.data[vault_id].get("tags", {}).keys()):
                dates = self.data[vault_id]["tags"][tag]
                self.data[vault_id]["tags"][tag] = {
                    d: count for d, count in dates.items()
                    if d >= cutoff_str
                }
                # Remove empty entries
                if not self.data[vault_id]["tags"][tag]:
                    del self.data[vault_id]["tags"][tag]
            
            # Clean lists
            for list_name in list(self.data[vault_id].get("lists", {}).keys()):
                dates = self.data[vault_id]["lists"][list_name]
                self.data[vault_id]["lists"][list_name] = {
                    d: count for d, count in dates.items()
                    if d >= cutoff_str
                }
                # Remove empty entries
                if not self.data[vault_id]["lists"][list_name]:
                    del self.data[vault_id]["lists"][list_name]
        
        self._save()
