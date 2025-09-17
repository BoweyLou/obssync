#!/usr/bin/env python3
"""
Comprehensive demonstration of vault-based organization system.

This script demonstrates:
- Complete vault-based organization workflow
- Integration with existing sync infrastructure
- Migration from legacy configuration
- Real-world usage patterns

Run this script to see the vault organization system in action.
"""

import json
import os
import tempfile
from datetime import datetime
from typing import Dict, List

# Import vault organization modules
from lib.vault_organization import VaultOrganizer, generate_stable_vault_id
from lib.catch_all_manager import CatchAllManager
from lib.legacy_cleanup import LegacyCleanupManager, generate_cleanup_report
from lib.vault_observability import get_vault_metrics_collector, OperationType
from lib.reminders_domain import (
    RemindersList, ReminderItem, RemindersStoreSnapshot,
    ReminderStatus, ListLocationType, VaultMapping, CatchAllMapping
)
from app_config import AppPreferences


class VaultOrganizationDemo:
    """Demonstration of vault-based organization features."""

    def __init__(self):
        """Initialize the demonstration environment."""
        self.temp_dir = tempfile.mkdtemp()
        print(f"🏗️  Demo environment created at: {self.temp_dir}")

        # Create mock vault directories
        self.vaults = self._create_mock_vaults()

        # Create mock reminders data
        self.reminders_snapshot = self._create_mock_reminders()

        # Configure application preferences
        self.app_prefs = AppPreferences(
            vault_organization_enabled=True,
            default_vault_id=self.vaults[0]["vault_id"],
            catch_all_filename="OtherAppleReminders.md",
            auto_create_vault_lists=True,
            list_naming_template="{vault_name}",
            cleanup_legacy_mappings=True
        )

        # Initialize metrics collector
        self.metrics_collector = get_vault_metrics_collector(
            metrics_dir=os.path.join(self.temp_dir, "metrics"),
            enabled=True
        )

        print("✅ Demo environment initialized")

    def run_complete_demo(self):
        """Run the complete vault organization demonstration."""
        print("\n" + "=" * 60)
        print("🚀 VAULT-BASED ORGANIZATION DEMONSTRATION")
        print("=" * 60)

        try:
            # Step 1: Analyze current setup
            self._demo_analysis()

            # Step 2: Generate organization plans
            self._demo_planning()

            # Step 3: Execute vault-list mapping
            self._demo_vault_list_creation()

            # Step 4: Demonstrate catch-all file management
            self._demo_catch_all_management()

            # Step 5: Show legacy cleanup
            self._demo_legacy_cleanup()

            # Step 6: Display metrics and observability
            self._demo_metrics_observability()

            print("\n✅ Demonstration completed successfully!")

        except Exception as e:
            print(f"\n❌ Demo failed: {e}")
            raise

        finally:
            self._cleanup_demo()

    def _create_mock_vaults(self) -> List[Dict]:
        """Create mock Obsidian vaults for demonstration."""
        vault_names = ["Work", "Personal", "Research"]
        vaults = []

        for name in vault_names:
            vault_path = os.path.join(self.temp_dir, f"vault_{name.lower()}")
            os.makedirs(os.path.join(vault_path, ".obsidian"))

            vault = {
                "name": name,
                "path": vault_path,
                "vault_id": generate_stable_vault_id(vault_path)
            }
            vaults.append(vault)

        print(f"📁 Created {len(vaults)} mock vaults")
        return vaults

    def _create_mock_reminders(self) -> RemindersStoreSnapshot:
        """Create mock reminders data for demonstration."""
        # Create reminders lists (some matching vaults, some external)
        lists = {
            "work-list": RemindersList(
                identifier="work-list",
                name="Work",
                list_location_type=ListLocationType.UNCLASSIFIED
            ),
            "personal-list": RemindersList(
                identifier="personal-list",
                name="Personal",
                list_location_type=ListLocationType.UNCLASSIFIED
            ),
            "shopping-list": RemindersList(
                identifier="shopping-list",
                name="Shopping",
                list_location_type=ListLocationType.UNCLASSIFIED
            ),
            "legacy-tasks": RemindersList(
                identifier="legacy-tasks",
                name="Old Tasks",
                list_location_type=ListLocationType.LEGACY
            ),
            "travel-list": RemindersList(
                identifier="travel-list",
                name="Travel Ideas",
                list_location_type=ListLocationType.UNCLASSIFIED
            )
        }

        # Create sample reminders
        reminders = {}

        # Work reminders
        work_tasks = [
            "Complete project documentation",
            "Review team performance",
            "Prepare quarterly report"
        ]

        for i, task in enumerate(work_tasks):
            reminder = ReminderItem(
                uuid=f"work-{i+1}",
                source_key=f"rem:work-{i+1}",
                list_info=lists["work-list"],
                status=ReminderStatus.TODO,
                description=task,
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
                last_seen=datetime.now().isoformat()
            )
            reminders[f"work-{i+1}"] = reminder

        # Personal reminders
        personal_tasks = [
            "Call dentist for appointment",
            "Plan weekend hiking trip"
        ]

        for i, task in enumerate(personal_tasks):
            reminder = ReminderItem(
                uuid=f"personal-{i+1}",
                source_key=f"rem:personal-{i+1}",
                list_info=lists["personal-list"],
                status=ReminderStatus.TODO,
                description=task,
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
                last_seen=datetime.now().isoformat()
            )
            reminders[f"personal-{i+1}"] = reminder

        # External list reminders (for catch-all)
        shopping_tasks = [
            "Buy groceries for the week",
            "Get new running shoes",
            "Pick up dry cleaning"
        ]

        for i, task in enumerate(shopping_tasks):
            reminder = ReminderItem(
                uuid=f"shopping-{i+1}",
                source_key=f"rem:shopping-{i+1}",
                list_info=lists["shopping-list"],
                status=ReminderStatus.TODO,
                description=task,
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
                last_seen=datetime.now().isoformat()
            )
            reminders[f"shopping-{i+1}"] = reminder

        travel_tasks = ["Research hotels in Tokyo", "Compare flight prices"]

        for i, task in enumerate(travel_tasks):
            reminder = ReminderItem(
                uuid=f"travel-{i+1}",
                source_key=f"rem:travel-{i+1}",
                list_info=lists["travel-list"],
                status=ReminderStatus.TODO,
                description=task,
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
                last_seen=datetime.now().isoformat()
            )
            reminders[f"travel-{i+1}"] = reminder

        snapshot = RemindersStoreSnapshot(
            reminders=reminders,
            lists=lists,
            collected_at=datetime.now().isoformat(),
            vault_organization_enabled=True
        )

        print(f"📝 Created {len(reminders)} mock reminders across {len(lists)} lists")
        return snapshot

    def _demo_analysis(self):
        """Demonstrate vault organization analysis."""
        print("\n📊 STEP 1: Analyzing Current Setup")
        print("-" * 40)

        with self.metrics_collector.track_operation(
            OperationType.VAULT_DISCOVERY,
            vault_organization_enabled=True
        ) as op_log:
            organizer = VaultOrganizer(self.app_prefs, {}, {})
            analysis = organizer.analyze_current_mappings(self.vaults, self.reminders_snapshot)

            op_log.vault_ids = [v["vault_id"] for v in self.vaults]

        print(f"🏛️  Discovered vaults: {analysis['vault_count']}")
        print(f"📋 Reminders lists: {analysis['list_count']}")
        print(f"🔗 Potential mappings: {len(analysis['potential_mappings'])}")
        print(f"❓ Unmapped vaults: {len(analysis['unmapped_vaults'])}")
        print(f"❓ Unmapped lists: {len(analysis['unmapped_lists'])}")

        if analysis["potential_mappings"]:
            print("\n🎯 Potential vault-list mappings:")
            for mapping in analysis["potential_mappings"]:
                print(f"   • {mapping['vault_name']} → {mapping['list_name']} ({mapping['confidence']})")

        if analysis["recommendations"]:
            print("\n💡 Recommendations:")
            for rec in analysis["recommendations"]:
                print(f"   • {rec['description']}")

    def _demo_planning(self):
        """Demonstrate organization plan generation."""
        print("\n📋 STEP 2: Generating Organization Plans")
        print("-" * 40)

        organizer = VaultOrganizer(self.app_prefs, {}, {})

        # Generate vault-list plans
        vault_plans = organizer.generate_vault_list_plan(self.vaults, self.reminders_snapshot)

        print(f"🏗️  Vault-list plans generated: {len(vault_plans)}")
        for plan in vault_plans:
            print(f"   • {plan.vault_name} → {plan.action} list '{plan.target_list_name}'")

        # Generate catch-all plans
        unmapped_lists = [
            {"list_id": "shopping-list", "list_name": "Shopping"},
            {"list_id": "travel-list", "list_name": "Travel Ideas"}
        ]

        default_vault = next(v for v in self.vaults if v["vault_id"] == self.app_prefs.default_vault_id)
        catch_all_plans = organizer.generate_catch_all_plan(
            unmapped_lists,
            default_vault["path"]
        )

        print(f"📄 Catch-all plans generated: {len(catch_all_plans)}")
        for plan in catch_all_plans:
            print(f"   • {plan.list_name} → section in {os.path.basename(plan.target_file)}")

    def _demo_vault_list_creation(self):
        """Demonstrate vault-list creation workflow."""
        print("\n🔨 STEP 3: Creating Vault-List Mappings")
        print("-" * 40)

        with self.metrics_collector.track_operation(
            OperationType.VAULT_MAPPING,
            vault_organization_enabled=True
        ) as op_log:
            # Simulate list creation (normally would use RemindersGateway)
            vault_mappings = {}

            for vault in self.vaults[:2]:  # Only map first two vaults
                list_id = f"list-{vault['vault_id'][:8]}"
                mapping = VaultMapping(
                    vault_id=vault["vault_id"],
                    vault_name=vault["name"],
                    vault_path=vault["path"],
                    list_id=list_id,
                    list_name=vault["name"],
                    is_auto_created=True,
                    created_at=datetime.now().isoformat()
                )
                vault_mappings[vault["vault_id"]] = mapping

                print(f"✅ Created list '{vault['name']}' for vault {vault['name']}")

                # Record list creation metric
                self.metrics_collector.record_list_creation(
                    vault["vault_id"], list_id, 45.0, True
                )

            op_log.vault_ids = list(vault_mappings.keys())
            op_log.list_ids = [m.list_id for m in vault_mappings.values()]

        print(f"🎉 Successfully created {len(vault_mappings)} vault-list mappings")

    def _demo_catch_all_management(self):
        """Demonstrate catch-all file management."""
        print("\n📄 STEP 4: Managing Catch-All File")
        print("-" * 40)

        with self.metrics_collector.track_operation(
            OperationType.CATCH_ALL_UPDATE,
            vault_organization_enabled=True
        ) as op_log:
            default_vault = next(v for v in self.vaults if v["vault_id"] == self.app_prefs.default_vault_id)
            catch_all_file = os.path.join(default_vault["path"], self.app_prefs.catch_all_filename)

            manager = CatchAllManager(catch_all_file)

            # Create mappings for external lists
            list_mappings = {
                "shopping-list": {
                    "list_name": "Shopping",
                    "section_heading": "## Shopping",
                    "anchor_start": "<!-- obs-tools:section:shopping:start -->",
                    "anchor_end": "<!-- obs-tools:section:shopping:end -->"
                },
                "travel-list": {
                    "list_name": "Travel Ideas",
                    "section_heading": "## Travel Ideas",
                    "anchor_start": "<!-- obs-tools:section:travel-ideas:start -->",
                    "anchor_end": "<!-- obs-tools:section:travel-ideas:end -->"
                }
            }

            # Update catch-all file
            start_time = datetime.now()
            updated = manager.update_sections(list_mappings, self.reminders_snapshot)
            update_time = (datetime.now() - start_time).total_seconds() * 1000

            if updated:
                print(f"✅ Updated catch-all file: {catch_all_file}")

                # Show file content preview
                with open(catch_all_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                print(f"📖 File size: {len(content)} characters")
                print(f"📊 Sections: {len(list_mappings)}")

                # Count tasks in each section
                shopping_tasks = len([r for r in self.reminders_snapshot.reminders.values()
                                    if r.list_info.identifier == "shopping-list"])
                travel_tasks = len([r for r in self.reminders_snapshot.reminders.values()
                                  if r.list_info.identifier == "travel-list"])

                print(f"   • Shopping: {shopping_tasks} tasks")
                print(f"   • Travel Ideas: {travel_tasks} tasks")

                # Record metrics
                self.metrics_collector.record_catch_all_update(
                    catch_all_file, len(list_mappings),
                    shopping_tasks + travel_tasks, update_time
                )

                op_log.affected_files = [catch_all_file]

    def _demo_legacy_cleanup(self):
        """Demonstrate legacy cleanup operations."""
        print("\n🧹 STEP 5: Legacy Cleanup Analysis")
        print("-" * 40)

        with self.metrics_collector.track_operation(
            OperationType.LEGACY_CLEANUP,
            vault_organization_enabled=True
        ) as op_log:
            cleanup_manager = LegacyCleanupManager(
                self.app_prefs,
                os.path.join(self.temp_dir, "backups")
            )

            # Analyze legacy mappings
            cleanup_plan = cleanup_manager.analyze_legacy_mappings(
                self.reminders_snapshot,
                {}  # No current vault mappings for demo
            )

            print(f"🔍 Legacy mappings found: {len(cleanup_plan.legacy_mappings)}")
            print(f"📦 Duplicate groups: {len(cleanup_plan.duplicate_groups)}")
            print(f"📋 Content migrations: {len(cleanup_plan.content_migrations)}")
            print(f"⚠️  Risk level: {cleanup_plan.risk_level}")

            # Generate cleanup report
            report = generate_cleanup_report(cleanup_plan)
            report_file = os.path.join(self.temp_dir, "cleanup_report.md")

            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(report)

            print(f"📋 Cleanup report saved: {report_file}")

            op_log.changes_summary = {
                "legacy_mappings": len(cleanup_plan.legacy_mappings),
                "duplicate_groups": len(cleanup_plan.duplicate_groups),
                "risk_level": cleanup_plan.risk_level
            }

    def _demo_metrics_observability(self):
        """Demonstrate metrics and observability features."""
        print("\n📈 STEP 6: Metrics and Observability")
        print("-" * 40)

        # Generate performance report
        report = self.metrics_collector.generate_performance_report(days=1)

        print(f"📊 Total operations tracked: {report['total_operations']}")
        print(f"✅ Success rate: {report['success_rate']:.1%}")
        print(f"⏱️  Average duration: {report['average_duration_ms']:.1f}ms")

        if report["operations_by_type"]:
            print("\n📋 Operations by type:")
            for op_type, stats in report["operations_by_type"].items():
                print(f"   • {op_type}: {stats['count']} ops, {stats['success_rate']:.1%} success")

        # Save metrics report
        metrics_file = os.path.join(self.temp_dir, "metrics_report.json")
        with open(metrics_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)

        print(f"💾 Metrics report saved: {metrics_file}")

    def _cleanup_demo(self):
        """Clean up demonstration environment."""
        print(f"\n🧹 Cleaning up demo environment at: {self.temp_dir}")

        # Show what was created
        print("\n📁 Demo artifacts created:")
        for root, dirs, files in os.walk(self.temp_dir):
            level = root.replace(self.temp_dir, '').count(os.sep)
            indent = ' ' * 2 * level
            print(f"{indent}{os.path.basename(root)}/")
            subindent = ' ' * 2 * (level + 1)
            for file in files:
                print(f"{subindent}{file}")

        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)


def main():
    """Run the vault organization demonstration."""
    print("🎭 Starting Vault-Based Organization Demonstration")
    print("This demo showcases the complete vault organization workflow")

    try:
        demo = VaultOrganizationDemo()
        demo.run_complete_demo()

        print("\n🎉 DEMONSTRATION SUMMARY")
        print("=" * 40)
        print("✅ Vault discovery and analysis")
        print("✅ Organization plan generation")
        print("✅ Vault-list mapping creation")
        print("✅ Catch-all file management")
        print("✅ Legacy cleanup analysis")
        print("✅ Metrics and observability")
        print("\n💡 The vault organization system is ready for production use!")

    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())