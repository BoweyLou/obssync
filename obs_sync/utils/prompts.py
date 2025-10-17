"""Interactive prompting utilities for obs-sync CLI."""

import builtins
import sys
from typing import List, Optional, Set, Union, Dict
from datetime import datetime

from ..core.models import ObsidianTask, RemindersTask, TaskStatus


def is_interactive() -> bool:
    """Return True when prompts can safely read from stdin."""
    # If input() has been monkeypatched (e.g. during tests), assume interactivity.
    if input is not builtins.input:  # type: ignore[name-defined]
        return True

    stdin = getattr(sys, "stdin", None)
    if stdin is None:
        return False

    try:
        return stdin.isatty()
    except Exception:
        return False


def _format_date_safe(date_value):
    """
    Safely format a date value that could be a datetime object or string.
    
    Args:
        date_value: datetime object, ISO string, or None
        
    Returns:
        Formatted date string or "unknown"
    """
    if not date_value:
        return "unknown"
    
    # If it's already a string, try to parse it first
    if isinstance(date_value, str):
        try:
            from datetime import datetime
            # Try parsing ISO format string
            if 'T' in date_value:
                parsed = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
            else:
                # Try parsing just the date part
                parsed = datetime.fromisoformat(date_value)
            return parsed.strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            # If parsing fails, return the string as-is if it looks like a date
            if len(str(date_value)) >= 10:
                return str(date_value)[:10]  # Take first 10 chars (YYYY-MM-DD)
            return str(date_value)
    
    # If it's a datetime object, format it
    if hasattr(date_value, 'strftime'):
        try:
            return date_value.strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            return str(date_value)
    
    # Fallback
    return str(date_value) if date_value else "unknown"


def format_task_for_display(task: Union[ObsidianTask, RemindersTask], 
                          index: int) -> str:
    """
    Format a task for display in interactive prompts.
    
    Args:
        task: Task to format
        index: Display index (1-based)
        
    Returns:
        Formatted task string
    """
    if isinstance(task, ObsidianTask):
        status_symbol = "✅" if task.status == TaskStatus.DONE else "⭕"
        location = f"{task.vault_name}:{task.file_path}:{task.line_number}"
        created = _format_date_safe(task.created_at)
        return f"  • #{index} [Obsidian] {status_symbol} {task.description}\n     📍 {location} | 📅 {created}"
    
    if isinstance(task, RemindersTask):
        status_symbol = "✅" if task.status == TaskStatus.DONE else "⭕" 
        location = task.list_name or "Unknown List"
        created = _format_date_safe(task.created_at)
        return f"  • #{index} [Reminders] {status_symbol} {task.title}\n     📍 {location} | 📅 {created}"
    
    return f"  • #{index} [Unknown] {task}"


def display_duplicate_cluster(cluster, obs_tasks_map=None, rem_tasks_map=None) -> None:
    """
    Display a duplicate cluster for user review.
    
    Args:
        cluster: The duplicate cluster to display
        obs_tasks_map: Optional dict mapping Obsidian UUIDs to tasks
        rem_tasks_map: Optional dict mapping Reminders UUIDs to tasks
    """
    print(f"\n🔍 Duplicate tasks detected for '{cluster.description}'.")
    print(f"   Found {cluster.total_count} related tasks:")
    
    all_tasks = cluster.get_all_tasks()
    for i, task in enumerate(all_tasks, 1):
        print(format_task_for_display(task, i))
        
        # Show linked counterpart if available
        if cluster.linked_counterparts and obs_tasks_map and rem_tasks_map:
            linked_uuid = cluster.linked_counterparts.get(task.uuid)
            if linked_uuid:
                # Determine if current task is Obsidian or Reminders
                if hasattr(task, 'vault_path'):  # Obsidian task
                    # Look for linked Reminders task
                    if linked_uuid in rem_tasks_map:
                        linked_task = rem_tasks_map[linked_uuid]
                        print(f"     └─ Synced with → [Reminders] {linked_task.title} ({linked_task.list_name})")
                else:  # Reminders task
                    # Look for linked Obsidian task
                    if linked_uuid in obs_tasks_map:
                        linked_task = obs_tasks_map[linked_uuid]
                        print(f"     └─ Synced with → [Obsidian] {linked_task.description} ({linked_task.vault_name}:{linked_task.file_path})")


def prompt_for_keeps(cluster) -> Optional[List[int]]:
    """
    Prompt user to select which tasks to keep from a duplicate cluster.

    Args:
        cluster: The duplicate cluster

    Returns:
        List of 0-based indices to keep, or None to skip
    """
    if not is_interactive():
        print("   ℹ️ Non-interactive environment detected—skipping duplicate review.")
        return None

    all_tasks = cluster.get_all_tasks()
    max_index = len(all_tasks)
    
    print(f"\n❓ Which tasks should stay? (1-{max_index})")
    print("   Options:")
    print("   • Enter numbers separated by commas (example: 1,3)")
    print("   • Type 'all' to keep everything")
    print("   • Type 'none' to delete all tasks in the cluster")
    print("   • Press Enter or type 'skip' to move to the next cluster")
    
    while True:
        try:
            response = input("   Tasks to keep: ").strip().lower()
            
            if not response or response == 'skip':
                return None
            
            if response in ['all', 'skip']:
                return None
                
            if response in ['none', 'n']:
                return []
            
            # Parse comma-separated indices
            indices = []
            for part in response.split(','):
                part = part.strip()
                if part.isdigit():
                    idx = int(part)
                    if 1 <= idx <= max_index:
                        indices.append(idx - 1)  # Convert to 0-based
                    else:
                        print(f"   ⚠️ {idx} is outside 1-{max_index}.")
                        raise ValueError()
                else:
                    print(f"   ⚠️ '{part}' isn’t numeric—enter digits only.")
                    raise ValueError()
            
            if not indices:
                print("   ⚠️ Enter at least one valid number.")
                continue
                
            # Remove duplicates and sort
            indices = sorted(set(indices))
            return indices
            
        except (ValueError, KeyboardInterrupt):
            if not response:  # Empty input means skip
                return None
            print("   Try again using one of the options above.")


def confirm_deduplication() -> bool:
    """
    Ask user if they want to proceed with deduplication.

    Returns:
        True if user wants to proceed, False otherwise
    """
    if not is_interactive():
        print("\nℹ️ Skipping interactive deduplication prompts (no TTY detected).")
        return False

    response = input("\n❓ Run task deduplication? This interactive step lets you remove duplicates across Obsidian and Reminders (y/N): ").strip().lower()
    return response in ['y', 'yes']


def show_deduplication_summary(clusters: List,
                              deletion_stats: dict) -> None:
    """
    Show summary of deduplication results.
    
    Args:
        clusters: List of duplicate clusters processed
        deletion_stats: Dict with deletion counts
    """
    if not clusters:
        return
        
    total_deleted = deletion_stats.get("obs_deleted", 0) + deletion_stats.get("rem_deleted", 0)
    
    if total_deleted > 0:
        print("\n✅ Deduplication complete:")
        if deletion_stats.get("obs_deleted", 0):
            print(f"   • Deleted {deletion_stats['obs_deleted']} Obsidian tasks.")
        if deletion_stats.get("rem_deleted", 0):
            print(f"   • Deleted {deletion_stats['rem_deleted']} Reminders tasks.")
        print(f"   • Processed {len(clusters)} duplicate clusters.")
    else:
        print("\n📝 Deduplication skipped or no changes were needed.")
        print(f"   • Found {len(clusters)} duplicate clusters.")
