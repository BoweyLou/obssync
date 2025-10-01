#!/usr/bin/env python3
"""
Demo script showing the new reconfigure amend functionality.
This demonstrates the behavior without requiring actual Obsidian vaults or Apple Reminders.
"""

import sys
import os
from unittest.mock import patch, MagicMock

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from obs_sync.core.models import SyncConfig, Vault, RemindersList
from obs_sync.commands.setup import SetupCommand


def demo_amend_flow():
    """Demonstrate the amend flow with a mock configuration."""
    
    print("=" * 60)
    print("DEMO: obs-sync setup --reconfigure (Amend Mode)")
    print("=" * 60)
    
    # Create a sample configuration
    config = SyncConfig()
    
    # Add some sample vaults
    config.vaults = [
        Vault(name="📊 Work Notes", path="/Users/demo/Work", vault_id="work-vault", is_default=True),
        Vault(name="🏠 Personal", path="/Users/demo/Personal", vault_id="personal-vault"),
        Vault(name="📚 Research", path="/Users/demo/Research", vault_id="research-vault")
    ]
    config.default_vault_id = "work-vault"
    
    # Add some sample Reminders lists
    config.reminders_lists = [
        RemindersList(name="Work Tasks", identifier="work-list", source_name="iCloud", 
                     source_type="cloud", color="blue", allows_modification=True),
        RemindersList(name="Personal", identifier="personal-list", source_name="iCloud",
                     source_type="cloud", color="green", allows_modification=True),
        RemindersList(name="Projects", identifier="projects-list", source_name="iCloud",
                     source_type="cloud", color="purple", allows_modification=True),
        RemindersList(name="Inbox", identifier="inbox-list", source_name="Local",
                     source_type="local", color="gray", allows_modification=True)
    ]
    config.default_calendar_id = "work-list"
    
    # Set up current mappings
    config.set_vault_mapping("work-vault", "work-list")
    config.set_vault_mapping("personal-vault", "personal-list")
    config.set_vault_mapping("research-vault", "projects-list")
    
    # Add some tag routes
    config.set_tag_route("work-vault", "#urgent", "inbox-list")
    config.set_tag_route("work-vault", "#meeting", "work-list")
    config.set_tag_route("personal-vault", "#shopping", "personal-list")
    
    setup_cmd = SetupCommand(config, verbose=False)
    
    print("\n📋 Current Configuration:")
    print("-" * 40)
    print("\nVaults:")
    for v in config.vaults:
        mapping = config.get_vault_mapping(v.vault_id)
        list_name = next((l.name for l in config.reminders_lists if l.identifier == mapping), "None")
        default = " ⭐" if v.is_default else ""
        print(f"  • {v.name}{default} → {list_name}")
    
    print("\nTag Routes:")
    for v in config.vaults:
        routes = config.get_tag_routes_for_vault(v.vault_id)
        if routes:
            print(f"  {v.name}:")
            for route in routes:
                list_name = next((l.name for l in config.reminders_lists 
                                if l.identifier == route['calendar_id']), "Unknown")
                print(f"    • {route['tag']} → {list_name}")
    
    print("\n" + "=" * 40)
    print("Simulating user choosing AMEND mode...")
    print("=" * 40)
    
    # Mock user inputs for demonstration
    with patch('builtins.input') as mock_input:
        # User chooses to amend vault mappings
        mock_input.side_effect = [
            '2',  # Choose amend instead of reset
            '1',  # Choose to modify vault mappings
            '4',  # Change Work Notes to Inbox list
            '',   # Keep Personal mapping
            '2',  # Change Research to Personal list
        ]
        
        # Mock the print to capture output
        original_print = print
        printed_lines = []
        
        def capture_print(*args, **kwargs):
            printed_lines.append(' '.join(str(arg) for arg in args))
            original_print(*args, **kwargs)
        
        with patch('builtins.print', side_effect=capture_print):
            setup_cmd._handle_reconfigure_choice()
    
    print("\n✅ After Amendment:")
    print("-" * 40)
    print("\nNew Vault Mappings:")
    for v in config.vaults:
        mapping = config.get_vault_mapping(v.vault_id)
        list_name = next((l.name for l in config.reminders_lists if l.identifier == mapping), "None")
        default = " ⭐" if v.is_default else ""
        print(f"  • {v.name}{default} → {list_name}")
    
    print("\n" + "=" * 60)
    print("Demo complete! This shows how users can adjust mappings")
    print("without losing their entire configuration.")
    print("=" * 60)


def demo_comparison():
    """Show the difference between reset and amend modes."""
    
    print("\n" + "=" * 60)
    print("COMPARISON: Reset vs Amend")
    print("=" * 60)
    
    print("\n🔄 RESET Mode (Option 1):")
    print("  • Clears all existing configuration")
    print("  • Re-discovers vaults and lists from scratch")
    print("  • User must reconfigure everything")
    print("  • Useful when: Major changes needed, starting fresh")
    
    print("\n✏️ AMEND Mode (Option 2):")
    print("  • Keeps existing vaults and lists")
    print("  • Allows selective changes to:")
    print("    - Vault to list mappings")
    print("    - Tag routing rules")
    print("    - Default vault selection")
    print("    - Default Reminders list")
    print("  • Useful when: Fine-tuning existing setup")
    
    print("\n💡 Example Use Cases:")
    print("  • Changed your Reminders list organization → Use AMEND")
    print("  • Want different vault-list associations → Use AMEND")
    print("  • Moving to entirely new vault structure → Use RESET")
    print("  • First-time setup was wrong → Use RESET")


if __name__ == "__main__":
    demo_amend_flow()
    demo_comparison()
    
    print("\n✨ To try this yourself:")
    print("  obs-sync setup --reconfigure")
    print("\nThe tool will prompt you to choose between:")
    print("  1. Reset - Start fresh")
    print("  2. Amend - Modify existing settings")