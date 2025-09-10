#!/usr/bin/env python3
"""
Duplication Finder Tool

Identifies and removes duplicate tasks in Obsidian and Apple Reminders.
Works by:
1. Finding all duplicates within each system (based on description similarity)
2. Checking which duplicates are synced vs unsynced
3. Providing interactive confirmation for removal
4. Leaving only one version of each duplicate group

Used by the TUI as a separate menu option.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Dict, List, Set, Tuple, Optional


def load_json_file(path: str) -> Dict:
    """Load a JSON file, return empty dict if file doesn't exist."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def normalize_description(desc: str) -> str:
    """Normalize task description for comparison."""
    if not desc:
        return ""
    # Remove extra whitespace, convert to lowercase
    normalized = re.sub(r'\s+', ' ', desc.strip().lower())
    # Remove common task prefixes/suffixes
    normalized = re.sub(r'^(todo|task|do):\s*', '', normalized)
    normalized = re.sub(r'\s*\(duplicate\)$', '', normalized)
    return normalized


def calculate_similarity(desc1: str, desc2: str) -> float:
    """Calculate similarity between two task descriptions."""
    norm1 = normalize_description(desc1)
    norm2 = normalize_description(desc2)
    
    if not norm1 or not norm2:
        return 0.0
    
    return SequenceMatcher(None, norm1, norm2).ratio()


def find_duplicate_groups(tasks: Dict[str, Dict], similarity_threshold: float = 0.85) -> List[List[str]]:
    """
    Find groups of duplicate tasks based on description similarity.
    Uses optimized approach with preprocessing for better performance.
    Returns list of groups, where each group is a list of task UUIDs.
    """
    task_list = [(uuid, task) for uuid, task in tasks.items() 
                 if not task.get('deleted', False) and task.get('description')]
    
    print(f"Processing {len(task_list)} tasks for duplicates...")
    
    # Pre-normalize all descriptions for faster comparison
    normalized_tasks = []
    for uuid, task in task_list:
        normalized = normalize_description(task.get('description', ''))
        if normalized:  # Skip empty descriptions
            normalized_tasks.append((uuid, task, normalized))
    
    # Group by exact normalized matches first (most common duplicates)
    exact_groups = {}
    for uuid, task, normalized in normalized_tasks:
        if normalized not in exact_groups:
            exact_groups[normalized] = []
        exact_groups[normalized].append(uuid)
    
    groups = []
    used_uuids = set()
    
    # Add exact match groups
    for normalized, uuid_list in exact_groups.items():
        if len(uuid_list) > 1:
            groups.append(uuid_list)
            used_uuids.update(uuid_list)
    
    # Only do fuzzy matching on remaining tasks if threshold < 1.0
    if similarity_threshold < 1.0:
        remaining_tasks = [(uuid, task, norm) for uuid, task, norm in normalized_tasks 
                          if uuid not in used_uuids]
        
        # Limit fuzzy matching to reasonable number for performance
        if len(remaining_tasks) > 1000:
            print(f"Warning: {len(remaining_tasks)} tasks remaining for fuzzy matching.")
            print("This may take a while. Consider using higher similarity threshold.")
        
        for i, (uuid1, task1, norm1) in enumerate(remaining_tasks):
            if uuid1 in used_uuids:
                continue
                
            group = [uuid1]
            used_uuids.add(uuid1)
            
            # Only check a reasonable subset for fuzzy matching
            max_comparisons = min(500, len(remaining_tasks) - i - 1)
            for j, (uuid2, task2, norm2) in enumerate(remaining_tasks[i+1:i+1+max_comparisons]):
                if uuid2 in used_uuids:
                    continue
                    
                similarity = SequenceMatcher(None, norm1, norm2).ratio()
                
                if similarity >= similarity_threshold:
                    group.append(uuid2)
                    used_uuids.add(uuid2)
            
            if len(group) > 1:
                groups.append(group)
    
    return groups


