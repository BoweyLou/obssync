"""Task matching with Hungarian algorithm for optimal pairing."""

from typing import Dict, List, Optional, Tuple
import logging

from ..core.models import ObsidianTask, RemindersTask, SyncLink
from ..utils.date import parse_date
from ..utils.text import dice_similarity, normalize_text_for_similarity


class TaskMatcher:
    """Matches tasks between Obsidian and Reminders using Hungarian algorithm."""
    
    def __init__(self, min_score: float = 0.75, days_tolerance: int = 1,
                 logger: Optional[logging.Logger] = None):
        self.min_score = min_score
        self.days_tolerance = days_tolerance
        self.logger = logger or logging.getLogger(__name__)
        
        # Try to import scipy for Hungarian algorithm
        try:
            from scipy.optimize import linear_sum_assignment
            self.linear_sum_assignment = linear_sum_assignment
            self.has_scipy = True
        except ImportError:
            self.has_scipy = False
            self.logger.warning("scipy not available, falling back to greedy matching")
    
    def find_matches(self, obs_tasks: List[ObsidianTask],
                    rem_tasks: List[RemindersTask],
                    existing_links: Optional[List[SyncLink]] = None) -> List[SyncLink]:
        """Find optimal matches between task lists, prioritizing existing links."""
        if not obs_tasks or not rem_tasks:
            return []
        
        # First, restore valid existing links
        validated_links = []
        used_obs_uuids = set()
        used_rem_uuids = set()
        
        if existing_links:
            obs_uuid_map = {task.uuid: task for task in obs_tasks}
            rem_uuid_map = {task.uuid: task for task in rem_tasks}
            
            for link in existing_links:
                # Check if both tasks still exist
                if (link.obs_uuid in obs_uuid_map and
                    link.rem_uuid in rem_uuid_map):
                    validated_links.append(link)
                    used_obs_uuids.add(link.obs_uuid)
                    used_rem_uuids.add(link.rem_uuid)
            
            self.logger.info(f"Restored {len(validated_links)} existing links")
        
        # Find remaining unmatched tasks
        unmatched_obs = [t for t in obs_tasks if t.uuid not in used_obs_uuids]
        unmatched_rem = [t for t in rem_tasks if t.uuid not in used_rem_uuids]
        
        # Find new matches for unmatched tasks
        if unmatched_obs and unmatched_rem:
            if self.has_scipy and len(unmatched_obs) * len(unmatched_rem) < 10000:
                new_links = self._hungarian_matching(unmatched_obs, unmatched_rem)
            else:
                new_links = self._greedy_matching(unmatched_obs, unmatched_rem)
            validated_links.extend(new_links)
        
        return validated_links
    
    def _calculate_similarity(self, obs_task: ObsidianTask,
                            rem_task: RemindersTask) -> float:
        """Calculate similarity score between two tasks."""
        # Title similarity (70% weight)
        obs_tokens = normalize_text_for_similarity(obs_task.description)
        rem_tokens = normalize_text_for_similarity(rem_task.display_title())
        
        # Special case: If both normalize to empty but raw strings match ignoring case/whitespace
        # This handles cases like URL-only tasks or single "#" tasks
        if not obs_tokens and not rem_tokens:
            # Compare raw strings, ignoring case and whitespace
            obs_raw = (obs_task.description or "").strip().lower()
            rem_raw = (rem_task.title or "").strip().lower()
            # If both are empty/whitespace only, or both are identical
            if obs_raw == rem_raw:
                # Perfect match for identical "empty" tasks
                # This includes both being empty string after strip
                return 1.0
        
        title_sim = dice_similarity(obs_tokens, rem_tokens)
        
        # Due date similarity (25% weight)
        date_score = 0.0
        obs_due = obs_task.due_date
        rem_due = rem_task.due_date

        if isinstance(obs_due, str):
            obs_due = parse_date(obs_due)
        if isinstance(rem_due, str):
            rem_due = parse_date(rem_due)

        if obs_due and rem_due:
            if obs_due == rem_due:
                date_score = 1.0
            else:
                diff_days = abs((obs_due - rem_due).days)
                if diff_days <= self.days_tolerance:
                    date_score = 0.5
        elif not obs_due and not rem_due:
            date_score = 0.5  # Both have no date
        
        # Priority boost (5% weight)
        priority_boost = 0.0
        if obs_task.priority and rem_task.priority:
            if obs_task.priority == rem_task.priority:
                priority_boost = 0.05
        
        # Calculate final score
        score = (0.70 * title_sim) + (0.25 * date_score) + priority_boost
        return min(score, 1.0)
    
    def _hungarian_matching(self, obs_tasks: List[ObsidianTask],
                          rem_tasks: List[RemindersTask]) -> List[SyncLink]:
        """Use Hungarian algorithm for optimal matching."""
        n_obs = len(obs_tasks)
        n_rem = len(rem_tasks)
        
        # Build cost matrix (negative scores since Hungarian minimizes)
        cost_matrix = []
        for i, obs_task in enumerate(obs_tasks):
            row = []
            for j, rem_task in enumerate(rem_tasks):
                score = self._calculate_similarity(obs_task, rem_task)
                if score >= self.min_score:
                    cost = -score  # Negative for minimization
                else:
                    cost = 1000  # High cost for pairs below threshold
                row.append(cost)
            cost_matrix.append(row)
        
        # Run Hungarian algorithm
        row_ind, col_ind = self.linear_sum_assignment(cost_matrix)
        
        # Extract valid matches
        links = []
        for i, j in zip(row_ind, col_ind):
            score = -cost_matrix[i][j]
            if score >= self.min_score:
                link = SyncLink(
                    obs_uuid=obs_tasks[i].uuid,
                    rem_uuid=rem_tasks[j].uuid,
                    score=score
                )
                links.append(link)
        
        self.logger.info(f"Hungarian matching found {len(links)} links")
        return links
    
    def _greedy_matching(self, obs_tasks: List[ObsidianTask],
                        rem_tasks: List[RemindersTask]) -> List[SyncLink]:
        """Fallback greedy matching algorithm."""
        # Calculate all pair scores
        candidates = []
        for obs_task in obs_tasks:
            for rem_task in rem_tasks:
                score = self._calculate_similarity(obs_task, rem_task)
                if score >= self.min_score:
                    candidates.append((obs_task.uuid, rem_task.uuid, score))
        
        # Sort by score descending
        candidates.sort(key=lambda x: -x[2])
        
        # Greedy selection (one-to-one)
        links = []
        used_obs = set()
        used_rem = set()
        
        for obs_uuid, rem_uuid, score in candidates:
            if obs_uuid not in used_obs and rem_uuid not in used_rem:
                link = SyncLink(
                    obs_uuid=obs_uuid,
                    rem_uuid=rem_uuid,
                    score=score
                )
                links.append(link)
                used_obs.add(obs_uuid)
                used_rem.add(rem_uuid)
        
        self.logger.info(f"Greedy matching found {len(links)} links")
        return links
