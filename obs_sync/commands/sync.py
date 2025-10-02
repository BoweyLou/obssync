"""Sync command - perform bidirectional task synchronization."""

import os
from typing import List, Optional
import logging
from datetime import date

from ..core.config import SyncConfig
from ..sync.engine import SyncEngine
from ..sync.deduplicator import TaskDeduplicator
from ..utils.prompts import (
    confirm_deduplication,
    display_duplicate_cluster,
    prompt_for_keeps,
    show_deduplication_summary
)


class SyncCommand:
    """Command for synchronizing tasks between Obsidian and Reminders."""

    def __init__(self, config: SyncConfig, verbose: bool = False):
        self.config = config
        self.verbose = verbose
        self.logger = logging.getLogger(__name__)
        if verbose:
            self.logger.setLevel(logging.DEBUG)

    def run(self, apply_changes: bool = False, direction: str = "both") -> bool:
        """Run the sync command."""
        try:
            # Get all vault mappings
            mappings = self.config.get_all_vault_mappings()

            if not mappings:
                # Fallback to legacy behavior if no mappings configured
                vault_path = self.config.default_vault_path
                if not vault_path:
                    print("No Obsidian vault configured. Run 'obs-sync setup' first.")
                    return False

                if not os.path.exists(vault_path):
                    print(f"Configured vault does not exist: {vault_path}")
                    return False

                list_ids = self.config.reminder_list_ids or None
                print(f"\n📁 Syncing vault: {os.path.basename(vault_path)}")
                vault_result = sync_command(
                    vault_path=vault_path,
                    list_ids=list_ids,
                    dry_run=not apply_changes,
                    direction=direction,
                    config=self.config,
                    show_summary=True,  # Legacy single vault keeps full summary
                )
                
                # Run calendar import if enabled and sync was successful
                self.logger.debug(f"Legacy calendar import check: apply_changes={apply_changes}, sync_success={vault_result['success']}, sync_calendar_events={getattr(self.config, 'sync_calendar_events', 'MISSING')}, has_default_vault={self.config.default_vault is not None}")
                if (apply_changes and vault_result['success'] and self.config.sync_calendar_events and
                    self.config.default_vault):
                    self.logger.info(f"Running legacy calendar import for vault: {self.config.default_vault.name}")
                    self._run_calendar_import(self.config.default_vault, list_ids)
                
                return vault_result['success']

            # Process each vault mapping
            all_success = True
            total_vaults = len(mappings)
            vault_results = []

            print(f"\n🔄 Syncing {total_vaults} vault(s)...")
            print("=" * 50)

            for idx, (vault, calendar_id) in enumerate(mappings, 1):
                vault_path = vault.path

                if not os.path.exists(vault_path):
                    print(f"\n⚠️  Vault {idx}/{total_vaults}: {vault.name}")
                    print(f"   Vault path does not exist: {vault_path}")
                    all_success = False
                    
                    # Add failed vault to results for summary
                    vault_results.append({
                        'success': False,
                        'vault_path': vault_path,
                        'vault_name': vault.name,
                        'error': f'Vault path does not exist: {vault_path}'
                    })
                    continue

                list_ids = self._collect_list_ids_for_vault(vault, calendar_id)

                print(f"\n📁 Vault {idx}/{total_vaults}: {vault.name}")

                if calendar_id:
                    list_name = self._get_list_name(calendar_id)
                    print(f"   → Syncing with default list: {list_name}")
                else:
                    print("   → No default Reminders list configured for this vault")

                tag_routes = self.config.get_tag_routes_for_vault(vault.vault_id)
                if tag_routes:
                    print("   Tag routes:")
                    for route in tag_routes:
                        route_list = self._get_list_name(route.get("calendar_id"))
                        import_mode = route.get("import_mode", "existing_only")
                        mode_display = "(existing only)" if import_mode == "existing_only" else "(full import)"
                        print(f"     • {route['tag']} → {route_list} {mode_display}")

                print(f"   🔄 Running sync...")
                
                # Run sync for this vault with all relevant lists, suppress individual summary
                vault_result = sync_command(
                    vault_path=vault_path,
                    list_ids=list_ids or None,
                    dry_run=not apply_changes,
                    direction=direction,
                    config=self.config,
                    show_summary=False,  # Suppress individual vault summaries
                )

                vault_results.append(vault_result)

                if not vault_result['success']:
                    all_success = False
                    print(f"   ❌ Sync failed: {vault_result.get('error', 'Unknown error')}")
                else:
                    print(f"   ✅ Sync completed")
                    
                    # Run calendar import if enabled and this is the default vault
                    self.logger.debug(f"Calendar import check: apply_changes={apply_changes}, sync_calendar_events={getattr(self.config, 'sync_calendar_events', 'MISSING')}, has_default_vault={self.config.default_vault is not None}, vault_matches={vault.vault_id == self.config.default_vault.vault_id if self.config.default_vault else False}")
                    if (apply_changes and self.config.sync_calendar_events and
                        self.config.default_vault and vault.vault_id == self.config.default_vault.vault_id):
                        self.logger.info(f"Running calendar import for vault: {vault.name}")
                        self._run_calendar_import(vault, list_ids)

                if idx < total_vaults:
                    print("-" * 50)

            print("\n" + "=" * 50)
            
            # Show consolidated summary
            self._show_consolidated_summary(vault_results, apply_changes)
            
            if all_success:
                print("\n✅ All vaults synced successfully!")
            else:
                print("\n⚠️  Some vaults had sync errors. Check the output above.")

            return all_success

        except Exception as exc:  # pragma: no cover - defensive
            self.logger.error("Sync command failed: %s", exc)
            if self.verbose:
                import traceback
                traceback.print_exc()
            return False

    def _collect_list_ids_for_vault(
        self,
        vault,
        default_calendar_id: Optional[str],
    ) -> List[str]:
        list_ids: List[str] = []
        if default_calendar_id:
            list_ids.append(default_calendar_id)

        for route in self.config.get_tag_routes_for_vault(vault.vault_id):
            calendar_id = route.get("calendar_id")
            if calendar_id and calendar_id not in list_ids:
                list_ids.append(calendar_id)

        return list_ids

    def _get_list_name(self, identifier: Optional[str]) -> str:
        if not identifier:
            return "Unknown"
        for lst in self.config.reminders_lists:
            if lst.identifier == identifier:
                return lst.name
        return identifier
    
    def _show_consolidated_summary(self, vault_results: List[dict], apply_changes: bool) -> None:
        """Show consolidated summary across all vaults."""
        print("\n🔄 Sync Summary")
        
        # Aggregate totals
        total_obs_tasks = 0
        total_rem_tasks = 0
        total_links = 0
        total_vaults_success = 0
        total_vaults_failed = 0
        
        # Aggregate changes
        aggregated_changes = {
            "obs_updated": 0,
            "rem_updated": 0,
            "obs_created": 0,
            "rem_created": 0,
            "obs_deleted": 0,
            "rem_deleted": 0,
            "links_created": 0,
            "links_deleted": 0,
            "conflicts_resolved": 0,
            "rem_rerouted": 0,
        }
        
        # Aggregate deduplication stats
        total_dedup_obs = 0
        total_dedup_rem = 0
        total_skipped_rem = 0
        
        # Collect tag routing info across all vaults
        all_tag_summaries = {}
        
        for vault_result in vault_results:
            if vault_result.get('success', False):
                total_vaults_success += 1
                results = vault_result.get('results', {})
                dedup_stats = vault_result.get('dedup_stats', {})
                
                # Ensure dedup_stats is a dict, not a string or None
                if not isinstance(dedup_stats, dict):
                    dedup_stats = {'obs_deleted': 0, 'rem_deleted': 0}
                
                # Aggregate basic counts
                total_obs_tasks += results.get('obs_tasks', 0)
                total_rem_tasks += results.get('rem_tasks', 0)
                total_links += results.get('links', 0)
                
                # Aggregate changes
                changes = results.get('changes', {})
                for key in aggregated_changes:
                    aggregated_changes[key] += changes.get(key, 0)
                
                # Aggregate deduplication
                total_dedup_obs += dedup_stats.get('obs_deleted', 0)
                total_dedup_rem += dedup_stats.get('rem_deleted', 0)
                
                # Aggregate skipped reminders
                total_skipped_rem += results.get('skipped_rem_count', 0)
                
                # Collect tag routing summaries
                tag_summary = results.get('tag_summary', {})
                if tag_summary and isinstance(tag_summary, dict):
                    for tag, stats in tag_summary.items():
                        if isinstance(stats, dict):
                            if tag not in all_tag_summaries:
                                all_tag_summaries[tag] = {}
                            for list_name, count in stats.items():
                                if isinstance(count, (int, float)):
                                    if list_name not in all_tag_summaries[tag]:
                                        all_tag_summaries[tag][list_name] = 0
                                    all_tag_summaries[tag][list_name] += count
            else:
                total_vaults_failed += 1
        
        # Show basic stats
        print(f"\nOverall Statistics:")
        print(f"  Total Obsidian tasks: {total_obs_tasks}")
        print(f"  Total Reminders tasks: {total_rem_tasks}")
        print(f"  Total matched pairs: {total_links}")
        if total_skipped_rem > 0:
            print(f"  Reminders tasks skipped (existing_only mode): {total_skipped_rem}")
        print(f"  Vaults processed: {total_vaults_success + total_vaults_failed} ({total_vaults_success} successful, {total_vaults_failed} failed)")
        
        # Show tag routing summary if available
        if all_tag_summaries:
            print("\n📊 Tag Routing Summary (All Vaults):")
            for tag, stats in all_tag_summaries.items():
                print(f"  {tag}:")
                for list_name, count in stats.items():
                    print(f"    → {list_name}: {count} task(s)")
        
        # Show changes summary
        has_sync_changes = any([
            aggregated_changes["obs_updated"],
            aggregated_changes["rem_updated"],
            aggregated_changes["obs_created"],
            aggregated_changes["rem_created"],
            aggregated_changes.get("obs_deleted", 0),
            aggregated_changes.get("rem_deleted", 0),
            aggregated_changes.get("rem_rerouted", 0),
        ])
        
        has_dedup_changes = total_dedup_obs > 0 or total_dedup_rem > 0
        
        if has_sync_changes or has_dedup_changes:
            dry_run = not apply_changes
            print(f"\nTotal Changes {'to make' if dry_run else 'made'}:")
            
            if has_sync_changes:
                if aggregated_changes["obs_updated"]:
                    print(f"  Obsidian updates: {aggregated_changes['obs_updated']}")
                if aggregated_changes["rem_updated"]:
                    print(f"  Reminders updates: {aggregated_changes['rem_updated']}")
                if aggregated_changes["obs_created"]:
                    print(f"  Obsidian creations: {aggregated_changes['obs_created']}")
                if aggregated_changes["rem_created"]:
                    print(f"  Reminders creations: {aggregated_changes['rem_created']}")
                if aggregated_changes.get("obs_deleted", 0):
                    print(f"  Obsidian deletions: {aggregated_changes['obs_deleted']}")
                if aggregated_changes.get("rem_deleted", 0):
                    print(f"  Reminders deletions: {aggregated_changes['rem_deleted']}")
                if aggregated_changes["links_created"]:
                    print(f"  New sync links: {aggregated_changes['links_created']}")
                if aggregated_changes.get("links_deleted", 0):
                    print(f"  Removed sync links: {aggregated_changes['links_deleted']}")
                if aggregated_changes["conflicts_resolved"]:
                    print(f"  Conflicts resolved: {aggregated_changes['conflicts_resolved']}")
                if aggregated_changes.get("rem_rerouted", 0):
                    print(f"  Tasks rerouted: {aggregated_changes['rem_rerouted']}")
            
            if has_dedup_changes:
                print(f"\nDeduplication {'to perform' if dry_run else 'complete'}:")
                if total_dedup_obs:
                    print(f"  Obsidian deletions: {total_dedup_obs}")
                if total_dedup_rem:
                    print(f"  Reminders deletions: {total_dedup_rem}")
            
            if dry_run:
                print("\n💡 This was a dry run. Use --apply to make changes.")
        else:
            print("\nNo changes needed - everything is in sync across all vaults!")

    def _run_calendar_import(self, vault, list_ids: Optional[List[str]]) -> None:
        """Run calendar import for the default vault if conditions are met."""
        try:
            from ..calendar.tracker import CalendarImportTracker
            from ..calendar.gateway import CalendarGateway
            from ..calendar.daily_notes import DailyNoteManager
            
            tracker = CalendarImportTracker()
            
            # Check if already ran today
            if tracker.has_run_today(vault.vault_id):
                if self.verbose:
                    print(f"   📅 Calendar import already ran today for {vault.name}")
                return
            
            # Collect all calendar IDs (union of config.calendar_ids and list_ids)
            calendar_ids = []
            if self.config.calendar_ids:
                calendar_ids.extend(self.config.calendar_ids)
            if list_ids:
                calendar_ids.extend(list_ids)
            
            # Deduplicate, pass None if empty
            calendar_ids = list(set(calendar_ids)) if calendar_ids else None
            
            # Initialize components
            gateway = CalendarGateway()
            note_manager = DailyNoteManager(vault.path)
            
            # Get events for today
            today = date.today()
            events = gateway.get_events_for_date(today, calendar_ids)
            
            if events:
                print(f"   📅 Importing {len(events)} calendar events to daily note")
                note_path = note_manager.update_daily_note(today, events)
                print(f"   📝 Updated daily note: {note_path}")
            else:
                print(f"   📅 No calendar events to import for {today}")
            
            # Mark as completed for today
            tracker.mark_run_today(vault.vault_id)
            
        except Exception as e:
            self.logger.error(f"Calendar import failed: {e}")
            if self.verbose:
                print(f"   ❌ Calendar import failed: {e}")


