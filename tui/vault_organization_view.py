#!/usr/bin/env python3
"""
TUI components for vault-based organization settings and management.

This module provides:
- Vault organization setup and configuration screens
- Vault-list mapping management interface
- Cleanup operation progress monitoring
- Interactive migration wizard

Key features:
- Real-time status updates
- Safe operation confirmation dialogs
- Progress tracking for long operations
- Rollback capability interface
"""

from __future__ import annotations

import curses
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Import domain models and utilities
from lib.vault_organization import VaultOrganizer, VaultListPlan, CatchAllPlan, generate_stable_vault_id
from lib.legacy_cleanup import LegacyCleanupManager, CleanupPlan, CleanupResults
from lib.safe_io import safe_load_json
from app_config import load_app_config, save_app_config, get_path


class VaultOrganizationView:
    """TUI view for vault-based organization management."""

    def __init__(self, stdscr, height: int, width: int):
        """Initialize vault organization view."""
        self.stdscr = stdscr
        self.height = height
        self.width = width
        self.current_screen = "main"
        self.selected_item = 0
        self.scroll_offset = 0

        # Load current state
        self.app_prefs, self.paths = load_app_config()
        self.vault_config = safe_load_json(self.paths["obsidian_vaults"]) or {}
        self.reminders_config = safe_load_json(self.paths["reminders_lists"]) or {}

        # Migration state
        self.migration_state = {
            "analysis_completed": False,
            "plan_generated": False,
            "backup_created": False,
            "migration_executed": False,
            "results_verified": False,
            "current_step": 0,
            "analysis_results": None,
            "migration_plan": None,
            "backup_path": None
        }

        # Screen state
        self.screens = {
            "main": self._draw_main_screen,
            "setup": self._draw_setup_screen,
            "mappings": self._draw_mappings_screen,
            "cleanup": self._draw_cleanup_screen,
            "migration": self._draw_migration_screen
        }

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------

    def _vault_entries(self) -> List[Dict]:
        """Return vault entries from the loaded configuration."""
        cfg = self.vault_config
        if isinstance(cfg, dict):
            entries = cfg.get("vaults", [])
        elif isinstance(cfg, list):
            entries = cfg
        else:
            entries = []

        normalized: List[Dict] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if not entry.get("vault_id") and entry.get("path"):
                # Ensure stable ID even if older config
                temporary = dict(entry)
                temporary["vault_id"] = generate_stable_vault_id(entry.get("path"))
                normalized.append(temporary)
            else:
                normalized.append(entry)
        return normalized

    def _reminder_list_entries(self) -> List[Dict]:
        """Return reminder list entries from configuration."""
        cfg = self.reminders_config
        if isinstance(cfg, dict):
            entries = cfg.get("lists", [])
        elif isinstance(cfg, list):
            entries = cfg
        else:
            entries = []

        return [entry for entry in entries if isinstance(entry, dict)]

    def _resolved_default_vault_id(self) -> Optional[str]:
        """Get the default vault identifier from preferences or config."""
        if self.app_prefs.default_vault_id:
            return self.app_prefs.default_vault_id
        if isinstance(self.vault_config, dict):
            return self.vault_config.get("default_vault_id")
        return None

    def draw(self) -> None:
        """Draw the current screen."""
        self.stdscr.clear()
        self._draw_header()

        # Draw current screen content
        if self.current_screen in self.screens:
            self.screens[self.current_screen]()
        else:
            self._draw_error_screen(f"Unknown screen: {self.current_screen}")

        self._draw_footer()
        self.stdscr.refresh()

    def handle_input(self, key: int) -> str:
        """
        Handle keyboard input for vault organization screens.

        Args:
            key: Curses key code

        Returns:
            Action string or empty string to continue
        """
        if key == ord('q'):
            return "quit"
        elif key == ord('h') or key == curses.KEY_LEFT:
            return self._handle_back()
        elif key == curses.KEY_UP:
            self._handle_cursor_up()
        elif key == curses.KEY_DOWN:
            self._handle_cursor_down()
        elif key == ord('\n') or key == curses.KEY_ENTER:
            return self._handle_enter()
        elif key == ord('r'):
            return self._handle_refresh()
        elif key >= ord('1') and key <= ord('9'):
            return self._handle_number_key(key - ord('0'))

        return ""

    def _draw_header(self) -> None:
        """Draw the header with title and status."""
        title = "Vault-Based Organization"
        status = "Enabled" if self.app_prefs.vault_organization_enabled else "Disabled"

        # Title line
        self.stdscr.addstr(0, 0, "=" * self.width)
        title_x = (self.width - len(title)) // 2
        self.stdscr.addstr(1, title_x, title, curses.A_BOLD)

        # Status line
        status_text = f"Status: {status}"
        if self.app_prefs.default_vault_id:
            default_vault = self._get_vault_by_id(self.app_prefs.default_vault_id)
            if default_vault:
                status_text += f" | Default: {default_vault.get('name', 'Unknown')}"

        self.stdscr.addstr(2, 2, status_text)
        self.stdscr.addstr(3, 0, "=" * self.width)

    def _draw_footer(self) -> None:
        """Draw the footer with navigation help."""
        footer_y = self.height - 2
        help_text = "q:Quit | ↑↓:Navigate | Enter:Select | h:Back | r:Refresh"
        self.stdscr.addstr(footer_y, 0, "-" * self.width)
        self.stdscr.addstr(footer_y + 1, 2, help_text[:self.width - 4])

    def _draw_main_screen(self) -> None:
        """Draw the main vault organization screen."""
        y = 5

        # Organization status
        if self.app_prefs.vault_organization_enabled:
            self.stdscr.addstr(y, 2, "✅ Vault organization is ENABLED", curses.A_BOLD)
            y += 2

            # Show current configuration
            self.stdscr.addstr(y, 4, f"Default vault: {self._get_default_vault_name()}")
            y += 1
            self.stdscr.addstr(y, 4, f"Catch-all file: {self.app_prefs.catch_all_filename}")
            y += 1
            self.stdscr.addstr(y, 4, f"Auto-create lists: {'Yes' if self.app_prefs.auto_create_vault_lists else 'No'}")
            y += 2
        else:
            self.stdscr.addstr(y, 2, "❌ Vault organization is DISABLED", curses.A_BOLD)
            y += 2

        # Main menu options
        menu_items = [
            ("1", "Setup/Configure", "Enable and configure vault organization"),
            ("2", "View Mappings", "View current vault-list mappings"),
            ("3", "Run Analysis", "Analyze organization opportunities"),
            ("4", "Migration Tools", "Migrate from legacy configuration"),
            ("5", "Cleanup Tools", "Clean up legacy mappings and duplicates")
        ]

        self.stdscr.addstr(y, 2, "Available Actions:", curses.A_BOLD)
        y += 2

        for i, (key, title, description) in enumerate(menu_items):
            attr = curses.A_REVERSE if i == self.selected_item else curses.A_NORMAL
            self.stdscr.addstr(y, 4, f"{key}. {title}", attr)
            self.stdscr.addstr(y + 1, 7, description, curses.A_DIM)
            y += 3

        # Show statistics
        y += 2
        self._draw_statistics(y)

    def _draw_setup_screen(self) -> None:
        """Draw the vault organization setup screen."""
        y = 5

        self.stdscr.addstr(y, 2, "Vault Organization Setup", curses.A_BOLD)
        y += 2

        # Current settings
        settings = [
            ("Organization enabled", "Yes" if self.app_prefs.vault_organization_enabled else "No"),
            ("Default vault", self._get_default_vault_name()),
            ("Catch-all filename", self.app_prefs.catch_all_filename),
            ("Auto-create lists", "Yes" if self.app_prefs.auto_create_vault_lists else "No"),
            ("List naming template", self.app_prefs.list_naming_template),
            ("Preserve list colors", "Yes" if self.app_prefs.preserve_list_colors else "No")
        ]

        for i, (setting, value) in enumerate(settings):
            attr = curses.A_REVERSE if i == self.selected_item else curses.A_NORMAL
            self.stdscr.addstr(y, 4, f"{setting}:", attr)
            self.stdscr.addstr(y, 30, value, attr | curses.A_BOLD)
            y += 1

        y += 2
        self.stdscr.addstr(y, 2, "Press Enter to modify selected setting, h to go back")

    def _draw_mappings_screen(self) -> None:
        """Draw the vault-list mappings screen."""
        y = 5

        self.stdscr.addstr(y, 2, "Vault-List Mappings", curses.A_BOLD)
        y += 2

        # Get current mappings
        mappings = self._get_current_mappings()

        if not mappings:
            self.stdscr.addstr(y, 4, "No vault-list mappings found")
            y += 2

            # Show setup options
            setup_options = [
                ("1", "Create Automatic Mappings", "Generate mappings for all discovered vaults"),
                ("2", "Manual Mapping Setup", "Manually map vaults to Reminders lists"),
                ("3", "Enable Vault Organization", "Turn on vault organization to create mappings")
            ]

            self.stdscr.addstr(y, 2, "Setup Options:", curses.A_BOLD)
            y += 2

            for i, (key, title, description) in enumerate(setup_options):
                attr = curses.A_REVERSE if i == self.selected_item else curses.A_NORMAL
                self.stdscr.addstr(y, 4, f"{key}. {title}", attr)
                self.stdscr.addstr(y + 1, 7, description, curses.A_DIM)
                y += 3

            y += 1
            self.stdscr.addstr(y, 2, "Press Enter to select option, h to go back")
            return

        # Headers
        self.stdscr.addstr(y, 4, "Vault", curses.A_BOLD)
        self.stdscr.addstr(y, 25, "Reminders List", curses.A_BOLD)
        self.stdscr.addstr(y, 50, "Status", curses.A_BOLD)
        y += 2

        # Mappings list
        for i, mapping in enumerate(mappings):
            attr = curses.A_REVERSE if i == self.selected_item else curses.A_NORMAL

            vault_name = mapping.get("vault_name", "Unknown")[:20]
            list_name = mapping.get("list_name", "Not mapped")[:24]
            status = "✅ Active" if mapping.get("active") else "❌ Inactive"

            self.stdscr.addstr(y, 4, vault_name, attr)
            self.stdscr.addstr(y, 25, list_name, attr)
            self.stdscr.addstr(y, 50, status, attr)
            y += 1

        # Show action options below the mappings
        y += 2

        # Check if there are inactive mappings
        inactive_count = sum(1 for m in mappings if not m.get("active"))

        if inactive_count > 0:
            action_options = [
                ("1", "Map to Existing Lists", f"Map {inactive_count} vaults to existing Reminders lists"),
                ("2", "Auto-Discover Mappings", "Search for lists with similar names"),
                ("3", "Refresh Mappings", "Refresh and check mapping status")
            ]

            self.stdscr.addstr(y, 2, "Actions:", curses.A_BOLD)
            y += 2

            for i, (key, title, description) in enumerate(action_options):
                # Adjust selection index to account for mappings above
                action_index = len(mappings) + i
                attr = curses.A_REVERSE if action_index == self.selected_item else curses.A_NORMAL
                self.stdscr.addstr(y, 4, f"{key}. {title}", attr)
                self.stdscr.addstr(y + 1, 7, description, curses.A_DIM)
                y += 3

            y += 1
            self.stdscr.addstr(y, 2, "Press Enter to select action, h to go back")
        else:
            self.stdscr.addstr(y, 2, "All vaults are properly mapped! Press h to go back")

    def _draw_cleanup_screen(self) -> None:
        """Draw the cleanup operations screen."""
        y = 5

        self.stdscr.addstr(y, 2, "Legacy Cleanup Tools", curses.A_BOLD)
        y += 2

        # Cleanup options
        cleanup_options = [
            ("1", "Analyze Legacy Mappings", "Identify legacy lists and duplicates"),
            ("2", "Preview Cleanup Plan", "See what would be cleaned up"),
            ("3", "Execute Cleanup (Dry Run)", "Simulate cleanup operations"),
            ("4", "Execute Cleanup (Live)", "⚠️  Actually perform cleanup"),
            ("5", "Rollback Last Cleanup", "Restore from backup")
        ]

        for i, (key, title, description) in enumerate(cleanup_options):
            attr = curses.A_REVERSE if i == self.selected_item else curses.A_NORMAL
            self.stdscr.addstr(y, 4, f"{key}. {title}", attr)
            self.stdscr.addstr(y + 1, 7, description, curses.A_DIM)
            y += 3

        # Show cleanup status
        y += 2
        self._draw_cleanup_status(y)

    def _draw_migration_screen(self) -> None:
        """Draw the migration wizard screen."""
        y = 5

        self.stdscr.addstr(y, 2, "Migration Wizard", curses.A_BOLD)
        y += 2

        migration_steps = [
            ("1", "Pre-migration Analysis", "Analyze current setup and requirements"),
            ("2", "Generate Migration Plan", "Create step-by-step migration plan"),
            ("3", "Backup Current State", "Create comprehensive backup"),
            ("4", "Execute Migration", "Perform the migration"),
            ("5", "Verify Results", "Validate migration success")
        ]

        # Map steps to migration state
        step_status_map = [
            self.migration_state["analysis_completed"],
            self.migration_state["plan_generated"],
            self.migration_state["backup_created"],
            self.migration_state["migration_executed"],
            self.migration_state["results_verified"]
        ]

        for i, (step, title, description) in enumerate(migration_steps):
            # Determine step status based on actual state
            if step_status_map[i]:
                status = "✅"  # Completed
            elif i == self.migration_state["current_step"]:
                status = "🔄"  # In progress
            elif i < self.migration_state["current_step"]:
                status = "✅"  # Completed (failsafe)
            else:
                status = "🔲"  # Not started

            attr = curses.A_REVERSE if i == self.selected_item else curses.A_NORMAL
            self.stdscr.addstr(y, 4, f"{status} {step}. {title}", attr)
            self.stdscr.addstr(y + 1, 7, description, curses.A_DIM)
            y += 3

        # Show additional info if available
        y += 1
        if self.migration_state["analysis_results"]:
            self.stdscr.addstr(y, 2, "Analysis Summary:", curses.A_BOLD)
            y += 1
            results = self.migration_state["analysis_results"]
            self.stdscr.addstr(y, 4, f"Vaults: {results.get('vault_count', 0)}, Lists: {results.get('list_count', 0)}")
            y += 1

        if self.migration_state["backup_path"]:
            self.stdscr.addstr(y, 2, f"Backup: {self.migration_state['backup_path']}", curses.A_DIM)
            y += 1

        y += 1
        self.stdscr.addstr(y, 2, "Press Enter to execute selected step, h to go back")

    def _draw_statistics(self, start_y: int) -> None:
        """Draw organization statistics."""
        y = start_y

        self.stdscr.addstr(y, 2, "Current Statistics:", curses.A_BOLD)
        y += 1

        # Get vault and list counts
        vault_count = len(self._vault_entries())
        list_count = len(self._reminder_list_entries())

        stats = [
            ("Vaults discovered", str(vault_count)),
            ("Reminders lists", str(list_count)),
            ("Mapped vaults", "0"),  # Would calculate from actual mappings
            ("Unmapped lists", str(list_count))  # Would calculate from actual mappings
        ]

        for stat_name, stat_value in stats:
            self.stdscr.addstr(y, 4, f"{stat_name}:")
            self.stdscr.addstr(y, 25, stat_value, curses.A_BOLD)
            y += 1

    def _draw_cleanup_status(self, start_y: int) -> None:
        """Draw cleanup operation status."""
        y = start_y

        self.stdscr.addstr(y, 2, "Cleanup Status:", curses.A_BOLD)
        y += 1

        # Check for recent cleanup operations
        backup_dir = get_path("backups_dir")
        if os.path.exists(backup_dir):
            backup_files = [f for f in os.listdir(backup_dir) if f.startswith("legacy_cleanup_backup_")]
            if backup_files:
                latest_backup = max(backup_files)
                self.stdscr.addstr(y, 4, f"Latest backup: {latest_backup}")
                y += 1
                self.stdscr.addstr(y, 4, "Rollback available: Yes", curses.A_BOLD)
            else:
                self.stdscr.addstr(y, 4, "No cleanup backups found")
        else:
            self.stdscr.addstr(y, 4, "Backup directory not initialized")

    def _draw_error_screen(self, error_message: str) -> None:
        """Draw an error screen."""
        y = self.height // 2
        x = (self.width - len(error_message)) // 2
        self.stdscr.addstr(y, x, f"Error: {error_message}", curses.A_BOLD)

    def _handle_back(self) -> str:
        """Handle back navigation."""
        if self.current_screen == "main":
            return "back_to_main"
        else:
            self.current_screen = "main"
            self.selected_item = 0
            return ""

    def _handle_cursor_up(self) -> None:
        """Handle up arrow key."""
        if self.selected_item > 0:
            self.selected_item -= 1

    def _handle_cursor_down(self) -> None:
        """Handle down arrow key."""
        max_items = self._get_max_items_for_screen()
        if self.selected_item < max_items - 1:
            self.selected_item += 1

    def _handle_enter(self) -> str:
        """Handle enter key."""
        if self.current_screen == "main":
            return self._handle_main_menu_selection()
        elif self.current_screen == "setup":
            return self._handle_setup_selection()
        elif self.current_screen == "mappings":
            return self._handle_mappings_selection()
        elif self.current_screen == "cleanup":
            return self._handle_cleanup_selection()
        elif self.current_screen == "migration":
            return self._handle_migration_selection()

        return ""

    def _handle_refresh(self) -> str:
        """Handle refresh key."""
        # Reload configuration
        self.app_prefs, self.paths = load_app_config()
        self.vault_config = safe_load_json(self.paths["obsidian_vaults"]) or {}
        self.reminders_config = safe_load_json(self.paths["reminders_lists"]) or {}
        return ""

    def _handle_number_key(self, number: int) -> str:
        """Handle number key shortcuts."""
        if self.current_screen == "main" and 1 <= number <= 5:
            self.selected_item = number - 1
            return self._handle_main_menu_selection()
        return ""

    def _handle_main_menu_selection(self) -> str:
        """Handle main menu item selection."""
        actions = ["setup", "mappings", "analysis", "migration", "cleanup"]
        if 0 <= self.selected_item < len(actions):
            action = actions[self.selected_item]
            if action == "analysis":
                return "run_analysis"
            else:
                self.current_screen = action
                self.selected_item = 0
        return ""

    def _handle_setup_selection(self) -> str:
        """Handle setup screen selection."""
        settings = [
            ("vault_organization_enabled", "Organization enabled", "bool"),
            ("default_vault_id", "Default vault", "vault_selector"),
            ("catch_all_filename", "Catch-all filename", "str"),
            ("auto_create_vault_lists", "Auto-create lists", "bool"),
            ("list_naming_template", "List naming template", "str"),
            ("preserve_list_colors", "Preserve list colors", "bool")
        ]

        if 0 <= self.selected_item < len(settings):
            attr_name, display_name, setting_type = settings[self.selected_item]
            return self._modify_setting(attr_name, display_name, setting_type)

        return ""

    def _handle_mappings_selection(self) -> str:
        """Handle mappings screen selection."""
        mappings = self._get_current_mappings()

        if not mappings:
            # Handle setup options when no mappings exist
            setup_actions = ["create_automatic", "manual_setup", "enable_vault_org"]
            if 0 <= self.selected_item < len(setup_actions):
                action = setup_actions[self.selected_item]
                if action == "create_automatic":
                    return self._create_automatic_mappings()
                elif action == "manual_setup":
                    return self._manual_mapping_setup()
                elif action == "enable_vault_org":
                    return self._enable_vault_organization()
        else:
            # Check if user is selecting a mapping or an action
            if self.selected_item < len(mappings):
                # User selected a mapping - could implement individual mapping management
                return "modify_individual_mapping"
            else:
                # User selected an action below the mappings
                action_index = self.selected_item - len(mappings)
                action_options = ["map_to_existing", "auto_discover", "refresh_mappings"]

                if 0 <= action_index < len(action_options):
                    action = action_options[action_index]
                    if action == "map_to_existing":
                        return self._map_to_existing_lists()
                    elif action == "auto_discover":
                        return self._auto_discover_mappings()
                    elif action == "refresh_mappings":
                        return self._refresh_mappings()

        return ""

    def _handle_cleanup_selection(self) -> str:
        """Handle cleanup screen selection."""
        cleanup_actions = ["analyze", "preview", "dry_run", "execute", "rollback"]
        if 0 <= self.selected_item < len(cleanup_actions):
            return f"cleanup_{cleanup_actions[self.selected_item]}"
        return ""

    def _handle_migration_selection(self) -> str:
        """Handle migration screen selection."""
        migration_methods = [
            self._execute_migration_analysis,
            self._execute_migration_plan,
            self._execute_migration_backup,
            self._execute_migration,
            self._execute_migration_verification
        ]

        if 0 <= self.selected_item < len(migration_methods):
            # Check if this step can be executed
            if self._can_execute_migration_step(self.selected_item):
                return migration_methods[self.selected_item]()
            else:
                return "migration_step_blocked"
        return ""

    def _get_max_items_for_screen(self) -> int:
        """Get maximum number of items for current screen."""
        if self.current_screen == "main":
            return 5
        elif self.current_screen == "setup":
            return 6
        elif self.current_screen == "cleanup":
            return 5
        elif self.current_screen == "migration":
            return 5
        elif self.current_screen == "mappings":
            mappings = self._get_current_mappings()
            if not mappings:
                return 3  # Setup options when no mappings
            else:
                # Mappings + action options
                inactive_count = sum(1 for m in mappings if not m.get("active"))
                if inactive_count > 0:
                    return len(mappings) + 3  # Mappings + 3 action options
                else:
                    return len(mappings)  # Just mappings, no actions needed
        return 0

    def _get_default_vault_name(self) -> str:
        """Get the name of the default vault."""
        default_identifier = self._resolved_default_vault_id()
        if not default_identifier:
            return "Not set"

        vault = self._get_vault_by_id(default_identifier)
        if vault:
            return vault.get("name", default_identifier)
        return default_identifier

    def _get_vault_by_id(self, vault_identifier: str) -> Optional[Dict]:
        """Get vault configuration by identifier (name for now, ID when implemented)."""
        for vault in self._vault_entries():
            vault_id = vault.get("vault_id") or generate_stable_vault_id(vault.get("path", ""))
            if vault_id == vault_identifier or vault.get("name") == vault_identifier:
                return vault
        return None

    def _get_current_mappings(self) -> List[Dict]:
        """Get current vault-list mappings."""
        mappings = []

        if not self.app_prefs.vault_organization_enabled:
            return mappings

        vaults = self._vault_entries()
        reminders_lists = self._reminder_list_entries()

        # Create a mapping from list names to list info for faster lookup
        list_map = {lst.get("name"): lst for lst in reminders_lists if lst.get("name")}

        for vault in vaults:
            vault_name = vault.get("name", "Unknown")
            vault_id = vault.get("vault_id") or generate_stable_vault_id(vault.get("path", ""))

            # Determine associated list
            matching_list = None
            associated_id = vault.get("associated_list_id")
            if associated_id:
                matching_list = next((lst for lst in reminders_lists if lst.get("identifier") == associated_id), None)
            if not matching_list and vault_name in list_map:
                matching_list = list_map[vault_name]

            mapping = {
                "vault_name": vault_name,
                "vault_id": vault_id,
                "vault_path": vault.get("path", ""),
                "list_name": matching_list.get("name") if matching_list else "Not mapped",
                "list_id": matching_list.get("identifier") if matching_list else None,
                "active": matching_list is not None
            }
            mappings.append(mapping)

        return mappings

    def _modify_setting(self, attr_name: str, display_name: str, setting_type: str) -> str:
        """Modify a vault organization setting interactively."""
        if setting_type == "bool":
            return self._modify_bool_setting(attr_name, display_name)
        elif setting_type == "str":
            return self._modify_str_setting(attr_name, display_name)
        elif setting_type == "vault_selector":
            return self._modify_vault_selector(attr_name, display_name)
        return ""

    def _modify_bool_setting(self, attr_name: str, display_name: str) -> str:
        """Modify a boolean setting."""
        current_value = getattr(self.app_prefs, attr_name)
        new_value = not current_value
        setattr(self.app_prefs, attr_name, new_value)
        save_app_config(self.app_prefs)
        return "modify_setting"

    def _modify_str_setting(self, attr_name: str, display_name: str) -> str:
        """Modify a string setting."""
        current_value = getattr(self.app_prefs, attr_name)

        # Show simple input dialog
        dialog = InputDialog(self.stdscr, f"Edit {display_name}", current_value)
        new_value = dialog.show()

        if new_value is not None and new_value != current_value:
            setattr(self.app_prefs, attr_name, new_value)
            save_app_config(self.app_prefs)

        return "modify_setting"

    def _modify_vault_selector(self, attr_name: str, display_name: str) -> str:
        """Modify vault selector setting."""
        vaults = self._vault_entries()

        if not vaults:
            return ""

        vault_options = []
        for vault in vaults:
            name = vault.get("name") or "Unnamed Vault"
            vault_id = vault.get("vault_id") or generate_stable_vault_id(vault.get("path", ""))
            vault_options.append((f"{name} ({vault_id})", vault_id))
        vault_options.append(("None", None))

        dialog = SelectionDialog(self.stdscr, f"Select {display_name}", vault_options)
        selected_vault_id = dialog.show()

        if selected_vault_id is not None:
            setattr(self.app_prefs, attr_name, selected_vault_id)
            save_app_config(self.app_prefs)

        return "modify_setting"

    def _create_automatic_mappings(self) -> str:
        """Create automatic vault-to-list mappings."""
        vaults = self._vault_entries()

        if not vaults:
            return ""

        # Show confirmation dialog
        message = f"Create Reminders lists for {len(vaults)} vaults?\n\nThis will create:\n"
        for vault in vaults[:3]:  # Show first 3
            vault_name = vault.get('name', 'Unnamed Vault')
            message += f"• {vault_name} → {vault_name} (Reminders list)\n"
        if len(vaults) > 3:
            message += f"• ... and {len(vaults) - 3} more\n"

        dialog = ConfirmationDialog(self.stdscr, "Create Automatic Mappings", message)
        if dialog.show():
            # Enable vault organization if not already enabled
            if not self.app_prefs.vault_organization_enabled:
                self.app_prefs.vault_organization_enabled = True
                save_app_config(self.app_prefs)
            return "create_vault_lists"
        return ""

    def _manual_mapping_setup(self) -> str:
        """Start manual vault-to-list mapping setup."""
        vaults = self._vault_entries()
        reminders_lists = self._reminder_list_entries()

        if not vaults:
            return ""

        # Show manual mapping interface
        # For now, just enable vault organization and return to setup
        if not self.app_prefs.vault_organization_enabled:
            self.app_prefs.vault_organization_enabled = True
            save_app_config(self.app_prefs)

        # Switch to setup screen for manual configuration
        self.current_screen = "setup"
        self.selected_item = 0
        return ""

    def _enable_vault_organization(self) -> str:
        """Enable vault organization feature."""
        if not self.app_prefs.vault_organization_enabled:
            self.app_prefs.vault_organization_enabled = True
            save_app_config(self.app_prefs)
            return "vault_org_enabled"
        return ""

    def _map_to_existing_lists(self) -> str:
        """Map vaults to existing Reminders lists."""
        mappings = self._get_current_mappings()
        inactive_mappings = [m for m in mappings if not m.get("active")]

        if not inactive_mappings:
            return ""

        # Start with the first unmapped vault
        first_vault = inactive_mappings[0]['vault_name']

        # Get available Reminders lists
        reminders_lists = self._reminder_list_entries()

        if not reminders_lists:
            return ""

        # Smart ordering: put exact and partial matches at the top
        exact_matches = []
        partial_matches = []
        other_lists = []

        for rlist in reminders_lists:
            list_name = rlist.get("name")
            list_id = rlist.get("identifier")
            if not list_name or not list_id:
                continue

            vault_name_lower = first_vault.lower()
            list_name_lower = list_name.lower()

            if vault_name_lower == list_name_lower:
                # Exact match (case-insensitive)
                exact_matches.append((f"✅ {list_name} (exact match)", list_id))
            elif (vault_name_lower in list_name_lower or
                  list_name_lower in vault_name_lower):
                # Partial match
                partial_matches.append((f"🔄 {list_name} (similar)", list_id))
            else:
                # Other lists
                other_lists.append((list_name, list_id))

        # Combine in smart order: exact matches, partial matches, then others
        list_options = exact_matches + partial_matches + other_lists

        # Add separator if we have matches
        if exact_matches or partial_matches:
            separator_index = len(exact_matches) + len(partial_matches)
            if separator_index < len(list_options):
                list_options.insert(separator_index, ("─" * 30, None))

        # Show list selection dialog for the first vault
        dialog = SelectionDialog(
            self.stdscr,
            f"Map '{first_vault}' vault to which Reminders list?",
            list_options
        )
        selected_list_id = dialog.show()

        if selected_list_id is not None:
            # For now, just refresh to show this would be implemented
            # In full implementation, would save the mapping
            return "manual_mapping_started"
        return ""

    def _auto_discover_mappings(self) -> str:
        """Automatically discover potential mappings based on name similarity."""
        mappings = self._get_current_mappings()
        inactive_mappings = [m for m in mappings if not m.get("active")]
        reminders_lists = self._reminder_list_entries()

        suggestions = []
        for mapping in inactive_mappings:
            vault_name = mapping['vault_name']
            # Look for case-insensitive matches or partial matches
            for rlist in reminders_lists:
                list_name = rlist.get('name', '')
                if not list_name:
                    continue
                if (vault_name.lower() in list_name.lower() or
                    list_name.lower() in vault_name.lower() or
                    vault_name.lower() == list_name.lower()):
                    suggestions.append((vault_name, list_name))
                    break

        if suggestions:
            message = f"Found {len(suggestions)} potential mappings:\n\n"
            for vault, rlist in suggestions:
                message += f"• {vault} → {rlist}\n"
            message += "\nApply these mappings?"

            dialog = ConfirmationDialog(self.stdscr, "Auto-Discovered Mappings", message)
            if dialog.show():
                return "auto_mappings_applied"
        else:
            return "no_auto_mappings_found"

        return ""

    def _refresh_mappings(self) -> str:
        """Refresh the mappings display."""
        # Reload configuration
        self.app_prefs, self.paths = load_app_config()
        self.vault_config = safe_load_json(self.paths["obsidian_vaults"]) or {}
        self.reminders_config = safe_load_json(self.paths["reminders_lists"]) or {}
        return "refresh_completed"

    def _can_execute_migration_step(self, step_index: int) -> bool:
        """Check if a migration step can be executed."""
        if step_index == 0:  # Analysis - always available
            return True
        elif step_index == 1:  # Plan - requires analysis
            return self.migration_state["analysis_completed"]
        elif step_index == 2:  # Backup - requires plan
            return self.migration_state["plan_generated"]
        elif step_index == 3:  # Execute - requires backup
            return self.migration_state["backup_created"]
        elif step_index == 4:  # Verify - requires execution
            return self.migration_state["migration_executed"]
        return False

    def _execute_migration_analysis(self) -> str:
        """Execute pre-migration analysis."""
        # Analyze current setup
        vaults = self._vault_entries()
        reminders_lists = self._reminder_list_entries()
        mappings = self._get_current_mappings()

        analysis_results = {
            "vault_count": len(vaults),
            "list_count": len(reminders_lists),
            "active_mappings": len([m for m in mappings if m.get("active")]),
            "inactive_mappings": len([m for m in mappings if not m.get("active")]),
            "vault_org_enabled": self.app_prefs.vault_organization_enabled,
            "recommendations": []
        }

        # Generate recommendations
        if not self.app_prefs.vault_organization_enabled:
            analysis_results["recommendations"].append("Enable vault organization")

        if analysis_results["inactive_mappings"] > 0:
            analysis_results["recommendations"].append(f"Map {analysis_results['inactive_mappings']} inactive vaults")

        # Update state
        self.migration_state["analysis_completed"] = True
        self.migration_state["analysis_results"] = analysis_results
        self.migration_state["current_step"] = max(1, self.migration_state["current_step"])

        return "migration_analysis_completed"

    def _execute_migration_plan(self) -> str:
        """Generate migration plan."""
        if not self.migration_state["analysis_completed"]:
            return "migration_analysis_required"

        analysis = self.migration_state["analysis_results"]
        plan_steps = []

        # Build migration plan based on analysis
        if not analysis["vault_org_enabled"]:
            plan_steps.append("Enable vault-based organization")

        if analysis["inactive_mappings"] > 0:
            plan_steps.append(f"Create mappings for {analysis['inactive_mappings']} vaults")

        plan_steps.append("Update sync configuration")
        plan_steps.append("Verify all mappings are active")

        migration_plan = {
            "steps": plan_steps,
            "estimated_time": "5-10 minutes",
            "backup_required": True,
            "reversible": True
        }

        # Update state
        self.migration_state["plan_generated"] = True
        self.migration_state["migration_plan"] = migration_plan
        self.migration_state["current_step"] = max(2, self.migration_state["current_step"])

        return "migration_plan_generated"

    def _execute_migration_backup(self) -> str:
        """Create comprehensive backup."""
        if not self.migration_state["plan_generated"]:
            return "migration_plan_required"

        import os
        from datetime import datetime

        # Create backup directory
        backup_dir = os.path.expanduser("~/.config/vault_migration_backups")
        os.makedirs(backup_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(backup_dir, f"backup_{timestamp}")
        os.makedirs(backup_path, exist_ok=True)

        # Backup configuration files
        import shutil
        try:
            if os.path.exists(self.paths["obsidian_vaults"]):
                shutil.copy2(self.paths["obsidian_vaults"],
                           os.path.join(backup_path, "obsidian_vaults.json"))

            if os.path.exists(self.paths["reminders_lists"]):
                shutil.copy2(self.paths["reminders_lists"],
                           os.path.join(backup_path, "reminders_lists.json"))

            # Backup app config
            config_path = os.path.expanduser("~/.config/obs_tools_config.json")
            if os.path.exists(config_path):
                shutil.copy2(config_path, os.path.join(backup_path, "obs_tools_config.json"))

        except Exception:
            return "migration_backup_failed"

        # Update state
        self.migration_state["backup_created"] = True
        self.migration_state["backup_path"] = backup_path
        self.migration_state["current_step"] = max(3, self.migration_state["current_step"])

        return "migration_backup_completed"

    def _execute_migration(self) -> str:
        """Execute the migration."""
        if not self.migration_state["backup_created"]:
            return "migration_backup_required"

        try:
            # Enable vault organization if not already enabled
            if not self.app_prefs.vault_organization_enabled:
                self.app_prefs.vault_organization_enabled = True
                save_app_config(self.app_prefs)

            # Set default vault if not set
            default_vault_id = self._resolved_default_vault_id()
            if not default_vault_id:
                vaults = self._vault_entries()
                if vaults:
                    default_entry = next((v for v in vaults if v.get("is_default")), None) or vaults[0]
                    default_vault_id = default_entry.get("vault_id") or generate_stable_vault_id(default_entry.get("path", ""))
                    self.app_prefs.default_vault_id = default_vault_id
                    save_app_config(self.app_prefs)

            # Perform actual task migration
            migration_results = self._perform_task_migration()
            self.migration_state["migration_results"] = migration_results

            # Update state
            self.migration_state["migration_executed"] = True
            self.migration_state["current_step"] = max(4, self.migration_state["current_step"])

            return "migration_executed"

        except Exception as e:
            self.migration_state["migration_error"] = str(e)
            return "migration_execution_failed"

    def _perform_task_migration(self) -> Dict:
        """Perform actual task migration using sync infrastructure."""
        from obs_tools.commands.collect_reminders_tasks import main as collect_reminders
        from obs_tools.commands.task_operations import TaskOperations
        from reminders_gateway import RemindersGateway
        from app_config import get_path
        import tempfile
        import os

        results = {
            "tasks_analyzed": 0,
            "tasks_moved": 0,
            "lists_created": 0,
            "errors": []
        }

        try:
            # Collect current reminders
            temp_file = tempfile.mktemp(suffix='.json')
            collect_result = collect_reminders([
                "--use-config",
                "--config", get_path("reminders_lists"),
                "--output", temp_file
            ])

            if collect_result != 0:
                results["errors"].append("Failed to collect current reminders")
                return results

            # Load reminders data
            import json
            with open(temp_file, 'r') as f:
                reminders_data = json.load(f)

            os.unlink(temp_file)

            tasks = reminders_data.get('tasks', {})
            results["tasks_analyzed"] = len(tasks)

            # Get vault-list mappings
            vault_entries = self._vault_entries()
            reminders_lists = self._reminder_list_entries()

            list_by_id = {}
            list_by_name = {}
            for lst in reminders_lists:
                identifier = lst.get("identifier")
                name = lst.get("name")
                if not identifier:
                    continue
                list_by_id[identifier] = lst
                if name:
                    list_by_name[name.lower()] = identifier

            vault_targets_by_id = {}
            vault_targets_by_name = {}
            for vault in vault_entries:
                vault_name = vault.get("name")
                vault_id = vault.get("vault_id") or generate_stable_vault_id(vault.get("path", ""))
                associated_id = vault.get("associated_list_id")
                if not associated_id and vault_name:
                    associated_id = list_by_name.get(vault_name.lower())
                if associated_id:
                    info = {
                        "vault_entry": vault,
                        "vault_id": vault_id,
                        "vault_name": vault_name or vault_id,
                        "list_id": associated_id,
                    }
                    vault_targets_by_id[vault_id] = info
                    if vault_name:
                        vault_targets_by_name[vault_name.lower()] = info

            # Initialize gateway and operations
            gateway = RemindersGateway()
            operations = TaskOperations()

            # Find tasks that need migration (from default catch-all lists)
            default_list_ids = {
                lst.get("identifier")
                for lst in reminders_lists
                if isinstance(lst, dict) and lst.get("name") in ["Reminders", "Tasks"] and lst.get("identifier")
            }

            resolved_default_id = self._resolved_default_vault_id()

            tasks_to_migrate = []
            for task_id, task in tasks.items():
                current_list_id = task.get('list', {}).get('identifier')
                current_list_name = task.get('list', {}).get('name')

                if current_list_id not in default_list_ids:
                    continue

                task_title = (task.get('description') or task.get('content', {}).get('title', '') or '').lower()

                target_info = None
                for name_lower, info in vault_targets_by_name.items():
                    if name_lower and name_lower in task_title:
                        target_info = info
                        break

                if not target_info and resolved_default_id:
                    if resolved_default_id in vault_targets_by_id:
                        target_info = vault_targets_by_id[resolved_default_id]
                    else:
                        lowered = resolved_default_id.lower()
                        target_info = vault_targets_by_name.get(lowered)

                if target_info and target_info["list_id"] != current_list_id:
                    tasks_to_migrate.append({
                        'task': task,
                        'from_list': current_list_name,
                        'to_list': target_info["vault_name"],
                        'to_list_id': target_info["list_id"],
                        'vault_entry': target_info["vault_entry"],
                        'vault_id': target_info["vault_id"],
                    })

            # Perform migration (limit to first 10 for safety)
            migration_limit = min(10, len(tasks_to_migrate))
            for i, migration in enumerate(tasks_to_migrate[:migration_limit]):
                try:
                    task = migration['task']
                    target_list_id = migration['to_list_id']

                    # Get external IDs
                    external_ids = task.get('external_ids', {})
                    item_id = external_ids.get('item')

                    if item_id:
                        # Find the reminder using gateway
                        reminder = gateway.find_reminder_by_id(item_id)
                        if reminder:
                            # Move to target list using setCalendar
                            store = gateway._get_store()
                            calendars = store.calendarsForEntityType_(gateway._EKEntityTypeReminder) or []
                            target_calendar = None

                            for cal in calendars:
                                if str(cal.calendarIdentifier()) == target_list_id:
                                    target_calendar = cal
                                    break

                            if target_calendar:
                                reminder.setCalendar_(target_calendar)
                                store.saveReminder_commit_error_(reminder, True, None)
                                results["tasks_moved"] += 1
                            else:
                                results["errors"].append(f"Target calendar not found: {migration['to_list']}")
                        else:
                            results["errors"].append(f"Reminder not found: {item_id}")

                except Exception as e:
                    results["errors"].append(f"Failed to migrate task: {str(e)}")

            return results

        except Exception as e:
            results["errors"].append(f"Migration failed: {str(e)}")
            return results

    def _execute_migration_verification(self) -> str:
        """Verify migration results."""
        if not self.migration_state["migration_executed"]:
            return "migration_execution_required"

        # Reload configuration
        self.app_prefs, self.paths = load_app_config()
        self.vault_config = safe_load_json(self.paths["obsidian_vaults"]) or {}
        self.reminders_config = safe_load_json(self.paths["reminders_lists"]) or {}

        # Get migration results from previous step
        migration_results = self.migration_state.get("migration_results", {})

        # Verify results
        verification_results = {
            "vault_org_enabled": self.app_prefs.vault_organization_enabled,
            "default_vault_set": bool(self.app_prefs.default_vault_id),
            "mappings_active": 0,
            "total_mappings": 0,
            "tasks_analyzed": migration_results.get("tasks_analyzed", 0),
            "tasks_moved": migration_results.get("tasks_moved", 0),
            "errors": migration_results.get("errors", []),
            "success": False
        }

        # Check mappings
        mappings = self._get_current_mappings()
        verification_results["total_mappings"] = len(mappings)
        verification_results["mappings_active"] = len([m for m in mappings if m.get("active")])

        # Determine success
        verification_results["success"] = (
            verification_results["vault_org_enabled"] and
            verification_results["default_vault_set"] and
            verification_results["mappings_active"] > 0 and
            len(verification_results["errors"]) == 0
        )

        # Update state
        self.migration_state["results_verified"] = True
        if verification_results["success"]:
            self.migration_state["current_step"] = 5
            return "migration_verification_success"
        else:
            return "migration_verification_failed"


class ProgressDialog:
    """Dialog for showing progress of long-running operations."""

    def __init__(self, stdscr, title: str, width: int = 60, height: int = 10):
        """Initialize progress dialog."""
        self.stdscr = stdscr
        self.title = title
        self.width = width
        self.height = height

        # Calculate position to center dialog
        screen_height, screen_width = stdscr.getmaxyx()
        self.start_y = (screen_height - height) // 2
        self.start_x = (screen_width - width) // 2

        # Create dialog window
        self.dialog_win = curses.newwin(height, width, self.start_y, self.start_x)

    def update_progress(self, step: str, progress: float, details: str = "") -> None:
        """
        Update progress dialog.

        Args:
            step: Current step description
            progress: Progress percentage (0.0 to 1.0)
            details: Additional details
        """
        self.dialog_win.clear()
        self.dialog_win.box()

        # Title
        title_x = (self.width - len(self.title)) // 2
        self.dialog_win.addstr(1, title_x, self.title, curses.A_BOLD)

        # Current step
        self.dialog_win.addstr(3, 2, f"Step: {step}")

        # Progress bar
        bar_width = self.width - 6
        filled_width = int(bar_width * progress)
        progress_bar = "█" * filled_width + "░" * (bar_width - filled_width)
        self.dialog_win.addstr(5, 2, f"[{progress_bar}] {progress:.1%}")

        # Details
        if details:
            max_detail_width = self.width - 4
            if len(details) > max_detail_width:
                details = details[:max_detail_width - 3] + "..."
            self.dialog_win.addstr(7, 2, details)

        self.dialog_win.refresh()

    def close(self) -> None:
        """Close the progress dialog."""
        del self.dialog_win


class ConfirmationDialog:
    """Dialog for confirming destructive operations."""

    def __init__(self, stdscr, title: str, message: str, width: int = 50, height: int = 8):
        """Initialize confirmation dialog."""
        self.stdscr = stdscr
        self.title = title
        self.message = message
        self.width = width
        self.height = height

        # Calculate position to center dialog
        screen_height, screen_width = stdscr.getmaxyx()
        self.start_y = (screen_height - height) // 2
        self.start_x = (screen_width - width) // 2

        # Create dialog window
        self.dialog_win = curses.newwin(height, width, self.start_y, self.start_x)

    def show(self) -> bool:
        """
        Show confirmation dialog and wait for user input.

        Returns:
            True if user confirmed, False otherwise
        """
        while True:
            self.dialog_win.clear()
            self.dialog_win.box()

            # Title
            title_x = (self.width - len(self.title)) // 2
            self.dialog_win.addstr(1, title_x, self.title, curses.A_BOLD)

            # Message
            message_lines = self._wrap_text(self.message, self.width - 4)
            for i, line in enumerate(message_lines):
                if i + 3 < self.height - 2:
                    self.dialog_win.addstr(i + 3, 2, line)

            # Buttons
            button_y = self.height - 2
            self.dialog_win.addstr(button_y, 2, "[Y]es", curses.A_BOLD)
            self.dialog_win.addstr(button_y, 12, "[N]o", curses.A_BOLD)

            self.dialog_win.refresh()

            # Wait for input
            key = self.dialog_win.getch()
            if key in [ord('y'), ord('Y')]:
                return True
            elif key in [ord('n'), ord('N'), 27]:  # 27 is ESC
                return False

    def _wrap_text(self, text: str, width: int) -> List[str]:
        """Wrap text to fit within specified width."""
        words = text.split()
        lines = []
        current_line = ""

        for word in words:
            if len(current_line + " " + word) <= width:
                current_line += " " + word if current_line else word
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word

        if current_line:
            lines.append(current_line)

        return lines


class InputDialog:
    """Dialog for string input."""

    def __init__(self, stdscr, title: str, initial_value: str = "", width: int = 60, height: int = 8):
        """Initialize input dialog."""
        self.stdscr = stdscr
        self.title = title
        self.initial_value = initial_value
        self.width = width
        self.height = height

        # Calculate position to center dialog
        screen_height, screen_width = stdscr.getmaxyx()
        self.start_y = (screen_height - height) // 2
        self.start_x = (screen_width - width) // 2

        # Create dialog window
        self.dialog_win = curses.newwin(height, width, self.start_y, self.start_x)
        self.dialog_win.keypad(True)  # Enable special key handling

    def show(self) -> Optional[str]:
        """
        Show input dialog and return user input.

        Returns:
            User input string or None if cancelled
        """
        current_text = self.initial_value
        cursor_pos = len(current_text)

        while True:
            self.dialog_win.clear()
            self.dialog_win.box()

            # Title
            title_x = (self.width - len(self.title)) // 2
            self.dialog_win.addstr(1, title_x, self.title, curses.A_BOLD)

            # Input field
            input_y = 3
            self.dialog_win.addstr(input_y, 2, "Value:")
            input_field_width = self.width - 6
            display_text = current_text[:input_field_width]
            self.dialog_win.addstr(input_y + 1, 2, display_text)

            # Show cursor
            if cursor_pos < input_field_width:
                try:
                    self.dialog_win.addstr(input_y + 1, 2 + cursor_pos, "_", curses.A_REVERSE)
                except curses.error:
                    pass

            # Help text
            help_y = self.height - 2
            self.dialog_win.addstr(help_y, 2, "Enter: Save  Esc: Cancel", curses.A_DIM)

            self.dialog_win.refresh()

            # Get input
            key = self.dialog_win.getch()

            if key == 27:  # Escape
                return None
            elif key in [10, 13]:  # Enter
                return current_text
            elif key in [8, 127, curses.KEY_BACKSPACE]:  # Backspace
                if cursor_pos > 0:
                    current_text = current_text[:cursor_pos-1] + current_text[cursor_pos:]
                    cursor_pos -= 1
            elif key == curses.KEY_LEFT and cursor_pos > 0:
                cursor_pos -= 1
            elif key == curses.KEY_RIGHT and cursor_pos < len(current_text):
                cursor_pos += 1
            elif 32 <= key <= 126:  # Printable characters
                current_text = current_text[:cursor_pos] + chr(key) + current_text[cursor_pos:]
                cursor_pos += 1


class SelectionDialog:
    """Dialog for selecting from a list of options."""

    def __init__(self, stdscr, title: str, options: List[Tuple[str, any]], width: int = 60, height: int = 15):
        """Initialize selection dialog."""
        self.stdscr = stdscr
        self.title = title
        self.options = options
        self.width = width
        self.height = height
        self.selected_index = 0
        self.scroll_offset = 0

        # Calculate position to center dialog
        screen_height, screen_width = stdscr.getmaxyx()
        self.start_y = (screen_height - height) // 2
        self.start_x = (screen_width - width) // 2

        # Create dialog window
        self.dialog_win = curses.newwin(height, width, self.start_y, self.start_x)
        self.dialog_win.keypad(True)  # Enable special key handling

    def show(self) -> any:
        """
        Show selection dialog and return selected value.

        Returns:
            Selected value or None if cancelled
        """
        while True:
            self.dialog_win.clear()
            self.dialog_win.box()

            # Title
            title_x = (self.width - len(self.title)) // 2
            self.dialog_win.addstr(1, title_x, self.title, curses.A_BOLD)

            # Options with scrolling
            options_start_y = 3
            max_visible_options = self.height - 6  # Leave space for title and help

            # Calculate scrolling
            if self.selected_index < self.scroll_offset:
                self.scroll_offset = self.selected_index
            elif self.selected_index >= self.scroll_offset + max_visible_options:
                self.scroll_offset = self.selected_index - max_visible_options + 1

            # Display visible options
            for i in range(max_visible_options):
                option_index = self.scroll_offset + i
                if option_index >= len(self.options):
                    break

                display_name, value = self.options[option_index]
                y_pos = options_start_y + i
                attr = curses.A_REVERSE if option_index == self.selected_index else curses.A_NORMAL

                # Truncate long option names and add indicator if more text
                max_text_width = self.width - 6
                if len(display_name) > max_text_width:
                    display_text = display_name[:max_text_width - 3] + "..."
                else:
                    display_text = display_name

                self.dialog_win.addstr(y_pos, 2, display_text, attr)

            # Show scroll indicators
            if len(self.options) > max_visible_options:
                # Scroll indicators
                if self.scroll_offset > 0:
                    self.dialog_win.addstr(options_start_y - 1, self.width - 3, "▲", curses.A_DIM)
                if self.scroll_offset + max_visible_options < len(self.options):
                    self.dialog_win.addstr(options_start_y + max_visible_options, self.width - 3, "▼", curses.A_DIM)

            # Help text
            help_y = self.height - 2
            self.dialog_win.addstr(help_y, 2, "↑↓: Navigate  Enter: Select  Esc: Cancel", curses.A_DIM)

            self.dialog_win.refresh()

            # Get input
            key = self.dialog_win.getch()

            if key == 27:  # Escape
                return None
            elif key in [10, 13]:  # Enter
                if 0 <= self.selected_index < len(self.options):
                    selected_value = self.options[self.selected_index][1]
                    # Skip separator items (None values)
                    if selected_value is None:
                        continue
                    return selected_value
                return None
            elif key == curses.KEY_UP or key == ord('k'):
                if self.selected_index > 0:
                    self.selected_index -= 1
            elif key == curses.KEY_DOWN or key == ord('j'):
                if self.selected_index < len(self.options) - 1:
                    self.selected_index += 1
