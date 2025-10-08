"""Conflict resolution for bidirectional sync."""

from typing import Dict, Optional, Tuple, List, Union
from datetime import datetime
from ..core.models import ObsidianTask, RemindersTask, TaskStatus, Priority
from ..utils.date import dates_equal
import logging


class ConflictResolver:
    """Resolves field-level conflicts during sync."""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
    
    def resolve_conflicts(self, obs_task: ObsidianTask,
                        rem_task: RemindersTask) -> Dict[str, str]:
        """
        Resolve field-level conflicts between tasks.
        
        Returns dict with keys like 'status_winner', 'due_winner' etc.
        Values are 'obs', 'rem', or 'none'.
        """
        results = {}
        
        # Compare modification times
        obs_time = self._parse_time(obs_task.modified_at)
        rem_time = self._parse_time(rem_task.modified_at)
        
        # Status conflict
        if self._status_differs(obs_task.status, rem_task.status):
            winner = self._compare_times(obs_time, rem_time)
            results['status_winner'] = winner
            self.logger.debug(f"Status conflict: obs='{obs_task.status}' vs rem='{rem_task.status}' -> {winner}")
        else:
            results['status_winner'] = 'none'
        
        # Title/description conflict (include URL if present)
        rem_display_title = rem_task.display_title()
        if self._text_differs(obs_task.description, rem_display_title):
            winner = self._compare_times(obs_time, rem_time)
            results['title_winner'] = winner
            self.logger.debug(
                f"Title conflict: obs='{obs_task.description}' vs rem='{rem_display_title}' -> {winner}"
            )
        else:
            results['title_winner'] = 'none'
        
        # Due date conflict
        if self._dates_differ(obs_task.due_date, rem_task.due_date):
            winner = self._compare_times(obs_time, rem_time)
            results['due_winner'] = winner
            self.logger.debug(f"Due date conflict: obs='{obs_task.due_date}' vs rem='{rem_task.due_date}' -> {winner}")
        else:
            results['due_winner'] = 'none'
        
        # Priority conflict
        if self._priority_differs(obs_task.priority, rem_task.priority):
            winner = self._compare_times(obs_time, rem_time)
            results['priority_winner'] = winner
            self.logger.debug(f"Priority conflict: obs='{obs_task.priority}' vs rem='{rem_task.priority}' -> {winner}")
        else:
            results['priority_winner'] = 'none'
        
        # Tag conflict
        if self._tags_differ(obs_task.tags, rem_task.tags):
            # For tags, we prefer merging rather than winner-takes-all
            # unless one side has no tags at all
            if not rem_task.tags and obs_task.tags:
                results['tags_winner'] = 'obs'
            elif not obs_task.tags and rem_task.tags:
                results['tags_winner'] = 'rem'
            else:
                # Both have tags - merge them
                results['tags_winner'] = 'merge'
            
            self.logger.debug(
                f"Tag conflict: obs={obs_task.tags} vs rem={rem_task.tags} -> {results.get('tags_winner', 'none')}"
            )
        else:
            results['tags_winner'] = 'none'
        
        # Log if any conflicts were found
        conflicts_found = [k for k, v in results.items() if v != 'none']
        if conflicts_found:
            self.logger.debug(f"Conflicts found for {obs_task.uuid}: {conflicts_found}")
        
        return results
    
    def _parse_time(self, time_value: Optional[Union[str, datetime]]) -> Optional[datetime]:
        """Parse timestamp from ISO string or datetime object.
        
        Args:
            time_value: Either an ISO 8601 string or a datetime object
            
        Returns:
            datetime object if parsing succeeds, None otherwise
        """
        if not time_value:
            return None
        
        # Already a datetime object (from RemindersTask)
        if isinstance(time_value, datetime):
            return time_value
        
        # Parse ISO string (from ObsidianTask)
        try:
            return datetime.fromisoformat(time_value.replace('Z', '+00:00'))
        except (AttributeError, ValueError):
            return None
    
    def _compare_times(self, obs_time: Optional[datetime],
                      rem_time: Optional[datetime]) -> str:
        """Compare modification times and return winner."""
        if obs_time and rem_time:
            if obs_time > rem_time:
                return 'obs'
            elif rem_time > obs_time:
                return 'rem'
            else:
                return 'none'
        elif obs_time:
            return 'obs'
        elif rem_time:
            return 'rem'
        else:
            return 'none'
    
    def _status_differs(self, obs_status: TaskStatus, rem_status: TaskStatus) -> bool:
        """Check if task statuses differ."""
        return obs_status != rem_status
    
    def _text_differs(self, obs_text: Optional[str], rem_text: Optional[str]) -> bool:
        """Check if text fields differ (with normalization)."""
        # Normalize both texts
        obs_normalized = (obs_text or "").strip()
        rem_normalized = (rem_text or "").strip()
        return obs_normalized != rem_normalized
    
    def _dates_differ(self, obs_date, rem_date) -> bool:
        """Check if dates differ (with tolerance)."""
        # Use zero-day tolerance so any change is detected
        return not dates_equal(obs_date, rem_date, tolerance_days=0)
    
    def _priority_differs(self, obs_priority: Optional[Priority],
                         rem_priority: Optional[Priority]) -> bool:
        """Check if priorities differ."""
        # Treat None and missing priority as equivalent
        return obs_priority != rem_priority
    
    def _tags_differ(self, obs_tags: List[str], rem_tags: List[str]) -> bool:
        """Check if tags differ between tasks."""
        # Normalize tags for comparison (ensure # prefix)
        def normalize(tags):
            return set(tag if tag.startswith('#') else f"#{tag}" for tag in tags)
        
        obs_set = normalize(obs_tags) if obs_tags else set()
        rem_set = normalize(rem_tags) if rem_tags else set()
        
        return obs_set != rem_set