def sync_command(
    vault_path: str,
    list_ids: Optional[List[str]] = None,
    dry_run: bool = True,
    direction: str = "both",
    config: Optional[SyncConfig] = None,
    show_summary: bool = True,
) -> dict:
    """Execute sync between Obsidian and Reminders."""
    logger = logging.getLogger(__name__)

    if not os.path.exists(vault_path):
        if show_summary:
            print(f"Vault not found at {vault_path}")
        return {
            'success': False,
            'vault_path': vault_path,
            'vault_name': os.path.basename(vault_path),
            'error': f"Vault not found at {vault_path}"
        }

    # Use provided config or defaults
    if not config:
        config = SyncConfig()

    engine_config = {
        "min_score": config.min_score,
        "days_tolerance": config.days_tolerance,
        "include_completed": config.include_completed,
        "obsidian_inbox_path": config.obsidian_inbox_path,
        "default_calendar_id": config.default_calendar_id,
        "links_path": config.links_path,
    }

    engine = SyncEngine(engine_config, logger, direction=direction, sync_config=config)

    try:
        # Run initial sync to get tasks and perform regular sync operations
        results = engine.sync(vault_path, list_ids, dry_run)

        created_obs_ids = results.get('created_obs_tasks', [])
        created_rem_ids = results.get('created_rem_tasks', [])

        if show_summary:
            print(f"\nSync {'Preview' if dry_run else 'Complete'}:")
            print(f"  Obsidian tasks: {results['obs_tasks']}")
            print(f"  Reminders tasks: {results['rem_tasks']}")
            print(f"  Matched pairs: {results['links']}")
            
            # Display tag routing summary if available
            if 'tag_summary' in results and results['tag_summary']:
                print("\n📊 Tag Routing Summary:")
                for tag, stats in results['tag_summary'].items():
                    print(f"  {tag}:")
                    for list_name, count in stats.items():
                        print(f"    → {list_name}: {count} task(s)")
            
            # Display verbose Reminders → Obsidian creation details if in verbose mode
            if logger.isEnabledFor(logging.DEBUG) and 'rem_to_obs_creations' in results:
                rem_to_obs_creations = results['rem_to_obs_creations']
                if rem_to_obs_creations:
                    action = "to create" if dry_run else "created"
                    print(f"\n📥 Obsidian tasks {action} from Reminders:")
                    
                    # Group creations by list name
                    by_list = {}
                    for creation in rem_to_obs_creations:
                        list_name = creation.get('list_name', 'Unknown')
                        if list_name not in by_list:
                            by_list[list_name] = []
                        by_list[list_name].append(creation)
                    
                    # Display grouped by list
                    for list_name, creations in sorted(by_list.items()):
                        print(f"  From {list_name}:")
                        for creation in creations:
                            title = creation.get('title', 'Untitled')
                            calendar_id = creation.get('calendar_id', 'N/A')
                            print(f"    • '{title}' (calendar_id: {calendar_id})")

        changes = results.get("changes", {})
        has_changes = any([
            changes.get("obs_updated", 0),
            changes.get("rem_updated", 0),
            changes.get("obs_created", 0),
            changes.get("rem_created", 0),
            changes.get("obs_deleted", 0),
            changes.get("rem_deleted", 0),
        ])
        
        if show_summary:
            if has_changes:
                print(f"\nChanges {'to make' if dry_run else 'made'}:")
                if changes.get("obs_updated", 0):
                    print(f"  Obsidian updates: {changes['obs_updated']}")
                if changes.get("rem_updated", 0):
                    print(f"  Reminders updates: {changes['rem_updated']}")
                if changes.get("obs_created", 0):
                    print(f"  Obsidian creations: {changes['obs_created']}")
                if changes.get("rem_created", 0):
                    print(f"  Reminders creations: {changes['rem_created']}")
                if changes.get("obs_deleted", 0):
                    print(f"  Obsidian deletions: {changes['obs_deleted']}")
                if changes.get("rem_deleted", 0):
                    print(f"  Reminders deletions: {changes['rem_deleted']}")
                if changes.get("links_created", 0):
                    print(f"  New sync links: {changes['links_created']}")
                if changes.get("links_deleted", 0):
                    print(f"  Removed sync links: {changes['links_deleted']}")
                if changes.get("conflicts_resolved", 0):
                    print(f"  Conflicts resolved: {changes['conflicts_resolved']}")
            else:
                print("\nNo changes needed - everything is in sync!")

        # Run deduplication analysis if enabled
        dedup_stats = {"obs_deleted": 0, "rem_deleted": 0}
        if config.enable_deduplication:
            dedup_stats = _run_deduplication(
                vault_path=vault_path,
                list_ids=list_ids,
                dry_run=dry_run,
                config=config,
                logger=logger,
                show_summary=show_summary,
                created_obs_ids=created_obs_ids,
                created_rem_ids=created_rem_ids,
            )
            
            # Add deduplication stats to changes
            if dedup_stats["obs_deleted"] or dedup_stats["rem_deleted"]:
                changes.update(dedup_stats)
                
        # Show deduplication summary if any deletions occurred
        if show_summary and (dedup_stats["obs_deleted"] or dedup_stats["rem_deleted"]):
            print(f"\nDeduplication {'to perform' if dry_run else 'complete'}:")
            if dedup_stats["obs_deleted"]:
                print(f"  Obsidian deletions: {dedup_stats['obs_deleted']}")
            if dedup_stats["rem_deleted"]:
                print(f"  Reminders deletions: {dedup_stats['rem_deleted']}")

        if show_summary and dry_run:
            print("\nThis was a dry run. Use --apply to make changes.")

        # Return comprehensive results
        return {
            'success': True,
            'vault_path': vault_path,
            'vault_name': os.path.basename(vault_path),
            'results': results,
            'dedup_stats': dedup_stats,
            'has_changes': has_changes or dedup_stats["obs_deleted"] or dedup_stats["rem_deleted"]
        }

    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Sync failed: %s", exc)
        if show_summary:
            print(f"Error: Sync failed - {exc}")
        return {
            'success': False,
            'vault_path': vault_path,
            'vault_name': os.path.basename(vault_path),
            'error': str(exc)
        }


