"""Sync command - perform bidirectional task synchronization."""

import os
from typing import List, Optional
import logging

from ..core.config import SyncConfig
from ..sync.engine import SyncEngine


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

        if dry_run:
            print("\nThis was a dry run. Use --apply to make changes.")

        return True

    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Sync failed: %s", exc)
        print(f"Error: Sync failed - {exc}")
        return False