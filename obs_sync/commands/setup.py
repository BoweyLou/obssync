"""
Setup command for initial configuration.
"""

import os
from typing import List

from obs_sync.core.models import SyncConfig, Vault, RemindersList
from obs_sync.obsidian.vault import find_vaults


class SetupCommand:
    """Interactive setup command."""
    
    def __init__(self, config: SyncConfig, verbose: bool = False):
        """
        Initialize setup command.
        
        Args:
            config: Configuration object to populate
            verbose: Enable verbose output
        """
        self.config = config
        self.verbose = verbose
    
    def run(self, reconfigure: bool = False) -> bool:
        """
        Run interactive setup.
        
        Args:
            reconfigure: Force reconfiguration even if already set up
        
        Returns:
            True if setup completed successfully
        """
        print("obs-sync Setup")
        print("=" * 40)
        
        # Check if already configured
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
                # Use first as default
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