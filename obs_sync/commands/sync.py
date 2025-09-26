"""Sync command - perform bidirectional task synchronization."""

import os
from typing import List, Optional
import logging

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
                return sync_command(
                    vault_path=vault_path,
                    list_ids=list_ids,
                    dry_run=not apply_changes,
                    direction=direction,
                    config=self.config,
                )

            # Process each vault mapping
            all_success = True
            total_vaults = len(mappings)

            print(f"\n🔄 Syncing {total_vaults} vault(s)...")
            print("=" * 50)

            for idx, (vault, calendar_id) in enumerate(mappings, 1):
                vault_path = vault.path

                if not os.path.exists(vault_path):
                    print(f"\n⚠️  Vault {idx}/{total_vaults}: {vault.name}")
                    print(f"   Vault path does not exist: {vault_path}")
                    all_success = False
                    continue

                # Find the list name for display
                list_name = "Unknown"
                for lst in self.config.reminders_lists:
                    if lst.identifier == calendar_id:
                        list_name = lst.name
                        break

                print(f"\n📁 Vault {idx}/{total_vaults}: {vault.name}")
                print(f"   → Syncing with list: {list_name}")

                # Run sync for this vault-list pair
                success = sync_command(
                    vault_path=vault_path,
                    list_ids=[calendar_id],  # Single list for this vault
                    dry_run=not apply_changes,
                    direction=direction,
                    config=self.config,
                )

                if not success:
                    all_success = False
                    print(f"   ❌ Sync failed for vault: {vault.name}")

                if idx < total_vaults:
                    print("-" * 50)

            print("\n" + "=" * 50)
            if all_success:
                print("✅ All vaults synced successfully!")
            else:
                print("⚠️  Some vaults had sync errors. Check the output above.")

            return all_success

        except Exception as exc:  # pragma: no cover - defensive
            self.logger.error("Sync command failed: %s", exc)
            if self.verbose:
                import traceback

                traceback.print_exc()
            return False


def sync_command(
    vault_path: str,
    list_ids: Optional[List[str]] = None,
    dry_run: bool = True,
    direction: str = "both",
    config: Optional[SyncConfig] = None,
) -> bool:
    """Execute sync between Obsidian and Reminders."""
    logger = logging.getLogger(__name__)

    if not os.path.exists(vault_path):
        print(f"Vault not found at {vault_path}")
        return False

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

    engine = SyncEngine(engine_config, logger, direction=direction)

    try:
        # Run initial sync to get tasks and perform regular sync operations
        results = engine.sync(vault_path, list_ids, dry_run)

        print(f"\nSync {'Preview' if dry_run else 'Complete'}:")
        print(f"  Obsidian tasks: {results['obs_tasks']}")
        print(f"  Reminders tasks: {results['rem_tasks']}")
        print(f"  Matched pairs: {results['links']}")

        changes = results["changes"]
        has_changes = any([
            changes["obs_updated"],
            changes["rem_updated"],
            changes["obs_created"],
            changes["rem_created"],
            changes.get("obs_deleted", 0),
            changes.get("rem_deleted", 0),
        ])
        
        if has_changes:
            print(f"\nChanges {'to make' if dry_run else 'made'}:")
            if changes["obs_updated"]:
                print(f"  Obsidian updates: {changes['obs_updated']}")
            if changes["rem_updated"]:
                print(f"  Reminders updates: {changes['rem_updated']}")
            if changes["obs_created"]:
                print(f"  Obsidian creations: {changes['obs_created']}")
            if changes["rem_created"]:
                print(f"  Reminders creations: {changes['rem_created']}")
            if changes.get("obs_deleted", 0):
                print(f"  Obsidian deletions: {changes['obs_deleted']}")
            if changes.get("rem_deleted", 0):
                print(f"  Reminders deletions: {changes['rem_deleted']}")
            if changes["links_created"]:
                print(f"  New sync links: {changes['links_created']}")
            if changes.get("links_deleted", 0):
                print(f"  Removed sync links: {changes['links_deleted']}")
            if changes["conflicts_resolved"]:
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
                logger=logger
            )
            
            # Add deduplication stats to changes
            if dedup_stats["obs_deleted"] or dedup_stats["rem_deleted"]:
                changes.update(dedup_stats)
                
        # Show deduplication summary if any deletions occurred
        if dedup_stats["obs_deleted"] or dedup_stats["rem_deleted"]:
            print(f"\nDeduplication {'to perform' if dry_run else 'complete'}:")
            if dedup_stats["obs_deleted"]:
                print(f"  Obsidian deletions: {dedup_stats['obs_deleted']}")
            if dedup_stats["rem_deleted"]:
                print(f"  Reminders deletions: {dedup_stats['rem_deleted']}")

        if dry_run:
            print("\nThis was a dry run. Use --apply to make changes.")

        return True

    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Sync failed: %s", exc)
        print(f"Error: Sync failed - {exc}")
        return False


def _run_deduplication(
    vault_path: str,
    list_ids: Optional[List[str]] = None,
    dry_run: bool = True,
    config: Optional[SyncConfig] = None,
    logger: Optional[logging.Logger] = None,
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
    deduplicator = TaskDeduplicator(obs_manager, rem_manager, logger)
    
    try:
        # Get current tasks
        obs_tasks = obs_manager.list_tasks(vault_path, include_completed=config.include_completed)
        rem_tasks = rem_manager.list_tasks(list_ids, include_completed=config.include_completed)
        
        # Load existing sync links to exclude already-synced task pairs
        from ..sync.engine import SyncEngine
        temp_engine = SyncEngine({"links_path": config.links_path}, logger)
        existing_links = temp_engine._load_existing_links()
        
        # Analyze for duplicates, excluding already-synced pairs
        dedup_results = deduplicator.analyze_duplicates(obs_tasks, rem_tasks, existing_links)
        
        if dedup_results.duplicate_clusters == 0:
            logger.info("No duplicate tasks found")
            return {"obs_deleted": 0, "rem_deleted": 0}
        
        duplicate_clusters = dedup_results.get_duplicate_clusters()
        
        # Show summary for dry run
        print(f"\n🔍 Deduplication Analysis:")
        print(f"  Found {dedup_results.duplicate_clusters} duplicate cluster(s)")
        print(f"  Affecting {dedup_results.duplicate_tasks} task(s)")
        
        if dry_run:
            # In dry run, just report what would be done
            total_would_delete = sum(
                cluster.total_count - 1 for cluster in duplicate_clusters
            )
            print(f"  Would interactively resolve {total_would_delete} duplicate(s)")
            return {"obs_deleted": 0, "rem_deleted": 0}
        
        # For apply mode, check if user wants to run deduplication
        if not config.dedup_auto_apply:
            if not confirm_deduplication():
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