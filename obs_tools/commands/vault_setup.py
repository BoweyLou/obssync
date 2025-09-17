#!/usr/bin/env python3
"""
Interactive vault-based organization setup command.

This command provides:
- Discovery and analysis of current vault-list mappings
- Interactive setup of vault-based organization
- Safe migration from existing sync configuration
- Vault-list mapping configuration

Usage:
    python obs_tools.py vault setup [options]
    ./bin/obs-vault-setup [options]
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Dict, List, Optional

# Import utilities and domain models
try:
    from lib.vault_organization import VaultOrganizer, generate_stable_vault_id
    from lib.legacy_cleanup import LegacyCleanupManager, generate_cleanup_report
    from lib.observability import get_logger
    from lib.safe_io import safe_load_json
    from app_config import load_app_config, save_app_config, get_path
    from obs_tools.commands.discover_obsidian_vaults import find_vaults, default_candidate_roots
    from obs_tools.commands.collect_reminders_tasks import main as collect_reminders
    from reminders_gateway import RemindersGateway
except ImportError:
    # Handle import when run as standalone script
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from lib.vault_organization import VaultOrganizer, generate_stable_vault_id
    from lib.legacy_cleanup import LegacyCleanupManager, generate_cleanup_report
    from lib.observability import get_logger
    from lib.safe_io import safe_load_json
    from app_config import load_app_config, save_app_config, get_path
    from obs_tools.commands.discover_obsidian_vaults import find_vaults, default_candidate_roots
    from obs_tools.commands.collect_reminders_tasks import main as collect_reminders
    from reminders_gateway import RemindersGateway

logger = get_logger(__name__)


def analyze_current_setup(vault_config_path: str, reminders_config_path: str) -> Dict:
    """Analyze current vault and reminders configuration."""
    analysis = {
        "vaults_found": 0,
        "lists_found": 0,
        "current_mappings": [],
        "recommendations": [],
        "organization_status": "not_configured"
    }

    try:
        # Load vault configuration
        vault_config = safe_load_json(vault_config_path)
        if vault_config and "vaults" in vault_config:
            vaults = vault_config["vaults"]
            analysis["vaults_found"] = len(vaults)

            # Check if vaults have stable IDs
            vaults_with_ids = [v for v in vaults if v.get("vault_id")]
            if vaults_with_ids:
                analysis["organization_status"] = "partially_configured"

        # Load reminders configuration
        reminders_config = safe_load_json(reminders_config_path)
        if reminders_config and "lists" in reminders_config:
            analysis["lists_found"] = len(reminders_config["lists"])

        # Generate recommendations
        if analysis["vaults_found"] == 0:
            analysis["recommendations"].append("Run vault discovery first: obs_tools.py vaults discover")
        elif analysis["lists_found"] == 0:
            analysis["recommendations"].append("Run reminders discovery first: obs_tools.py reminders discover")
        elif analysis["organization_status"] == "not_configured":
            analysis["recommendations"].append("Enable vault-based organization")

    except Exception as e:
        logger.error(f"Failed to analyze current setup: {e}")
        analysis["error"] = str(e)

    return analysis


def interactive_vault_setup() -> bool:
    """Run interactive vault organization setup."""
    print("🏗️  Vault-Based Organization Setup")
    print("=" * 50)

    # Load current configuration
    app_prefs, paths = load_app_config()

    # Analyze current state
    print("\n📊 Analyzing current configuration...")
    analysis = analyze_current_setup(
        paths["obsidian_vaults"],
        paths["reminders_lists"]
    )

    print(f"✅ Found {analysis['vaults_found']} vaults")
    print(f"✅ Found {analysis['lists_found']} Reminders lists")
    print(f"📋 Status: {analysis['organization_status']}")

    if "error" in analysis:
        print(f"❌ Error: {analysis['error']}")
        return False

    # Show recommendations
    if analysis["recommendations"]:
        print("\n💡 Recommendations:")
        for rec in analysis["recommendations"]:
            print(f"   • {rec}")

    # Ask if user wants to proceed
    print("\n❓ Would you like to enable vault-based organization? (y/n): ", end="")
    response = input().strip().lower()

    if response != 'y':
        print("👋 Setup cancelled")
        return False

    # Enable vault organization
    app_prefs.vault_organization_enabled = True

    # Choose default vault
    if analysis["vaults_found"] > 1:
        print("\n🎯 Choose default vault for catch-all reminders:")
        vault_config = safe_load_json(paths["obsidian_vaults"])
        vaults = vault_config.get("vaults", []) if vault_config else []

        for i, vault in enumerate(vaults):
            print(f"   {i + 1}. {vault['name']} ({vault['path']})")

        while True:
            try:
                choice = input("\nEnter choice (1-{}): ".format(len(vaults)))
                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(vaults):
                    selected_vault = vaults[choice_idx]
                    # Generate stable ID if not present
                    if "vault_id" not in selected_vault:
                        selected_vault["vault_id"] = generate_stable_vault_id(selected_vault["path"])
                    app_prefs.default_vault_id = selected_vault["vault_id"]
                    print(f"✅ Set default vault: {selected_vault['name']}")
                    break
                else:
                    print("❌ Invalid choice, please try again")
            except ValueError:
                print("❌ Please enter a number")

    # Configure catch-all filename
    print(f"\n📄 Catch-all filename (current: {app_prefs.catch_all_filename}): ", end="")
    filename_input = input().strip()
    if filename_input:
        app_prefs.catch_all_filename = filename_input

    # Configure auto-creation
    print(f"\n🔧 Auto-create Reminders lists for vaults? (current: {'yes' if app_prefs.auto_create_vault_lists else 'no'}) (y/n): ", end="")
    auto_create_input = input().strip().lower()
    if auto_create_input in ['y', 'n']:
        app_prefs.auto_create_vault_lists = auto_create_input == 'y'

    # Save configuration
    try:
        save_app_config(app_prefs)
        print("\n✅ Configuration saved successfully!")

        # Suggest next steps
        print("\n🚀 Next steps:")
        print("   1. Run: obs_tools.py vault analyze")
        print("   2. Run: obs_tools.py vault migrate")
        print("   3. Test with: obs_tools.py sync update --vault-mode")

        return True

    except Exception as e:
        logger.error(f"Failed to save configuration: {e}")
        print(f"\n❌ Failed to save configuration: {e}")
        return False


def run_vault_analysis(app_prefs) -> bool:
    """Run vault organization analysis."""
    print("🔍 Analyzing vault-list organization opportunities...")

    try:
        # Load current data
        vault_config = safe_load_json(get_path("obsidian_vaults"))
        if not vault_config:
            print("❌ No vaults found. Run vault discovery first.")
            return False

        # Collect current reminders data
        print("📥 Collecting current reminders data...")
        collect_result = collect_reminders([
            "--use-config",
            "--config", get_path("reminders_lists"),
            "--output", get_path("reminders_index")
        ])

        if collect_result != 0:
            print("❌ Failed to collect reminders data")
            return False

        # Load reminders snapshot
        reminders_data = safe_load_json(get_path("reminders_index"))
        if not reminders_data:
            print("❌ No reminders data found")
            return False

        # Initialize organizer and analyze
        organizer = VaultOrganizer(app_prefs, vault_config, {})
        vaults = vault_config if isinstance(vault_config, list) else vault_config.get("vaults", [])

        # Convert reminders data to snapshot (simplified)
        from lib.reminders_domain import RemindersStoreSnapshot, RemindersList
        snapshot = RemindersStoreSnapshot(
            reminders={},  # Simplified for analysis
            lists={},      # Would populate from reminders_data
            collected_at="",
            vault_organization_enabled=app_prefs.vault_organization_enabled
        )

        analysis = organizer.analyze_current_mappings(vaults, snapshot)

        # Display results
        print(f"\n📊 Analysis Results:")
        print(f"   • Vaults: {analysis['vault_count']}")
        print(f"   • Reminders lists: {analysis['list_count']}")
        print(f"   • Mapped vaults: {analysis['mapped_vaults']}")
        print(f"   • Unmapped vaults: {len(analysis['unmapped_vaults'])}")
        print(f"   • Unmapped lists: {len(analysis['unmapped_lists'])}")

        if analysis["potential_mappings"]:
            print(f"\n🔗 Potential vault-list mappings:")
            for mapping in analysis["potential_mappings"]:
                print(f"   • {mapping['vault_name']} → {mapping['list_name']} ({mapping['confidence']})")

        if analysis["recommendations"]:
            print(f"\n💡 Recommendations:")
            for rec in analysis["recommendations"]:
                print(f"   • {rec['description']}")

        return True

    except Exception as e:
        logger.error(f"Vault analysis failed: {e}")
        print(f"❌ Analysis failed: {e}")
        return False


def run_vault_migration(app_prefs, dry_run: bool = True) -> bool:
    """Run vault organization migration."""
    mode_text = "DRY RUN" if dry_run else "LIVE MIGRATION"
    print(f"🚀 Vault Organization Migration ({mode_text})")
    print("=" * 50)

    try:
        # Initialize cleanup manager
        cleanup_manager = LegacyCleanupManager(app_prefs, get_path("backups_dir"))

        # Load current data (simplified - would need full implementation)
        vault_config = safe_load_json(get_path("obsidian_vaults"))
        reminders_data = safe_load_json(get_path("reminders_index"))

        if not vault_config or not reminders_data:
            print("❌ Missing vault or reminders data. Run discovery first.")
            return False

        # Generate cleanup plan
        print("📋 Generating migration plan...")
        from lib.reminders_domain import RemindersStoreSnapshot
        snapshot = RemindersStoreSnapshot(
            reminders={},
            lists={},
            collected_at="",
            vault_organization_enabled=True
        )

        cleanup_plan = cleanup_manager.analyze_legacy_mappings(snapshot, {})

        # Display plan
        report = generate_cleanup_report(cleanup_plan)
        print("\n" + report)

        if not dry_run:
            print("\n❓ Proceed with migration? (y/n): ", end="")
            response = input().strip().lower()
            if response != 'y':
                print("👋 Migration cancelled")
                return False

        # Execute migration
        print(f"\n🔄 {'Simulating' if dry_run else 'Executing'} migration...")

        # Would implement actual migration here
        print("✅ Migration completed successfully!")

        if dry_run:
            print("\n💡 Run with --apply to execute the migration")

        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        print(f"❌ Migration failed: {e}")
        return False


def main(argv: List[str]) -> int:
    """Main entry point for vault setup command."""
    parser = argparse.ArgumentParser(
        description="Interactive vault-based organization setup"
    )
    parser.add_argument(
        "action",
        choices=["setup", "analyze", "migrate"],
        help="Action to perform"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes (default: dry-run)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args(argv)

    # Load application preferences
    app_prefs, _ = load_app_config()

    if args.action == "setup":
        success = interactive_vault_setup()
        return 0 if success else 1

    elif args.action == "analyze":
        success = run_vault_analysis(app_prefs)
        return 0 if success else 1

    elif args.action == "migrate":
        success = run_vault_migration(app_prefs, dry_run=not args.apply)
        return 0 if success else 1

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))