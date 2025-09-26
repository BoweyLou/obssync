"""Task deduplication module for obs-sync.

Detects and manages duplicate tasks across Obsidian and Reminders.
Duplicates are defined as tasks with identical description text.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Union, Tuple
import logging
from collections import defaultdict

from ..core.models import ObsidianTask, RemindersTask, TaskStatus


@dataclass
class DuplicateCluster:
    """Represents a cluster of duplicate tasks."""
    description: str
    obsidian_tasks: List[ObsidianTask]
    reminders_tasks: List[RemindersTask]
    linked_counterparts: Optional[Dict[str, str]] = field(default_factory=dict)  # Maps task UUID to its linked counterpart UUID
    
    @property
    def total_count(self) -> int:
        """Total number of tasks in this cluster."""
        return len(self.obsidian_tasks) + len(self.reminders_tasks)
    
    @property
    def has_duplicates(self) -> bool:
        """True if cluster contains actual duplicates, not just a sync pair.
        
        A cluster is considered to have duplicates if:
        - It has 2+ tasks in the same system (Obsidian or Reminders)
        - It has 3+ total tasks (indicating at least one duplicate)
        
        A single Obsidian + single Reminders task is likely a sync pair, not duplicates.
        """
        obs_count = len(self.obsidian_tasks)
        rem_count = len(self.reminders_tasks)
        
        # Multiple tasks in either system = duplicates
        if obs_count > 1 or rem_count > 1:
            return True
        
        # Single task in each system = likely sync pair, not duplicates
        if obs_count == 1 and rem_count == 1:
            return False
            
        # Any other case with multiple tasks
        return self.total_count > 1
    
    def get_all_tasks(self) -> List[Union[ObsidianTask, RemindersTask]]:
        """Get all tasks in the cluster."""
        return list(self.obsidian_tasks) + list(self.reminders_tasks)
    
    def get_task_by_index(self, index: int) -> Optional[Union[ObsidianTask, RemindersTask]]:
        """Get task by its display index (0-based)."""
        all_tasks = self.get_all_tasks()
        if 0 <= index < len(all_tasks):
            return all_tasks[index]
        return None


@dataclass 
class DeduplicationResults:
    """Results from deduplication analysis."""
    clusters: List[DuplicateCluster]
    total_tasks: int
    duplicate_tasks: int
    duplicate_clusters: int
    
    def get_duplicate_clusters(self) -> List[DuplicateCluster]:
        """Get only clusters that have duplicates."""
        return [cluster for cluster in self.clusters if cluster.has_duplicates]


class TaskDeduplicator:
    """Detects and manages task duplicates."""
    
    def __init__(self, 
                 obs_manager=None,
                 rem_manager=None,
                 logger: Optional[logging.Logger] = None):
        # Use lazy imports to avoid circular dependencies
        if obs_manager is None:
            from ..obsidian.tasks import ObsidianTaskManager
            obs_manager = ObsidianTaskManager()
        if rem_manager is None:
            from ..reminders.tasks import RemindersTaskManager
            rem_manager = RemindersTaskManager()
            
        self.obs_manager = obs_manager
        self.rem_manager = rem_manager
        self.logger = logger or logging.getLogger(__name__)
    
    def analyze_duplicates(self, 
                          obs_tasks: List[ObsidianTask],
                          rem_tasks: List[RemindersTask],
                          existing_links: Optional[List] = None) -> DeduplicationResults:
        """
        Analyze tasks for duplicates across both systems.
        
        Args:
            obs_tasks: List of Obsidian tasks
            rem_tasks: List of Reminders tasks
            existing_links: List of existing sync links to exclude from duplicate detection
            
        Returns:
            DeduplicationResults with all duplicate clusters found
        """
        self.logger.info("Analyzing %d Obsidian and %d Reminders tasks for duplicates", 
                        len(obs_tasks), len(rem_tasks))
        
        # Create sets of already-linked task UUIDs and mappings for counterpart display
        linked_obs_uuids = set()
        linked_rem_uuids = set()
        # Maps for finding linked counterparts
        obs_to_rem_links = {}  # Obsidian UUID -> Reminders UUID
        rem_to_obs_links = {}  # Reminders UUID -> Obsidian UUID
        
        if existing_links:
            for link in existing_links:
                if hasattr(link, 'obs_uuid') and hasattr(link, 'rem_uuid'):
                    linked_obs_uuids.add(link.obs_uuid)
                    linked_rem_uuids.add(link.rem_uuid)
                    obs_to_rem_links[link.obs_uuid] = link.rem_uuid
                    rem_to_obs_links[link.rem_uuid] = link.obs_uuid
            
            self.logger.info("Excluding %d already-synced Obsidian and %d Reminders tasks",
                           len(linked_obs_uuids), len(linked_rem_uuids))
        
        # Filter out already-linked Obsidian tasks (they have legitimate sync counterparts)
        obs_tasks_filtered = [t for t in obs_tasks if t.uuid not in linked_obs_uuids]
        
        # For Reminders: we need to detect duplicates within the same list even if they have links
        # So we'll separate them into two groups:
        # 1. Reminders with links - only check for same-list duplicates
        # 2. Reminders without links - check for all duplicates
        rem_tasks_with_links = [t for t in rem_tasks if t.uuid in linked_rem_uuids]
        rem_tasks_without_links = [t for t in rem_tasks if t.uuid not in linked_rem_uuids]
        
        self.logger.info("After filtering: %d Obsidian, %d unlinked Reminders, %d linked Reminders for duplicate analysis",
                        len(obs_tasks_filtered), len(rem_tasks_without_links), len(rem_tasks_with_links))
        
        # Group tasks by normalized description
        clusters_dict: Dict[str, DuplicateCluster] = defaultdict(
            lambda: DuplicateCluster("", [], [])
        )
        
        # First, group reminders by list to detect same-list duplicates
        # This includes both linked and unlinked reminders
        reminders_by_list: Dict[str, List[RemindersTask]] = defaultdict(list)
        for task in rem_tasks:
            reminders_by_list[task.calendar_id].append(task)
        
        # Track which reminders are part of same-list duplicate groups
        same_list_duplicates: Set[str] = set()
        same_list_clusters: Dict[str, DuplicateCluster] = {}
        
        # Find duplicates within each reminders list
        for list_id, list_tasks in reminders_by_list.items():
            if len(list_tasks) < 2:
                continue
                
            # Group by normalized title within this list
            list_groups: Dict[str, List[RemindersTask]] = defaultdict(list)
            for task in list_tasks:
                normalized = self._normalize_description(task.title)
                list_groups[normalized].append(task)
            
            # Add duplicate groups from this list
            for normalized, group in list_groups.items():
                if len(group) > 1:
                    # This is a same-list duplicate group
                    # Use a unique key that includes the list ID to prevent cross-list merging
                    cluster_key = f"{list_id}:{normalized}"
                    
                    # Build linked counterparts map for this cluster
                    linked_map = {}
                    for task in group:
                        if task.uuid in rem_to_obs_links:
                            linked_map[task.uuid] = rem_to_obs_links[task.uuid]
                    
                    same_list_clusters[cluster_key] = DuplicateCluster(
                        group[0].title, [], group, linked_counterparts=linked_map if linked_map else None
                    )
                    # Mark these reminders as same-list duplicates
                    for task in group:
                        same_list_duplicates.add(task.uuid)
        
        # Process filtered Obsidian tasks
        for task in obs_tasks_filtered:
            normalized_desc = self._normalize_description(task.description)
            if normalized_desc not in clusters_dict:
                clusters_dict[normalized_desc] = DuplicateCluster(
                    task.description, [], [], linked_counterparts={}
                )
            clusters_dict[normalized_desc].obsidian_tasks.append(task)
            # Track if this task has a linked counterpart
            if task.uuid in obs_to_rem_links:
                if clusters_dict[normalized_desc].linked_counterparts is None:
                    clusters_dict[normalized_desc].linked_counterparts = {}
                clusters_dict[normalized_desc].linked_counterparts[task.uuid] = obs_to_rem_links[task.uuid]
        
        # Process unlinked Reminders tasks that aren't already in same-list duplicate groups
        for task in rem_tasks_without_links:
            if task.uuid not in same_list_duplicates:
                # Use title for Reminders tasks
                normalized_desc = self._normalize_description(task.title)
                if normalized_desc not in clusters_dict:
                    clusters_dict[normalized_desc] = DuplicateCluster(
                        task.title, [], [], linked_counterparts={}
                    )
                # Only add if not already added as part of same-list duplicate
                if task not in clusters_dict[normalized_desc].reminders_tasks:
                    clusters_dict[normalized_desc].reminders_tasks.append(task)
        
        # Merge same-list clusters with cross-system clusters
        # Add same-list clusters that don't have cross-system matches
        for cluster_key, cluster in same_list_clusters.items():
            clusters_dict[cluster_key] = cluster
        
        # Convert to list and calculate stats
        clusters = list(clusters_dict.values())
        duplicate_clusters = [c for c in clusters if c.has_duplicates]
        duplicate_task_count = sum(c.total_count for c in duplicate_clusters)
        
        # Total unique tasks analyzed (avoiding double-counting)
        unique_tasks_analyzed = len(obs_tasks_filtered) + len(rem_tasks)
        
        results = DeduplicationResults(
            clusters=clusters,
            total_tasks=unique_tasks_analyzed,
            duplicate_tasks=duplicate_task_count,
            duplicate_clusters=len(duplicate_clusters)
        )
        
        self.logger.info("Found %d duplicate clusters affecting %d tasks", 
                        results.duplicate_clusters, results.duplicate_tasks)
        
        return results
    
    def _normalize_description(self, description: Optional[str]) -> str:
        """
        Normalize task description for duplicate detection.
        
        Args:
            description: Task description text
            
        Returns:
            Normalized description for comparison
        """
        if not description:
            return ""
        
        # Convert to lowercase and strip whitespace
        normalized = description.lower().strip()
        
        # Remove common task markup (checkboxes, etc.)
        # But keep the core text for exact matching
        import re
        normalized = re.sub(r'^\s*[-\*]\s*\[[x\s]\]\s*', '', normalized)
        normalized = re.sub(r'\s+', ' ', normalized)  # Normalize whitespace
        
        return normalized
    
    def delete_tasks(self, 
                    tasks_to_delete: List[Union[ObsidianTask, RemindersTask]],
                    dry_run: bool = True) -> Dict[str, int]:
        """
        Delete specified tasks.
        
        Args:
            tasks_to_delete: List of tasks to delete
            dry_run: If True, don't actually delete
            
        Returns:
            Dict with deletion counts by type
        """
        results = {"obs_deleted": 0, "rem_deleted": 0}
        
        for task in tasks_to_delete:
            if isinstance(task, ObsidianTask):
                if not dry_run:
                    success = self.obs_manager.delete_task(task)
                    if success:
                        results["obs_deleted"] += 1
                        self.logger.info("Deleted Obsidian task: %s", task.description)
                    else:
                        self.logger.error("Failed to delete Obsidian task: %s", task.description)
                else:
                    results["obs_deleted"] += 1
                    self.logger.info("Would delete Obsidian task: %s", task.description)
            
            elif isinstance(task, RemindersTask):
                if not dry_run:
                    success = self.rem_manager.delete_task(task)
                    if success:
                        results["rem_deleted"] += 1 
                        self.logger.info("Deleted Reminders task: %s", task.title)
                    else:
                        self.logger.error("Failed to delete Reminders task: %s", task.title)
                else:
                    results["rem_deleted"] += 1
                    self.logger.info("Would delete Reminders task: %s", task.title)
        
        return results