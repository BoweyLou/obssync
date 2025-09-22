"""Main sync engine orchestrating the synchronization process."""

from typing import List, Dict, Optional, Set
from datetime import datetime, timezone
import uuid
import json
import os
from ..core.models import ObsidianTask, RemindersTask, SyncLink, TaskStatus
from ..obsidian.tasks import ObsidianTaskManager
from ..reminders.tasks import RemindersTaskManager
from .matcher import TaskMatcher
from .resolver import ConflictResolver
import logging


class SyncEngine:
    """Main engine for bidirectional task synchronization."""

    def __init__(
        self,
        config: Dict,
        logger: Optional[logging.Logger] = None,
        direction: str = "both",
    ):
        self.config = config
        self.direction = direction
        self.logger = logger or logging.getLogger(__name__)

        # Initialize components
        self.obs_manager = ObsidianTaskManager(logger=self.logger)
        self.rem_manager = RemindersTaskManager(logger=self.logger)
        
        # Set include_completed flag from config
        include_completed = config.get("include_completed", True)
        self.obs_manager.include_completed = include_completed
        self.rem_manager.include_completed = include_completed
        
        self.matcher = TaskMatcher(
            min_score=config.get("min_score", 0.75),
            days_tolerance=config.get("days_tolerance", 1),
            logger=self.logger,
        )
        self.resolver = ConflictResolver(logger=self.logger)

        # Track changes
        self.changes_made = {
            "obs_updated": 0,
            "rem_updated": 0,
            "obs_created": 0,
            "rem_created": 0,
            "links_created": 0,
            "conflicts_resolved": 0,
        }
        
        # Store vault path and config for task creation
        self.vault_path = None
        self.inbox_path = config.get("obsidian_inbox_path", "AppleRemindersInbox.md")
        self.default_calendar_id = config.get("default_calendar_id")
        self.links_path = config.get("links_path", "~/.config/sync_links.json")

    def sync(
        self,
        vault_path: str,
        list_ids: Optional[List[str]] = None,
        dry_run: bool = True,
    ) -> Dict:
        """
        Perform bidirectional sync between Obsidian and Reminders.

        Returns dict with sync results and statistics.
        """
        self.logger.info("Starting sync (dry_run=%s, direction=%s)", dry_run, self.direction)

        # Reset counters for this run
        self.changes_made = {
            "obs_updated": 0,
            "rem_updated": 0,
            "obs_created": 0,
            "rem_created": 0,
            "links_created": 0,
            "conflicts_resolved": 0,
        }
        
        # Store vault path for creation operations
        self.vault_path = vault_path

        # 1. Collect tasks from both systems
        # Always include completed tasks for matching to detect status changes
        user_include_completed = self.config.get("include_completed", True)
        
        self.logger.info("Collecting Obsidian tasks (including completed for matching)...")
        obs_tasks_all = self.obs_manager.list_tasks(vault_path, include_completed=True)
        
        self.logger.info("Collecting Reminders tasks (including completed for matching)...")
        rem_tasks_all = self.rem_manager.list_tasks(list_ids, include_completed=True)
        
        # Filter for display purposes based on user preference
        if user_include_completed:
            obs_tasks = obs_tasks_all
            rem_tasks = rem_tasks_all
        else:
            obs_tasks = [t for t in obs_tasks_all if t.status != TaskStatus.DONE]
            rem_tasks = [t for t in rem_tasks_all if t.status != TaskStatus.DONE]
        
        self.logger.info(f"Found {len(obs_tasks_all)} total Obsidian tasks ({len(obs_tasks)} for processing)")
        self.logger.info(f"Found {len(rem_tasks_all)} total Reminders tasks ({len(rem_tasks)} for processing)")
        if not user_include_completed:
            self.logger.info("Note: Completed tasks included for matching but excluded from counts")
        
        # 2. Load existing links and find matches
        self.logger.info("Loading existing links...")
        existing_links = self._load_existing_links()
        
        self.logger.info("Finding task matches...")
        # Use all tasks (including completed) for matching to detect status changes
        links = self.matcher.find_matches(obs_tasks_all, rem_tasks_all, existing_links)
        self.logger.info(f"Found {len(links)} matched pairs")
        
        # 3. Identify unmatched tasks
        matched_obs_uuids = {link.obs_uuid for link in links}
        matched_rem_uuids = {link.rem_uuid for link in links}
        
        # Find unmatched tasks, but exclude completed ones from counterpart creation
        unmatched_obs_all = [t for t in obs_tasks_all if t.uuid not in matched_obs_uuids]
        unmatched_rem_all = [t for t in rem_tasks_all if t.uuid not in matched_rem_uuids]
        
        # Filter out completed tasks from counterpart creation
        unmatched_obs = [t for t in unmatched_obs_all if t.status != TaskStatus.DONE]
        unmatched_rem = [t for t in unmatched_rem_all if t.status != TaskStatus.DONE]
        
        self.logger.info(f"Found {len(unmatched_obs_all)} total unmatched Obsidian tasks ({len(unmatched_obs)} active)")
        self.logger.info(f"Found {len(unmatched_rem_all)} total unmatched Reminders tasks ({len(unmatched_rem)} active)")
        
        # 4. Create counterpart tasks for unmatched items
        new_links = self._create_counterparts(unmatched_obs, unmatched_rem, list_ids, dry_run)
        links.extend(new_links)
        
        # 5. Process each link
        for link in links:
            obs_task = self._find_task(obs_tasks_all, link.obs_uuid)
            rem_task = self._find_task(rem_tasks_all, link.rem_uuid)
            
            if not obs_task or not rem_task:
                continue
            
            # Resolve conflicts
            conflicts = self.resolver.resolve_conflicts(obs_task, rem_task)
            
            # Apply changes based on conflict resolution
            self._apply_sync_changes(obs_task, rem_task, conflicts, dry_run)
        
        # 6. Save links to persistent storage
        if not dry_run and links:
            self._persist_links(links)
        
        # Return results
        return {
            'success': True,
            'obs_tasks': len(obs_tasks),
            'rem_tasks': len(rem_tasks),
            'links': len(links),
            'changes': self.changes_made,
            'dry_run': dry_run
        }
    
    def _find_task(self, tasks: List, uuid: str):
        """Find task by UUID."""
        for task in tasks:
            if task.uuid == uuid:
                return task
        return None
    
    def _apply_sync_changes(
        self,
        obs_task: ObsidianTask,
        rem_task: RemindersTask,
        conflicts: Dict[str, str],
        dry_run: bool,
    ) -> None:
        """Apply sync changes based on conflict resolution."""

        allow_obs_updates = self.direction in ("both", "rem-to-obs")
        allow_rem_updates = self.direction in ("both", "obs-to-rem")
        change_applied = False

        # Status sync
        if conflicts["status_winner"] == "obs" and allow_rem_updates:
            new_status = "done" if obs_task.status == TaskStatus.DONE else "todo"
            if not dry_run:
                self.rem_manager.update_task(rem_task, {"status": new_status})
            self.changes_made["rem_updated"] += 1
            change_applied = True
            self.logger.debug("Queued Reminders status update for %s", rem_task.title)

        elif conflicts["status_winner"] == "rem" and allow_obs_updates:
            new_status = TaskStatus.DONE if rem_task.status == TaskStatus.DONE else TaskStatus.TODO
            if not dry_run:
                self.obs_manager.update_task(obs_task, {"status": new_status})
            self.changes_made["obs_updated"] += 1
            change_applied = True
            self.logger.debug("Queued Obsidian status update for %s", obs_task.description)

        # Title / description sync
        if conflicts["title_winner"] == "obs" and allow_rem_updates:
            if not dry_run:
                self.rem_manager.update_task(rem_task, {"title": obs_task.description})
            self.changes_made["rem_updated"] += 1
            change_applied = True

        elif conflicts["title_winner"] == "rem" and allow_obs_updates:
            if not dry_run:
                self.obs_manager.update_task(obs_task, {"description": rem_task.title})
            self.changes_made["obs_updated"] += 1
            change_applied = True

        # Due date sync
        if conflicts["due_winner"] == "obs" and allow_rem_updates:
            if not dry_run:
                self.rem_manager.update_task(rem_task, {"due_date": obs_task.due_date})
            self.changes_made["rem_updated"] += 1
            change_applied = True

        elif conflicts["due_winner"] == "rem" and allow_obs_updates:
            if not dry_run:
                self.obs_manager.update_task(obs_task, {"due_date": rem_task.due_date})
            self.changes_made["obs_updated"] += 1
            change_applied = True

        # Priority sync
        if conflicts["priority_winner"] == "obs" and allow_rem_updates:
            if not dry_run:
                self.rem_manager.update_task(rem_task, {"priority": obs_task.priority})
            self.changes_made["rem_updated"] += 1
            change_applied = True

        elif conflicts["priority_winner"] == "rem" and allow_obs_updates:
            if not dry_run:
                self.obs_manager.update_task(obs_task, {"priority": rem_task.priority})
            self.changes_made["obs_updated"] += 1
            change_applied = True

        if change_applied:
            self.changes_made["conflicts_resolved"] += 1
    
    def _create_counterparts(self, unmatched_obs: List[ObsidianTask],
                             unmatched_rem: List[RemindersTask],
                             list_ids: Optional[List[str]],
                             dry_run: bool) -> List[SyncLink]:
        """Create counterpart tasks for unmatched items."""
        new_links = []
        
        # Create Reminders tasks for unmatched Obsidian tasks
        if self.direction in ("both", "obs-to-rem") and unmatched_obs:
            # Determine target calendar
            calendar_id = self.default_calendar_id
            if not calendar_id and list_ids:
                calendar_id = list_ids[0]
            
            if calendar_id:
                for obs_task in unmatched_obs:
                    self.logger.debug(f"Creating Reminders task for: {obs_task.description}")
                    
                    # Create RemindersTask object
                    rem_task = RemindersTask(
                        uuid=f"rem-{uuid.uuid4().hex[:8]}",
                        item_id="",  # Will be set by gateway
                        calendar_id=calendar_id,
                        list_name="",  # Will be set by gateway
                        status=obs_task.status,
                        title=obs_task.description,
                        due_date=obs_task.due_date,
                        priority=obs_task.priority,
                        notes="Created from Obsidian",
                        created_at=datetime.now(timezone.utc).isoformat(),
                        modified_at=datetime.now(timezone.utc).isoformat(),
                    )
                    
                    if not dry_run:
                        # Actually create the task
                        created_task = self.rem_manager.create_task(calendar_id, rem_task)
                        if created_task:
                            # Create a link for the new pair
                            link = SyncLink(
                                obs_uuid=obs_task.uuid,
                                rem_uuid=created_task.uuid,
                                score=1.0,  # Perfect match as it's a copy
                                last_synced=datetime.now(timezone.utc).isoformat(),
                            )
                            new_links.append(link)
                    
                    # Count both actual and planned creations
                    self.changes_made["rem_created"] += 1
                    self.changes_made["links_created"] += 1
            else:
                self.logger.warning("No calendar ID available for creating Reminders tasks")
        
        # Create Obsidian tasks for unmatched Reminders tasks
        if self.direction in ("both", "rem-to-obs") and unmatched_rem:
            for rem_task in unmatched_rem:
                self.logger.debug(f"Creating Obsidian task for: {rem_task.title}")
                
                # Create ObsidianTask object
                obs_task = ObsidianTask(
                    uuid=f"obs-{uuid.uuid4().hex[:8]}",
                    vault_id=os.path.basename(self.vault_path),
                    vault_name=os.path.basename(self.vault_path),
                    vault_path=self.vault_path,
                    file_path=self.inbox_path,
                    line_number=0,  # Will be set when created
                    block_id=None,  # Will be set when created
                    status=rem_task.status,
                    description=rem_task.title,
                    raw_line="",  # Will be set when created
                    due_date=rem_task.due_date,
                    completion_date=None,
                    priority=rem_task.priority,
                    tags=["#from-reminders"],
                    created_at=datetime.now(timezone.utc).isoformat(),
                    modified_at=datetime.now(timezone.utc).isoformat(),
                )
                
                if not dry_run:
                    # Actually create the task
                    created_task = self.obs_manager.create_task(
                        self.vault_path, self.inbox_path, obs_task
                    )
                    if created_task:
                        # Create a link for the new pair
                        link = SyncLink(
                            obs_uuid=created_task.uuid,
                            rem_uuid=rem_task.uuid,
                            score=1.0,  # Perfect match as it's a copy
                            last_synced=datetime.now(timezone.utc).isoformat(),
                        )
                        new_links.append(link)
                
                # Count both actual and planned creations
                self.changes_made["obs_created"] += 1
                self.changes_made["links_created"] += 1
        
        return new_links
    
    def _load_existing_links(self) -> List[SyncLink]:
        """Load existing sync links from file."""
        try:
            links_path = os.path.expanduser(self.links_path)
            if not os.path.exists(links_path):
                return []
            
            with open(links_path, 'r') as f:
                data = json.load(f)
                links = []
                for link_data in data.get('links', []):
                    link = SyncLink.from_dict(link_data)
                    links.append(link)
                
                self.logger.debug(f"Loaded {len(links)} existing links")
                return links
        except Exception as e:
            self.logger.error(f"Failed to load existing links: {e}")
            return []
    
    def _persist_links(self, links: List[SyncLink]) -> None:
        """Persist sync links to file."""
        try:
            # Expand path
            links_path = os.path.expanduser(self.links_path)
            
            # Load existing links if file exists
            existing_links = {}
            if os.path.exists(links_path):
                try:
                    with open(links_path, 'r') as f:
                        data = json.load(f)
                        for link_data in data.get('links', []):
                            key = f"{link_data['obs_uuid']}:{link_data['rem_uuid']}"
                            existing_links[key] = link_data
                except (json.JSONDecodeError, KeyError):
                    pass
            
            # Update with new/modified links
            for link in links:
                key = f"{link.obs_uuid}:{link.rem_uuid}"
                existing_links[key] = link.to_dict()
            
            # Save back to file
            os.makedirs(os.path.dirname(links_path), exist_ok=True)
            with open(links_path, 'w') as f:
                json.dump(
                    {'links': list(existing_links.values())},
                    f,
                    indent=2
                )
            
            self.logger.debug(f"Persisted {len(links)} links to {links_path}")
        except Exception as e:
            self.logger.error(f"Failed to persist links: {e}")