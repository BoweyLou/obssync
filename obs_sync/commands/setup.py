"""
Setup command for initial configuration.
"""

import os
import traceback
from collections import Counter
from pathlib import Path
from typing import List, Optional, Set

from obs_sync.core.models import SyncConfig, Vault, RemindersList
from obs_sync.obsidian.tasks import ObsidianTaskManager
from obs_sync.obsidian.vault import find_vaults
from obs_sync.utils.suggestions import (
    SuggestionAnalyzer,
    VaultMappingSuggestion,
    TagRouteSuggestion,
)


class SetupCommand:
    """Interactive setup command."""

    def __init__(self, config: SyncConfig, verbose: bool = False, enable_suggestions: bool = True):
        """Initialize setup command.
        
        Args:
            config: Sync configuration
            verbose: Enable verbose output
            enable_suggestions: Enable smart routing suggestions (disable for testing)
        """
        self.config = config
        self.verbose = verbose
        self.enable_suggestions = enable_suggestions

    def run(self, reconfigure: bool = False, add: bool = False) -> bool:
        """Run interactive setup or additive flow."""
        print("obs-sync Setup Assistant")
        print("=" * 40)

        if add and reconfigure:
            print("\n⚠️ Ignoring --add because --reconfigure already covers adding items.")
            add = False

        if add:
            print("\nℹ️  '--add' is deprecated; use --reconfigure and pick the add options during that flow.")
            if not self.config.vaults:
                print("\nNo existing configuration detected—starting the full setup.")
                return self._run_full_setup(reconfigure=True)
            return self._run_additional_flow()

        return self._run_full_setup(reconfigure=reconfigure)

    def _show_backup_warning(self) -> bool:
        """Show backup warning and get user confirmation.

        Returns:
            True if user confirms, False otherwise
        """
        print("\n⚠️  BACKUP REMINDER")
        print("=" * 40)
        print("obs-sync will modify your Obsidian vaults and Apple Reminders.")
        print("Before proceeding, ensure you have backups of:")
        print("  • Your Obsidian vaults")
        print("  • Your Apple Reminders lists")
        print()
        confirm = input("Continue with setup? (y/N): ").strip().lower()
        return confirm == 'y'

    def _run_full_setup(self, reconfigure: bool) -> bool:
        """Run the full interactive setup."""
        if self.config.vaults and not reconfigure:
            print("An existing configuration is in place. Run with --reconfigure to update it.")
            return True
        
        # If reconfiguring and already have config, ask whether to reset or amend
        if reconfigure and self.config.vaults:
            return self._handle_reconfigure_choice()

        # Show backup warning for first-time setup
        if not self.config.vaults:
            if not self._show_backup_warning():
                print("\nSetup cancelled. No changes were made.")
                return False

        # Store existing vault IDs so we can preserve stable identifiers when reselecting vault paths
        existing_vault_ids = {}
        if self.config.vaults:
            for vault in self.config.vaults:
                normalized_path = self._normalize_path(vault.path)
                existing_vault_ids[normalized_path] = vault.vault_id

        # Discover vaults
        print("\n🔍 Looking for Obsidian vaults...")
        vaults = self._discover_vaults()

        if not vaults:
            print("No Obsidian vaults were detected—enter a vault path manually.")
            vault_path = input("Enter vault path: ").strip()
            if os.path.isdir(vault_path):
                vault_name = os.path.basename(vault_path)
                vaults = [Vault(name=vault_name, path=vault_path)]
            else:
                print("That path couldn’t be opened. Enter a valid vault directory.")
                return False

        # Select vaults
        print(f"\nFound {len(vaults)} vault(s):")
        for i, vault in enumerate(vaults, 1):
            print(f"  {i}. {vault.name} — {vault.path}")

        if len(vaults) > 1:
            print("\nChoose the vaults to sync (comma-separated numbers or type 'all'):")
            selection = input("Your selection: ").strip()

            if selection.lower() == 'all':
                selected_vaults = vaults
            else:
                try:
                    indices = [int(x.strip()) - 1 for x in selection.split(',')]
                    selected_vaults = [vaults[i] for i in indices if 0 <= i < len(vaults)]
                except (ValueError, IndexError):
                    print("Selection not recognized—use numbers or 'all'.")
                    return False
        else:
            selected_vaults = vaults

        # Preserve existing vault IDs for selected vaults
        for vault in selected_vaults:
            normalized_path = self._normalize_path(vault.path)
            if normalized_path in existing_vault_ids:
                old_id = existing_vault_ids[normalized_path]
                vault.vault_id = old_id
                print(f"  ℹ️  Preserving vault ID for {vault.name}: {old_id}")

        # Set default vault
        if len(selected_vaults) > 1:
            print("\nPick the default vault.")
            for i, vault in enumerate(selected_vaults, 1):
                print(f"  {i}. {vault.name}")
            try:
                default_idx = int(input("Default vault number: ").strip()) - 1
                if 0 <= default_idx < len(selected_vaults):
                    selected_vaults[default_idx].is_default = True
                    self.config.default_vault_id = selected_vaults[default_idx].vault_id
            except (ValueError, IndexError):
                selected_vaults[0].is_default = True
                self.config.default_vault_id = selected_vaults[0].vault_id
        elif selected_vaults:
            selected_vaults[0].is_default = True
            self.config.default_vault_id = selected_vaults[0].vault_id

        self.config.vaults = selected_vaults

        # Discover Reminders lists
        print("\n📋 Discovering Apple Reminders lists...")
        lists = self._discover_reminders_lists()

        if lists:
            print(f"\nFound {len(lists)} Reminders list(s):")
            for i, lst in enumerate(lists, 1):
                print(f"  {i}. {lst.name} — {lst.identifier or 'Unknown ID'}")

            print("\nChoose the Reminders lists to sync (comma-separated numbers or 'all'):")
            selection = input("Your selection: ").strip()

            if selection.lower() == 'all':
                selected_lists = lists
            else:
                try:
                    indices = [int(x.strip()) - 1 for x in selection.split(',')]
                    selected_lists = [lists[i] for i in indices if 0 <= i < len(lists)]
                except (ValueError, IndexError):
                    print("Invalid selection.")
                    selected_lists = []

            self.config.reminders_lists = selected_lists
            self.config.calendar_ids = [lst.identifier for lst in selected_lists]

            # Set default list
            if selected_lists:
                self.config.default_calendar_id = selected_lists[0].identifier

        # Set up vault-to-list mappings
        if self.config.vaults and self.config.reminders_lists:
            print("\n🔗 Map vaults to Reminders lists")
            print("Assign each vault to a default Reminders list for syncing:")

            for vault in self.config.vaults:
                print(f"\nVault: {vault.name}")
                
                # Try to offer smart suggestions first (optional)
                suggested_list_id = None
                if self.enable_suggestions and len(self.config.reminders_lists) > 1:
                    suggested_list_id = self._offer_vault_mapping_suggestions(vault)
                
                # If no suggestion accepted, proceed with manual selection
                if not suggested_list_id:
                    print("Available lists:")
                    for i, lst in enumerate(self.config.reminders_lists, 1):
                        print(f"  {i}. {lst.name} — {lst.identifier or 'Unknown ID'}")

                    # Default to first list or existing mapping
                    existing_mapping = self.config.get_vault_mapping(vault.vault_id)
                    default_choice = 1
                    if existing_mapping:
                        # Find index of existing mapping
                        for i, lst in enumerate(self.config.reminders_lists, 1):
                            if lst.identifier == existing_mapping:
                                default_choice = i
                                break

                    choice_input = input(f"Select a Reminders list for this vault [{default_choice}] (Enter to accept default): ").strip()

                    if choice_input:
                        try:
                            choice = int(choice_input)
                        except ValueError:
                            choice = default_choice
                    else:
                        choice = default_choice

                    if 1 <= choice <= len(self.config.reminders_lists):
                        selected_list = self.config.reminders_lists[choice - 1]
                        suggested_list_id = selected_list.identifier
                    else:
                        # Default to first list if invalid choice
                        selected_list = self.config.reminders_lists[0]
                        suggested_list_id = selected_list.identifier
                
                # Apply the mapping
                self.config.set_vault_mapping(vault.vault_id, suggested_list_id)
                list_name = self._get_list_name(suggested_list_id)
                print(f"✓ Mapped to {list_name}.")

                self._configure_tag_routes(vault)

        # Sync settings
        print("\n⚙️ Sync settings")

        # Minimum score
        print(f"Minimum match score (0.0-1.0) [default {self.config.min_score}]: ", end="")
        score_input = input().strip()
        if score_input:
            try:
                self.config.min_score = float(score_input)
            except ValueError:
                pass

        # Include completed tasks
        print("Include completed tasks? (y/N): ", end="")
        include_input = input().strip().lower()
        self.config.include_completed = include_input == 'y'

        # Calendar sync
        print("Sync Apple Calendar events to daily notes? (y/N): ", end="")
        calendar_input = input().strip().lower()
        self.config.sync_calendar_events = calendar_input == 'y'

        # Automation setup (macOS only)
        self._prompt_automation_setup(is_initial_setup=True)

        print("\n✅ Setup complete")
        print("\nNext steps:")
        print("  1. Run 'obs-sync sync' to review changes")
        print("  2. Run 'obs-sync sync --apply' to apply changes")

        return True

    def _handle_reconfigure_choice(self) -> bool:
        """Handle the reconfigure choice between reset and amend."""
        print("\n⚙️ Reconfigure options")
        print("  1. Reset - clear the configuration and start over")
        print("  2. Amend - adjust vault/list mappings or tag routes")
        
        while True:
            choice = input("\nChoose an option [1-2]: ").strip()
            if choice == '1':
                print("\n🔄 Resetting configuration...")
                return self._run_full_reset()
            elif choice == '2':
                print("\n✏️  Amending existing configuration...")
                return self._run_amend_flow()
            else:
                print("Please enter 1 or 2 to continue.")
    
    def _run_full_reset(self) -> bool:
        """Run the full reset flow - clear all existing state and start fresh."""
        print("\n🗑️ Clearing existing sync data...")
        
        # Clear sync links store
        try:
            from ..core.paths import get_path_manager
            path_manager = get_path_manager()
            sync_links_path = path_manager.sync_links_path
            if sync_links_path.exists():
                sync_links_path.unlink()
                print(f"✓ Removed sync links store - {sync_links_path}")
            else:
                print("✓ No existing sync link store found.")
                
            # Clear task indices as well for clean slate
            obsidian_index_path = path_manager.obsidian_index_path
            if obsidian_index_path.exists():
                obsidian_index_path.unlink()
                print(f"✓ Removed Obsidian task index - {obsidian_index_path}")
                
            reminders_index_path = path_manager.reminders_index_path
            if reminders_index_path.exists():
                reminders_index_path.unlink()
                print(f"✓ Removed Reminders task index - {reminders_index_path}")
                
        except Exception as e:
            print(f"⚠️ Warning: Could not clear sync store: {e}")
            if self.verbose:
                traceback.print_exc()
        
        # Clear inbox files from existing vaults
        self._clear_inbox_files()
        
        # Clear tag routes from config
        self.config.tag_routes = []
        print("✓ Cleared tag routes.")
        
        # Continue with the original full setup logic
        return self._continue_full_setup()
    
    def _clear_inbox_files(self) -> None:
        """Clear inbox files from all configured vaults."""
        if not self.config.vaults:
            print("✓ No vaults configured—skipping inbox cleanup.")
            return
            
        inbox_filename = self.config.obsidian_inbox_path
        cleared_count = 0
        
        for vault in self.config.vaults:
            try:
                vault_path = Path(vault.path)
                if not vault_path.exists():
                    if self.verbose:
                        print(f"⚠️ Vault path does not exist: {vault_path}")
                    continue
                    
                inbox_path = vault_path / inbox_filename
                if inbox_path.exists():
                    inbox_path.unlink()
                    cleared_count += 1
                    if self.verbose:
                        print(f"✓ Removed inbox from {vault.name} - {inbox_path}")
                        
            except Exception as e:
                print(f"⚠️ Could not clear inbox from {vault.name}: {e}")
                if self.verbose:
                    traceback.print_exc()
        
        if cleared_count > 0:
            print(f"✓ Cleared {cleared_count} inbox files.")
        else:
            print("✓ No inbox files needed removal.")

    def _clear_vault_inbox(self, vault_path: str, vault_name: str) -> bool:
        """Clear inbox file from a specific vault.
        
        Args:
            vault_path: Path to the vault
            vault_name: Name of the vault (for logging)
            
        Returns:
            True if inbox was cleared or didn't exist, False on error
        """
        try:
            vault_path_obj = Path(vault_path)
            if not vault_path_obj.exists():
                if self.verbose:
                    print(f"⚠️ Vault path does not exist: {vault_path}")
                return True  # Consider non-existent path as "cleared"
                
            inbox_path = vault_path_obj / self.config.obsidian_inbox_path
            if inbox_path.exists():
                inbox_path.unlink()
                print(f"✓ Removed inbox from {vault_name} - {inbox_path}")
            elif self.verbose:
                print(f"✓ No inbox file found in {vault_name}.")
            return True
            
        except Exception as e:
            print(f"⚠️ Could not clear inbox from {vault_name}: {e}")
            if self.verbose:
                traceback.print_exc()
            return False

    def _clear_vault_sync_links(self, vault_id: str) -> None:
        """Clear sync links for a specific vault from the links store.
        
        Args:
            vault_id: The vault ID to clear links for
        """
        try:
            from ..utils.io import safe_read_json, safe_write_json
            from ..core.paths import get_path_manager
            path_manager = get_path_manager()
            sync_links_path = path_manager.sync_links_path
            
            if not sync_links_path.exists():
                if self.verbose:
                    print("✓ No sync links file found.")
                return
                
            # Load existing links
            links_data = safe_read_json(str(sync_links_path), default={"links": []})
            original_count = len(links_data.get("links", []))
            
            # Filter out links for the removed vault
            filtered_links = [
                link for link in links_data.get("links", [])
                if link.get("vault_id") != vault_id
            ]
            
            # Save filtered links
            links_data["links"] = filtered_links
            if safe_write_json(str(sync_links_path), links_data):
                removed_count = original_count - len(filtered_links)
                if removed_count > 0:
                    print(f"✓ Removed {removed_count} sync link(s) for vault.")
                elif self.verbose:
                    print("✓ No sync links found for this vault.")
            else:
                print("⚠️ Could not update the sync links file.")
                
        except Exception as e:
            print(f"⚠️ Could not clear sync links: {e}")
            if self.verbose:
                traceback.print_exc()
    
    def _run_amend_flow(self) -> bool:
        """Amend existing vault/list mappings and tag routes without full reset."""
        print("\n📋 Current configuration overview:")
        print(f"\nVaults ({len(self.config.vaults)}):")
        for vault in self.config.vaults:
            default_marker = " (default)" if vault.is_default else ""
            print(f"  • {vault.name}{default_marker}")
        
        print(f"\nReminders lists ({len(self.config.reminders_lists)}):")
        for lst in self.config.reminders_lists:
            default_marker = " (default)" if lst.identifier == self.config.default_calendar_id else ""
            print(f"  • {lst.name}{default_marker}")
        
        print("\n📝 What would you like to update?")
        menu_options = [
            ("1", "Vault to List mappings", self._amend_vault_mappings),
            ("2", "Tag routing rules", self._amend_tag_routes),
            ("3", "Default vault", self._amend_default_vault),
            ("4", "Default Reminders list", self._amend_default_list),
            ("5", "Calendar sync settings", self._amend_calendar_sync),
            ("6", "Add a new vault", self._add_new_vaults_option),
            ("7", "Add a new Reminders list", self._add_new_reminders_option),
            ("8", "Remove a vault", self._remove_vault),
            ("9", "Remove a Reminders list", self._remove_reminders_list),
            ("10", "Automation settings (macOS LaunchAgent)", self._amend_automation),
            ("11", "Insights and analytics settings", self._amend_insights_settings),
        ]

        for key, label, _ in menu_options:
            print(f"  {key}. {label}")
        print("  12. Do everything in options 1-5, 10, and 11")
        print("  13. Cancel")

        choice = input("\nSelect options (comma-separated, e.g. '1,2' or 'all'): ").strip()
        if not choice:
            print("\nNo amendments were applied.")
            return True

        lower_choice = choice.lower()
        if lower_choice == 'cancel' or choice == '13':
            print("\nAmendment cancelled.")
            return True

        if lower_choice == 'all' or choice == '12':
            selected_keys = ['1', '2', '3', '4', '5', '10', '11']
        else:
            selected_keys = [c.strip() for c in choice.split(',') if c.strip()]

        option_map = {key: handler for key, _, handler in menu_options}

        executed = False
        for key in selected_keys:
            action = option_map.get(key)
            if action:
                action()
                executed = True
            else:
                print(f"\n⚠️  Unknown option '{key}'. Skipping.")

        if executed:
            print("\n✅ Configuration amendments complete!")
        else:
            print("\nNo amendments were applied.")

        return True
    
    def _amend_vault_mappings(self) -> None:
        """Amend vault to list mappings."""
        print("\n🔗 Update vault-to-list mappings")
        
        for vault in self.config.vaults:
            current_mapping = self.config.get_vault_mapping(vault.vault_id)
            current_list_name = self._get_list_name(current_mapping) if current_mapping else "None"
            
            print(f"\nVault: {vault.name} (currently: {current_list_name})")
            
            # Offer smart suggestions (optional)
            if self.enable_suggestions and len(self.config.reminders_lists) > 1:
                show_suggestion = input("   Show smart suggestion? (y/N): ").strip().lower()
                if show_suggestion == 'y':
                    suggested_list_id = self._offer_vault_mapping_suggestions(vault)
                    if suggested_list_id:
                        self.config.set_vault_mapping(vault.vault_id, suggested_list_id)
                        list_name = self._get_list_name(suggested_list_id)
                        print(f"✓ Updated mapping to {list_name}.")
                        continue
            
            print("Available lists:")
            for i, lst in enumerate(self.config.reminders_lists, 1):
                current_marker = " (current)" if lst.identifier == current_mapping else ""
                print(f"  {i}. {lst.name}{current_marker} — {lst.identifier or 'Unknown ID'}")
            
            print("Press Enter to keep the current list, or enter a new list number:")
            choice_input = input("Enter choice: ").strip()
            
            if choice_input:
                try:
                    choice = int(choice_input)
                    if 1 <= choice <= len(self.config.reminders_lists):
                        selected_list = self.config.reminders_lists[choice - 1]
                        self.config.set_vault_mapping(vault.vault_id, selected_list.identifier)
                        print(f"✓ Updated mapping to {selected_list.name}.")
                except ValueError:
                    print(f"⚠️ Input not understood—keeping the current mapping.")
    
    def _amend_tag_routes(self) -> None:
        """Amend tag routing rules for all vaults."""
        print("\n🏷️  Tag Route Amendment")
        
        for vault in self.config.vaults:
            print(f"\nVault: {vault.name}")
            response = input("Configure tag routes for this vault? (y/N): ").strip().lower()
            if response == 'y':
                self._configure_tag_routes(vault)
    
    def _amend_default_vault(self) -> None:
        """Amend the default vault selection."""
        current_default = self.config.default_vault
        print(f"\n📁 Current default vault: {current_default.name if current_default else 'None'}")
        print("\nSelect a new default vault:")
        
        for i, vault in enumerate(self.config.vaults, 1):
            current_marker = " (current)" if vault.is_default else ""
            print(f"  {i}. {vault.name}{current_marker}")
        
        choice_input = input("\nChoice (or Enter to keep current): ").strip()
        if choice_input:
            try:
                choice = int(choice_input)
                if 1 <= choice <= len(self.config.vaults):
                    self._set_default_vault(self.config.vaults[choice - 1].vault_id)
                    print(f"✓ Default vault updated to {self.config.vaults[choice - 1].name}.")
            except (ValueError, IndexError):
                print("⚠️ Invalid selection. Keeping current default.")
    
    def _amend_default_list(self) -> None:
        """Amend the default Reminders list selection."""
        current = next((lst for lst in self.config.reminders_lists
                       if lst.identifier == self.config.default_calendar_id), None)
        print(f"\n📋 Current default Reminders list: {current.name if current else 'None'}")
        print("\nSelect new default list:")
        
        for i, lst in enumerate(self.config.reminders_lists, 1):
            current_marker = " (current)" if lst.identifier == self.config.default_calendar_id else ""
            print(f"  {i}. {lst.name}{current_marker}")
        
        choice_input = input("\nChoice (or Enter to keep current): ").strip()
        if choice_input:
            try:
                choice = int(choice_input)
                if 1 <= choice <= len(self.config.reminders_lists):
                    self.config.default_calendar_id = self.config.reminders_lists[choice - 1].identifier
                    print(f"✓ Default list updated to {self.config.reminders_lists[choice - 1].name}.")
            except (ValueError, IndexError):
                print("⚠️ Invalid selection. Keeping current default.")
    
    def _amend_calendar_sync(self) -> None:
        """Amend the calendar sync setting."""
        current_status = "enabled" if self.config.sync_calendar_events else "disabled"
        print(f"\n📅 Calendar sync to daily notes is currently: {current_status}")
        print("\nCalendar sync automatically imports Apple Calendar events to your default vault's")
        print("daily notes when running 'obs-sync sync --apply' (once per day).")
        
        new_setting = "n" if self.config.sync_calendar_events else "y"
        action = "disable" if self.config.sync_calendar_events else "enable"
        
        choice = input(f"\nWould you like to {action} calendar sync? (y/{new_setting.upper()}): ").strip().lower()
        
        if not choice:
            choice = new_setting
        
        if choice == 'y':
            if not self.config.sync_calendar_events:
                self.config.sync_calendar_events = True
                print("✓ Calendar sync enabled.")
            else:
                print("Calendar sync is already enabled")
        elif choice == 'n':
            if self.config.sync_calendar_events:
                self.config.sync_calendar_events = False
                print("✓ Calendar sync disabled.")
            else:
                print("Calendar sync is already disabled")
        else:
            print("⚠️ Invalid choice. No changes made.")
    
    def _amend_insights_settings(self) -> None:
        """Amend insights and analytics settings."""
        print("\n📊 Insights & Analytics Settings")
        print("\nThese features provide task completion tracking, streak analytics,")
        print("and hygiene recommendations for your Apple Reminders tasks.")
        
        # Show current settings
        print(f"\nCurrent settings:")
        print(f"  • Insights display: {'enabled' if self.config.enable_insights else 'disabled'}")
        print(f"  • Streak tracking: {'enabled' if self.config.enable_streak_tracking else 'disabled'}")
        print(f"  • Daily note injection: {'enabled' if self.config.insights_in_daily_notes else 'disabled'}")
        print(f"  • Hygiene assistant: {'enabled' if self.config.enable_hygiene_assistant else 'disabled'}")
        print(f"  • Stagnant task threshold: {self.config.hygiene_stagnant_threshold} days")
        
        print("\nWhat would you like to update?")
        print("  1. Enable/disable all insights features")
        print("  2. Toggle streak tracking")
        print("  3. Toggle daily note injection")
        print("  4. Toggle hygiene assistant")
        print("  5. Change stagnant task threshold")
        print("  6. Cancel")
        
        choice = input("\nSelect option: ").strip()
        
        if choice == '1':
            # Toggle all features
            new_state = not self.config.enable_insights
            action = "enable" if new_state else "disable"
            confirm = input(f"This will {action} all insights features. Continue? (y/N): ").strip().lower()
            if confirm == 'y':
                self.config.enable_insights = new_state
                self.config.enable_streak_tracking = new_state
                self.config.insights_in_daily_notes = new_state
                self.config.enable_hygiene_assistant = new_state
                print(f"✓ All insights features {'enabled' if new_state else 'disabled'}.")
            else:
                print("Cancelled.")
        
        elif choice == '2':
            # Toggle streak tracking
            self.config.enable_streak_tracking = not self.config.enable_streak_tracking
            status = "enabled" if self.config.enable_streak_tracking else "disabled"
            print(f"✓ Streak tracking {status}.")
        
        elif choice == '3':
            # Toggle daily note injection
            self.config.insights_in_daily_notes = not self.config.insights_in_daily_notes
            status = "enabled" if self.config.insights_in_daily_notes else "disabled"
            print(f"✓ Daily note injection {status}.")
        
        elif choice == '4':
            # Toggle hygiene assistant
            self.config.enable_hygiene_assistant = not self.config.enable_hygiene_assistant
            status = "enabled" if self.config.enable_hygiene_assistant else "disabled"
            print(f"✓ Hygiene assistant {status}.")
        
        elif choice == '5':
            # Change threshold
            print(f"\nCurrent threshold: {self.config.hygiene_stagnant_threshold} days")
            try:
                new_threshold = int(input("Enter new threshold (days): ").strip())
                if new_threshold > 0:
                    self.config.hygiene_stagnant_threshold = new_threshold
                    print(f"✓ Stagnant task threshold set to {new_threshold} days.")
                else:
                    print("⚠️ Threshold must be positive. No changes made.")
            except ValueError:
                print("⚠️ Invalid input. No changes made.")
        
        elif choice == '6':
            print("Cancelled.")
        else:
            print("⚠️ Invalid choice. No changes made.")
    
    def _prompt_automation_setup(self, is_initial_setup: bool = False) -> None:
        """Prompt for and configure automation settings (shared helper).

        Args:
            is_initial_setup: If True, uses first-run defaults and messaging
        """
        from ..utils.launchd import (
            is_macos, is_agent_loaded, load_agent, unload_agent,
            install_agent, uninstall_agent, get_obs_sync_executable,
            describe_interval, get_launchagent_path
        )
        from ..core.paths import get_path_manager

        if not is_macos():
            if not is_initial_setup:  # Only show warning in reconfigure
                print("\n⚠️  Automation via LaunchAgent is only available on macOS.")
            return

        # Show current status
        current_enabled = self.config.automation_enabled
        current_interval = self.config.automation_interval
        agent_loaded = is_agent_loaded()

        if is_initial_setup:
            print("\n🤖 Automation (optional)")
            print("Schedule obs-sync to run automatically in the background.")
            print(f"Current setting: {('enabled' if current_enabled else 'disabled')}")
        else:
            print(f"\n🤖 Automation Settings (macOS LaunchAgent)")
            print(f"  Configuration: {('enabled' if current_enabled else 'disabled')}")
            print(f"  Schedule: {describe_interval(current_interval)}")
            print(f"  LaunchAgent: {('loaded' if agent_loaded else 'not loaded')}")

            if agent_loaded and not current_enabled:
                print("\n⚠️  LaunchAgent is loaded but config shows disabled - they're out of sync")
            elif not agent_loaded and current_enabled:
                print("\n⚠️  Config shows enabled but LaunchAgent is not loaded - they're out of sync")

        # Prompt for enable/disable
        if is_initial_setup:
            print("\nAutomation runs 'obs-sync sync --apply' on a schedule.")
            prompt_text = "Enable automation? (y/N): "
            default_choice = "n"
        else:
            print("\nAutomation runs 'obs-sync sync --apply' on the schedule you choose.")
            action = "disable" if current_enabled else "enable"
            default_choice = "n" if current_enabled else "y"
            prompt_text = "Disable automation now?" if current_enabled else "Enable automation now?"
            prompt_text += f" (y/{default_choice.upper()}): "

        choice = input(prompt_text).strip().lower()

        if not choice:
            choice = default_choice

        if choice == 'n':
            if current_enabled or agent_loaded:
                # Disable automation
                print("\n🛑 Disabling automation...")

                if agent_loaded:
                    success, error = unload_agent()
                    if success:
                        print("✓ LaunchAgent unloaded.")
                    else:
                        print(f"⚠️ Failed to unload LaunchAgent: {error}")

                plist_path = get_launchagent_path()
                if plist_path.exists():
                    success, error = uninstall_agent()
                    if success:
                        print(f"✓ Removed LaunchAgent plist - {plist_path}.")
                    else:
                        print(f"⚠️ Failed to remove plist: {error}")

                self.config.automation_enabled = False
                print("✓ Automation disabled in configuration.")
            else:
                if not is_initial_setup:
                    print("Automation is already disabled.")
            return

        elif choice != 'y':
            if not is_initial_setup:
                print("⚠️ Invalid choice. No changes made.")
            return

        # User wants to enable automation
        print("\n⚙️ Configuring automation schedule...")
        print("\nAvailable schedules:")
        print("  1) Hourly (every 3600 seconds) [recommended]")
        print("  2) Twice daily (every 43,200 seconds / 12 hours)")
        print("  3) Custom interval (specify seconds)")

        schedule_choice = input("Choose a schedule [default 1]: ").strip()

        if not schedule_choice or schedule_choice == '1':
            interval = 3600  # Hourly
        elif schedule_choice == '2':
            interval = 43200  # Twice daily
        elif schedule_choice == '3':
            custom_input = input("Enter a custom interval in seconds: ").strip()
            try:
                interval = int(custom_input)
                if interval < 60:
                    print("⚠️ Minimum interval is 60 seconds. Using 60.")
                    interval = 60
                elif interval > 604800:  # 1 week
                    print("⚠️ Maximum interval is 604800 seconds (one week). Using 604800.")
                    interval = 604800
            except ValueError:
                print("⚠️ Invalid interval. Using default (3600 seconds).")
                interval = 3600
        else:
            print("⚠️ Invalid choice. Using default (hourly).")
            interval = 3600

        print(f"\n  Selected: {describe_interval(interval)}")

        # Find obs-sync executable
        obs_sync_path = get_obs_sync_executable()
        if not obs_sync_path:
            print("\n⚠️ obs-sync executable not found.")
            print("Install obs-sync and confirm it appears in your PATH, then retry.")
            return

        print(f"✓ Using executable: {obs_sync_path}.")

        # Get log directory
        path_manager = get_path_manager()
        log_dir = path_manager.log_dir

        # Unload existing agent if loaded
        if agent_loaded:
            print("\n  Unloading existing LaunchAgent...")
            success, error = unload_agent()
            if not success:
                print(f"⚠️ Warning: Failed to unload the existing agent: {error}")

        # Install the LaunchAgent plist
        print("\n  Installing LaunchAgent...")
        success, error = install_agent(interval, obs_sync_path, log_dir)

        if not success:
            print(f"  ✗ Failed to install LaunchAgent: {error}")
            return

        print(f"✓ LaunchAgent plist created at {get_launchagent_path()}.")

        # Load the agent
        print("  Loading LaunchAgent...")
        success, error = load_agent()

        if not success:
            print(f"  ✗ Failed to load LaunchAgent: {error}")
            return

        print("✓ LaunchAgent loaded and scheduled.")

        # Update config
        self.config.automation_enabled = True
        self.config.automation_interval = interval

        print(f"\n✅ Automation enabled! obs-sync will run {describe_interval(interval)}")
        print(f"   Logs: {log_dir}/obs-sync-agent.stdout.log")
        print(f"         {log_dir}/obs-sync-agent.stderr.log")

    def _amend_automation(self) -> None:
        """Amend automation settings (macOS LaunchAgent)."""
        self._prompt_automation_setup(is_initial_setup=False)
    
    def _continue_full_setup(self) -> bool:
        """Continue with the original full setup flow after reset choice."""
        # This contains the original setup logic that was in _run_full_setup

        # Show backup warning
        if not self._show_backup_warning():
            print("\nSetup cancelled. No changes were made.")
            return False

        # Store existing vault IDs for preservation
        existing_vault_ids = {}
        if self.config.vaults:
            for vault in self.config.vaults:
                normalized_path = self._normalize_path(vault.path)
                existing_vault_ids[normalized_path] = vault.vault_id

        # Discover vaults
        print("\n🔍 Looking for Obsidian vaults...")
        vaults = self._discover_vaults()

        if not vaults:
            print("No Obsidian vaults were detected—enter a vault path manually.")
            vault_path = input("Enter vault path: ").strip()
            if os.path.isdir(vault_path):
                vault_name = os.path.basename(vault_path)
                vaults = [Vault(name=vault_name, path=vault_path)]
            else:
                print("That path couldn’t be opened. Enter a valid vault directory.")
                return False

        # Select vaults
        print(f"\nFound {len(vaults)} vault(s):")
        for i, vault in enumerate(vaults, 1):
            print(f"  {i}. {vault.name} — {vault.path}")

        if len(vaults) > 1:
            print("\nChoose the vaults to sync (comma-separated numbers or type 'all'):")
            selection = input("Your selection: ").strip()

            if selection.lower() == 'all':
                selected_vaults = vaults
            else:
                try:
                    indices = [int(x.strip()) - 1 for x in selection.split(',')]
                    selected_vaults = [vaults[i] for i in indices if 0 <= i < len(vaults)]
                except (ValueError, IndexError):
                    print("Selection not recognized—use numbers or 'all'.")
                    return False
        else:
            selected_vaults = vaults

        # Preserve existing vault IDs for selected vaults
        for vault in selected_vaults:
            normalized_path = self._normalize_path(vault.path)
            if normalized_path in existing_vault_ids:
                old_id = existing_vault_ids[normalized_path]
                vault.vault_id = old_id
                print(f"  ℹ️  Preserving vault ID for {vault.name}: {old_id}")

        # Set default vault
        if len(selected_vaults) > 1:
            print("\nPick the default vault.")
            for i, vault in enumerate(selected_vaults, 1):
                print(f"  {i}. {vault.name}")
            try:
                default_idx = int(input("Default vault number: ").strip()) - 1
                if 0 <= default_idx < len(selected_vaults):
                    selected_vaults[default_idx].is_default = True
                    self.config.default_vault_id = selected_vaults[default_idx].vault_id
            except (ValueError, IndexError):
                selected_vaults[0].is_default = True
                self.config.default_vault_id = selected_vaults[0].vault_id
        elif selected_vaults:
            selected_vaults[0].is_default = True
            self.config.default_vault_id = selected_vaults[0].vault_id

        self.config.vaults = selected_vaults

        # Discover Reminders lists
        print("\n📋 Discovering Apple Reminders lists...")
        lists = self._discover_reminders_lists()

        if lists:
            print(f"\nFound {len(lists)} Reminders list(s):")
            for i, lst in enumerate(lists, 1):
                print(f"  {i}. {lst.name} — {lst.identifier or 'Unknown ID'}")

            print("\nChoose the Reminders lists to sync (comma-separated numbers or 'all'):")
            selection = input("Your selection: ").strip()

            if selection.lower() == 'all':
                selected_lists = lists
            else:
                try:
                    indices = [int(x.strip()) - 1 for x in selection.split(',')]
                    selected_lists = [lists[i] for i in indices if 0 <= i < len(lists)]
                except (ValueError, IndexError):
                    print("Selection not recognized—use numbers or 'all'.")
                    return False

            self.config.reminders_lists = selected_lists
            self.config.calendar_ids = [lst.identifier for lst in selected_lists]

            # Set default list
            if selected_lists:
                self.config.default_calendar_id = selected_lists[0].identifier

        # Set up vault-to-list mappings
        if self.config.vaults and self.config.reminders_lists:
            print("\n🔗 Map vaults to Reminders lists")
            print("Assign each vault to a default Reminders list for syncing:")

            for vault in self.config.vaults:
                print(f"\nVault: {vault.name}")
                
                # Try to offer smart suggestions first (optional)
                suggested_list_id = None
                if self.enable_suggestions and len(self.config.reminders_lists) > 1:
                    suggested_list_id = self._offer_vault_mapping_suggestions(vault)
                
                # If no suggestion accepted, proceed with manual selection
                if not suggested_list_id:
                    print("Available lists:")
                    for i, lst in enumerate(self.config.reminders_lists, 1):
                        print(f"  {i}. {lst.name} — {lst.identifier or 'Unknown ID'}")

                    # Default to first list or existing mapping
                    existing_mapping = self.config.get_vault_mapping(vault.vault_id)
                    default_choice = 1
                    if existing_mapping:
                        # Find index of existing mapping
                        for i, lst in enumerate(self.config.reminders_lists, 1):
                            if lst.identifier == existing_mapping:
                                default_choice = i
                                break

                    choice_input = input(f"Select a Reminders list for this vault [{default_choice}] (Enter to accept default): ").strip()

                    if choice_input:
                        try:
                            choice = int(choice_input)
                        except ValueError:
                            choice = default_choice
                    else:
                        choice = default_choice

                    if 1 <= choice <= len(self.config.reminders_lists):
                        selected_list = self.config.reminders_lists[choice - 1]
                        suggested_list_id = selected_list.identifier
                    else:
                        # Default to first list if invalid choice
                        selected_list = self.config.reminders_lists[0]
                        suggested_list_id = selected_list.identifier
                
                # Apply the mapping
                self.config.set_vault_mapping(vault.vault_id, suggested_list_id)
                list_name = self._get_list_name(suggested_list_id)
                print(f"✓ Mapped to {list_name}.")

                self._configure_tag_routes(vault)

        # Sync settings
        print("\n⚙️ Sync settings")

        # Minimum score
        print(f"Minimum match score (0.0-1.0) [default {self.config.min_score}]: ", end="")
        score_input = input().strip()
        if score_input:
            try:
                self.config.min_score = float(score_input)
            except ValueError:
                pass

        # Include completed tasks
        print("Include completed tasks? (y/N): ", end="")
        include_input = input().strip().lower()
        self.config.include_completed = include_input == 'y'

        # Calendar sync
        print("Sync Apple Calendar events to daily notes? (y/N): ", end="")
        calendar_input = input().strip().lower()
        self.config.sync_calendar_events = calendar_input == 'y'

        # Automation setup (macOS only)
        self._prompt_automation_setup(is_initial_setup=True)

        print("\n✅ Setup complete")
        print("\nNext steps:")
        print("  1. Run 'obs-sync sync' to review changes")
        print("  2. Run 'obs-sync sync --apply' to apply changes")

        return True
    
    def _apply_new_vaults(self, new_vaults: List[Vault]) -> bool:
        """Apply new vaults to the configuration and prompt for list mappings."""
        if not new_vaults:
            return False

        self.config.vaults.extend(new_vaults)
        self._handle_default_vault_change(new_vaults)

        if not self.config.reminders_lists:
            print("\n⚠️  No Reminders lists configured yet; map vaults later as needed.")
            return True

        print("\n🔗 Map new vaults to Reminders lists:")
        for vault in new_vaults:
            print(f"\nVault: {vault.name}")
            print("Available lists:")
            for i, lst in enumerate(self.config.reminders_lists, 1):
                print(f"  {i}. {lst.name} — {lst.identifier or 'Unknown ID'}")

            choice_input = input("Select list for this vault [1]: ").strip()
            choice = 1
            if choice_input:
                try:
                    choice = int(choice_input)
                except ValueError:
                    choice = 1

            if 1 <= choice <= len(self.config.reminders_lists):
                selected_list = self.config.reminders_lists[choice - 1]
                print(f"✓ Mapped to {selected_list.name}.")
            else:
                selected_list = self.config.reminders_lists[0]
                print(f"✓ Mapped to {selected_list.name} (default).")

            self.config.set_vault_mapping(vault.vault_id, selected_list.identifier)
            self._configure_tag_routes(vault)

        return True

    def _review_mappings_for_new_lists(self, new_lists: List[RemindersList]) -> None:
        """Optionally remap existing vaults after new lists are added."""
        if not new_lists or not self.config.vaults:
            return

        print("\n🔗 Update vault mappings with new lists?")
        response = input("Review vault mappings now? (y/N): ").strip().lower()
        if response != 'y':
            return

        for vault in self.config.vaults:
            current_mapping = self.config.get_vault_mapping(vault.vault_id)
            current_list_name = "None"
            if current_mapping:
                for lst in self.config.reminders_lists:
                    if lst.identifier == current_mapping:
                        current_list_name = lst.name
                        break

            print(f"\nVault: {vault.name} (currently mapped to: {current_list_name})")
            print("Available lists:")
            for i, lst in enumerate(self.config.reminders_lists, 1):
                marker = " (current)" if lst.identifier == current_mapping else ""
                print(f"  {i}. {lst.name}{marker} — {lst.identifier or 'Unknown ID'}")

            print("Press Enter to keep the current list, or enter a new list number:")
            choice_input = input("Enter choice: ").strip()

            if choice_input:
                try:
                    choice = int(choice_input)
                    if 1 <= choice <= len(self.config.reminders_lists):
                        selected_list = self.config.reminders_lists[choice - 1]
                        self.config.set_vault_mapping(vault.vault_id, selected_list.identifier)
                        print(f"✓ Updated mapping to {selected_list.name}.")
                except ValueError:
                    pass

            self._configure_tag_routes(vault)

    def _apply_new_lists(
        self,
        new_lists: List[RemindersList],
        *,
        prompt_for_mapping: bool = True,
        refresh_calendar_ids: bool = True,
    ) -> bool:
        """Apply new Reminders lists to the configuration."""
        if not new_lists:
            return False

        self.config.reminders_lists.extend(new_lists)
        self._handle_default_calendar_change(new_lists)

        if prompt_for_mapping:
            self._review_mappings_for_new_lists(new_lists)

        if refresh_calendar_ids:
            self._refresh_calendar_ids()

        return True

    def _add_new_vaults_option(self) -> None:
        """Interactive flow for adding vaults during reconfigure."""
        print("\n➕ Add New Vault")
        new_vaults = self._collect_additional_vaults()
        if self._apply_new_vaults(new_vaults):
            print("\n✅ Vault configuration updated.")
        else:
            print("\nNo new vaults were added.")

    def _add_new_reminders_option(self) -> None:
        """Interactive flow for adding Reminders lists during reconfigure."""
        print("\n➕ Add New Reminders List")
        new_lists = self._collect_additional_lists()
        if self._apply_new_lists(new_lists, prompt_for_mapping=True):
            print("\n✅ Reminders configuration updated.")
        else:
            print("\nNo new Reminders lists were added.")

    def _run_additional_flow(self) -> bool:
        """Add additional vaults and reminders lists without full reset."""
        print("\n➕ Add additional vaults or Reminders lists")

        new_vaults = self._collect_additional_vaults()
        new_lists = self._collect_additional_lists()

        if not new_vaults and not new_lists:
            print("\nNo changes requested. Existing configuration unchanged.")
            return True

        lists_added = self._apply_new_lists(
            new_lists,
            prompt_for_mapping=False,
            refresh_calendar_ids=False,
        )
        vaults_added = self._apply_new_vaults(new_vaults)

        if lists_added:
            self._review_mappings_for_new_lists(new_lists)

        if lists_added or vaults_added:
            self._refresh_calendar_ids()
            print("\n✅ Additional configuration updated.")
        else:
            print("\nNo changes requested. Existing configuration unchanged.")

        return True

    def _collect_additional_vaults(self) -> List[Vault]:
        """Collect vaults to add to the existing configuration."""
        existing_paths = {self._normalize_path(v.path) for v in self.config.vaults}
        vaults = self._discover_vaults()
        available = [v for v in vaults if self._normalize_path(v.path) not in existing_paths]

        added: List[Vault] = []

        if available:
            print(f"\nDiscovered {len(available)} additional vault(s):")
            for i, vault in enumerate(available, 1):
                print(f"  {i}. {vault.name} — {vault.path}")
            print("Select vaults to add (comma-separated numbers, 'all', or press Enter to skip)")
            selection = input("Your selection: ").strip()
            if selection:
                if selection.lower() == 'all':
                    added = list(available)
                else:
                    try:
                        indices = [int(x.strip()) - 1 for x in selection.split(',')]
                        added = [available[i] for i in indices if 0 <= i < len(available)]
                    except (ValueError, IndexError):
                        print("Invalid selection. Skipping automatic additions.")
                        added = []

        if added:
            existing_paths.update(self._normalize_path(v.path) for v in added)

        manual = self._prompt_manual_vaults(existing_paths)
        if manual:
            added.extend(manual)

        if added:
            print("\nAdded vaults:")
            for vault in added:
                print(f"  - {vault.name} ({vault.path})")

        return added

    def _prompt_manual_vaults(self, existing_paths: Set[str]) -> List[Vault]:
        """Prompt the user to add vaults by path."""
        added: List[Vault] = []
        response = input("\nAdd a vault by path? (y/N): ").strip().lower()

        while response == 'y':
            vault_path = input("Enter vault path: ").strip()
            normalized = self._normalize_path(vault_path)

            if not os.path.isdir(normalized):
                print("That path couldn’t be opened. Enter a valid vault directory. Please try again.")
            elif normalized in existing_paths or normalized in {self._normalize_path(v.path) for v in added}:
                print("Vault already configured.")
            else:
                default_name = os.path.basename(normalized.rstrip(os.sep)) or normalized
                name_input = input(f"Vault name [{default_name} or Enter to keep]: ").strip()
                name = name_input or default_name
                added_vault = Vault(name=name, path=normalized)
                added.append(added_vault)
                existing_paths.add(normalized)
                print(f"Added vault '{name}'.")

            response = input("Add another vault? (y/N): ").strip().lower()

        return added

    def _collect_additional_lists(self) -> List[RemindersList]:
        """Collect reminders lists to add to the existing configuration."""
        lists = self._discover_reminders_lists()
        if not lists:
            return []

        existing_ids = {lst.identifier for lst in self.config.reminders_lists if lst.identifier}
        available = [lst for lst in lists if lst.identifier and lst.identifier not in existing_ids]

        if not available:
            return []

        print(f"\nDiscovered {len(available)} additional Reminders list(s):")
        for i, lst in enumerate(available, 1):
            print(f"  {i}. {lst.name}")
        print("Select lists to add (comma-separated numbers, 'all', or press Enter to skip)")
        selection = input("Your selection: ").strip()

        if not selection:
            return []

        if selection.lower() == 'all':
            chosen = list(available)
        else:
            try:
                indices = [int(x.strip()) - 1 for x in selection.split(',')]
                chosen = [available[i] for i in indices if 0 <= i < len(available)]
            except (ValueError, IndexError):
                print("Invalid selection. Skipping Reminders additions.")
                return []

        if chosen:
            print("\nAdded Reminders lists:")
            for lst in chosen:
                print(f"  - {lst.name}")

        return chosen

    def _check_route_conflicts(self, vault_id: str, calendar_id: str) -> List[Vault]:
        """Check if other vaults already route to the same calendar."""
        conflicting_vaults = []
        for route in self.config.tag_routes:
            if route.get("calendar_id") == calendar_id and route.get("vault_id") != vault_id:
                # Find the vault
                for v in self.config.vaults:
                    if v.vault_id == route.get("vault_id"):
                        if v not in conflicting_vaults:
                            conflicting_vaults.append(v)
                        break
        return conflicting_vaults

    def _configure_tag_routes(self, vault: Vault) -> None:
        """Interactive tag routing configuration for a given vault."""
        if not vault or not self.config.reminders_lists:
            return

        if len(self.config.reminders_lists) < 2:
            return  # Nothing to route to beyond the default list

        try:
            manager = ObsidianTaskManager()
            tasks = manager.list_tasks(vault.path, include_completed=True)
        except Exception as exc:
            if self.verbose:
                print(f"\n⚠️  Unable to analyse tags for {vault.name}: {exc}")
            return

        tag_counts = self._collect_tag_frequencies(tasks, vault.vault_id)
        if not tag_counts:
            if self.verbose:
                print(f"\n🏷️  No tags detected for {vault.name}.")
            return

        print(f"\n🏷️  Tag routing for {vault.name}")
        
        # Offer smart suggestions first (optional)
        suggestions_accepted = False
        if self.enable_suggestions:
            default_list_id = self.config.get_vault_mapping(vault.vault_id)
            suggestions_accepted = self._offer_tag_route_suggestions(vault, default_list_id)
        
        # Allow manual configuration
        if suggestions_accepted:
            proceed = input("\n   Configure additional tag routes manually? (y/N): ").strip().lower()
            if proceed != 'y':
                return
        else:
            print("   Press Enter to skip or map tags to specific Reminders lists.")

        while True:
            current_routes = self.config.get_tag_routes_for_vault(vault.vault_id)
            if current_routes:
                print("\n   Current routes:")
                for route in current_routes:
                    list_name = self._get_list_name(route.get("calendar_id"))
                    print(f"     • {route['tag']} → {list_name}")
            else:
                print("\n   No tag routes configured yet.")

            print("\n   Available tags (most used first):")
            for idx, (tag_value, count) in enumerate(tag_counts, 1):
                count_label = f" ({count})" if count else ""
                print(f"     {idx}. {tag_value}{count_label}")

            print("\n   • Enter numbers separated by commas to map tags (e.g., '1,3')")
            print("   • Enter 'remove 2' or 'remove #tag' to delete a route")
            print("   • Press Enter or type 'done' to finish")

            response = input("   Tag selection: ").strip()
            if not response or response.lower() in {"done", "skip"}:
                break

            lower = response.lower()
            if lower.startswith("remove"):
                _, _, removal_target = lower.partition(" ")
                if not removal_target:
                    print("   ⚠️ Provide a tag number or tag name to remove.")
                    continue

                tag_to_remove: Optional[str] = None
                if removal_target.isdigit():
                    idx = int(removal_target)
                    if 1 <= idx <= len(tag_counts):
                        tag_to_remove = tag_counts[idx - 1][0]
                    else:
                        print("   ⚠️ Invalid tag number.")
                        continue
                else:
                    tag_to_remove = SyncConfig._normalize_tag_value(removal_target)
                    if not tag_to_remove:
                        print("   ⚠️ Tag format not recognized.")
                        continue

                if self.config.get_tag_route(vault.vault_id, tag_to_remove):
                    self.config.remove_tag_route(vault.vault_id, tag_to_remove)
                    print(f"   ⏹️  Removed routing for {tag_to_remove}")
                else:
                    print("   ⚠️ No routing exists for that tag.")
                continue

            selections = [part.strip() for part in response.split(',') if part.strip()]
            if not selections:
                print("   ⚠️ Select at least one tag number.")
                continue

            indices: List[int] = []
            valid = True
            for part in selections:
                if not part.isdigit():
                    print(f"   ⚠️ '{part}' isn’t a number—enter digits only.")
                    valid = False
                    break
                idx = int(part)
                if idx < 1 or idx > len(tag_counts):
                    print(f"   ⚠️ Tag number out of range: {idx}")
                    valid = False
                    break
                indices.append(idx)

            if not valid:
                continue

            for idx in dict.fromkeys(indices):  # Preserve order, avoid duplicates
                tag_value = tag_counts[idx - 1][0]
                current_calendar = self.config.get_tag_route(vault.vault_id, tag_value)
                selected_list = self._prompt_list_choice(
                    prompt=f"Select destination list for {tag_value}",
                    default_identifier=current_calendar,
                )
                if not selected_list:
                    print(f"   ⏭️  Skipped mapping for {tag_value}")
                    continue

                # Check for conflicts with other vaults
                conflicts = self._check_route_conflicts(vault.vault_id, selected_list.identifier)
                if conflicts:
                    print(f"\n   ⚠️  Warning: The following vaults also route to '{selected_list.name}':")
                    for cv in conflicts:
                        print(f"      - {cv.name}")
                    confirm = input("   Continue with this mapping? (y/N): ").strip().lower()
                    if confirm not in {"y", "yes"}:
                        print(f"   ⏭️  Skipped mapping for {tag_value}")
                        continue

                # Prompt for import mode
                current_mode = self.config.get_tag_route_import_mode(vault.vault_id, tag_value)
                print(f"\n   Import mode for {tag_value}:")
                print("      1. existing_only — Keep syncing only tasks already in this vault")
                print("      2. full_import — Import all Reminders tasks with this tag")
                mode_input = input(f"   Enter choice (1/2) [current: {current_mode}]: ").strip()
                import_mode = current_mode
                if mode_input == "1":
                    import_mode = "existing_only"
                elif mode_input == "2":
                    import_mode = "full_import"

                self.config.set_tag_route(vault.vault_id, tag_value, selected_list.identifier, import_mode)
                list_name = self._get_list_name(selected_list.identifier)
                mode_display = "(existing only)" if import_mode == "existing_only" else "(full import)"
                print(f"   ✓ {tag_value} → {list_name} {mode_display}")

        print("   Tag routing updates saved.")

    def _collect_tag_frequencies(self, tasks, vault_id: str) -> List[tuple[str, int]]:
        counts: Counter[str] = Counter()
        for task in tasks or []:
            tags = getattr(task, "tags", None) or []
            for tag in tags:
                normalized = SyncConfig._normalize_tag_value(tag)
                if not normalized or normalized.startswith("#from-"):
                    continue
                counts[normalized] += 1

        for route in self.config.get_tag_routes_for_vault(vault_id):
            tag_value = route.get("tag")
            if tag_value and tag_value not in counts:
                counts[tag_value] = 0

        return sorted(counts.items(), key=lambda item: (-item[1], item[0]))

    def _prompt_list_choice(
        self,
        prompt: str,
        default_identifier: Optional[str] = None,
    ) -> Optional[RemindersList]:
        if not self.config.reminders_lists:
            return None

        default_index = 1
        if default_identifier:
            for idx, lst in enumerate(self.config.reminders_lists, 1):
                if lst.identifier == default_identifier:
                    default_index = idx
                    break

        while True:
            print("\n   Available lists:")
            for idx, lst in enumerate(self.config.reminders_lists, 1):
                marker = " (current)" if lst.identifier == default_identifier else ""
                print(f"     {idx}. {lst.name}{marker}")

            response = input(f"   {prompt} [{default_index}]: ").strip()
            if not response:
                choice = default_index
            else:
                lowered = response.lower()
                if lowered in {"skip", "cancel"}:
                    return None
                try:
                    choice = int(response)
                except ValueError:
                    print("Selection not recognized—use numbers or 'all'.")
                    return False

            if 1 <= choice <= len(self.config.reminders_lists):
                return self.config.reminders_lists[choice - 1]

            print("   ⚠️ Selection not recognized—press Enter to keep the current list.")

    def _get_list_name(self, identifier: Optional[str]) -> str:
        if not identifier:
            return "Unknown"
        for lst in self.config.reminders_lists:
            if lst.identifier == identifier:
                return lst.name
        return identifier
    
    def _offer_vault_mapping_suggestions(
        self,
        vault: Vault,
    ) -> Optional[str]:
        """
        Offer smart vault→list mapping suggestions based on historical data.
        
        Args:
            vault: The vault to analyze
            
        Returns:
            Selected list ID if user accepts a suggestion, None otherwise
        """
        try:
            print(f"\n💡 Analyzing task history for smart suggestions...")
            analyzer = SuggestionAnalyzer(self.config, logger=None)
            suggestions = analyzer.analyze_vault_mapping_suggestions(vault, min_confidence=0.3)
            
            if not suggestions:
                if self.verbose:
                    print("   No suggestions available (insufficient historical data).")
                return None
            
            # Show top suggestion
            top = suggestions[0]
            confidence_pct = int(top.confidence * 100)
            
            print(f"\n✨ Suggested mapping: {top.suggested_list_name}")
            print(f"   Confidence: {confidence_pct}%")
            print(f"   Reason: {top.reasoning}")
            
            response = input("\n   Accept this suggestion? (y/N): ").strip().lower()
            if response == 'y':
                return top.suggested_list_id
                
        except Exception as e:
            if self.verbose:
                print(f"   Could not generate suggestions: {e}")
                traceback.print_exc()
        
        return None
    
    def _offer_tag_route_suggestions(
        self,
        vault: Vault,
        default_list_id: Optional[str] = None,
    ) -> bool:
        """
        Offer smart tag→list route suggestions based on historical data.
        
        Args:
            vault: The vault to analyze
            default_list_id: Default list ID to exclude from suggestions
            
        Returns:
            True if user accepted suggestions, False otherwise
        """
        try:
            print(f"\n💡 Analyzing tag patterns for smart routing suggestions...")
            analyzer = SuggestionAnalyzer(self.config, logger=None)
            suggestions = analyzer.analyze_tag_route_suggestions(
                vault,
                default_list_id=default_list_id,
                min_frequency=3,
                min_confidence=0.4,
            )
            
            if not suggestions:
                if self.verbose:
                    print("   No tag route suggestions available.")
                return False
            
            # Show suggestions
            print(f"\n✨ Found {len(suggestions)} suggested tag route(s):")
            for idx, sugg in enumerate(suggestions[:5], 1):  # Show top 5
                confidence_pct = int(sugg.confidence * 100)
                print(f"\n   {idx}. #{sugg.tag} → {sugg.suggested_list_name}")
                print(f"      Confidence: {confidence_pct}%")
                print(f"      {sugg.reasoning}")
            
            if len(suggestions) > 5:
                print(f"\n   ... and {len(suggestions) - 5} more")
            
            print("\nOptions:")
            print("  1. Accept all suggestions")
            print("  2. Review and accept individually")
            print("  3. Skip suggestions (configure manually)")
            
            choice = input("\nYour choice [3]: ").strip()
            
            if choice == '1':
                # Accept all
                for sugg in suggestions:
                    self.config.set_tag_route(
                        vault.vault_id,
                        sugg.tag,
                        sugg.suggested_list_id,
                        import_mode="existing_only"
                    )
                print(f"\n✓ Applied {len(suggestions)} tag route(s).")
                return True
                
            elif choice == '2':
                # Review individually
                applied = 0
                for sugg in suggestions:
                    confidence_pct = int(sugg.confidence * 100)
                    print(f"\n#{sugg.tag} → {sugg.suggested_list_name} ({confidence_pct}% confidence)")
                    accept = input("   Accept? (y/N): ").strip().lower()
                    if accept == 'y':
                        self.config.set_tag_route(
                            vault.vault_id,
                            sugg.tag,
                            sugg.suggested_list_id,
                            import_mode="existing_only"
                        )
                        applied += 1
                        
                if applied > 0:
                    print(f"\n✓ Applied {applied} tag route(s).")
                    return True
            
        except Exception as e:
            if self.verbose:
                print(f"   Could not generate tag route suggestions: {e}")
                traceback.print_exc()
        
        return False

    def _handle_default_vault_change(self, new_vaults: List[Vault]) -> None:
        """Optionally update the default vault after additions."""
        if not new_vaults:
            return

        current_default = self.config.default_vault
        if current_default is None:
            self._set_default_vault(new_vaults[0].vault_id)
            print(f"\nDefault vault set to {new_vaults[0].name}.")
            return

        print(f"\nCurrent default vault: {current_default.name} ({current_default.path})")
        print("Set one of the newly added vaults as default? Enter number or press Enter to keep current.")
        for idx, vault in enumerate(new_vaults, 1):
            print(f"  {idx}. {vault.name} ({vault.path})")

        response = input("Default vault number: ").strip()
        if not response:
            return

        try:
            selected_idx = int(response) - 1
            if 0 <= selected_idx < len(new_vaults):
                self._set_default_vault(new_vaults[selected_idx].vault_id)
                print(f"Default vault updated to {new_vaults[selected_idx].name}.")
            else:
                print("Selection not recognized—keeping the current default.")
        except ValueError:
            print("Invalid selection. Keeping current default.")

    def _handle_default_calendar_change(self, new_lists: List[RemindersList]) -> None:
        """Optionally update the default Reminders list after additions."""
        if not new_lists:
            return

        if not self.config.default_calendar_id:
            self.config.default_calendar_id = new_lists[0].identifier
            print(f"\nDefault Reminders list set to {new_lists[0].name}.")
            return

        current = next((lst for lst in self.config.reminders_lists
                         if lst.identifier == self.config.default_calendar_id), None)
        if current:
            print(f"\nCurrent default Reminders list: {current.name}")
        else:
            print("\nNo default Reminders list is currently set.")

        print("Set one of the newly added lists as default? Enter number or press Enter to keep current.")
        for idx, lst in enumerate(new_lists, 1):
            print(f"  {idx}. {lst.name}")

        response = input("Default list number: ").strip()
        if not response:
            return

        try:
            selected_idx = int(response) - 1
            if 0 <= selected_idx < len(new_lists):
                self.config.default_calendar_id = new_lists[selected_idx].identifier
                print(f"Default Reminders list updated to {new_lists[selected_idx].name}.")
            else:
                print("Invalid selection. Keeping current default.")
        except ValueError:
            print("Invalid selection. Keeping current default.")

    def _refresh_calendar_ids(self) -> None:
        """Refresh calendar IDs based on configured lists."""
        unique_ids: List[str] = []
        seen: Set[str] = set()
        for lst in self.config.reminders_lists:
            if lst.identifier and lst.identifier not in seen:
                unique_ids.append(lst.identifier)
                seen.add(lst.identifier)
        self.config.calendar_ids = unique_ids

    def _set_default_vault(self, vault_id: str) -> None:
        """Set the default vault by ID and update flags."""
        self.config.default_vault_id = vault_id
        for vault in self.config.vaults:
            vault.is_default = vault.vault_id == vault_id

    def _remove_vault(self) -> None:
        """Handle vault removal flow."""
        if not self.config.vaults:
            print("\n❌ No vaults configured to remove.")
            return
            
        print("\n🗑️ Remove Vault")
        print("\nConfigured vaults:")
        
        for i, vault in enumerate(self.config.vaults, 1):
            default_marker = " (default)" if vault.is_default else ""
            print(f"  {i}. {vault.name}{default_marker} — {vault.path}")
            
        try:
            choice = input(f"\nSelect a vault to remove (1-{len(self.config.vaults)} or type 'cancel'): ").strip()
            
            if choice.lower() == 'cancel':
                print("Vault removal cancelled.")
                return
                
            vault_index = int(choice) - 1
            if vault_index < 0 or vault_index >= len(self.config.vaults):
                print("❌ Selection not recognized—no vault removed.")
                return
                
        except (ValueError, KeyboardInterrupt):
            print("❌ Input not recognized or action cancelled.")
            return
            
        vault_to_remove = self.config.vaults[vault_index]
        
        # Get impact analysis
        impact = self.config.get_vault_removal_impact(vault_to_remove.vault_id)
        
        print(f"\n⚠️ Impact of removing vault '{vault_to_remove.name}':")
        if impact["is_default"]:
            remaining_vaults = len(self.config.vaults) - 1
            if remaining_vaults > 0:
                print("  • This vault is the current default—you’ll need to choose a new default.")
            else:
                print("  • This is the only remaining vault—removing it will leave you with none.")
                
        if impact["mappings_cleared"] > 0:
            print(f"  • {impact['mappings_cleared']} vault mapping(s) will be cleared.")
            
        if impact["tag_routes_cleared"] > 0:
            print(f"  • {impact['tag_routes_cleared']} tag routing rule(s) will be cleared:")
            for route in impact["tag_routes"]:
                tag = route.get("tag", "")
                calendar_id = route.get("calendar_id", "")
                # Find list name
                list_name = calendar_id
                for lst in self.config.reminders_lists:
                    if lst.identifier == calendar_id:
                        list_name = lst.name
                        break
                print(f"    - Tag '{tag}' → {list_name}")
                
        print("  • Inbox file will be removed from the vault if it exists.")
        print("  • All sync links for this vault will be removed.")
        
        confirm = input(f"\nType 'yes' to remove '{vault_to_remove.name}' or press Enter to cancel: ").strip().lower()
        if confirm not in ['yes', 'y']:
            print("Vault removal cancelled.")
            return
            
        # Handle default vault change before removal
        if impact["is_default"] and len(self.config.vaults) > 1:
            remaining_vaults = [v for v in self.config.vaults if v.vault_id != vault_to_remove.vault_id]
            print("\nSelect a new default vault:")
            for i, vault in enumerate(remaining_vaults, 1):
                print(f"  {i}. {vault.name}")
                
            try:
                new_default_choice = input(f"Select a new default (1-{len(remaining_vaults)}): ").strip()
                new_default_index = int(new_default_choice) - 1
                if new_default_index < 0 or new_default_index >= len(remaining_vaults):
                    print("❌ Selection not recognized—removal cancelled.")
                    return
                new_default_vault = remaining_vaults[new_default_index]
            except (ValueError, KeyboardInterrupt):
                print("❌ Input not recognized—removal cancelled.")
                return
        else:
            new_default_vault = None
            
        # Perform the removal
        print(f"\n🗑️ Removing vault '{vault_to_remove.name}'...")
        
        # Clear vault-specific data
        self._clear_vault_inbox(vault_to_remove.path, vault_to_remove.name)
        self._clear_vault_sync_links(vault_to_remove.vault_id)
        
        # Remove from config (this handles mappings, tag routes, and defaults)
        if self.config.remove_vault(vault_to_remove.vault_id):
            # Set new default if we had to choose one
            if new_default_vault:
                self._set_default_vault(new_default_vault.vault_id)
                print(f"✓ Set '{new_default_vault.name}' as the new default vault.")
                
            print(f"✓ Removed vault '{vault_to_remove.name}' from the configuration.")
            print(f"✓ Cleared {impact['mappings_cleared']} vault mapping(s).")
            print(f"✓ Cleared {impact['tag_routes_cleared']} tag routing rule(s).")
        else:
            print(f"  ❌ Failed to remove vault from configuration")

    def _remove_reminders_list(self) -> None:
        """Handle Reminders list removal flow."""
        if not self.config.reminders_lists:
            print("\n❌ No Reminders lists configured to remove.")
            return
            
        print("\n🗑️ Remove Reminders List")
        print("\nConfigured lists:")
        
        for i, lst in enumerate(self.config.reminders_lists, 1):
            default_marker = " (default)" if lst.identifier == self.config.default_calendar_id else ""
            print(f"  {i}. {lst.name}{default_marker} — {lst.identifier or 'Unknown ID'}")
            
        try:
            choice = input(f"\nSelect a list to remove (1-{len(self.config.reminders_lists)} or type 'cancel'): ").strip()
            
            if choice.lower() == 'cancel':
                print("List removal cancelled.")
                return
                
            list_index = int(choice) - 1
            if list_index < 0 or list_index >= len(self.config.reminders_lists):
                print("❌ Selection not recognized—no list removed.")
                return
                
        except (ValueError, KeyboardInterrupt):
            print("❌ Input not recognized or action cancelled.")
            return
            
        list_to_remove = self.config.reminders_lists[list_index]
        
        # Get impact analysis
        impact = self.config.get_list_removal_impact(list_to_remove.identifier)
        
        print(f"\n⚠️ Impact of removing list '{list_to_remove.name}':")
        if impact["is_default"]:
            remaining_lists = len(self.config.reminders_lists) - 1
            if remaining_lists > 0:
                print("  • This list is the current default—you’ll need to choose a new default.")
            else:
                print("  • This is the only remaining list—removing it will leave you with none.")
                
        if impact["mappings_cleared"] > 0:
            print(f"  • {impact['mappings_cleared']} vault mapping(s) will be cleared:")
            for vault_name in impact["affected_vaults"]:
                print(f"    - {vault_name}")
                
        if impact["tag_routes_cleared"] > 0:
            print(f"  • {impact['tag_routes_cleared']} tag routing rule(s) will be cleared.")
            
        confirm = input(f"\nType 'yes' to remove '{list_to_remove.name}' or press Enter to cancel: ").strip().lower()
        if confirm not in ['yes', 'y']:
            print("List removal cancelled.")
            return
            
        # Handle default list change before removal
        if impact["is_default"] and len(self.config.reminders_lists) > 1:
            remaining_lists = [lst for lst in self.config.reminders_lists if lst.identifier != list_to_remove.identifier]
            print("\nSelect a new default list:")
            for i, lst in enumerate(remaining_lists, 1):
                print(f"  {i}. {lst.name} — {lst.identifier or 'Unknown ID'}")
                
            try:
                new_default_choice = input(f"Select a new default (1-{len(remaining_lists)}): ").strip()
                new_default_index = int(new_default_choice) - 1
                if new_default_index < 0 or new_default_index >= len(remaining_lists):
                    print("❌ Selection not recognized—removal cancelled.")
                    return
                new_default_list = remaining_lists[new_default_index]
            except (ValueError, KeyboardInterrupt):
                print("❌ Input not recognized—removal cancelled.")
                return
        else:
            new_default_list = None
            
        # Perform the removal
        print(f"\n🗑️ Removing list '{list_to_remove.name}'...")
        
        # Remove from config (this handles mappings, tag routes, and defaults)
        if self.config.remove_reminders_list(list_to_remove.identifier):
            # Set new default if we had to choose one
            if new_default_list:
                self.config.default_calendar_id = new_default_list.identifier
                print(f"✓ Set '{new_default_list.name}' as the new default list.")
                
            print(f"✓ Removed list '{list_to_remove.name}' from the configuration.")
            print(f"✓ Cleared {impact['mappings_cleared']} vault mapping(s).")
            print(f"✓ Cleared {impact['tag_routes_cleared']} tag routing rule(s).")
        else:
            print("❌ Failed to remove list from the configuration.")

    @staticmethod
    def _normalize_path(path: str) -> str:
        """Normalize a filesystem path for comparisons."""
        return os.path.abspath(os.path.expanduser(path))

    def _discover_vaults(self) -> List[Vault]:
        """Discover Obsidian vaults."""
        try:
            return find_vaults()
        except Exception as e:
            if self.verbose:
                print(f"Vault discovery error: {e}")
            return []

    def _discover_reminders_lists(self) -> List[RemindersList]:
        """Discover Apple Reminders lists."""
        try:
            # Import here to avoid dependency issues on non-macOS
            from obs_sync.reminders.gateway import RemindersGateway

            from obs_sync.core.exceptions import (
                EventKitImportError,
                AuthorizationError,
                RemindersError
            )

            gateway = RemindersGateway()
            calendars = gateway.get_lists()

            lists = []
            for cal in calendars:
                lists.append(RemindersList(
                    name=cal['name'],
                    identifier=cal['id'],
                    source_name=None,
                    source_type=None,
                    color=None
                ))

            return lists

        except EventKitImportError as e:
            # EventKit not available - show installation instructions
            print(f"\n❌ EventKit not available: {e}")
            print("\n📦 Install missing EventKit dependencies with:")
            print("    pip install pyobjc pyobjc-framework-EventKit")
            print("\nOr run:")
            print("    obs-sync install-deps macos")
            return []

        except AuthorizationError as e:
            # Authorization denied - show how to grant permissions
            print(f"\n🔒 Authorization error: {e}")
            print("\n✅ Follow the steps above, then rerun the command.")
            return []

        except RemindersError as e:
            # Generic Reminders error - show the specific error
            print(f"\n⚠️ Reminders error: {e}")
            return []

        except Exception as e:
            # Unexpected error - show details if verbose
            if self.verbose:
                print(f"\n⚠️ Unexpected error accessing Reminders: {e}")
                import traceback
                traceback.print_exc()
            else:
                print("\n⚠️ Could not access Apple Reminders. Re-run with --verbose for diagnostic details.")
            return []