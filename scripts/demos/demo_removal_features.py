#!/usr/bin/env python3
"""
Demo script to showcase the new vault and Reminders list removal features.
This demonstrates the updated amend menu and removal capabilities.
"""

from obs_sync.core.models import SyncConfig, Vault, RemindersList
from obs_sync.commands.setup import SetupCommand


def create_demo_config():
    """Create a demo configuration with sample data."""
    config = SyncConfig()
    
    # Add sample vaults
    config.vaults = [
        Vault(name="Work Vault", path="/Users/demo/Obsidian/Work", vault_id="work-vault-id", is_default=True),
        Vault(name="Personal Vault", path="/Users/demo/Obsidian/Personal", vault_id="personal-vault-id"),
        Vault(name="Archive Vault", path="/Users/demo/Obsidian/Archive", vault_id="archive-vault-id")
    ]
    config.default_vault_id = "work-vault-id"
    
    # Add sample Reminders lists
    config.reminders_lists = [
        RemindersList(name="Work Tasks", identifier="work-tasks-id", source_name="Reminders",
                     source_type="local", color="blue", allows_modification=True),
        RemindersList(name="Personal Tasks", identifier="personal-tasks-id", source_name="Reminders",
                     source_type="local", color="green", allows_modification=True),
        RemindersList(name="Shopping List", identifier="shopping-list-id", source_name="Reminders",
                     source_type="local", color="orange", allows_modification=True)
    ]
    config.default_calendar_id = "work-tasks-id"
    
    # Set up some sample mappings and tag routes
    config.set_vault_mapping("work-vault-id", "work-tasks-id")
    config.set_vault_mapping("personal-vault-id", "personal-tasks-id")
    config.set_vault_mapping("archive-vault-id", "shopping-list-id")
    
    config.set_tag_route("work-vault-id", "urgent", "work-tasks-id")
    config.set_tag_route("work-vault-id", "meeting", "work-tasks-id")
    config.set_tag_route("personal-vault-id", "home", "personal-tasks-id")
    config.set_tag_route("personal-vault-id", "shopping", "shopping-list-id")
    config.set_tag_route("archive-vault-id", "old", "shopping-list-id")
    
    return config


def demo_impact_analysis():
    """Demonstrate the impact analysis features."""
    print("=== Impact Analysis Demo ===\n")
    
    config = create_demo_config()
    
    # Demo vault removal impact
    print("📋 Analysis for removing 'Personal Vault':")
    impact = config.get_vault_removal_impact("personal-vault-id")
    print(f"  • Vault found: {impact['vault_found']}")
    print(f"  • Vault name: {impact['vault_name']}")
    print(f"  • Is default: {impact['is_default']}")
    print(f"  • Mappings to clear: {impact['mappings_cleared']}")
    print(f"  • Tag routes to clear: {impact['tag_routes_cleared']}")
    if impact['tag_routes']:
        for route in impact['tag_routes']:
            print(f"    - Tag '{route['tag']}' → List {route['calendar_id']}")
    
    print("\n📋 Analysis for removing 'Shopping List':")
    impact = config.get_list_removal_impact("shopping-list-id")
    print(f"  • List found: {impact['list_found']}")
    print(f"  • List name: {impact['list_name']}")
    print(f"  • Is default: {impact['is_default']}")
    print(f"  • Mappings to clear: {impact['mappings_cleared']}")
    print(f"  • Affected vaults: {impact['affected_vaults']}")
    print(f"  • Tag routes to clear: {impact['tag_routes_cleared']}")


def demo_removal_methods():
    """Demonstrate the removal methods."""
    print("\n=== Removal Methods Demo ===\n")
    
    config = create_demo_config()
    
    print("📋 Before removal:")
    print(f"  • Vaults: {[v.name for v in config.vaults]}")
    print(f"  • Lists: {[l.name for l in config.reminders_lists]}")
    print(f"  • Default vault: {config.default_vault.name if config.default_vault else 'None'}")
    print(f"  • Default list: {config.default_calendar_id}")
    
    # Remove a non-default vault
    print("\n🗑️  Removing 'Archive Vault'...")
    success = config.remove_vault("archive-vault-id")
    print(f"  • Removal successful: {success}")
    
    # Remove a non-default list
    print("\n🗑️  Removing 'Shopping List'...")
    success = config.remove_reminders_list("shopping-list-id")
    print(f"  • Removal successful: {success}")
    
    print("\n📋 After removal:")
    print(f"  • Vaults: {[v.name for v in config.vaults]}")
    print(f"  • Lists: {[l.name for l in config.reminders_lists]}")
    print(f"  • Default vault: {config.default_vault.name if config.default_vault else 'None'}")
    print(f"  • Default list: {config.default_calendar_id}")
    
    # Check that mappings and routes were cleaned up
    archive_mapping = config.get_vault_mapping("archive-vault-id")
    print(f"  • Archive vault mapping cleared: {archive_mapping is None}")
    
    archive_routes = config.get_tag_routes_for_vault("archive-vault-id")
    print(f"  • Archive tag routes cleared: {len(archive_routes) == 0}")


def demo_menu_options():
    """Show the new menu options."""
    print("\n=== New Amend Menu Options ===\n")
    
    config = create_demo_config()
    setup_cmd = SetupCommand(config, verbose=True)
    
    print("The amend menu now includes these new options:")
    print("  1. Vault to List mappings")
    print("  2. Tag routing rules")
    print("  3. Default vault")
    print("  4. Default Reminders list")
    print("  5. Calendar sync settings")
    print("  6. Remove a vault              ← NEW!")
    print("  7. Remove a Reminders list     ← NEW!")
    print("  8. All of the above (options 1-5)")
    print("  9. Cancel")
    
    print("\nThe removal options provide:")
    print("  • Impact analysis before removal")
    print("  • Safe handling of default changes")
    print("  • Automatic cleanup of related data")
    print("  • User confirmation required")


if __name__ == "__main__":
    print("🎉 ObsSync Setup Removal Features Demo\n")
    
    demo_impact_analysis()
    demo_removal_methods()
    demo_menu_options()
    
    print("\n✅ Demo completed!")
    print("\nKey Features Added:")
    print("  ✓ Safe vault removal with impact analysis")
    print("  ✓ Safe Reminders list removal with impact analysis")
    print("  ✓ Automatic cleanup of sync links, mappings, and tag routes")
    print("  ✓ Default handling when removing default items")
    print("  ✓ Comprehensive test coverage")
    print("  ✓ Integration with existing amend flow")