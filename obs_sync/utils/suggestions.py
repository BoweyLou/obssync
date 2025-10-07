"""
Smart routing suggestion analyzer for vault→list mappings and tag routes.

Analyzes historical task data from both Obsidian and Reminders to suggest
optimal routing configurations based on tag usage patterns and completion history.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import logging

from ..core.models import SyncConfig, Vault, RemindersList, TaskStatus
from ..obsidian.tasks import ObsidianTaskManager
from ..reminders.tasks import RemindersTaskManager
from ..core.exceptions import RemindersError, AuthorizationError


@dataclass
class VaultMappingSuggestion:
    """Suggestion for vault→list mapping."""
    vault_id: str
    vault_name: str
    suggested_list_id: str
    suggested_list_name: str
    confidence: float  # 0.0 to 1.0
    reasoning: str
    tag_overlap: int  # Number of overlapping tags


@dataclass
class TagRouteSuggestion:
    """Suggestion for tag-based routing."""
    vault_id: str
    tag: str
    suggested_list_id: str
    suggested_list_name: str
    tag_frequency: int
    completion_rate: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0
    reasoning: str


class SuggestionAnalyzer:
    """Analyzes task data to generate smart routing suggestions."""
    
    def __init__(
        self,
        config: SyncConfig,
        obs_manager: Optional[ObsidianTaskManager] = None,
        rem_manager: Optional[RemindersTaskManager] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize the suggestion analyzer.
        
        Args:
            config: Current sync configuration
            obs_manager: Obsidian task manager (created if not provided)
            rem_manager: Reminders task manager (created if not provided)
            logger: Optional logger instance
        """
        self.config = config
        self.obs_manager = obs_manager or ObsidianTaskManager(logger=logger)
        self.rem_manager = rem_manager or RemindersTaskManager(logger=logger)
        self.logger = logger or logging.getLogger(__name__)
        
    def analyze_vault_mapping_suggestions(
        self,
        vault: Vault,
        min_confidence: float = 0.3,
    ) -> List[VaultMappingSuggestion]:
        """
        Suggest vault→list mappings based on tag overlap analysis.
        
        Strategy:
        1. Analyze tags in the Obsidian vault
        2. Analyze tags in each Reminders list
        3. Calculate overlap scores
        4. Rank lists by tag overlap and completion rates
        
        Args:
            vault: The vault to analyze
            min_confidence: Minimum confidence threshold (0.0-1.0)
            
        Returns:
            List of suggestions sorted by confidence (highest first)
        """
        suggestions = []
        
        try:
            # Get Obsidian tasks and extract tag frequencies
            obs_tasks = self.obs_manager.list_tasks(vault.path, include_completed=True)
            vault_tag_counts = self._count_tags(obs_tasks)
            
            if not vault_tag_counts:
                self.logger.debug(f"No tags found in vault {vault.name}")
                return []
            
            # Get Reminders tasks for all available lists
            all_list_ids = [lst.identifier for lst in self.config.reminders_lists]
            rem_tasks = self.rem_manager.list_tasks(list_ids=all_list_ids, include_completed=True)
            
            # Group Reminders tasks by list
            tasks_by_list = defaultdict(list)
            for task in rem_tasks:
                tasks_by_list[task.calendar_id].append(task)
            
            # Analyze each list for tag overlap
            for lst in self.config.reminders_lists:
                list_tasks = tasks_by_list.get(lst.identifier, [])
                if not list_tasks:
                    continue
                    
                list_tag_counts = self._count_tags(list_tasks)
                if not list_tag_counts:
                    continue
                
                # Calculate overlap metrics
                overlap_tags = set(vault_tag_counts.keys()) & set(list_tag_counts.keys())
                overlap_count = len(overlap_tags)
                
                if overlap_count == 0:
                    continue
                
                # Calculate completion rate for overlapping tags
                completion_rate = self._calculate_completion_rate(
                    list_tasks, 
                    filter_tags=overlap_tags
                )
                
                # Calculate confidence score
                # Factors: tag overlap, completion rate, tag frequency alignment
                vault_total = sum(vault_tag_counts.values())
                overlap_frequency = sum(vault_tag_counts[tag] for tag in overlap_tags)
                frequency_ratio = overlap_frequency / vault_total if vault_total > 0 else 0
                
                confidence = (
                    0.4 * min(overlap_count / 5, 1.0) +  # More overlap = higher confidence (cap at 5 tags)
                    0.3 * completion_rate +  # Higher completion = higher confidence
                    0.3 * frequency_ratio  # More frequent tags overlap = higher confidence
                )
                
                if confidence >= min_confidence:
                    reasoning = self._build_vault_mapping_reasoning(
                        overlap_tags, completion_rate, vault_tag_counts, list_tag_counts
                    )
                    
                    suggestions.append(VaultMappingSuggestion(
                        vault_id=vault.vault_id,
                        vault_name=vault.name,
                        suggested_list_id=lst.identifier,
                        suggested_list_name=lst.name,
                        confidence=confidence,
                        reasoning=reasoning,
                        tag_overlap=overlap_count,
                    ))
            
            # Sort by confidence (highest first)
            suggestions.sort(key=lambda s: s.confidence, reverse=True)
            
        except (RemindersError, AuthorizationError) as e:
            self.logger.warning(f"Cannot analyze Reminders data: {e}")
        except Exception as e:
            self.logger.error(f"Error analyzing vault mapping suggestions: {e}")
        
        return suggestions
    
    def analyze_tag_route_suggestions(
        self,
        vault: Vault,
        default_list_id: Optional[str] = None,
        min_frequency: int = 3,
        min_confidence: float = 0.4,
    ) -> List[TagRouteSuggestion]:
        """
        Suggest tag→list routes based on completion history.
        
        Strategy:
        1. Find frequent tags in the vault
        2. For each tag, check which lists have completed tasks with that tag
        3. Calculate confidence based on completion rate and frequency
        4. Exclude suggestions for the default list (already the fallback)
        
        Args:
            vault: The vault to analyze
            default_list_id: Default list to exclude from suggestions
            min_frequency: Minimum tag frequency threshold
            min_confidence: Minimum confidence threshold (0.0-1.0)
            
        Returns:
            List of suggestions sorted by confidence (highest first)
        """
        suggestions = []
        
        try:
            # Get Obsidian tasks and extract tag frequencies
            obs_tasks = self.obs_manager.list_tasks(vault.path, include_completed=True)
            vault_tag_counts = self._count_tags(obs_tasks)
            
            # Filter to frequent tags
            frequent_tags = {
                tag: count 
                for tag, count in vault_tag_counts.items() 
                if count >= min_frequency
            }
            
            if not frequent_tags:
                self.logger.debug(f"No frequent tags found in vault {vault.name}")
                return []
            
            # Get Reminders tasks for all available lists
            all_list_ids = [lst.identifier for lst in self.config.reminders_lists]
            rem_tasks = self.rem_manager.list_tasks(list_ids=all_list_ids, include_completed=True)
            
            # Group Reminders tasks by list
            tasks_by_list = defaultdict(list)
            for task in rem_tasks:
                tasks_by_list[task.calendar_id].append(task)
            
            # Analyze each frequent tag
            for tag, frequency in frequent_tags.items():
                # Find lists that have this tag
                list_scores = []
                
                for lst in self.config.reminders_lists:
                    # Skip the default list (no need to route there explicitly)
                    if lst.identifier == default_list_id:
                        continue
                    
                    list_tasks = tasks_by_list.get(lst.identifier, [])
                    if not list_tasks:
                        continue
                    
                    # Find tasks with this tag
                    tagged_tasks = [
                        t for t in list_tasks 
                        if tag in (getattr(t, 'tags', None) or [])
                    ]
                    
                    if not tagged_tasks:
                        continue
                    
                    # Calculate completion rate for this tag in this list
                    completed_count = sum(
                        1 for t in tagged_tasks 
                        if t.status == TaskStatus.DONE
                    )
                    completion_rate = completed_count / len(tagged_tasks) if tagged_tasks else 0
                    
                    # Calculate confidence
                    # Factors: completion rate, task count, frequency in vault
                    task_count_score = min(len(tagged_tasks) / 10, 1.0)  # Cap at 10 tasks
                    frequency_score = min(frequency / 20, 1.0)  # Cap at 20 occurrences
                    
                    confidence = (
                        0.5 * completion_rate +  # Higher completion = higher confidence
                        0.3 * task_count_score +  # More tasks = higher confidence
                        0.2 * frequency_score  # More frequent in vault = higher confidence
                    )
                    
                    if confidence >= min_confidence:
                        list_scores.append((lst, completion_rate, confidence, len(tagged_tasks)))
                
                # Create suggestion for the best-scoring list
                if list_scores:
                    # Sort by confidence
                    list_scores.sort(key=lambda x: x[2], reverse=True)
                    best_list, completion_rate, confidence, task_count = list_scores[0]
                    
                    reasoning = self._build_tag_route_reasoning(
                        tag, frequency, completion_rate, task_count
                    )
                    
                    suggestions.append(TagRouteSuggestion(
                        vault_id=vault.vault_id,
                        tag=tag,
                        suggested_list_id=best_list.identifier,
                        suggested_list_name=best_list.name,
                        tag_frequency=frequency,
                        completion_rate=completion_rate,
                        confidence=confidence,
                        reasoning=reasoning,
                    ))
            
            # Sort by confidence (highest first)
            suggestions.sort(key=lambda s: s.confidence, reverse=True)
            
        except (RemindersError, AuthorizationError) as e:
            self.logger.warning(f"Cannot analyze Reminders data: {e}")
        except Exception as e:
            self.logger.error(f"Error analyzing tag route suggestions: {e}")
        
        return suggestions
    
    def _count_tags(self, tasks) -> Counter:
        """
        Count tag frequencies across tasks.
        
        Args:
            tasks: List of ObsidianTask or RemindersTask objects
            
        Returns:
            Counter of tag frequencies
        """
        counts = Counter()
        for task in tasks:
            tags = getattr(task, 'tags', None) or []
            for tag in tags:
                # Normalize tag (remove # if present, lowercase)
                normalized = SyncConfig._normalize_tag_value(tag)
                if normalized and not normalized.startswith('#from-'):
                    counts[normalized] = counts.get(normalized, 0) + 1
        return counts
    
    def _calculate_completion_rate(
        self, 
        tasks, 
        filter_tags: Optional[set] = None
    ) -> float:
        """
        Calculate task completion rate.
        
        Args:
            tasks: List of tasks to analyze
            filter_tags: Optional set of tags to filter by
            
        Returns:
            Completion rate (0.0 to 1.0)
        """
        if filter_tags:
            # Filter to tasks with at least one of the specified tags
            filtered_tasks = []
            for task in tasks:
                task_tags = set(
                    SyncConfig._normalize_tag_value(tag)
                    for tag in (getattr(task, 'tags', None) or [])
                )
                if task_tags & filter_tags:
                    filtered_tasks.append(task)
            tasks = filtered_tasks
        
        if not tasks:
            return 0.0
        
        completed = sum(1 for t in tasks if t.status == TaskStatus.DONE)
        return completed / len(tasks)
    
    def _build_vault_mapping_reasoning(
        self,
        overlap_tags: set,
        completion_rate: float,
        vault_tag_counts: Counter,
        list_tag_counts: Counter,
    ) -> str:
        """Build human-readable reasoning for vault mapping suggestion."""
        # Find top overlapping tags
        top_tags = sorted(
            overlap_tags, 
            key=lambda t: vault_tag_counts[t], 
            reverse=True
        )[:3]
        
        tag_examples = ', '.join(f"#{tag}" for tag in top_tags)
        completion_pct = int(completion_rate * 100)
        
        return (
            f"{len(overlap_tags)} shared tags ({tag_examples}), "
            f"{completion_pct}% completion rate"
        )
    
    def _build_tag_route_reasoning(
        self,
        tag: str,
        frequency: int,
        completion_rate: float,
        task_count: int,
    ) -> str:
        """Build human-readable reasoning for tag route suggestion."""
        completion_pct = int(completion_rate * 100)
        return (
            f"{frequency} uses in vault, {task_count} completed tasks "
            f"in this list ({completion_pct}% completion)"
        )
