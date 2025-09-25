"""
Setup command for initial configuration.
"""

import os
from typing import List, Set

from obs_sync.core.models import SyncConfig, Vault, RemindersList
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