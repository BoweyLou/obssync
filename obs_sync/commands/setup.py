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


class SetupCommand:
    """Interactive setup command."""

    def __init__(self, config: SyncConfig, verbose: bool = False):
        """Initialize setup command."""
        self.config = config
        self.verbose = verbose

    def run(self, reconfigure: bool = False, add: bool = False) -> bool:
        """Run interactive setup or additive flow."""
        print("obs-sync Setup")
        print("=" * 40)

        if add and reconfigure:
            print("\n⚠️ '--add' ignored because '--reconfigure' was provided.")
            add = False

        if add:
            if not self.config.vaults:
                print("\nNo existing configuration found. Running full setup instead.")
                return self._run_full_setup(reconfigure=True)
            return self._run_additional_flow()

        return self._run_full_setup(reconfigure=reconfigure)

    def _run_full_setup(self, reconfigure: bool) -> bool:
        """Run the full interactive setup."""
        if self.config.vaults and not reconfigure:
            print("Already configured. Use --reconfigure to change settings.")
            return True
        
        # If reconfiguring and already have config, ask whether to reset or amend
        if reconfigure and self.config.vaults:
            return self._handle_reconfigure_choice()

        # Store existing vault IDs so we can preserve stable identifiers when reselecting vault paths
        existing_vault_ids = {}
        if self.config.vaults:
            for vault in self.config.vaults:
                normalized_path = self._normalize_path(vault.path)
                existing_vault_ids[normalized_path] = vault.vault_id

        # Discover vaults
        print("\n🔍 Searching for Obsidian vaults...")
        vaults = self._discover_vaults()

        if not vaults:
            print("No vaults found. Please specify vault location manually.")
            vault_path = input("Vault path: ").strip()
            if os.path.isdir(vault_path):
                vault_name = os.path.basename(vault_path)
                vaults = [Vault(name=vault_name, path=vault_path)]
            else:
                print("Invalid path.")
                return False

        # Select vaults
        print(f"\nFound {len(vaults)} vault(s):")
        for i, vault in enumerate(vaults, 1):
            print(f"  {i}. {vault.name} ({vault.path})")

        if len(vaults) > 1:
            print("\nWhich vaults do you want to sync? (comma-separated numbers, or 'all')")
            selection = input("Selection: ").strip()

            if selection.lower() == 'all':
                selected_vaults = vaults
            else:
                try:
                    indices = [int(x.strip()) - 1 for x in selection.split(',')]
                    selected_vaults = [vaults[i] for i in indices if 0 <= i < len(vaults)]
                except (ValueError, IndexError):
                    print("Invalid selection.")
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
            print("\nWhich vault should be the default?")
            for i, vault in enumerate(selected_vaults, 1):
                print(f"  {i}. {vault.name}")
            try:
                default_idx = int(input("Default vault: ").strip()) - 1
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
        print("\n📋 Setting up Apple Reminders...")
        lists = self._discover_reminders_lists()

        if lists:
            print(f"\nFound {len(lists)} Reminders list(s):")
            for i, lst in enumerate(lists, 1):
                print(f"  {i}. {lst.name}")

            print("\nWhich lists do you want to sync? (comma-separated numbers, or 'all')")
            selection = input("Selection: ").strip()

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
            print("\n🔗 Vault to List Mapping")
            print("Map each vault to a specific Reminders list for sync:")

            for vault in self.config.vaults:
                print(f"\nVault: {vault.name}")
                print("Available lists:")
                for i, lst in enumerate(self.config.reminders_lists, 1):
                    print(f"  {i}. {lst.name}")

                # Default to first list or existing mapping
                existing_mapping = self.config.get_vault_mapping(vault.vault_id)
                default_choice = 1
                if existing_mapping:
                    # Find index of existing mapping
                    for i, lst in enumerate(self.config.reminders_lists, 1):
                        if lst.identifier == existing_mapping:
                            default_choice = i
                            break

                choice_input = input(f"Select list for this vault [{default_choice}]: ").strip()

                if choice_input:
                    try:
                        choice = int(choice_input)
                    except ValueError:
                        choice = default_choice
                else:
                    choice = default_choice

                if 1 <= choice <= len(self.config.reminders_lists):
                    selected_list = self.config.reminders_lists[choice - 1]
                    self.config.set_vault_mapping(vault.vault_id, selected_list.identifier)
                    print(f"  ✓ Mapped to: {selected_list.name}")
                else:
                    # Default to first list if invalid choice
                    selected_list = self.config.reminders_lists[0]
                    self.config.set_vault_mapping(vault.vault_id, selected_list.identifier)
                    print(f"  ✓ Mapped to: {selected_list.name} (default)")

                self._configure_tag_routes(vault)

        # Sync settings
        print("\n⚙️ Sync Settings")

        # Minimum score
        print(f"Minimum match score (0.0-1.0) [default: {self.config.min_score}]: ", end="")
        score_input = input().strip()
        if score_input:
            try:
                self.config.min_score = float(score_input)
            except ValueError:
                pass

        # Include completed tasks
        print("Include completed tasks? (y/n) [default: n]: ", end="")
        include_input = input().strip().lower()
        self.config.include_completed = include_input == 'y'

        # Calendar sync
        print("Sync calendar events to daily notes? (y/n) [default: n]: ", end="")
        calendar_input = input().strip().lower()
        self.config.sync_calendar_events = calendar_input == 'y'

        print("\n✅ Setup complete!")
        print("\nNext steps:")
        print("  1. Run 'obs-sync sync' to preview sync")
        print("  2. Run 'obs-sync sync --apply' to apply changes")

        return True

    def _handle_reconfigure_choice(self) -> bool:
        """Handle the reconfigure choice between reset and amend."""
        print("\n⚙️  Reconfigure Options:")
        print("  1. Reset - Clear configuration and start fresh")
        print("  2. Amend - Modify existing vault/list mappings and tag routes")
        
        while True:
            choice = input("\nChoose option [1-2]: ").strip()
            if choice == '1':
                print("\n🔄 Resetting configuration...")
                return self._run_full_reset()
            elif choice == '2':
                print("\n✏️  Amending existing configuration...")
                return self._run_amend_flow()
            else:
                print("Invalid choice. Please enter 1 or 2.")
    
    def _run_full_reset(self) -> bool:
        """Run the full reset flow - clear all existing state and start fresh."""
        print("\n🗑️  Clearing existing sync state...")
        
        # Clear sync links store
        try:
            from ..core.paths import get_path_manager
            path_manager = get_path_manager()
            sync_links_path = path_manager.sync_links_path
            if sync_links_path.exists():
                sync_links_path.unlink()
                print(f"  ✓ Removed sync links store: {sync_links_path}")
            else:
                print("  ✓ No existing sync links store found")
                
            # Clear task indices as well for clean slate
            obsidian_index_path = path_manager.obsidian_index_path
            if obsidian_index_path.exists():
                obsidian_index_path.unlink()
                print(f"  ✓ Removed Obsidian task index: {obsidian_index_path}")
                
            reminders_index_path = path_manager.reminders_index_path
            if reminders_index_path.exists():
                reminders_index_path.unlink()
                print(f"  ✓ Removed Reminders task index: {reminders_index_path}")
                
        except Exception as e:
            print(f"  ⚠️  Warning: Could not clear sync store: {e}")
            if self.verbose:
                traceback.print_exc()
        
        # Clear inbox files from existing vaults
        self._clear_inbox_files()
        
        # Clear tag routes from config
        self.config.tag_routes = []
        print("  ✓ Cleared tag routes")
        
        # Continue with the original full setup logic
        return self._continue_full_setup()
    
    def _clear_inbox_files(self) -> None:
        """Clear inbox files from all configured vaults."""
        if not self.config.vaults:
            print("  ✓ No vaults configured, skipping inbox cleanup")
            return
            
        inbox_filename = self.config.obsidian_inbox_path
        cleared_count = 0
        
        for vault in self.config.vaults:
            try:
                vault_path = Path(vault.path)
                if not vault_path.exists():
                    if self.verbose:
                        print(f"  ⚠️  Vault path does not exist: {vault_path}")
                    continue
                    
                inbox_path = vault_path / inbox_filename
                if inbox_path.exists():
                    inbox_path.unlink()
                    cleared_count += 1
                    if self.verbose:
                        print(f"  ✓ Removed inbox from {vault.name}: {inbox_path}")
                        
            except Exception as e:
                print(f"  ⚠️  Could not clear inbox from {vault.name}: {e}")
                if self.verbose:
                    traceback.print_exc()
        
        if cleared_count > 0:
            print(f"  ✓ Cleared {cleared_count} inbox file(s)")
        else:
            print("  ✓ No inbox files found to clear")

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
                    print(f"  ⚠️  Vault path does not exist: {vault_path}")
                return True  # Consider non-existent path as "cleared"
                
            inbox_path = vault_path_obj / self.config.obsidian_inbox_path
            if inbox_path.exists():
                inbox_path.unlink()
                print(f"  ✓ Removed inbox from {vault_name}: {inbox_path}")
            elif self.verbose:
                print(f"  ✓ No inbox file found in {vault_name}")
            return True
            
        except Exception as e:
            print(f"  ⚠️  Could not clear inbox from {vault_name}: {e}")
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
                    print("  ✓ No sync links file found")
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
                    print(f"  ✓ Removed {removed_count} sync link(s) for vault")
                elif self.verbose:
                    print("  ✓ No sync links found for vault")
            else:
                print("  ⚠️  Could not update sync links file")
                
        except Exception as e:
            print(f"  ⚠️  Could not clear sync links: {e}")
            if self.verbose:
                traceback.print_exc()
    
    def _run_amend_flow(self) -> bool:
        """Amend existing vault/list mappings and tag routes without full reset."""
        print("\n📋 Current Configuration:")
        print(f"\nVaults ({len(self.config.vaults)}):")
        for vault in self.config.vaults:
            default_marker = " (default)" if vault.is_default else ""
            print(f"  • {vault.name}{default_marker}")
        
        print(f"\nReminders Lists ({len(self.config.reminders_lists)}):")
        for lst in self.config.reminders_lists:
            default_marker = " (default)" if lst.identifier == self.config.default_calendar_id else ""
            print(f"  • {lst.name}{default_marker}")
        
        # Option to change defaults
        print("\n📝 What would you like to modify?")
        print("  1. Vault to List mappings")
        print("  2. Tag routing rules")
        print("  3. Default vault")
        print("  4. Default Reminders list")
        print("  5. Calendar sync settings")
        print("  6. Remove a vault")
        print("  7. Remove a Reminders list")
        print("  8. Automation settings (macOS LaunchAgent)")
        print("  9. All of the above (options 1-5, 8)")
        print("  10. Cancel")
        
        choice = input("\nSelect options (comma-separated, e.g. '1,2' or 'all'): ").strip()
        
        if choice == '10' or choice.lower() == 'cancel':
            print("\nAmendment cancelled.")
            return True
        
        if choice == '9' or choice.lower() == 'all':
            choices = ['1', '2', '3', '4', '5', '8']
        else:
            choices = [c.strip() for c in choice.split(',')]
        
        if '1' in choices:
            self._amend_vault_mappings()
        
        if '2' in choices:
            self._amend_tag_routes()
        
        if '3' in choices:
            self._amend_default_vault()
        
        if '4' in choices:
            self._amend_default_list()
        
        if '5' in choices:
            self._amend_calendar_sync()
        
        if '6' in choices:
            self._remove_vault()
        
        if '7' in choices:
            self._remove_reminders_list()
        
        if '8' in choices:
            self._amend_automation()
        
        print("\n✅ Configuration amendments complete!")
        return True
    
    def _amend_vault_mappings(self) -> None:
        """Amend vault to list mappings."""
        print("\n🔗 Vault to List Mapping (Amendment)")
        
        for vault in self.config.vaults:
            current_mapping = self.config.get_vault_mapping(vault.vault_id)
            current_list_name = self._get_list_name(current_mapping) if current_mapping else "None"
            
            print(f"\nVault: {vault.name} (currently: {current_list_name})")
            print("Available lists:")
            for i, lst in enumerate(self.config.reminders_lists, 1):
                current_marker = " (current)" if lst.identifier == current_mapping else ""
                print(f"  {i}. {lst.name}{current_marker}")
            
            print("Press Enter to keep current, or select new list:")
            choice_input = input("Choice: ").strip()
            
            if choice_input:
                try:
                    choice = int(choice_input)
                    if 1 <= choice <= len(self.config.reminders_lists):
                        selected_list = self.config.reminders_lists[choice - 1]
                        self.config.set_vault_mapping(vault.vault_id, selected_list.identifier)
                        print(f"  ✓ Updated mapping to: {selected_list.name}")
                except ValueError:
                    print(f"  ⚠️ Invalid input, keeping current mapping")
    
    def _amend_tag_routes(self) -> None:
        """Amend tag routing rules for all vaults."""
        print("\n🏷️  Tag Route Amendment")
        
        for vault in self.config.vaults:
            print(f"\nVault: {vault.name}")
            response = input("Configure tag routes for this vault? (y/n) [n]: ").strip().lower()
            if response == 'y':
                self._configure_tag_routes(vault)
    
    def _amend_default_vault(self) -> None:
        """Amend the default vault selection."""
        current_default = self.config.default_vault
        print(f"\n📁 Current default vault: {current_default.name if current_default else 'None'}")
        print("\nSelect new default vault:")
        
        for i, vault in enumerate(self.config.vaults, 1):
            current_marker = " (current)" if vault.is_default else ""
            print(f"  {i}. {vault.name}{current_marker}")
        
        choice_input = input("\nChoice (or Enter to keep current): ").strip()
        if choice_input:
            try:
                choice = int(choice_input)
                if 1 <= choice <= len(self.config.vaults):
                    self._set_default_vault(self.config.vaults[choice - 1].vault_id)
                    print(f"✓ Default vault updated to: {self.config.vaults[choice - 1].name}")
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
                    print(f"✓ Default list updated to: {self.config.reminders_lists[choice - 1].name}")
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
        
        choice = input(f"\nWould you like to {action} calendar sync? (y/n) [default: {new_setting}]: ").strip().lower()
        
        if not choice:
            choice = new_setting
        
        if choice == 'y':
            if not self.config.sync_calendar_events:
                self.config.sync_calendar_events = True
                print("✓ Calendar sync enabled")
            else:
                print("Calendar sync is already enabled")
        elif choice == 'n':
            if self.config.sync_calendar_events:
                self.config.sync_calendar_events = False
                print("✓ Calendar sync disabled")
            else:
                print("Calendar sync is already disabled")
        else:
            print("⚠️ Invalid choice. No changes made.")
    
    def _amend_automation(self) -> None:
        """Amend automation settings (macOS LaunchAgent)."""
        from ..utils.launchd import (
            is_macos, is_agent_loaded, load_agent, unload_agent,
            install_agent, uninstall_agent, get_obs_sync_executable,
            describe_interval, get_launchagent_path
        )
        from ..core.paths import get_path_manager
        
        if not is_macos():
            print("\n⚠️  Automation via LaunchAgent is only available on macOS.")
            return
        
        # Show current status
        current_enabled = self.config.automation_enabled
        current_interval = self.config.automation_interval
        agent_loaded = is_agent_loaded()
        
        print(f"\n🤖 Automation Settings (macOS LaunchAgent)")
        print(f"  Configuration: {('enabled' if current_enabled else 'disabled')}")
        print(f"  Schedule: {describe_interval(current_interval)}")
        print(f"  LaunchAgent: {('loaded' if agent_loaded else 'not loaded')}")
        
        if agent_loaded and not current_enabled:
            print("\n⚠️  LaunchAgent is loaded but config shows disabled - they're out of sync")
        elif not agent_loaded and current_enabled:
            print("\n⚠️  Config shows enabled but LaunchAgent is not loaded - they're out of sync")
        
        # Prompt for enable/disable
        print("\nAutomation runs 'obs-sync sync --apply' on a schedule.")
        action = "disable" if current_enabled else "enable"
        default_choice = "n" if current_enabled else "y"
        
        choice = input(f"Would you like to {action} automation? (y/n) [default: {default_choice}]: ").strip().lower()
        
        if not choice:
            choice = default_choice
        
        if choice == 'n':
            if current_enabled or agent_loaded:
                # Disable automation
                print("\n🛑 Disabling automation...")
                
                if agent_loaded:
                    success, error = unload_agent()
                    if success:
                        print("  ✓ LaunchAgent unloaded")
                    else:
                        print(f"  ⚠️  Failed to unload LaunchAgent: {error}")
                
                plist_path = get_launchagent_path()
                if plist_path.exists():
                    success, error = uninstall_agent()
                    if success:
                        print(f"  ✓ Removed LaunchAgent plist: {plist_path}")
                    else:
                        print(f"  ⚠️  Failed to remove plist: {error}")
                
                self.config.automation_enabled = False
                print("  ✓ Automation disabled in configuration")
            else:
                print("Automation is already disabled")
            return
        
        elif choice != 'y':
            print("⚠️ Invalid choice. No changes made.")
            return
        
        # User wants to enable automation
        print("\n⚙️  Configuring automation schedule...")
        print("\nAvailable schedules:")
        print("  1. Hourly (every 3600 seconds) [recommended]")
        print("  2. Twice daily (every 43200 seconds / 12 hours)")
        print("  3. Custom interval (specify seconds)")
        
        schedule_choice = input("Choose schedule [1]: ").strip()
        
        if not schedule_choice or schedule_choice == '1':
            interval = 3600  # Hourly
        elif schedule_choice == '2':
            interval = 43200  # Twice daily
        elif schedule_choice == '3':
            custom_input = input("Enter interval in seconds: ").strip()
            try:
                interval = int(custom_input)
                if interval < 60:
                    print("⚠️  Minimum interval is 60 seconds. Using 60.")
                    interval = 60
                elif interval > 604800:  # 1 week
                    print("⚠️  Maximum interval is 604800 seconds (1 week). Using 604800.")
                    interval = 604800
            except ValueError:
                print("⚠️  Invalid interval. Using default (3600 seconds).")
                interval = 3600
        else:
            print("⚠️  Invalid choice. Using default (hourly).")
            interval = 3600
        
        print(f"\n  Selected: {describe_interval(interval)}")
        
        # Find obs-sync executable
        obs_sync_path = get_obs_sync_executable()
        if not obs_sync_path:
            print("\n⚠️  Could not find obs-sync executable.")
            print("Please ensure obs-sync is installed and in your PATH.")
            return
        
        print(f"  Using executable: {obs_sync_path}")
        
        # Get log directory
        path_manager = get_path_manager()
        log_dir = path_manager.log_dir
        
        # Unload existing agent if loaded
        if agent_loaded:
            print("\n  Unloading existing LaunchAgent...")
            success, error = unload_agent()
            if not success:
                print(f"  ⚠️  Warning: Failed to unload existing agent: {error}")
        
        # Install the LaunchAgent plist
        print("\n  Installing LaunchAgent...")
        success, error = install_agent(interval, obs_sync_path, log_dir)
        
        if not success:
            print(f"  ✗ Failed to install LaunchAgent: {error}")
            return
        
        print(f"  ✓ LaunchAgent plist created: {get_launchagent_path()}")
        
        # Load the agent
        print("  Loading LaunchAgent...")
        success, error = load_agent()
        
        if not success:
            print(f"  ✗ Failed to load LaunchAgent: {error}")
            return
        
        print("  ✓ LaunchAgent loaded and scheduled")
        
        # Update config
        self.config.automation_enabled = True
        self.config.automation_interval = interval
        
        print(f"\n✅ Automation enabled! obs-sync will run {describe_interval(interval)}")
        print(f"   Logs: {log_dir}/obs-sync-agent.stdout.log")
        print(f"         {log_dir}/obs-sync-agent.stderr.log")
    
    def _continue_full_setup(self) -> bool:
        """Continue with the original full setup flow after reset choice."""
        # This contains the original setup logic that was in _run_full_setup

        # Store existing vault IDs for preservation
        existing_vault_ids = {}
        if self.config.vaults:
            for vault in self.config.vaults:
                normalized_path = self._normalize_path(vault.path)
                existing_vault_ids[normalized_path] = vault.vault_id

        # Discover vaults
        print("\n🔍 Searching for Obsidian vaults...")
        vaults = self._discover_vaults()

        if not vaults:
            print("No vaults found. Please specify vault location manually.")
            vault_path = input("Vault path: ").strip()
            if os.path.isdir(vault_path):
                vault_name = os.path.basename(vault_path)
                vaults = [Vault(name=vault_name, path=vault_path)]
            else:
                print("Invalid path.")
                return False

        # Select vaults
        print(f"\nFound {len(vaults)} vault(s):")
        for i, vault in enumerate(vaults, 1):
            print(f"  {i}. {vault.name} ({vault.path})")

        if len(vaults) > 1:
            print("\nWhich vaults do you want to sync? (comma-separated numbers, or 'all')")
            selection = input("Selection: ").strip()

            if selection.lower() == 'all':
                selected_vaults = vaults
            else:
                try:
                    indices = [int(x.strip()) - 1 for x in selection.split(',')]
                    selected_vaults = [vaults[i] for i in indices if 0 <= i < len(vaults)]
                except (ValueError, IndexError):
                    print("Invalid selection.")
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
            print("\nWhich vault should be the default?")
            for i, vault in enumerate(selected_vaults, 1):
                print(f"  {i}. {vault.name}")
            try:
                default_idx = int(input("Default vault: ").strip()) - 1
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
        print("\n📋 Setting up Apple Reminders...")
        lists = self._discover_reminders_lists()

        if lists:
            print(f"\nFound {len(lists)} Reminders list(s):")
            for i, lst in enumerate(lists, 1):
                print(f"  {i}. {lst.name}")

            print("\nWhich lists do you want to sync? (comma-separated numbers, or 'all')")
            selection = input("Selection: ").strip()

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
            print("\n🔗 Vault to List Mapping")
            print("Map each vault to a specific Reminders list for sync:")

            for vault in self.config.vaults:
                print(f"\nVault: {vault.name}")
                print("Available lists:")
                for i, lst in enumerate(self.config.reminders_lists, 1):
                    print(f"  {i}. {lst.name}")

                # Default to first list or existing mapping
                existing_mapping = self.config.get_vault_mapping(vault.vault_id)
                default_choice = 1
                if existing_mapping:
                    # Find index of existing mapping
                    for i, lst in enumerate(self.config.reminders_lists, 1):
                        if lst.identifier == existing_mapping:
                            default_choice = i
                            break

                choice_input = input(f"Select list for this vault [{default_choice}]: ").strip()

                if choice_input:
                    try:
                        choice = int(choice_input)
                    except ValueError:
                        choice = default_choice
                else:
                    choice = default_choice

                if 1 <= choice <= len(self.config.reminders_lists):
                    selected_list = self.config.reminders_lists[choice - 1]
                    self.config.set_vault_mapping(vault.vault_id, selected_list.identifier)
                    print(f"  ✓ Mapped to: {selected_list.name}")
                else:
                    # Default to first list if invalid choice
                    selected_list = self.config.reminders_lists[0]
                    self.config.set_vault_mapping(vault.vault_id, selected_list.identifier)
                    print(f"  ✓ Mapped to: {selected_list.name} (default)")

                self._configure_tag_routes(vault)

        # Sync settings
        print("\n⚙️ Sync Settings")

        # Minimum score
        print(f"Minimum match score (0.0-1.0) [default: {self.config.min_score}]: ", end="")
        score_input = input().strip()
        if score_input:
            try:
                self.config.min_score = float(score_input)
            except ValueError:
                pass

        # Include completed tasks
        print("Include completed tasks? (y/n) [default: n]: ", end="")
        include_input = input().strip().lower()
        self.config.include_completed = include_input == 'y'

        print("\n✅ Setup complete!")
        print("\nNext steps:")
        print("  1. Run 'obs-sync sync' to preview sync")
        print("  2. Run 'obs-sync sync --apply' to apply changes")

        # Calendar sync
        print("Sync calendar events to daily notes? (y/n) [default: n]: ", end="")
        calendar_input = input().strip().lower()
        self.config.sync_calendar_events = calendar_input == 'y'

        return True
    
    def _run_additional_flow(self) -> bool:
        """Add additional vaults and reminders lists without full reset."""
        print("\n➕ Add additional vaults or Reminders lists")

        new_vaults = self._collect_additional_vaults()
        new_lists = self._collect_additional_lists()

        if not new_vaults and not new_lists:
            print("\nNo changes requested. Existing configuration unchanged.")
            return True

        # Add new lists to config FIRST so they're available for vault mapping
        if new_lists:
            self.config.reminders_lists.extend(new_lists)
            self._handle_default_calendar_change(new_lists)

        if new_vaults:
            self.config.vaults.extend(new_vaults)
            self._handle_default_vault_change(new_vaults)

            # Set up mappings for new vaults (now includes newly added lists)
            if self.config.reminders_lists:
                print("\n🔗 Map new vaults to Reminders lists:")
                for vault in new_vaults:
                    print(f"\nVault: {vault.name}")
                    print("Available lists:")
                    for i, lst in enumerate(self.config.reminders_lists, 1):
                        print(f"  {i}. {lst.name}")

                    choice_input = input(f"Select list for this vault [1]: ").strip()
                    choice = 1
                    if choice_input:
                        try:
                            choice = int(choice_input)
                        except ValueError:
                            pass

                    if 1 <= choice <= len(self.config.reminders_lists):
                        selected_list = self.config.reminders_lists[choice - 1]
                        self.config.set_vault_mapping(vault.vault_id, selected_list.identifier)
                        print(f"  ✓ Mapped to: {selected_list.name}")
                    else:
                        # Default to first list
                        selected_list = self.config.reminders_lists[0]
                        self.config.set_vault_mapping(vault.vault_id, selected_list.identifier)
                        print(f"  ✓ Mapped to: {selected_list.name} (default)")

                    self._configure_tag_routes(vault)

        # Handle optional vault remapping for new lists (only if both new lists exist and vaults exist)
        if new_lists:

            # Optionally update vault mappings for new lists
            if self.config.vaults and new_lists:
                print("\n🔗 Update vault mappings with new lists?")
                response = input("Review vault mappings? (y/n) [n]: ").strip().lower()
                if response == 'y':
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
                            print(f"  {i}. {lst.name}{marker}")

                        print("Press Enter to keep current, or select new list:")
                        choice_input = input("Choice: ").strip()

                        if choice_input:
                            try:
                                choice = int(choice_input)
                                if 1 <= choice <= len(self.config.reminders_lists):
                                    selected_list = self.config.reminders_lists[choice - 1]
                                    self.config.set_vault_mapping(vault.vault_id, selected_list.identifier)
                                    print(f"  ✓ Updated mapping to: {selected_list.name}")
                            except ValueError:
                                pass

                        self._configure_tag_routes(vault)

        self._refresh_calendar_ids()

        print("\n✅ Additional configuration updated.")
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
                print(f"  {i}. {vault.name} ({vault.path})")
            print("Select vaults to add (comma-separated numbers, 'all', or press Enter to skip)")
            selection = input("Selection: ").strip()
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
        response = input("\nAdd a vault by path? (y/n): ").strip().lower()

        while response == 'y':
            vault_path = input("Vault path: ").strip()
            normalized = self._normalize_path(vault_path)

            if not os.path.isdir(normalized):
                print("Invalid path. Please try again.")
            elif normalized in existing_paths or normalized in {self._normalize_path(v.path) for v in added}:
                print("Vault already configured.")
            else:
                default_name = os.path.basename(normalized.rstrip(os.sep)) or normalized
                name_input = input(f"Vault name [{default_name}]: ").strip()
                name = name_input or default_name
                added_vault = Vault(name=name, path=normalized)
                added.append(added_vault)
                existing_paths.add(normalized)
                print(f"Added vault '{name}'.")

            response = input("Add another vault? (y/n): ").strip().lower()

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
        selection = input("Selection: ").strip()

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

            response = input("   Selection: ").strip()
            if not response or response.lower() in {"done", "skip"}:
                break

            lower = response.lower()
            if lower.startswith("remove"):
                _, _, removal_target = lower.partition(" ")
                if not removal_target:
                    print("   ⚠️  Provide a number or tag name to remove.")
                    continue

                tag_to_remove: Optional[str] = None
                if removal_target.isdigit():
                    idx = int(removal_target)
                    if 1 <= idx <= len(tag_counts):
                        tag_to_remove = tag_counts[idx - 1][0]
                    else:
                        print("   ⚠️  Invalid tag number.")
                        continue
                else:
                    tag_to_remove = SyncConfig._normalize_tag_value(removal_target)
                    if not tag_to_remove:
                        print("   ⚠️  Invalid tag format.")
                        continue

                if self.config.get_tag_route(vault.vault_id, tag_to_remove):
                    self.config.remove_tag_route(vault.vault_id, tag_to_remove)
                    print(f"   ⏹️  Removed routing for {tag_to_remove}")
                else:
                    print("   ⚠️  No routing exists for that tag.")
                continue

            selections = [part.strip() for part in response.split(',') if part.strip()]
            if not selections:
                print("   ⚠️  Provide at least one tag number.")
                continue

            indices: List[int] = []
            valid = True
            for part in selections:
                if not part.isdigit():
                    print(f"   ⚠️  Invalid input: '{part}'")
                    valid = False
                    break
                idx = int(part)
                if idx < 1 or idx > len(tag_counts):
                    print(f"   ⚠️  Tag number out of range: {idx}")
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
                    confirm = input("   Continue anyway? (y/N): ").strip().lower()
                    if confirm not in {"y", "yes"}:
                        print(f"   ⏭️  Skipped mapping for {tag_value}")
                        continue

                # Prompt for import mode
                current_mode = self.config.get_tag_route_import_mode(vault.vault_id, tag_value)
                print(f"\n   Import mode for {tag_value}:")
                print("      1. existing_only - Only sync tasks already in this vault")
                print("      2. full_import - Import all tasks with this tag from Reminders")
                mode_input = input(f"   Choice (1/2) [current: {current_mode}]: ").strip()
                import_mode = current_mode
                if mode_input == "1":
                    import_mode = "existing_only"
                elif mode_input == "2":
                    import_mode = "full_import"

                self.config.set_tag_route(vault.vault_id, tag_value, selected_list.identifier, import_mode)
                list_name = self._get_list_name(selected_list.identifier)
                mode_display = "(existing only)" if import_mode == "existing_only" else "(full import)"
                print(f"   ✓ {tag_value} → {list_name} {mode_display}")

        print("   Tag routing complete.")

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
                    print("   ⚠️  Invalid selection.")
                    continue

            if 1 <= choice <= len(self.config.reminders_lists):
                return self.config.reminders_lists[choice - 1]

            print("   ⚠️  Invalid selection.")

    def _get_list_name(self, identifier: Optional[str]) -> str:
        if not identifier:
            return "Unknown"
        for lst in self.config.reminders_lists:
            if lst.identifier == identifier:
                return lst.name
        return identifier

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

        response = input("Default vault: ").strip()
        if not response:
            return

        try:
            selected_idx = int(response) - 1
            if 0 <= selected_idx < len(new_vaults):
                self._set_default_vault(new_vaults[selected_idx].vault_id)
                print(f"Default vault updated to {new_vaults[selected_idx].name}.")
            else:
                print("Invalid selection. Keeping current default.")
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
            print("\nNo default Reminders list currently set.")

        print("Set one of the newly added lists as default? Enter number or press Enter to keep current.")
        for idx, lst in enumerate(new_lists, 1):
            print(f"  {idx}. {lst.name}")

        response = input("Default list: ").strip()
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
            
        print("\n🗑️  Remove Vault")
        print("\nConfigured vaults:")
        
        for i, vault in enumerate(self.config.vaults, 1):
            default_marker = " (default)" if vault.is_default else ""
            print(f"  {i}. {vault.name}{default_marker}")
            
        try:
            choice = input(f"\nSelect vault to remove (1-{len(self.config.vaults)}, or 'cancel'): ").strip()
            
            if choice.lower() == 'cancel':
                print("Vault removal cancelled.")
                return
                
            vault_index = int(choice) - 1
            if vault_index < 0 or vault_index >= len(self.config.vaults):
                print("❌ Invalid vault selection.")
                return
                
        except (ValueError, KeyboardInterrupt):
            print("❌ Invalid input or cancelled.")
            return
            
        vault_to_remove = self.config.vaults[vault_index]
        
        # Get impact analysis
        impact = self.config.get_vault_removal_impact(vault_to_remove.vault_id)
        
        print(f"\n⚠️  Impact of removing vault '{vault_to_remove.name}':")
        if impact["is_default"]:
            remaining_vaults = len(self.config.vaults) - 1
            if remaining_vaults > 0:
                print(f"  • This is the default vault - you'll need to select a new default")
            else:
                print(f"  • This is the only remaining vault - removal will leave you with no vaults")
                
        if impact["mappings_cleared"] > 0:
            print(f"  • {impact['mappings_cleared']} vault mapping(s) will be cleared")
            
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
                
        print(f"  • Inbox file will be removed from vault (if exists)")
        print(f"  • All sync links for this vault will be removed")
        
        confirm = input(f"\nAre you sure you want to remove '{vault_to_remove.name}'? (yes/no): ").strip().lower()
        if confirm not in ['yes', 'y']:
            print("Vault removal cancelled.")
            return
            
        # Handle default vault change before removal
        if impact["is_default"] and len(self.config.vaults) > 1:
            remaining_vaults = [v for v in self.config.vaults if v.vault_id != vault_to_remove.vault_id]
            print(f"\nSelect new default vault:")
            for i, vault in enumerate(remaining_vaults, 1):
                print(f"  {i}. {vault.name}")
                
            try:
                new_default_choice = input(f"Select new default (1-{len(remaining_vaults)}): ").strip()
                new_default_index = int(new_default_choice) - 1
                if new_default_index < 0 or new_default_index >= len(remaining_vaults):
                    print("❌ Invalid selection. Removal cancelled.")
                    return
                new_default_vault = remaining_vaults[new_default_index]
            except (ValueError, KeyboardInterrupt):
                print("❌ Invalid input. Removal cancelled.")
                return
        else:
            new_default_vault = None
            
        # Perform the removal
        print(f"\n🗑️  Removing vault '{vault_to_remove.name}'...")
        
        # Clear vault-specific data
        self._clear_vault_inbox(vault_to_remove.path, vault_to_remove.name)
        self._clear_vault_sync_links(vault_to_remove.vault_id)
        
        # Remove from config (this handles mappings, tag routes, and defaults)
        if self.config.remove_vault(vault_to_remove.vault_id):
            # Set new default if we had to choose one
            if new_default_vault:
                self._set_default_vault(new_default_vault.vault_id)
                print(f"  ✓ Set '{new_default_vault.name}' as new default vault")
                
            print(f"  ✓ Removed vault '{vault_to_remove.name}' from configuration")
            print(f"  ✓ Cleared {impact['mappings_cleared']} vault mapping(s)")
            print(f"  ✓ Cleared {impact['tag_routes_cleared']} tag routing rule(s)")
        else:
            print(f"  ❌ Failed to remove vault from configuration")

    def _remove_reminders_list(self) -> None:
        """Handle Reminders list removal flow."""
        if not self.config.reminders_lists:
            print("\n❌ No Reminders lists configured to remove.")
            return
            
        print("\n🗑️  Remove Reminders List")
        print("\nConfigured lists:")
        
        for i, lst in enumerate(self.config.reminders_lists, 1):
            default_marker = " (default)" if lst.identifier == self.config.default_calendar_id else ""
            print(f"  {i}. {lst.name}{default_marker}")
            
        try:
            choice = input(f"\nSelect list to remove (1-{len(self.config.reminders_lists)}, or 'cancel'): ").strip()
            
            if choice.lower() == 'cancel':
                print("List removal cancelled.")
                return
                
            list_index = int(choice) - 1
            if list_index < 0 or list_index >= len(self.config.reminders_lists):
                print("❌ Invalid list selection.")
                return
                
        except (ValueError, KeyboardInterrupt):
            print("❌ Invalid input or cancelled.")
            return
            
        list_to_remove = self.config.reminders_lists[list_index]
        
        # Get impact analysis
        impact = self.config.get_list_removal_impact(list_to_remove.identifier)
        
        print(f"\n⚠️  Impact of removing list '{list_to_remove.name}':")
        if impact["is_default"]:
            remaining_lists = len(self.config.reminders_lists) - 1
            if remaining_lists > 0:
                print(f"  • This is the default list - you'll need to select a new default")
            else:
                print(f"  • This is the only remaining list - removal will leave you with no lists")
                
        if impact["mappings_cleared"] > 0:
            print(f"  • {impact['mappings_cleared']} vault mapping(s) will be cleared:")
            for vault_name in impact["affected_vaults"]:
                print(f"    - {vault_name}")
                
        if impact["tag_routes_cleared"] > 0:
            print(f"  • {impact['tag_routes_cleared']} tag routing rule(s) will be cleared")
            
        confirm = input(f"\nAre you sure you want to remove '{list_to_remove.name}'? (yes/no): ").strip().lower()
        if confirm not in ['yes', 'y']:
            print("List removal cancelled.")
            return
            
        # Handle default list change before removal
        if impact["is_default"] and len(self.config.reminders_lists) > 1:
            remaining_lists = [lst for lst in self.config.reminders_lists if lst.identifier != list_to_remove.identifier]
            print(f"\nSelect new default list:")
            for i, lst in enumerate(remaining_lists, 1):
                print(f"  {i}. {lst.name}")
                
            try:
                new_default_choice = input(f"Select new default (1-{len(remaining_lists)}): ").strip()
                new_default_index = int(new_default_choice) - 1
                if new_default_index < 0 or new_default_index >= len(remaining_lists):
                    print("❌ Invalid selection. Removal cancelled.")
                    return
                new_default_list = remaining_lists[new_default_index]
            except (ValueError, KeyboardInterrupt):
                print("❌ Invalid input. Removal cancelled.")
                return
        else:
            new_default_list = None
            
        # Perform the removal
        print(f"\n🗑️  Removing list '{list_to_remove.name}'...")
        
        # Remove from config (this handles mappings, tag routes, and defaults)
        if self.config.remove_reminders_list(list_to_remove.identifier):
            # Set new default if we had to choose one
            if new_default_list:
                self.config.default_calendar_id = new_default_list.identifier
                print(f"  ✓ Set '{new_default_list.name}' as new default list")
                
            print(f"  ✓ Removed list '{list_to_remove.name}' from configuration")
            print(f"  ✓ Cleared {impact['mappings_cleared']} vault mapping(s)")
            print(f"  ✓ Cleared {impact['tag_routes_cleared']} tag routing rule(s)")
        else:
            print(f"  ❌ Failed to remove list from configuration")

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
            print("\n📦 To fix this, install the required dependencies:")
            print("    pip install pyobjc pyobjc-framework-EventKit")
            print("\nOr use the built-in installer:")
            print("    obs-sync install-deps macos")
            return []

        except AuthorizationError as e:
            # Authorization denied - show how to grant permissions
            print(f"\n🔒 Authorization error: {e}")
            print("\n✅ To fix this issue, follow the instructions above.")
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
                print("\n⚠️ Could not access Apple Reminders. Run with --verbose for details.")
            return []