def get_sync_status(obs_groups: List[List[str]], rem_groups: List[List[str]], 
                   links: List[Dict]) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Determine sync status for duplicate groups.
    Returns (obs_uuid_to_rem_uuid, rem_uuid_to_obs_uuid) mappings.
    """
    obs_to_rem = {}
    rem_to_obs = {}
    
    for link in links:
        obs_uuid = link.get('obs_uuid')
        rem_uuid = link.get('rem_uuid')
        if obs_uuid and rem_uuid:
            obs_to_rem[obs_uuid] = rem_uuid
            rem_to_obs[rem_uuid] = obs_uuid
    
    return obs_to_rem, rem_to_obs


def format_task_summary(task: Dict, system: str) -> str:
    """Format a task for display in confirmation prompts."""
    desc = task.get('description', 'No description')[:60]
    status = task.get('status', 'unknown')
    due = task.get('due', '')
    
    if system == 'obs':
        file_info = task.get('file', {})
        vault = file_info.get('vault_name', 'Unknown')
        path = file_info.get('relative_path', 'Unknown')
        location = f"{vault}:{path}"
    else:
        location = task.get('list_name', 'Unknown list')
    
    parts = [f"[{status}]", desc]
    if due:
        parts.append(f"due:{due}")
    parts.append(f"in:{location}")
    
    return " | ".join(parts)


class DuplicationFinder:
    """Main duplication finder class."""
    
    def __init__(self, obs_index_path: str, rem_index_path: str, links_path: str):
        self.obs_index_path = obs_index_path
        self.rem_index_path = rem_index_path
        self.links_path = links_path
        
        # Load data
        self.obs_data = load_json_file(obs_index_path)
        self.rem_data = load_json_file(rem_index_path)
        self.links_data = load_json_file(links_path)
        
        self.obs_tasks = self.obs_data.get('tasks', {})
        self.rem_tasks = self.rem_data.get('tasks', {})
        self.links = self.links_data.get('links', [])
        
        # Track what we've removed
        self.removed_obs = []
        self.removed_rem = []
        
    def find_duplicates(self, similarity_threshold: float = 0.85) -> Tuple[List[List[str]], List[List[str]]]:
        """Find duplicate groups in both systems."""
        obs_groups = find_duplicate_groups(self.obs_tasks, similarity_threshold)
        rem_groups = find_duplicate_groups(self.rem_tasks, similarity_threshold)
        
        print(f"\nFound {len(obs_groups)} Obsidian duplicate groups")
        print(f"Found {len(rem_groups)} Reminders duplicate groups")
        
        return obs_groups, rem_groups
    
    def resolve_duplicates_interactive(self, obs_groups: List[List[str]], 
                                     rem_groups: List[List[str]], 
                                     batch_mode: bool = False,
                                     dry_run: bool = False,
                                     auto_remove_unsynced: bool = False,
                                     physical_remove: bool = False) -> bool:
        """Interactively resolve duplicates with user confirmation."""
        obs_to_rem, rem_to_obs = get_sync_status(obs_groups, rem_groups, self.links)
        
        total_processed = 0
        
        # If dry run, just show summary
        if dry_run:
            obs_synced = sum(1 for group in obs_groups 
                           for uuid in group if uuid in obs_to_rem)
            obs_unsynced = sum(len(group) for group in obs_groups) - obs_synced
            
            rem_synced = sum(1 for group in rem_groups 
                           for uuid in group if uuid in rem_to_obs)
            rem_unsynced = sum(len(group) for group in rem_groups) - rem_synced
            
            print("\nDUPLICATE SUMMARY:")
            print(f"Obsidian: {len(obs_groups)} groups, {obs_synced} synced, {obs_unsynced} unsynced")
            print(f"Reminders: {len(rem_groups)} groups, {rem_synced} synced, {rem_unsynced} unsynced")
            return False
        
        # Process Obsidian duplicates
        for i, group in enumerate(obs_groups, 1):
            print(f"\n{'='*60}")
            print(f"Obsidian Duplicate Group {i}/{len(obs_groups)}")
            print(f"{'='*60}")
            
            # Show all tasks in group
            synced_tasks = []
            unsynced_tasks = []
            
            for uuid in group:
                task = self.obs_tasks.get(uuid, {})
                if uuid in obs_to_rem:
                    synced_tasks.append((uuid, task, obs_to_rem[uuid]))
                else:
                    unsynced_tasks.append((uuid, task))
            
            print(f"\nSynced tasks ({len(synced_tasks)}):")
            for j, (uuid, task, rem_uuid) in enumerate(synced_tasks, 1):
                print(f"  {j}. {format_task_summary(task, 'obs')} [UUID:{uuid[:8]}...] -> REM:{rem_uuid[:8]}...")
            
            print(f"\nUnsynced tasks ({len(unsynced_tasks)}):")
            for j, (uuid, task) in enumerate(unsynced_tasks, 1):
                print(f"  {j}. {format_task_summary(task, 'obs')} [UUID:{uuid[:8]}...]")
            
            # Decide what to keep
            if len(synced_tasks) > 1:
                if batch_mode:
                    # In batch mode, keep the first synced task
                    keep_uuid = synced_tasks[0][0]
                    for uuid, _, _ in synced_tasks[1:]:
                        self._mark_task_for_removal('obs', uuid, physical_remove)
                        total_processed += 1
                else:
                    choice = input(f"\nMultiple synced tasks found. Keep which one? (1-{len(synced_tasks)}, or 'skip'): ").strip()
                    if choice.lower() == 'skip':
                        continue
                    try:
                        keep_idx = int(choice) - 1
                        if 0 <= keep_idx < len(synced_tasks):
                            keep_uuid = synced_tasks[keep_idx][0]
                            # Remove other synced tasks
                            for uuid, _, _ in synced_tasks:
                                if uuid != keep_uuid:
                                    self._mark_task_for_removal('obs', uuid, physical_remove)
                                    total_processed += 1
                        else:
                            print("Invalid choice, skipping group")
                            continue
                    except ValueError:
                        print("Invalid choice, skipping group")
                        continue
            elif len(synced_tasks) == 1:
                keep_uuid = synced_tasks[0][0]
            else:
                # No synced tasks, handle unsynced
                if len(unsynced_tasks) > 1:
                    if batch_mode and not auto_remove_unsynced:
                        # In batch mode, skip unsynced duplicates unless auto-remove is enabled
                        print("  Skipping unsynced duplicates in batch mode")
                        continue
                    elif auto_remove_unsynced or batch_mode:
                        # Auto-remove unsynced duplicates, keep the first one
                        keep_uuid = unsynced_tasks[0][0]
                        print(f"  Auto-keeping first unsynced task: {unsynced_tasks[0][0][:8]}...")
                    else:
                        choice = input(f"\nNo synced tasks. Keep which unsynced task? (1-{len(unsynced_tasks)}, or 'skip'): ").strip()
                        if choice.lower() == 'skip':
                            continue
                        try:
                            keep_idx = int(choice) - 1
                            if 0 <= keep_idx < len(unsynced_tasks):
                                keep_uuid = unsynced_tasks[keep_idx][0]
                            else:
                                print("Invalid choice, skipping group")
                                continue
                        except ValueError:
                            print("Invalid choice, skipping group")
                            continue
                else:
                    continue  # Only one task, nothing to do
            
            # Remove all unsynced tasks except the kept one (if any)
            for uuid, _ in unsynced_tasks:
                if 'keep_uuid' in locals() and uuid != keep_uuid:
                    self._mark_task_for_removal('obs', uuid, physical_remove)
                    total_processed += 1
        
        # Process Reminders duplicates
        for i, group in enumerate(rem_groups, 1):
            print(f"\n{'='*60}")
            print(f"Reminders Duplicate Group {i}/{len(rem_groups)}")
            print(f"{'='*60}")
            
            # Show all tasks in group
            synced_tasks = []
            unsynced_tasks = []
            
            for uuid in group:
                task = self.rem_tasks.get(uuid, {})
                if uuid in rem_to_obs:
                    synced_tasks.append((uuid, task, rem_to_obs[uuid]))
                else:
                    unsynced_tasks.append((uuid, task))
            
            print(f"\nSynced tasks ({len(synced_tasks)}):")
            for j, (uuid, task, obs_uuid) in enumerate(synced_tasks, 1):
                print(f"  {j}. {format_task_summary(task, 'rem')} [UUID:{uuid[:8]}...] -> OBS:{obs_uuid[:8]}...")
            
            print(f"\nUnsynced tasks ({len(unsynced_tasks)}):")
            for j, (uuid, task) in enumerate(unsynced_tasks, 1):
                print(f"  {j}. {format_task_summary(task, 'rem')} [UUID:{uuid[:8]}...]")
            
            # Decide what to keep (similar logic as Obsidian)
            if len(synced_tasks) > 1:
                if batch_mode:
                    keep_uuid = synced_tasks[0][0]
                    for uuid, _, _ in synced_tasks[1:]:
                        self._mark_task_for_removal('rem', uuid, physical_remove)
                        total_processed += 1
                else:
                    choice = input(f"\nMultiple synced tasks found. Keep which one? (1-{len(synced_tasks)}, or 'skip'): ").strip()
                    if choice.lower() == 'skip':
                        continue
                    try:
                        keep_idx = int(choice) - 1
                        if 0 <= keep_idx < len(synced_tasks):
                            keep_uuid = synced_tasks[keep_idx][0]
                            for uuid, _, _ in synced_tasks:
                                if uuid != keep_uuid:
                                    self._mark_task_for_removal('rem', uuid, physical_remove)
                                    total_processed += 1
                        else:
                            print("Invalid choice, skipping group")
                            continue
                    except ValueError:
                        print("Invalid choice, skipping group")
                        continue
            elif len(synced_tasks) == 1:
                keep_uuid = synced_tasks[0][0]
            else:
                if len(unsynced_tasks) > 1:
                    if batch_mode and not auto_remove_unsynced:
                        print("  Skipping unsynced duplicates in batch mode")
                        continue
                    elif auto_remove_unsynced or batch_mode:
                        keep_uuid = unsynced_tasks[0][0]
                        print(f"  Auto-keeping first unsynced task: {unsynced_tasks[0][0][:8]}...")
                    else:
                        choice = input(f"\nNo synced tasks. Keep which unsynced task? (1-{len(unsynced_tasks)}, or 'skip'): ").strip()
                        if choice.lower() == 'skip':
                            continue
                        try:
                            keep_idx = int(choice) - 1
                            if 0 <= keep_idx < len(unsynced_tasks):
                                keep_uuid = unsynced_tasks[keep_idx][0]
                            else:
                                print("Invalid choice, skipping group")
                                continue
                        except ValueError:
                            print("Invalid choice, skipping group")
                            continue
                else:
                    continue
            
            # Remove unsynced tasks except the kept one
            for uuid, _ in unsynced_tasks:
                if 'keep_uuid' in locals() and uuid != keep_uuid:
                    self._mark_task_for_removal('rem', uuid, physical_remove)
                    total_processed += 1
        
        print(f"\nProcessed {total_processed} duplicate tasks total")
        print(f"Marked {len(self.removed_obs)} Obsidian tasks for removal")
        print(f"Marked {len(self.removed_rem)} Reminders tasks for removal")
        
        if total_processed > 0:
            if auto_remove_unsynced and batch_mode:  # Auto-confirm in batch mode with auto-remove
                print(f"\nAuto-confirming removal of {total_processed} duplicate tasks in batch mode")
                return True
            else:
                confirm = input(f"\nConfirm removal of {total_processed} duplicate tasks? (yes/no): ").strip().lower()
                if confirm in ('yes', 'y'):
                    return True
        
        return False
    
    def _mark_task_for_removal(self, system: str, uuid: str, physical_remove: bool = False):
        """Mark a task for removal by setting deleted flag (unless physical removal)."""
        if system == 'obs':
            if uuid in self.obs_tasks:
                if not physical_remove:
                    # Only mark as deleted in index if not doing physical removal
                    self.obs_tasks[uuid]['deleted'] = True
                    self.obs_tasks[uuid]['deleted_at'] = datetime.now().isoformat()
                self.removed_obs.append(uuid)
        else:
            if uuid in self.rem_tasks:
                if not physical_remove:
                    # Only mark as deleted in index if not doing physical removal
                    self.rem_tasks[uuid]['deleted'] = True
                    self.rem_tasks[uuid]['deleted_at'] = datetime.now().isoformat()  
                self.removed_rem.append(uuid)
    
    def apply_removals(self) -> bool:
        """Apply the removals by updating the index files."""
        try:
            # Update Obsidian index
            if self.removed_obs:
                with open(self.obs_index_path, 'w', encoding='utf-8') as f:
                    json.dump(self.obs_data, f, indent=2, ensure_ascii=False)
                print(f"Updated {self.obs_index_path}")
            
            # Update Reminders index  
            if self.removed_rem:
                with open(self.rem_index_path, 'w', encoding='utf-8') as f:
                    json.dump(self.rem_data, f, indent=2, ensure_ascii=False)
                print(f"Updated {self.rem_index_path}")
            
            return True
            
        except Exception as e:
            print(f"Error applying removals: {e}")
            return False


def main(argv: list[str] = None) -> int:
    # Use centralized path configuration
    try:
        from app_config import get_path
        default_obs = get_path("obsidian_index")
        default_rem = get_path("reminders_index")
        default_links = get_path("links")
    except ImportError:
        # Fallback for standalone execution
        default_obs = os.path.expanduser('~/.config/obsidian_tasks_index.json')
        default_rem = os.path.expanduser('~/.config/reminders_tasks_index.json')
        default_links = os.path.expanduser('~/.config/sync_links.json')
    
    parser = argparse.ArgumentParser(description="Find and remove duplicate tasks")
    parser.add_argument('--obs', default=default_obs)
    parser.add_argument('--rem', default=default_rem)
    parser.add_argument('--links', default=default_links)
    parser.add_argument('--similarity', type=float, default=0.85, help='Similarity threshold (0.0-1.0)')
    parser.add_argument('--dry-run', action='store_true', help='Show duplicates without removing')
    parser.add_argument('--batch', action='store_true', help='Batch mode - skip all unsynced duplicates automatically')
    parser.add_argument('--auto-remove-unsynced', action='store_true', help='Automatically remove unsynced duplicates (keeps first one)')
    parser.add_argument('--yes', action='store_true', help='Auto-confirm removal without prompting')
    parser.add_argument('--physical-remove', action='store_true', help='Actually remove duplicates from source files (not just mark as deleted in index)')
    
    args = parser.parse_args(argv)
    
    finder = DuplicationFinder(args.obs, args.rem, args.links)
    
    print("Duplication Finder")
    print("==================")
    print(f"Obsidian tasks: {len(finder.obs_tasks)}")
    print(f"Reminders tasks: {len(finder.rem_tasks)}")
    print(f"Sync links: {len(finder.links)}")
    
    obs_groups, rem_groups = finder.find_duplicates(args.similarity)
    
    if not obs_groups and not rem_groups:
        print("\nNo duplicates found!")
        return 0
    
    if args.dry_run:
        print("\nDRY RUN - showing duplicates only, not removing")
        finder.resolve_duplicates_interactive(obs_groups, rem_groups, args.batch, dry_run=True, auto_remove_unsynced=args.auto_remove_unsynced, physical_remove=args.physical_remove)
        return 0
    
    if finder.resolve_duplicates_interactive(obs_groups, rem_groups, args.batch, auto_remove_unsynced=args.auto_remove_unsynced, physical_remove=args.physical_remove):
        if args.physical_remove:
            # Use task operations to physically remove from source files
            from task_operations import TaskOperations
            operations = TaskOperations(dry_run=False, verbose=True)
            
            print(f"\nPhysically removing {len(finder.removed_obs)} Obsidian and {len(finder.removed_rem)} Reminders duplicates...")
            obs_removed, rem_removed = operations.delete_task_list(finder.removed_obs, finder.removed_rem, finder.obs_tasks, finder.rem_tasks)
            
            try:
                from app_config import get_path
                changeset_path = get_path("duplicate_removal_backup")
            except ImportError:
                changeset_path = os.path.expanduser('~/.config/obs-tools/backups/duplicate_removal.json')
            operations.save_changeset(changeset_path)
            
            print(f"\nPhysical removal complete!")
            print(f"  Obsidian tasks removed from files: {obs_removed}")
            print(f"  Reminders tasks removed from app: {rem_removed}")
            print(f"  Changeset saved to: {changeset_path}")
            return 0
        else:
            # Use original index-only approach
            if finder.apply_removals():
                print("\nDuplicates marked as deleted in indexes!")
                print("Note: Use --physical-remove to actually remove from source files.")
                return 0
            else:
                print("\nError applying changes!")
                return 1
    else:
        print("\nNo changes made.")
        return 0


if __name__ == '__main__':
    import sys
    raise SystemExit(main(sys.argv[1:]))