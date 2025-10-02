"""Main sync engine orchestrating the synchronization process."""

from typing import List, Dict, Optional, Set, Any, Tuple
from datetime import datetime, timezone
import uuid
import json
import os
from ..core.models import ObsidianTask, RemindersTask, SyncLink, TaskStatus, SyncConfig
from ..core.paths import get_path_manager
from ..obsidian.tasks import ObsidianTaskManager
from ..reminders.tasks import RemindersTaskManager
from .matcher import TaskMatcher
from .resolver import ConflictResolver
from ..utils.tags import merge_tags
import logging


class SyncEngine:
    """Main engine for bidirectional task synchronization."""

    def __init__(
        self,
        config: Dict,
        logger: Optional[logging.Logger] = None,
        direction: str = "both",
        sync_config: Optional[SyncConfig] = None,
    ):
        self.config = config
        self.sync_config = sync_config
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
            "obs_deleted": 0,
            "rem_deleted": 0,
            "links_created": 0,
            "links_deleted": 0,
            "conflicts_resolved": 0,
        }
        
        # Track tasks created during the current sync run
        self.created_obs_task_ids: Set[str] = set()
        self.created_rem_task_ids: Set[str] = set()
        
        # Track metadata for Reminders → Obsidian creations (for verbose output)
        self.rem_to_obs_creations: List[Dict[str, Any]] = []
        
        # Store vault path and config for task creation
        self.vault_path = None
        self.vault_id = None
        self.vault_name = None
        self.vault_default_calendar = None
        self.inbox_path = config.get("obsidian_inbox_path", "AppleRemindersInbox.md")
        self.default_calendar_id = config.get("default_calendar_id")
        
        # Use PathManager for default links_path
        manager = get_path_manager()
        default_links_path = str(manager.sync_links_path)
        self.links_path = config.get("links_path", default_links_path)
        
        # Flag to track when links need persisting due to normalization
        self._links_need_persist = False

    def _resolve_vault_for_path(self, vault_path: str) -> Optional[Any]:
        """Resolve vault configuration for a given path with improved normalization.

        Args:
            vault_path: Path to the vault

        Returns:
            Vault object if found, None otherwise
        """
        if not self.sync_config or not vault_path:
            return None

        # Normalize the input path
        normalized_input = os.path.normpath(os.path.abspath(os.path.expanduser(vault_path)))

        for vault in getattr(self.sync_config, "vaults", []):
            if not vault or not hasattr(vault, 'path'):
                continue

            try:
                # Normalize the vault path for comparison
                vault_normalized = os.path.normpath(os.path.abspath(os.path.expanduser(vault.path)))

                # Compare normalized paths
                if vault_normalized == normalized_input:
                    return vault

                # Also try comparing just the resolved real paths (handles symlinks)
                try:
                    if os.path.realpath(vault_normalized) == os.path.realpath(normalized_input):
                        return vault
                except OSError:
                    pass

            except (AttributeError, TypeError, OSError) as e:
                self.logger.debug(f"Error comparing vault path {vault.path}: {e}")
                continue

        return None

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
            "obs_deleted": 0,
            "rem_deleted": 0,
            "links_created": 0,
            "links_deleted": 0,
            "conflicts_resolved": 0,
        }
        self.created_obs_task_ids = set()
        self.created_rem_task_ids = set()
        self.rem_to_obs_creations = []
        
        # Store vault path for creation operations
        self.vault_path = vault_path
        self.vault_id = None
        self.vault_name = os.path.basename(vault_path)
        self.vault_default_calendar = None

        if self.sync_config:
            resolved_vault = self._resolve_vault_for_path(vault_path)

            if resolved_vault:
                self.vault_id = resolved_vault.vault_id
                self.vault_name = resolved_vault.name
                self.vault_default_calendar = self.sync_config.get_vault_mapping(self.vault_id)
                self.logger.debug(f"Resolved vault: {self.vault_name} (ID: {self.vault_id})")
            else:
                # Fallback: use basename as vault_id
                self.vault_id = os.path.basename(vault_path)
                self.logger.warning(f"Could not resolve vault configuration for {vault_path}, using basename: {self.vault_id}")

        if not self.vault_id:
            self.vault_id = os.path.basename(vault_path)

        # Collect all relevant calendar IDs including routed calendars
        requested_list_ids = list(list_ids) if isinstance(list_ids, (list, tuple, set)) else list_ids
        list_ids = list(list_ids) if list_ids else []

        if not list_ids:
            if self.vault_default_calendar:
                list_ids.append(self.vault_default_calendar)
            elif self.default_calendar_id and self.default_calendar_id not in list_ids:
                list_ids.append(self.default_calendar_id)

        # Add calendars from tag routes to ensure routed tasks are always queried
        if self.sync_config and self.vault_id:
            for route in self.sync_config.get_tag_routes_for_vault(self.vault_id):
                calendar_id = route.get("calendar_id")
                if calendar_id and calendar_id not in list_ids:
                    list_ids.append(calendar_id)

        if requested_list_ids and list_ids != list(requested_list_ids):
            self.logger.debug(
                "Augmented requested list IDs %s with routed calendars -> %s",
                requested_list_ids,
                list_ids,
            )

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
        
        # Track current vault task UUIDs for persistence and tagging
        current_obs_uuids = {task.uuid for task in obs_tasks_all}

        # 2. Load existing links and find matches
        self.logger.info("Loading existing links...")
        existing_links = self._load_existing_links()

        # Filter out links that clearly belong to other vaults so matching stays scoped
        excluded_rem_uuids: Set[str] = set()
        excluded_obs_uuids: Set[str] = set()
        if self.vault_id:
            scoped_links = []
            filtered_count = 0
            for link in existing_links:
                link_vault = getattr(link, "vault_id", None)
                if link_vault and link_vault != self.vault_id:
                    filtered_count += 1
                    if getattr(link, "rem_uuid", None):
                        excluded_rem_uuids.add(link.rem_uuid)
                    if getattr(link, "obs_uuid", None):
                        excluded_obs_uuids.add(link.obs_uuid)
                    continue
                scoped_links.append(link)
            if filtered_count:
                self.logger.debug(
                    "Filtered %d links belonging to other vaults (current vault_id=%s)",
                    filtered_count,
                    self.vault_id,
                )
            existing_links = scoped_links

        if excluded_rem_uuids:
            rem_tasks_all = [task for task in rem_tasks_all if task.uuid not in excluded_rem_uuids]
            rem_tasks = [task for task in rem_tasks if task.uuid not in excluded_rem_uuids]
        if excluded_obs_uuids:
            obs_tasks_all = [task for task in obs_tasks_all if task.uuid not in excluded_obs_uuids]
            obs_tasks = [task for task in obs_tasks if task.uuid not in excluded_obs_uuids]
            current_obs_uuids = {task.uuid for task in obs_tasks_all}

        # Attach vault identifiers to legacy links belonging to this vault
        for link in existing_links:
            if not getattr(link, "vault_id", None) and link.obs_uuid in current_obs_uuids:
                link.vault_id = self.vault_id
        
        # 2.1 Normalize existing links to fix stale UUID references
        existing_links = self._normalize_links(existing_links, obs_tasks_all, rem_tasks_all)
        
        # Persist normalized links if any were updated (even in dry-run to fix data)
        if hasattr(self, '_links_need_persist') and self._links_need_persist:
            self.logger.info("Persisting normalized links to fix stale UUID references...")
            self._persist_links(existing_links, current_obs_uuids=current_obs_uuids)
            self._links_need_persist = False

        self.logger.info("Finding task matches...")
        # Pass normalized existing_links to matcher
        links = self.matcher.find_matches(obs_tasks_all, rem_tasks_all, existing_links)

        # Ensure all links are tagged with the current vault identifier
        for link in links:
            if not getattr(link, "vault_id", None):
                link.vault_id = self.vault_id

        # 2.5 Detect orphaned tasks (tasks whose counterpart was deleted) *after* matching
        orphaned_rem_uuids, orphaned_obs_uuids = self._detect_orphaned_tasks(
            existing_links,
            obs_tasks_all,
            rem_tasks_all,
            active_links=links,
        )

        # Defer orphan cleanup until after potential counterpart creation so we
        # can avoid deleting tasks that will be recreated within this run.
        self.logger.debug(
            "Initial orphan detection: rem=%s obs=%s",
            sorted(orphaned_rem_uuids),
            sorted(orphaned_obs_uuids),
        )
        
        self.logger.info(f"Found {len(links)} matched pairs")
        
        # 3. Identify unmatched tasks
        matched_obs_uuids = {link.obs_uuid for link in links}
        matched_rem_uuids = {link.rem_uuid for link in links}
        
        # Find unmatched tasks, but exclude completed ones from counterpart creation
        unmatched_obs_all = [t for t in obs_tasks_all if t.uuid not in matched_obs_uuids]
        unmatched_rem_all = [t for t in rem_tasks_all if t.uuid not in matched_rem_uuids]

        # IMPORTANT: Exclude orphaned tasks from unmatched lists to prevent recreation
        unmatched_obs_all = [t for t in unmatched_obs_all if t.uuid not in orphaned_obs_uuids]
        unmatched_rem_all = [t for t in unmatched_rem_all if t.uuid not in orphaned_rem_uuids]

        # Filter out completed tasks from counterpart creation
        unmatched_obs = [t for t in unmatched_obs_all if t.status != TaskStatus.DONE]
        unmatched_rem = [t for t in unmatched_rem_all if t.status != TaskStatus.DONE]
        
        self.logger.info(f"Found {len(unmatched_obs_all)} total unmatched Obsidian tasks ({len(unmatched_obs)} active)")
        self.logger.info(f"Found {len(unmatched_rem_all)} total unmatched Reminders tasks ({len(unmatched_rem)} active)")
        
        # 4. Create counterpart tasks for unmatched items
        new_links, created_obs_tasks, created_rem_tasks = self._create_counterparts(
            unmatched_obs,
            unmatched_rem,
            list_ids,
            dry_run,
        )
        links.extend(new_links)

        if not dry_run:
            if created_obs_tasks:
                obs_tasks_all.extend(created_obs_tasks)
                current_obs_uuids.update(
                    task.uuid for task in created_obs_tasks if getattr(task, "uuid", None)
                )
                if user_include_completed:
                    obs_tasks.extend(created_obs_tasks)
                else:
                    obs_tasks.extend(
                        [t for t in created_obs_tasks if t.status != TaskStatus.DONE]
                    )
            if created_rem_tasks:
                rem_tasks_all.extend(created_rem_tasks)
                if user_include_completed:
                    rem_tasks.extend(created_rem_tasks)
                else:
                    rem_tasks.extend(
                        [t for t in created_rem_tasks if t.status != TaskStatus.DONE]
                    )

        # Re-evaluate orphaned tasks now that new counterparts may have been created
        final_orphaned_rem_uuids, final_orphaned_obs_uuids = self._detect_orphaned_tasks(
            existing_links,
            obs_tasks_all,
            rem_tasks_all,
            active_links=links,
        )

        # Never delete tasks that were created within this run
        final_orphaned_rem_uuids = {
            uuid for uuid in final_orphaned_rem_uuids if uuid not in self.created_rem_task_ids
        }
        final_orphaned_obs_uuids = {
            uuid for uuid in final_orphaned_obs_uuids if uuid not in self.created_obs_task_ids
        }

        if final_orphaned_rem_uuids:
            self.logger.info(
                "Found %d orphaned Reminders tasks (Obsidian counterparts deleted)",
                len(final_orphaned_rem_uuids),
            )
        if final_orphaned_obs_uuids:
            self.logger.info(
                "Found %d orphaned Obsidian tasks (Reminders counterparts deleted)",
                len(final_orphaned_obs_uuids),
            )

        # Handle orphaned tasks based on sync direction using the filtered sets
        if self.direction in ("both", "obs-to-rem") and final_orphaned_rem_uuids:
            for rem_uuid in final_orphaned_rem_uuids:
                rem_task = self._find_task(rem_tasks_all, rem_uuid)
                if rem_task and not dry_run:
                    self.logger.info("Deleting orphaned Reminders task: %s", rem_task.title)
                    self.rem_manager.delete_task(rem_task)
                elif not rem_task:
                    self.logger.debug(
                        "Skipping delete for orphaned Reminders task %s (task not found)",
                        rem_uuid,
                    )
                self.changes_made["rem_deleted"] = self.changes_made.get("rem_deleted", 0) + 1

                existing_links = [
                    link for link in existing_links if link.rem_uuid != rem_uuid
                ]
                links = [link for link in links if link.rem_uuid != rem_uuid]
                self.changes_made["links_deleted"] = self.changes_made.get("links_deleted", 0) + 1

        if self.direction in ("both", "rem-to-obs") and final_orphaned_obs_uuids:
            for obs_uuid in final_orphaned_obs_uuids:
                obs_task = self._find_task(obs_tasks_all, obs_uuid)
                if obs_task and not dry_run:
                    self.logger.info(
                        "Deleting orphaned Obsidian task: %s", obs_task.description
                    )
                    self.obs_manager.delete_task(obs_task)
                elif not obs_task:
                    self.logger.debug(
                        "Skipping delete for orphaned Obsidian task %s (task not found)",
                        obs_uuid,
                    )
                self.changes_made["obs_deleted"] = self.changes_made.get("obs_deleted", 0) + 1

                existing_links = [
                    link for link in existing_links if link.obs_uuid != obs_uuid
                ]
                links = [link for link in links if link.obs_uuid != obs_uuid]
                self.changes_made["links_deleted"] = self.changes_made.get("links_deleted", 0) + 1

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
            
            # Check for tag-based rerouting (independent of conflict resolution)
            # Only evaluate if task has tags that could match a route
            if self.direction in ("both", "obs-to-rem") and obs_task.tags:
                # Check if any tag matches a configured route for this vault
                has_routing_tag = False
                if self.sync_config and self.vault_id:
                    vault_routes = self.sync_config.get_tag_routes_for_vault(self.vault_id)
                    if vault_routes:
                        routing_tags = {route['tag'] for route in vault_routes}
                        has_routing_tag = any(tag in routing_tags for tag in obs_task.tags)
                
                if has_routing_tag:
                    target_calendar = self._should_reroute_task(obs_task, rem_task.calendar_id)
                    if target_calendar:
                        list_name = self._get_list_name(target_calendar)
                        self.logger.info(
                            f"Rerouting task '{obs_task.description}' from {self._get_list_name(rem_task.calendar_id)} to {list_name}"
                        )
                        if not dry_run:
                            if self.rem_manager.update_task(rem_task, {"calendar_id": target_calendar}):
                                rem_task.calendar_id = target_calendar
                                rem_task.list_name = list_name
                                self.changes_made["rem_rerouted"] = self.changes_made.get("rem_rerouted", 0) + 1
                            else:
                                self.logger.warning(f"Failed to reroute task '{obs_task.description}' to {list_name}")
                        else:
                            self.changes_made["rem_rerouted"] = self.changes_made.get("rem_rerouted", 0) + 1
        
        # 6. Save links to persistent storage
        if not dry_run:
            # Clean up links for deleted tasks
            # IMPORTANT: Only remove links where the OBSIDIAN task is missing.
            # If Reminders task is missing, it might be in a different list or deleted,
            # but we shouldn't remove the link as it might be valid for other syncs.
            cleaned_links = []
            for link in links:
                # Only keep links where both tasks still exist
                obs_found = self._find_task(obs_tasks_all, link.obs_uuid)
                rem_found = self._find_task(rem_tasks_all, link.rem_uuid)
                
                if obs_found and rem_found:
                    cleaned_links.append(link)
                elif obs_found and not rem_found:
                    # Obsidian task exists but Reminders task not found
                    # This could mean: 1) task in different list, 2) task deleted, 3) config changed
                    # For safety, keep the link but log a warning
                    self.logger.warning(
                        f"Link {link.obs_uuid} <-> {link.rem_uuid}: Obsidian task found but Reminders task missing. "
                        f"Keeping link in case Reminders task is in a different list."
                    )
                    cleaned_links.append(link)
                elif not obs_found and rem_found:
                    # Obsidian task deleted but Reminders task exists
                    # This is a true orphan - remove the link
                    self.changes_made["links_deleted"] += 1
                    self.logger.info(
                        f"Removing link for deleted Obsidian task: {link.obs_uuid} <-> {link.rem_uuid}"
                    )
                else:
                    # Both tasks missing - remove the link
                    self.changes_made["links_deleted"] += 1
                    self.logger.debug(
                        f"Removing stale link (both tasks missing): {link.obs_uuid} <-> {link.rem_uuid}"
                    )

            if cleaned_links:
                self._persist_links(cleaned_links, current_obs_uuids=current_obs_uuids)

        # Collect tag routing summary
        tag_summary = self._collect_tag_routing_summary(obs_tasks, rem_tasks, links)
        
        # Return results
        return {
            'success': True,
            'obs_tasks': len(obs_tasks),
            'rem_tasks': len(rem_tasks),
            'links': len(links),
            'changes': self.changes_made,
            'tag_summary': tag_summary,
            'created_obs_tasks': list(self.created_obs_task_ids),
            'created_rem_tasks': list(self.created_rem_task_ids),
            'rem_to_obs_creations': self.rem_to_obs_creations,
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
        
        # Tags sync
        if "tags_winner" in conflicts:
            if conflicts["tags_winner"] == "obs" and allow_rem_updates:
                if not dry_run:
                    self.rem_manager.update_task(rem_task, {"tags": obs_task.tags})
                self.changes_made["rem_updated"] += 1
                change_applied = True
            
            elif conflicts["tags_winner"] == "rem" and allow_obs_updates:
                if not dry_run:
                    self.obs_manager.update_task(obs_task, {"tags": rem_task.tags})
                self.changes_made["obs_updated"] += 1
                change_applied = True
            
            elif conflicts["tags_winner"] == "merge":
                # Merge tags from both sources
                merged_tags = merge_tags(obs_task.tags, rem_task.tags)
                
                if allow_obs_updates and obs_task.tags != merged_tags:
                    if not dry_run:
                        self.obs_manager.update_task(obs_task, {"tags": merged_tags})
                    self.changes_made["obs_updated"] += 1
                    change_applied = True
                
                if allow_rem_updates and rem_task.tags != merged_tags:
                    if not dry_run:
                        self.rem_manager.update_task(rem_task, {"tags": merged_tags})
                    self.changes_made["rem_updated"] += 1
                    change_applied = True

        if change_applied:
            self.changes_made["conflicts_resolved"] += 1
    
    def _get_default_calendar_id(self, list_ids: Optional[List[str]]) -> Optional[str]:
        if self.vault_default_calendar:
            return self.vault_default_calendar
        if list_ids:
            return list_ids[0]
        return self.default_calendar_id

    def _select_calendar_for_obs_task(
        self,
        obs_task: ObsidianTask,
        default_calendar: Optional[str],
        list_ids: Optional[List[str]],
    ) -> Optional[str]:
        """Select the appropriate calendar for an Obsidian task based on tag routes.

        Args:
            obs_task: The task to route
            default_calendar: Default calendar if no route matches
            list_ids: Optional list of calendar IDs to restrict to. If None, all routes are considered.

        Returns:
            Calendar ID for the task
        """
        if self.sync_config and self.vault_id:
            normalized_tags = {
                tag
                for tag in (
                    SyncConfig._normalize_tag_value(t)
                    for t in (getattr(obs_task, "tags", None) or [])
                )
                if tag
            }
            if normalized_tags:
                routes = self.sync_config.get_tag_routes_for_vault(self.vault_id)
                # Sort routes by tag specificity (longer tags first) for deterministic matching
                sorted_routes = sorted(routes, key=lambda r: len(r.get("tag", "")), reverse=True)

                for route in sorted_routes:
                    route_tag = route.get("tag")
                    calendar_id = route.get("calendar_id")
                    if (
                        route_tag
                        and calendar_id
                        and route_tag in normalized_tags
                        and (not list_ids or calendar_id in list_ids)
                    ):
                        self.logger.debug(
                            f"Task matches route: {route_tag} -> {calendar_id}"
                        )
                        return calendar_id
        return default_calendar

    def _get_route_tag_for_calendar(self, calendar_id: Optional[str]) -> Optional[str]:
        if not (self.sync_config and self.vault_id and calendar_id):
            return None
        return self.sync_config.get_route_tag_for_calendar(self.vault_id, calendar_id)

    def _get_list_name(self, calendar_id: Optional[str]) -> str:
        if not self.sync_config or not calendar_id:
            return "Reminders"
        for lst in getattr(self.sync_config, "reminders_lists", []):
            if getattr(lst, "identifier", None) == calendar_id:
                return getattr(lst, "name", calendar_id)
        return calendar_id

    def _should_reroute_task(self, obs_task: ObsidianTask, current_calendar_id: str) -> Optional[str]:
        """Check if a task should be moved to a different calendar based on its tags.

        Args:
            obs_task: The Obsidian task to check
            current_calendar_id: The calendar ID where the task currently resides

        Returns:
            Target calendar_id if task should be moved, None otherwise
        """
        if not self.sync_config or not self.vault_id:
            return None

        # Get the calendar this task should route to based on its tags
        target_calendar = self._select_calendar_for_obs_task(
            obs_task,
            self.vault_default_calendar,
            None  # Check against all configured routes
        )

        # If target is different from current, task needs re-routing
        if target_calendar and target_calendar != current_calendar_id:
            self.logger.info(
                f"Task '{obs_task.description}' should move from calendar {current_calendar_id} to {target_calendar}"
            )
            return target_calendar

        return None

    def _create_counterparts(
        self,
        unmatched_obs: List[ObsidianTask],
        unmatched_rem: List[RemindersTask],
        list_ids: Optional[List[str]],
        dry_run: bool,
    ) -> Tuple[List[SyncLink], List[ObsidianTask], List[RemindersTask]]:
        """Create counterpart tasks for unmatched items."""
        new_links: List[SyncLink] = []
        created_obs_tasks: List[ObsidianTask] = []
        created_rem_tasks: List[RemindersTask] = []
        
        # Create Reminders tasks for unmatched Obsidian tasks
        if self.direction in ("both", "obs-to-rem") and unmatched_obs:
            default_calendar = self._get_default_calendar_id(list_ids)

            if not default_calendar and not list_ids:
                self.logger.warning("No calendar ID available for creating Reminders tasks")

            for obs_task in unmatched_obs:
                target_calendar = self._select_calendar_for_obs_task(
                    obs_task,
                    default_calendar,
                    list_ids,
                )
                if not target_calendar:
                    self.logger.debug(
                        "Skipping Reminders creation for %s - no calendar mapping",
                        obs_task.description,
                    )
                    continue

                list_name = self._get_list_name(target_calendar)
                self.logger.debug(
                    "Creating Reminders task for %s in list %s (obs_uuid=%s)",
                    obs_task.description,
                    list_name,
                    obs_task.uuid,
                )

                rem_task = RemindersTask(
                    uuid=f"rem-{uuid.uuid4().hex[:8]}",
                    item_id="",  # Will be set by gateway
                    calendar_id=target_calendar,
                    list_name=list_name,
                    status=obs_task.status,
                    title=obs_task.description,
                    due_date=obs_task.due_date,
                    priority=obs_task.priority,
                    notes="Created from Obsidian",
                    tags=obs_task.tags,
                    created_at=datetime.now(timezone.utc).isoformat(),
                    modified_at=datetime.now(timezone.utc).isoformat(),
                )

                if not dry_run:
                    self.logger.debug(f"About to call rem_manager.create_task for {obs_task.description}")
                    created_task = self.rem_manager.create_task(target_calendar, rem_task)
                    self.logger.debug(f"rem_manager.create_task returned: {created_task}")
                    if created_task:
                        created_rem_tasks.append(created_task)
                        self.created_rem_task_ids.add(created_task.uuid)
                        link = SyncLink(
                            obs_uuid=obs_task.uuid,
                            rem_uuid=created_task.uuid,
                            score=1.0,
                            vault_id=self.vault_id,
                            last_synced=datetime.now(timezone.utc).isoformat(),
                        )
                        new_links.append(link)
                        self.logger.debug(
                            f"Created link: obs={obs_task.uuid} <-> rem={created_task.uuid} "
                            f"for task '{obs_task.description}'"
                        )

                # Count both actual and planned creations
                self.changes_made["rem_created"] += 1
                self.changes_made["links_created"] += 1
        
        # Create Obsidian tasks for unmatched Reminders tasks
        if self.direction in ("both", "rem-to-obs") and unmatched_rem:
            for rem_task in unmatched_rem:
                list_name = self._get_list_name(rem_task.calendar_id)
                self.logger.debug(
                    "Creating Obsidian task for '%s' from Reminders list '%s' (calendar_id=%s, rem_uuid=%s)",
                    rem_task.title,
                    list_name,
                    rem_task.calendar_id,
                    rem_task.uuid,
                )

                route_tag = self._get_route_tag_for_calendar(rem_task.calendar_id)
                obs_tags = list(rem_task.tags) if rem_task.tags else []
                if route_tag and route_tag not in obs_tags:
                    obs_tags.append(route_tag)
                if "#from-reminders" not in obs_tags:
                    obs_tags.append("#from-reminders")

                vault_id = self.vault_id or os.path.basename(self.vault_path)
                vault_name = self.vault_name or os.path.basename(self.vault_path)

                obs_task = ObsidianTask(
                    uuid=f"obs-{uuid.uuid4().hex[:8]}",
                    vault_id=vault_id,
                    vault_name=vault_name,
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
                    tags=obs_tags,
                    created_at=datetime.now(timezone.utc).isoformat(),
                    modified_at=datetime.now(timezone.utc).isoformat(),
                )
                
                # Track metadata for verbose output
                creation_metadata = {
                    "title": rem_task.title,
                    "rem_uuid": rem_task.uuid,
                    "list_name": list_name,
                    "calendar_id": rem_task.calendar_id,
                    "obs_uuid": None,  # Will be set after creation if not dry_run
                }
                
                if not dry_run:
                    # Actually create the task
                    created_task = self.obs_manager.create_task(
                        self.vault_path, self.inbox_path, obs_task
                    )
                    if created_task:
                        created_obs_tasks.append(created_task)
                        self.created_obs_task_ids.add(created_task.uuid)
                        creation_metadata["obs_uuid"] = created_task.uuid
                        # Create a link for the new pair
                        link = SyncLink(
                            obs_uuid=created_task.uuid,
                            rem_uuid=rem_task.uuid,
                            score=1.0,  # Perfect match as it's a copy
                            vault_id=self.vault_id,
                            last_synced=datetime.now(timezone.utc).isoformat(),
                        )
                        new_links.append(link)
                else:
                    # In dry run, use the planned obs_task UUID
                    creation_metadata["obs_uuid"] = obs_task.uuid
                
                self.rem_to_obs_creations.append(creation_metadata)
                
                # Count both actual and planned creations
                self.changes_made["obs_created"] += 1
                self.changes_made["links_created"] += 1
        
        return new_links, created_obs_tasks, created_rem_tasks
    
    def _detect_orphaned_tasks(
        self,
        existing_links: List[SyncLink],
        obs_tasks: List[ObsidianTask],
        rem_tasks: List[RemindersTask],
        active_links: Optional[List[SyncLink]] = None,
    ) -> tuple[Set[str], Set[str]]:
        """Detect tasks that had links but their counterpart was deleted.

        Args:
            existing_links: Links loaded from storage prior to matching
            obs_tasks: Current Obsidian task list
            rem_tasks: Current Reminders task list
            active_links: Links that are currently considered valid matches after
                normalization/matching. When provided, entries that already have a
                live match are ignored to prevent false orphan reports during
                normalization migrations.

        Returns:
            Tuple of (orphaned_rem_uuids, orphaned_obs_uuids)
        """
        obs_uuid_set = {task.uuid for task in obs_tasks}
        rem_uuid_set = {task.uuid for task in rem_tasks}
        active_obs = {link.obs_uuid for link in active_links} if active_links else set()
        active_rem = {link.rem_uuid for link in active_links} if active_links else set()

        orphaned_rem_uuids: Set[str] = set()
        orphaned_obs_uuids: Set[str] = set()

        for link in existing_links:
            # Skip links that already have an active match after normalization/matching
            if active_links and (
                link.obs_uuid in active_obs or link.rem_uuid in active_rem
            ):
                continue

            obs_exists = link.obs_uuid in obs_uuid_set
            rem_exists = link.rem_uuid in rem_uuid_set

            # If Obsidian task deleted but Reminders task still exists
            if not obs_exists and rem_exists:
                orphaned_rem_uuids.add(link.rem_uuid)
                self.logger.debug(
                    "Found orphaned Reminders task: %s (Obsidian counterpart %s was deleted)",
                    link.rem_uuid,
                    link.obs_uuid,
                )

            # If Reminders task deleted but Obsidian task still exists
            elif not rem_exists and obs_exists:
                orphaned_obs_uuids.add(link.obs_uuid)
                self.logger.debug(
                    "Found orphaned Obsidian task: %s (Reminders counterpart %s was deleted)",
                    link.obs_uuid,
                    link.rem_uuid,
                )

        return orphaned_rem_uuids, orphaned_obs_uuids
    
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
    
    def _normalize_links(self, links: List[SyncLink], obs_tasks: List[ObsidianTask], rem_tasks: List[RemindersTask] = None) -> List[SyncLink]:
        """Normalize existing links to fix stale UUID references.
        
        When ObsidianTaskManager creates tasks with temporary UUIDs (e.g. 'obs-temp-123')
        but later list_tasks generates canonical UUIDs like 'obs-{block_id}' or stable
        hash-based UUIDs for tasks without block IDs, this method fixes the discrepancy
        by updating the links to use the canonical UUID.
        
        Args:
            links: Existing sync links to normalize
            obs_tasks: Current Obsidian tasks to check against
            rem_tasks: Optional Reminders tasks for better matching
            
        Returns:
            List of normalized links with any necessary UUID corrections applied
        """
        # Build maps for quick lookups
        obs_by_uuid = {task.uuid: task for task in obs_tasks}
        obs_by_blockid = {}
        for task in obs_tasks:
            if task.block_id:
                obs_by_blockid[task.block_id] = task
        
        normalized_links = []
        links_updated = 0
        
        for link in links:
            updated_link = link
            
            # Check if this link's obs_uuid needs normalization
            if link.obs_uuid and link.obs_uuid.startswith('obs-'):
                stub_suffix = link.obs_uuid[4:]  # Remove 'obs-' prefix
                
                # First check if there's a task with this exact UUID (already canonical)
                if link.obs_uuid in obs_by_uuid:
                    # UUID is valid as-is
                    normalized_links.append(link)
                # Check if the suffix matches a block_id (meaning this is a canonical form)
                elif stub_suffix in obs_by_blockid:
                    # This is already in canonical form
                    normalized_links.append(link)
                else:
                    # This might be a stale temporary UUID
                    # For temporary UUIDs (especially obs-temp-*), try to find the canonical task
                    found_canonical = False
                    
                    # If it looks like a temporary UUID, try to match by looking at all tasks
                    if 'temp' in link.obs_uuid or len(stub_suffix) in [8, 36]:
                        # Look for a task that could be the canonical version
                        # We'll match by checking if there's exactly one unmatched task
                        # that could correspond to this Reminder
                        
                        # Get all links with this reminder UUID
                        links_for_rem = [l for l in links if l.rem_uuid == link.rem_uuid]
                        
                        if len(links_for_rem) == 1:  # Only this link references this reminder
                            # Look for tasks that aren't already linked
                            linked_obs_uuids = {l.obs_uuid for l in links if l != link}
                            unlinked_tasks = [t for t in obs_tasks if t.uuid not in linked_obs_uuids]
                            
                            # If there's exactly one unlinked task, it's likely the match
                            # If there are multiple, we need to be more careful
                            if len(unlinked_tasks) == 1:
                                candidate = unlinked_tasks[0]
                                
                                # Update the link to use the candidate's UUID
                                updated_link = SyncLink(
                                    obs_uuid=candidate.uuid,
                                    rem_uuid=link.rem_uuid,
                                    score=link.score,
                                    vault_id=link.vault_id or self.vault_id,
                                    last_synced=link.last_synced,
                                    created_at=link.created_at
                                )
                                links_updated += 1
                                found_canonical = True
                                self.logger.info(
                                    f"Normalized legacy link: {link.obs_uuid} -> {candidate.uuid} "
                                    f"(single unlinked match: {candidate.file_path}:{candidate.line_number})"
                                )
                            elif len(unlinked_tasks) > 1 and rem_tasks:
                                # Multiple unlinked tasks - use matcher to find best match
                                rem_task = None
                                for rt in rem_tasks:
                                    if rt.uuid == link.rem_uuid:
                                        rem_task = rt
                                        break
                                
                                if rem_task:
                                    # Use the matcher to find the best match
                                    best_score = 0.0
                                    best_candidate = None
                                    
                                    for obs_task in unlinked_tasks:
                                        score = self.matcher._calculate_similarity(obs_task, rem_task)
                                        if score > best_score and score >= self.matcher.min_score:
                                            best_score = score
                                            best_candidate = obs_task
                                    
                                    if best_candidate:
                                        # Update the link to use the best candidate's UUID
                                        updated_link = SyncLink(
                                            obs_uuid=best_candidate.uuid,
                                            rem_uuid=link.rem_uuid,
                                            score=best_score,
                                            vault_id=link.vault_id or self.vault_id,
                                            last_synced=link.last_synced,
                                            created_at=link.created_at
                                        )
                                        links_updated += 1
                                        found_canonical = True
                                        self.logger.info(
                                            f"Normalized legacy link via matcher: {link.obs_uuid} -> {best_candidate.uuid} "
                                            f"(score: {best_score:.2f}, task: {best_candidate.file_path}:{best_candidate.line_number})"
                                        )
                                    else:
                                        self.logger.debug(
                                            f"Cannot normalize {link.obs_uuid}: no matches above threshold among {len(unlinked_tasks)} candidates"
                                        )
                                else:
                                    self.logger.debug(
                                        f"Cannot normalize {link.obs_uuid}: reminder task not found"
                                    )
                            elif len(unlinked_tasks) > 1:
                                # No rem_tasks provided - can't use matcher
                                self.logger.debug(
                                    f"Cannot normalize {link.obs_uuid}: {len(unlinked_tasks)} potential matches, no rem_tasks for matching"
                                )
                    
                    if found_canonical:
                        normalized_links.append(updated_link)
                    else:
                        # Can't normalize, keep as-is (might be for deleted task)
                        normalized_links.append(link)
            else:
                # Non-Obsidian UUID or doesn't start with 'obs-', keep as-is
                normalized_links.append(link)
        
        # Remove duplicate links (same obs_uuid and rem_uuid)
        unique_links = {}
        for link in normalized_links:
            key = f"{link.obs_uuid}:{link.rem_uuid}"
            if key not in unique_links or link.score > unique_links[key].score:
                # Keep the link with the higher score if duplicates exist
                unique_links[key] = link
        
        final_links = list(unique_links.values())
        
        if links_updated > 0:
            self.logger.info(f"Normalized {links_updated} links with updated UUIDs")
            # Mark that we need to persist these normalized links
            self._links_need_persist = True
        
        return final_links
    
    def _collect_tag_routing_summary(self, obs_tasks: List[ObsidianTask],
                                      rem_tasks: List[RemindersTask],
                                      links: List[SyncLink]) -> Dict[str, Dict[str, int]]:
        """Collect summary of tasks per tag and their destination lists.
        
        Returns:
            Dict mapping tags to list names and their task counts
        """
        if not self.sync_config or not self.vault_id:
            return {}
            
        tag_routes = self.sync_config.get_tag_routes_for_vault(self.vault_id)
        if not tag_routes:
            return {}
            
        summary: Dict[str, Dict[str, int]] = {}
        
        # Create a map of task UUIDs that are linked
        linked_obs_uuids = {link.obs_uuid for link in links}
        linked_rem_uuids = {link.rem_uuid for link in links}
        
        # Process each configured tag route
        for route in tag_routes:
            tag = route.get('tag')
            calendar_id = route.get('calendar_id')
            if not tag or not calendar_id:
                continue
                
            list_name = self._get_list_name(calendar_id)
            
            # Count Obsidian tasks with this tag that are synced to the target list
            count = 0
            for obs_task in obs_tasks:
                if obs_task.uuid not in linked_obs_uuids:
                    continue
                    
                # Check if task has the tag
                normalized_tags = {
                    SyncConfig._normalize_tag_value(t)
                    for t in (obs_task.tags or [])
                    if SyncConfig._normalize_tag_value(t)
                }
                
                if tag in normalized_tags:
                    # Find the linked Reminders task to verify it's in the right list
                    for link in links:
                        if link.obs_uuid == obs_task.uuid:
                            rem_task = self._find_task(rem_tasks, link.rem_uuid)
                            if rem_task and rem_task.calendar_id == calendar_id:
                                count += 1
                                break
            
            if count > 0:
                if tag not in summary:
                    summary[tag] = {}
                summary[tag][list_name] = count
        
        return summary
    
    def _persist_links(self, links: List[SyncLink], current_obs_uuids: Optional[Set[str]] = None) -> None:
        """Persist sync links to file, preserving other vaults' entries.

        Args:
            links: The current active links for the vault being processed.
            current_obs_uuids: UUIDs for tasks present in this vault; used to
                identify and replace legacy entries without vault identifiers.
        """
        try:
            links_path = os.path.expanduser(self.links_path)
            existing_map: Dict[str, Dict[str, Any]] = {}
            current_obs_uuids = set(current_obs_uuids or [])

            # Load existing links if the file already exists
            if os.path.exists(links_path):
                with open(links_path, 'r') as f:
                    data = json.load(f)
                    for entry in data.get('links', []):
                        key = f"{entry.get('obs_uuid')}:{entry.get('rem_uuid')}"
                        if entry.get('obs_uuid') and entry.get('rem_uuid'):
                            existing_map[key] = entry

            # Remove entries belonging to this vault so we can replace them
            filtered_map: Dict[str, Dict[str, Any]] = {}
            for key, entry in existing_map.items():
                entry_vault = entry.get('vault_id')
                entry_obs_uuid = entry.get('obs_uuid')

                belongs_to_current = False
                if entry_vault and self.vault_id and entry_vault == self.vault_id:
                    belongs_to_current = True
                elif not entry_vault and entry_obs_uuid in current_obs_uuids:
                    belongs_to_current = True

                if not belongs_to_current:
                    filtered_map[key] = entry

            # Add/replace with the current vault's links
            for link in links:
                key = f"{link.obs_uuid}:{link.rem_uuid}"
                filtered_map[key] = link.to_dict()

            # Persist the merged set back to disk
            os.makedirs(os.path.dirname(links_path), exist_ok=True)
            with open(links_path, 'w') as f:
                json.dump({'links': list(filtered_map.values())}, f, indent=2)

            self.logger.debug(f"Persisted {len(links)} active links (total {len(filtered_map)}) to {links_path}")
        except Exception as e:
            self.logger.error(f"Failed to persist links: {e}")