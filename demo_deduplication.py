#!/usr/bin/env python3
"""
Demo script showing the task deduplication functionality.

This script demonstrates how the deduplication feature works in obs-sync,
including detection of duplicate tasks and interactive resolution.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch

# Add project root to path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from obs_sync.core.models import ObsidianTask, RemindersTask, TaskStatus, SyncConfig
from obs_sync.sync.deduplicator import TaskDeduplicator, DuplicateCluster
from obs_sync.utils.prompts import display_duplicate_cluster, format_task_for_display

def create_sample_tasks():
    """Create sample duplicate tasks for demonstration."""
    
    # Create some duplicate Obsidian tasks
    obs_tasks = [
        ObsidianTask(
            uuid="obs-1",
            vault_id="work-vault",
            vault_name="Work Vault",
            vault_path="/Users/demo/Obsidian/Work",
            file_path="daily-notes/2024-01-15.md",
            line_number=10,
            block_id=None,
            status=TaskStatus.TODO,
            description="Review quarterly budget",
            raw_line="- [ ] Review quarterly budget",
            due_date=None,
            completion_date=None,
            priority=None,
            tags=["#work", "#finance"],
            created_at=datetime(2024, 1, 15, 9, 0, tzinfo=timezone.utc),
            modified_at=datetime(2024, 1, 15, 9, 0, tzinfo=timezone.utc)
        ),
        ObsidianTask(
            uuid="obs-2",
            vault_id="work-vault", 
            vault_name="Work Vault",
            vault_path="/Users/demo/Obsidian/Work",
            file_path="projects/finance.md",
            line_number=5,
            block_id=None,
            status=TaskStatus.TODO,
            description="Review quarterly budget",  # Duplicate
            raw_line="- [ ] Review quarterly budget #important",
            due_date=None,
            completion_date=None,
            priority=None,
            tags=["#important"],
            created_at=datetime(2024, 1, 16, 14, 30, tzinfo=timezone.utc),
            modified_at=datetime(2024, 1, 16, 14, 30, tzinfo=timezone.utc)
        ),
        ObsidianTask(
            uuid="obs-3",
            vault_id="work-vault",
            vault_name="Work Vault", 
            vault_path="/Users/demo/Obsidian/Work",
            file_path="inbox.md",
            line_number=3,
            block_id=None,
            status=TaskStatus.TODO,
            description="Call dentist for appointment",  # Unique
            raw_line="- [ ] Call dentist for appointment",
            due_date=None,
            completion_date=None,
            priority=None,
            tags=[],
            created_at=datetime(2024, 1, 17, 11, 15, tzinfo=timezone.utc),
            modified_at=datetime(2024, 1, 17, 11, 15, tzinfo=timezone.utc)
        )
    ]
    
    # Create some Reminders tasks, including cross-system duplicates
    rem_tasks = [
        RemindersTask(
            uuid="rem-1",
            item_id="apple-item-1",
            calendar_id="work-calendar",
            list_name="Work Tasks",
            status=TaskStatus.TODO,
            title="Review quarterly budget",  # Cross-system duplicate
            due_date=None,
            priority=None,
            notes="Synced from Obsidian",
            tags=["work", "finance"],
            created_at=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            modified_at=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        ),
        RemindersTask(
            uuid="rem-2",
            item_id="apple-item-2",
            calendar_id="personal-calendar",
            list_name="Personal",
            status=TaskStatus.TODO,
            title="Buy groceries",  # Unique
            due_date=None,
            priority=None,
            notes=None,
            tags=[],
            created_at=datetime(2024, 1, 18, 8, 0, tzinfo=timezone.utc),
            modified_at=datetime(2024, 1, 18, 8, 0, tzinfo=timezone.utc)
        ),
        RemindersTask(
            uuid="rem-3",
            item_id="apple-item-3",
            calendar_id="personal-calendar", 
            list_name="Personal",
            status=TaskStatus.DONE,
            title="Pick up dry cleaning",  # Unique, completed
            due_date=None,
            priority=None,
            notes=None,
            tags=[],
            created_at=datetime(2024, 1, 16, 16, 0, tzinfo=timezone.utc),
            modified_at=datetime(2024, 1, 19, 12, 0, tzinfo=timezone.utc)
        )
    ]
    
    return obs_tasks, rem_tasks

def demo_duplicate_analysis():
    """Demonstrate duplicate detection and analysis."""
    print("🔍 Task Deduplication Demo")
    print("=" * 50)
    
    # Create sample tasks
    obs_tasks, rem_tasks = create_sample_tasks()
    
    print(f"\n📋 Sample Data:")
    print(f"  • {len(obs_tasks)} Obsidian tasks")
    print(f"  • {len(rem_tasks)} Reminders tasks")
    print(f"  • {len(obs_tasks) + len(rem_tasks)} total tasks")
    
    # Analyze for duplicates
    deduplicator = TaskDeduplicator()
    results = deduplicator.analyze_duplicates(obs_tasks, rem_tasks)
    
    print(f"\n🔍 Analysis Results:")
    print(f"  • Found {results.duplicate_clusters} duplicate cluster(s)")
    print(f"  • Affecting {results.duplicate_tasks} task(s)")
    print(f"  • {results.total_tasks - results.duplicate_tasks} unique tasks")
    
    # Show duplicate clusters
    duplicate_clusters = results.get_duplicate_clusters()
    
    for i, cluster in enumerate(duplicate_clusters, 1):
        print(f"\n{'='*60}")
        print(f"Duplicate Cluster {i}: \"{cluster.description}\"")
        print(f"Found {cluster.total_count} identical tasks:")
        
        all_tasks = cluster.get_all_tasks()
        for j, task in enumerate(all_tasks, 1):
            print(format_task_for_display(task, j))

def demo_interactive_resolution():
    """Demonstrate interactive resolution (simulated)."""
    print(f"\n\n🛠️  Interactive Resolution Demo")
    print("=" * 50)
    
    # Simulate user choices
    print(f"\nIn a real scenario, users would be prompted to:")
    print(f"  1. Choose which tasks to keep from each duplicate cluster")
    print(f"  2. Delete the remaining duplicates")
    print(f"  3. See a summary of changes made")
    
    print(f"\nExample interaction:")
    print(f"  ❓ Which tasks would you like to keep? (1-3)")
    print(f"     • Enter '1,3' to keep tasks 1 and 3")
    print(f"     • Enter 'skip' to keep all tasks") 
    print(f"     • Enter 'none' to delete all tasks")
    print(f"  👤 User input: 1,2")
    print(f"  ✅ Kept 2 tasks, deleted 1 task")

def demo_cli_integration():
    """Show how deduplication integrates with CLI."""
    print(f"\n\n🔧 CLI Integration")
    print("=" * 50)
    
    print(f"\nDuring sync operations:")
    print(f"  obs-sync sync --apply")
    print(f"  └── Performs regular sync operations")
    print(f"  └── Runs deduplication analysis") 
    print(f"  └── Prompts user for interactive resolution")
    print(f"  └── Shows combined summary")
    
    print(f"\nCLI Options:")
    print(f"  --no-dedup          Disable deduplication for this run")
    print(f"  --dedup-auto-apply  Skip prompts and auto-resolve")
    
    print(f"\nConfiguration (SyncConfig):")
    print(f"  enable_deduplication: true   # Enable by default")
    print(f"  dedup_auto_apply: false      # Require user confirmation")

def demo_dry_run_vs_apply():
    """Show difference between dry run and apply modes."""
    print(f"\n\n🏃 Dry Run vs Apply Mode")
    print("=" * 50)
    
    print(f"\nDry Run (obs-sync sync):")
    print(f"  🔍 Deduplication Analysis:")
    print(f"    Found 1 duplicate cluster(s)")
    print(f"    Affecting 3 task(s)")
    print(f"    Would interactively resolve 2 duplicate(s)")
    print(f"  📝 This was a dry run. Use --apply to make changes.")
    
    print(f"\nApply Mode (obs-sync sync --apply):")
    print(f"  🔍 Deduplication Analysis:")
    print(f"    Found 1 duplicate cluster(s)")
    print(f"  ❓ Run task deduplication? (y/n) [default: n]: y")
    print(f"  [Interactive resolution...]")
    print(f"  ✅ Deduplication complete:")
    print(f"    • Deleted 1 Obsidian task(s)")
    print(f"    • Deleted 1 Reminders task(s)")

if __name__ == "__main__":
    try:
        demo_duplicate_analysis()
        demo_interactive_resolution()
        demo_cli_integration()
        demo_dry_run_vs_apply()
        
        print(f"\n\n🎉 Demo Complete!")
        print(f"\nThe deduplication feature provides:")
        print(f"  • Automatic duplicate detection across both systems")
        print(f"  • Interactive resolution with user choice")
        print(f"  • Integration with existing sync workflow")
        print(f"  • Read-only analysis in dry run mode")
        print(f"  • Configurable behavior via CLI and config")
        
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)