def _run_deduplication(
    vault_path: str,
    list_ids: Optional[List[str]] = None,
    dry_run: bool = True,
    config: Optional[SyncConfig] = None,
    logger: Optional[logging.Logger] = None,
    show_summary: bool = True,
    created_obs_ids: Optional[List[str]] = None,
    created_rem_ids: Optional[List[str]] = None,
) -> dict:
    """
    Run deduplication analysis and optionally apply deletions.
    
    Args:
        vault_path: Path to the Obsidian vault
        list_ids: List of Reminders list IDs to analyze
        dry_run: If True, don't actually delete tasks
        config: Sync configuration
        logger: Logger instance
        
    Returns:
        Dict with deletion statistics
    """
    if not logger:
        logger = logging.getLogger(__name__)
    
    if not config:
        config = SyncConfig()
    
    # Initialize task managers and deduplicator
    from ..obsidian.tasks import ObsidianTaskManager
    from ..reminders.tasks import RemindersTaskManager
    
    obs_manager = ObsidianTaskManager(logger=logger)
    rem_manager = RemindersTaskManager(logger=logger)
    deduplicator = TaskDeduplicator(obs_manager, rem_manager, logger, links_path=config.links_path)
    
    try:
        # Get current tasks
        obs_tasks = obs_manager.list_tasks(vault_path, include_completed=config.include_completed)
        rem_tasks = rem_manager.list_tasks(list_ids, include_completed=config.include_completed)

        created_obs_set = {uid for uid in (created_obs_ids or []) if uid}
        created_rem_set = {uid for uid in (created_rem_ids or []) if uid}

        if created_obs_set:
            obs_tasks = [task for task in obs_tasks if getattr(task, "uuid", None) not in created_obs_set]
        if created_rem_set:
            rem_tasks = [task for task in rem_tasks if getattr(task, "uuid", None) not in created_rem_set]

        if (created_obs_set or created_rem_set) and not dry_run:
            if show_summary:
                print("\n⏭️  Skipping deduplication for this run (new tasks were just created)")
            logger.debug(
                "Skipping deduplication due to newly created tasks: obs=%s rem=%s",
                sorted(created_obs_set),
                sorted(created_rem_set),
            )
            return {"obs_deleted": 0, "rem_deleted": 0}
        
        # Load existing sync links to exclude already-synced task pairs
        from ..sync.engine import SyncEngine
        temp_engine = SyncEngine({"links_path": config.links_path}, logger, sync_config=config)
        existing_links = temp_engine._load_existing_links()

        if existing_links and (created_obs_set or created_rem_set):
            existing_links = [
                link
                for link in existing_links
                if getattr(link, "obs_uuid", None) not in created_obs_set
                and getattr(link, "rem_uuid", None) not in created_rem_set
            ]
        
        # Analyze for duplicates, excluding already-synced pairs
        dedup_results = deduplicator.analyze_duplicates(obs_tasks, rem_tasks, existing_links)
        
        if dedup_results.duplicate_clusters == 0:
            logger.info("No duplicate tasks found")
            return {"obs_deleted": 0, "rem_deleted": 0}
        
        duplicate_clusters = dedup_results.get_duplicate_clusters()
        
        # Show summary for dry run
        if show_summary:
            print(f"\n🔍 Deduplication Analysis:")
            print(f"  Found {dedup_results.duplicate_clusters} duplicate cluster(s)")
            print(f"  Affecting {dedup_results.duplicate_tasks} task(s)")
        
        if dry_run:
            # In dry run, just report what would be done
            total_would_delete = sum(
                cluster.total_count - 1 for cluster in duplicate_clusters
            )
            if show_summary:
                print(f"  Would interactively resolve {total_would_delete} duplicate(s)")
            return {"obs_deleted": 0, "rem_deleted": 0}
        
        # For apply mode, check if user wants to run deduplication
        if not config.dedup_auto_apply:
            if not confirm_deduplication():
                if show_summary:
                    print("Deduplication skipped.")
                return {"obs_deleted": 0, "rem_deleted": 0}
        
        # Create task maps for linked counterpart display
        obs_tasks_map = {task.uuid: task for task in obs_tasks}
        rem_tasks_map = {task.uuid: task for task in rem_tasks}
        
        # Interactive deduplication
        total_stats = {"obs_deleted": 0, "rem_deleted": 0}
        
        for i, cluster in enumerate(duplicate_clusters, 1):
            try:
                print(f"\n{'='*60}")
                print(f"Duplicate cluster {i} of {len(duplicate_clusters)}:")
                display_duplicate_cluster(cluster, obs_tasks_map, rem_tasks_map)
                
                # Get user choice
                keep_indices = prompt_for_keeps(cluster)
            except Exception as e:
                logger.error(f"Error displaying cluster {i}: {e}")
                print(f"   ⚠️  Error processing cluster {i}, skipping...")
                continue
            
            if keep_indices is None:
                print("   ⏭️  Skipped this cluster")
                continue
                
            # Determine which tasks to delete
            all_tasks = cluster.get_all_tasks()
            if not keep_indices:  # User selected 'none'
                tasks_to_delete = all_tasks
            else:
                # Keep selected tasks, delete the rest
                keep_set = set(keep_indices)
                tasks_to_delete = [
                    task for idx, task in enumerate(all_tasks)
                    if idx not in keep_set
                ]
            
            if tasks_to_delete:
                # Perform deletions
                delete_stats = deduplicator.delete_tasks(tasks_to_delete, dry_run=False)
                total_stats["obs_deleted"] += delete_stats["obs_deleted"]
                total_stats["rem_deleted"] += delete_stats["rem_deleted"]
                
                kept_count = len(all_tasks) - len(tasks_to_delete)
                print(f"   ✅ Kept {kept_count} task(s), deleted {len(tasks_to_delete)} task(s)")
            else:
                print("   📝 All tasks kept")
        
        return total_stats
        
    except Exception as exc:
        logger.error("Deduplication failed: %s", exc)
        print(f"Error: Deduplication failed - {exc}")
        return {"obs_deleted": 0, "rem_deleted": 0}