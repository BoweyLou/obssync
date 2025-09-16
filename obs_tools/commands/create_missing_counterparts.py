#!/usr/bin/env python3
"""
Create Missing Counterparts - Add tasks to the opposite system for unlinked items.

This command identifies tasks that exist in one system (Obsidian or Reminders) but 
have no corresponding counterpart in the other system, then creates the missing 
counterparts with proper field mapping.

Inputs:
  - obsidian_tasks_index.json (schema v2)
  - reminders_tasks_index.json (schema v2) 
  - sync_links.json (existing links to avoid duplicates)

Output:
  - Updated sync_links.json with new links
  - Newly created tasks in target systems
  - Changeset tracking for rollback capability

Modes:
  - dry-run (default): Show what would be created, no changes
  - --apply: Actually create the missing counterparts
  - Direction control: --both, --obs-to-rem, --rem-to-obs

Filters:
  - --include-done: Include completed tasks (default: false)
  - --since DAYS: Only process tasks created/modified within N days
  - --max N: Limit number of creations per run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set, Tuple, Any, Union
from dataclasses import dataclass, asdict

# Add the project root to the path for imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from lib.safe_io import safe_write_json_with_lock, safe_load_json
from lib.backup_system import BackupManager
from lib.date_utils import normalize_date_string, dates_equal, now_iso, get_today_string, days_ago
from lib.observability import get_logger
import app_config
from app_config import get_path


@dataclass
class CreationPlan:
    """Plan for creating missing counterparts."""
    obs_to_rem: List[Dict] = None
    rem_to_obs: List[Dict] = None
    total_creates: int = 0
    direction: str = "both"
    filters_applied: Dict = None
    
    def __post_init__(self):
        if self.obs_to_rem is None:
            self.obs_to_rem = []
        if self.rem_to_obs is None:
            self.rem_to_obs = []
        if self.filters_applied is None:
            self.filters_applied = {}
        self.total_creates = len(self.obs_to_rem) + len(self.rem_to_obs)


@dataclass
class CreationResult:
    """Result of counterpart creation operation."""
    success: bool
    plan: CreationPlan
    created_obs: int = 0
    created_rem: int = 0
    new_links: List[Dict] = None
    errors: List[str] = None
    changeset_id: Optional[str] = None
    
    def __post_init__(self):
        if self.new_links is None:
            self.new_links = []
        if self.errors is None:
            self.errors = []


@dataclass
class CreationConfig:
    """Configuration for counterpart creation."""
    # Default targets
    obs_inbox_file: str = "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Work/Tasks.md"
    rem_default_calendar_id: Optional[str] = None
    
    # Mapping rules
    obs_to_rem_rules: List[Dict] = None  # [{"tag": "#work", "calendar_id": "XXX"}]
    rem_to_obs_rules: List[Dict] = None  # [{"list_name": "Work", "target_file": "path", "heading": "Imported"}]
    
    # Limits and filters
    max_creates_per_run: int = 50
    since_days: int = 30
    include_done: bool = False
    
    def __post_init__(self):
        if self.obs_to_rem_rules is None:
            self.obs_to_rem_rules = []
        if self.rem_to_obs_rules is None:
            self.rem_to_obs_rules = []


class MissingCounterpartsCreator:
    """Creates missing counterpart tasks between Obsidian and Reminders."""
    
    def __init__(self, config: CreationConfig = None, logger=None):
        self.config = config or CreationConfig()
        self.logger = logger or get_logger("create_missing_counterparts")
        self.backup_manager = BackupManager(get_path("backups_dir"))
    
    def load_indices_and_links(self, obs_path: str, rem_path: str, links_path: str) -> Tuple[Dict, Dict, Dict]:
        """Load task indices and existing links."""
        self.logger.info(f"Loading indices from {obs_path}, {rem_path}, {links_path}")
        
        obs_index = safe_load_json(obs_path, {"meta": {}, "tasks": {}})
        rem_index = safe_load_json(rem_path, {"meta": {}, "tasks": {}})
        links_data = safe_load_json(links_path, {"meta": {}, "links": []})
        
        self.logger.info(f"Loaded {len(obs_index.get('tasks', {}))} Obsidian tasks, "
                        f"{len(rem_index.get('tasks', {}))} Reminders tasks, "
                        f"{len(links_data.get('links', []))} existing links")
        
        return obs_index, rem_index, links_data
    
    def build_linked_sets(self, links_data: Dict) -> Tuple[Set[str], Set[str]]:
        """Build sets of already-linked task UUIDs."""
        linked_obs = set()
        linked_rem = set()
        
        for link in links_data.get("links", []):
            obs_uuid = link.get("obs_uuid")
            rem_uuid = link.get("rem_uuid")
            if obs_uuid:
                linked_obs.add(obs_uuid)
            if rem_uuid:
                linked_rem.add(rem_uuid)
        
        self.logger.info(f"Found {len(linked_obs)} linked Obsidian tasks, {len(linked_rem)} linked Reminders tasks")
        return linked_obs, linked_rem
    
    def filter_tasks(self, tasks: Dict[str, Dict], linked_uuids: Set[str], 
                    include_done: bool = False, since_days: Optional[int] = None) -> Dict[str, Dict]:
        """Filter tasks based on criteria."""
        filtered = {}
        
        for uuid, task in tasks.items():
            # Skip if already linked
            if uuid in linked_uuids:
                continue
            
            # Skip if deleted or missing
            if task.get("deleted", False) or task.get("missing_since"):
                continue
            
            # Skip completed tasks unless explicitly included
            # Handle both Obsidian (status == "done") and Reminders (is_completed == True) format
            is_completed = (task.get("status") == "done" or task.get("is_completed") == True)
            if not include_done and is_completed:
                continue
            
            # Filter by recency if specified
            if since_days is not None:
                cutoff_date = days_ago(since_days)
                task_date = task.get("updated_at") or task.get("created_at")
                if task_date and task_date[:10] < cutoff_date:
                    continue
            
            filtered[uuid] = task
        
        return filtered
    
    def map_obsidian_to_reminders_fields(self, obs_task: Dict) -> Dict:
        """Map Obsidian task fields to Reminders format."""
        mapped = {}
        
        # Title (required)
        title = obs_task.get("description", "").strip()
        if not title:
            title = "Untitled Task"
        mapped["title"] = title
        
        # Due date (date-only)
        obs_due = obs_task.get("due")
        if obs_due:
            normalized_due = normalize_date_string(obs_due)
            if normalized_due:  # Only set if normalization was successful
                mapped["due_date"] = normalized_due
        
        # Priority mapping: high/medium/low -> EventKit: 1/5/9 (1 is highest priority)
        priority_map = {"high": 1, "medium": 5, "low": 9}
        obs_priority = (obs_task.get("priority") or "").lower()
        if obs_priority in priority_map:
            mapped["priority"] = priority_map[obs_priority]
        
        # Notes with breadcrumbs
        notes_parts = []
        file_info = obs_task.get("file", {})
        if file_info.get("relative_path"):
            notes_parts.append(f"Source: {file_info['relative_path']}")
            if file_info.get("line"):
                notes_parts.append(f"Line: {file_info['line']}")
        
        # Add tags as context
        tags = obs_task.get("tags", [])
        if tags:
            notes_parts.append(f"Tags: {', '.join(tags)}")
        
        if notes_parts:
            mapped["notes"] = "\n".join(notes_parts)
        
        # URL - create obsidian:// deep-link if possible
        if file_info.get("relative_path") and obs_task.get("block_id"):
            vault_name = obs_task.get("vault", {}).get("name", "")
            if vault_name:
                block_id = obs_task["block_id"]
                mapped["url"] = f"obsidian://open?vault={vault_name}&file={file_info['relative_path']}#{block_id}"
        
        return mapped
    
    def map_reminders_to_obsidian_fields(self, rem_task: Dict) -> Dict:
        """Map Reminders task fields to Obsidian format."""
        mapped = {}
        
        # Title/description
        mapped["description"] = rem_task.get("description", "Untitled Task").strip()
        
        # Status
        mapped["status"] = "done" if rem_task.get("is_completed", False) else "todo"
        
        # Due date (date-only)
        rem_due = rem_task.get("due_date")
        if rem_due:
            normalized_due = normalize_date_string(rem_due)
            if normalized_due:  # Only set if normalization was successful
                mapped["due"] = normalized_due
        
        # Priority mapping: EventKit 1/5/9 -> high/medium/low (1 is highest priority)
        rem_priority = rem_task.get("priority") or 0
        try:
            rem_priority = int(rem_priority)
        except (ValueError, TypeError):
            rem_priority = 0
        
        if rem_priority <= 1:
            mapped["priority"] = "high"
        elif rem_priority <= 5:
            mapped["priority"] = "medium"
        elif rem_priority >= 9:
            mapped["priority"] = "low"
        
        # Tags from list name
        list_info = rem_task.get("list", {})
        list_name = list_info.get("name", "")
        if list_name and list_name != "Tasks":  # Don't tag default list
            mapped["tags"] = [f"#{list_name.lower().replace(' ', '_')}"]
        
        return mapped
    
    def determine_target_calendar(self, obs_task: Dict) -> Optional[str]:
        """Determine target Reminders calendar for an Obsidian task."""
        # Check mapping rules first
        task_tags = obs_task.get("tags", [])
        for rule in self.config.obs_to_rem_rules:
            rule_tag = rule.get("tag", "")
            if rule_tag in task_tags:
                return rule.get("calendar_id")
        
        # Use default calendar
        return self.config.rem_default_calendar_id
    
    def determine_target_file(self, rem_task: Dict) -> Tuple[str, Optional[str]]:
        """Determine target Obsidian file and heading for a Reminders task."""
        list_info = rem_task.get("list", {})
        list_name = list_info.get("name", "")
        
        # Check mapping rules first
        for rule in self.config.rem_to_obs_rules:
            if rule.get("list_name") == list_name:
                return rule.get("target_file", self.config.obs_inbox_file), rule.get("heading")
        
        # Use default inbox file
        return self.config.obs_inbox_file, None
    
    def create_plan(self, obs_index: Dict, rem_index: Dict, links_data: Dict, 
                   direction: str = "both", include_done: bool = False, 
                   since_days: Optional[int] = None, max_creates: Optional[int] = None) -> CreationPlan:
        """Create a plan for missing counterpart creation."""
        
        linked_obs, linked_rem = self.build_linked_sets(links_data)
        
        # Filter unlinked tasks
        obs_tasks = obs_index.get("tasks", {})
        rem_tasks = rem_index.get("tasks", {})
        
        unlinked_obs = self.filter_tasks(obs_tasks, linked_obs, include_done, since_days)
        unlinked_rem = self.filter_tasks(rem_tasks, linked_rem, include_done, since_days)
        
        plan = CreationPlan(direction=direction)
        plan.filters_applied = {
            "include_done": include_done,
            "since_days": since_days,
            "max_creates": max_creates
        }
        
        # Plan Obsidian -> Reminders creations
        if direction in ["both", "obs-to-rem"]:
            for uuid, obs_task in unlinked_obs.items():
                target_calendar = self.determine_target_calendar(obs_task)
                mapped_fields = self.map_obsidian_to_reminders_fields(obs_task)
                
                plan.obs_to_rem.append({
                    "obs_uuid": uuid,
                    "obs_task": obs_task,
                    "target_calendar_id": target_calendar,
                    "mapped_fields": mapped_fields
                })
        
        # Plan Reminders -> Obsidian creations
        if direction in ["both", "rem-to-obs"]:
            for uuid, rem_task in unlinked_rem.items():
                target_file, target_heading = self.determine_target_file(rem_task)
                mapped_fields = self.map_reminders_to_obsidian_fields(rem_task)
                
                plan.rem_to_obs.append({
                    "rem_uuid": uuid,
                    "rem_task": rem_task,
                    "target_file": target_file,
                    "target_heading": target_heading,
                    "mapped_fields": mapped_fields
                })
        
        # Apply max_creates limit
        if max_creates and max_creates > 0:
            total_planned = len(plan.obs_to_rem) + len(plan.rem_to_obs)
            if total_planned > max_creates:
                # Distribute limit proportionally
                obs_limit = int(max_creates * len(plan.obs_to_rem) / total_planned) if total_planned > 0 else 0
                rem_limit = max_creates - obs_limit
                
                plan.obs_to_rem = plan.obs_to_rem[:obs_limit]
                plan.rem_to_obs = plan.rem_to_obs[:rem_limit]
        
        plan.total_creates = len(plan.obs_to_rem) + len(plan.rem_to_obs)
        
        self.logger.info(f"Creation plan: {len(plan.obs_to_rem)} Obs->Rem, {len(plan.rem_to_obs)} Rem->Obs")
        return plan
    
    def execute_plan(self, plan: CreationPlan, links_path: str, run_id: str) -> CreationResult:
        """Execute the creation plan."""
        result = CreationResult(success=False, plan=plan)
        
        try:
            # Start changeset tracking
            changeset_id = self.backup_manager.start_session(f"create_missing_counterparts_{run_id}")
            result.changeset_id = changeset_id
            
            new_links = []
            
            # Execute Obsidian -> Reminders creations
            for item in plan.obs_to_rem:
                try:
                    success = self._create_reminder_counterpart(item, changeset_id)
                    if success:
                        # Create new link
                        link = self._create_link_entry(
                            obs_uuid=item["obs_uuid"],
                            rem_uuid=success["rem_uuid"],  # From creation result
                            score=1.0,  # Perfect score for created counterparts
                            obs_task=item["obs_task"],
                            rem_task=success["rem_task"]
                        )
                        new_links.append(link)
                        result.created_rem += 1
                except Exception as e:
                    self.logger.error(f"Failed to create Reminders counterpart: {str(e)}")
                    result.errors.append(f"Reminders creation failed: {str(e)}")
            
            # Execute Reminders -> Obsidian creations  
            for item in plan.rem_to_obs:
                try:
                    success = self._create_obsidian_counterpart(item, changeset_id)
                    if success:
                        # Create new link
                        link = self._create_link_entry(
                            obs_uuid=success["obs_uuid"],  # From creation result
                            rem_uuid=item["rem_uuid"],
                            score=1.0,  # Perfect score for created counterparts
                            obs_task=success["obs_task"],
                            rem_task=item["rem_task"]
                        )
                        new_links.append(link)
                        result.created_obs += 1
                except Exception as e:
                    self.logger.error(f"Failed to create Obsidian counterpart: {str(e)}")
                    result.errors.append(f"Obsidian creation failed: {str(e)}")
            
            # Update sync_links.json with new links
            if new_links:
                self._append_new_links(links_path, new_links, changeset_id)
                result.new_links = new_links
            
            # Finalize changeset
            self.backup_manager.end_session(success=True)
            result.success = True
            
            self.logger.info(f"Creation completed: {result.created_obs} Obsidian, {result.created_rem} Reminders, {len(result.errors)} errors")
            
        except Exception as e:
            self.logger.error(f"Plan execution failed: {str(e)}")
            result.errors.append(f"Execution failed: {str(e)}")
            if result.changeset_id:
                self.backup_manager.end_session(success=False, error_message=str(e))
        
        return result
    
    def _create_reminder_counterpart(self, item: Dict, changeset_id: str) -> Optional[Dict]:
        """Create a Reminders counterpart for an Obsidian task."""
        try:
            from reminders_gateway import RemindersGateway
            
            gateway = RemindersGateway(logger=self.logger)
            
            title = item['mapped_fields']['title']
            calendar_id = item.get('target_calendar_id')
            properties = {k: v for k, v in item['mapped_fields'].items() if k != 'title'}
            
            self.logger.info(f"Creating Reminders task: {title}")
            
            result = gateway.create_reminder(
                title=title,
                calendar_id=calendar_id,
                properties=properties
            )
            
            if not result:
                self.logger.error("Failed to create Reminders task")
                return None
            
            # Record the task creation
            self.backup_manager.record_task_change(
                operation="create",
                task_id=result['uuid'],
                task_system="reminders",
                original_state=None,
                new_state=result
            )
            
            self.logger.info(f"Successfully created Reminders task: {result['uuid']}")
            
            return {
                "rem_uuid": result['uuid'],
                "rem_task": {
                    "uuid": result['uuid'],
                    "description": title,
                    "calendar_id": result.get('calendar_id'),
                    "created_at": result['created_at']
                }
            }
            
        except Exception as e:
            self.logger.error(f"Exception creating Reminders task: {str(e)}")
            return None
    
    def _create_obsidian_counterpart(self, item: Dict, changeset_id: str) -> Optional[Dict]:
        """Create an Obsidian counterpart for a Reminders task."""
        try:
            from obs_tools.commands.task_operations import ObsidianOperations
            
            # Format the task text
            task_text = self._format_obsidian_task(item['mapped_fields'])
            target_file = os.path.expanduser(item['target_file'])
            
            self.logger.info(f"Creating Obsidian task: {item['mapped_fields']['description']}")
            
            # Use ObsidianOperations.create_task
            result = ObsidianOperations.create_task(target_file, task_text)
            
            if not result.success:
                self.logger.error(f"Failed to create Obsidian task: {result.message}")
                return None
            
            # Extract details for tracking
            line_number = result.details.get('line_number', 0)
            
            # Extract the actual block ID from the created task text
            task_uuid = None
            created_text = result.details.get('task_text', task_text)
            block_match = re.search(r'\^t-([a-f0-9]{12})', created_text)
            if block_match:
                task_uuid = f"t-{block_match.group(1)}"
            else:
                # Fallback: generate UUID if no block ID found
                task_uuid = str(uuid.uuid4())
            
            # Record the file change
            self.backup_manager.record_file_change(
                operation="modify",
                file_path=target_file,
                line_number=line_number + 1,
                original_content="",
                new_content=task_text,
                create_backup=True
            )
            
            self.logger.info(f"Successfully created Obsidian task at {os.path.basename(target_file)}:{line_number+1}")
            
            return {
                "obs_uuid": task_uuid,
                "obs_task": {
                    "uuid": task_uuid,
                    "description": item['mapped_fields']['description'],
                    "file": {"relative_path": target_file, "line": line_number + 1},
                    "created_at": now_iso()
                }
            }
            
        except Exception as e:
            self.logger.error(f"Exception creating Obsidian task: {str(e)}")
            return None
    
    def _format_obsidian_task(self, fields: Dict) -> str:
        """Format mapped fields into Obsidian task syntax."""
        task_parts = ["- [ ]", fields.get("description", "Untitled Task")]
        
        # Add due date
        if fields.get("due"):
            task_parts.append(f"📅 {fields['due']}")
        
        # Add priority
        if fields.get("priority"):
            priority_symbols = {"high": "⏫", "medium": "🔼", "low": "🔽"}
            symbol = priority_symbols.get(fields["priority"], "")
            if symbol:
                task_parts.append(symbol)
        
        # Add tags
        if fields.get("tags"):
            task_parts.extend(fields["tags"])
        
        return " ".join(task_parts)
    
    def _create_link_entry(self, obs_uuid: str, rem_uuid: str, score: float, 
                          obs_task: Dict, rem_task: Dict) -> Dict:
        """Create a new link entry."""
        return {
            "obs_uuid": obs_uuid,
            "rem_uuid": rem_uuid,
            "score": score,
            "title_similarity": 1.0,  # Perfect for created counterparts
            "date_distance_days": 0,
            "due_equal": True,
            "created_at": now_iso(),
            "last_scored": now_iso(),
            "last_synced": None,
            "fields": {
                "obs_title": obs_task.get("description", ""),
                "rem_title": rem_task.get("description", ""),
                "obs_due": obs_task.get("due"),
                "rem_due": rem_task.get("due_date")
            }
        }
    
    def _append_new_links(self, links_path: str, new_links: List[Dict], changeset_id: str):
        """Append new links to sync_links.json."""
        # Load existing links
        links_data = safe_load_json(links_path, {"meta": {}, "links": []})
        
        # Record changeset
        self.backup_manager.record_file_change(
            operation="modify",
            file_path=links_path,
            create_backup=True
        )
        
        # Append new links
        links_data["links"].extend(new_links)
        links_data["meta"] = {
            "schema": 1,
            "generated_at": now_iso(),
            "total_links": len(links_data["links"])
        }
        
        # Write atomically
        safe_write_json_with_lock(links_path, links_data, timeout=30.0)
        self.logger.info(f"Added {len(new_links)} new links to {links_path}")


def load_config_from_app_json() -> CreationConfig:
    """Load configuration from TUI app.json file and convert to CreationConfig."""
    try:
        # Load the TUI configuration
        prefs, _ = app_config.load_app_config()
        
        # Convert to CreationConfig format
        config = CreationConfig(
            obs_inbox_file=prefs.creation_defaults.obs_inbox_file,
            rem_default_calendar_id=prefs.creation_defaults.rem_default_calendar_id,
            max_creates_per_run=prefs.creation_defaults.max_creates_per_run,
            since_days=prefs.creation_defaults.since_days,
            include_done=prefs.creation_defaults.include_done,
            obs_to_rem_rules=[{
                "tag": rule.tag,
                "calendar_id": rule.calendar_id
            } for rule in prefs.obs_to_rem_rules],
            rem_to_obs_rules=[{
                "list_name": rule.list_name,
                "target_file": rule.target_file,
                "heading": rule.heading
            } for rule in prefs.rem_to_obs_rules]
        )
        
        return config
        
    except Exception as e:
        # Fall back to default config if app.json loading fails
        print(f"Warning: Could not load configuration from app.json ({e}), using defaults")
        return CreationConfig()


def main(argv: List[str] = None) -> int:
    """Main entry point for create missing counterparts command."""
    if argv is None:
        argv = sys.argv[1:]
    
    ap = argparse.ArgumentParser(
        description="Create missing counterpart tasks between Obsidian and Reminders",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Input paths
    ap.add_argument("--obs", default=get_path("obsidian_index"),
                   help="Path to Obsidian tasks index")
    ap.add_argument("--rem", default=get_path("reminders_index"), 
                   help="Path to Reminders tasks index")
    ap.add_argument("--links", default=get_path("links"),
                   help="Path to sync links file")
    
    # Operation mode
    ap.add_argument("--apply", action="store_true",
                   help="Actually create counterparts (default: dry-run)")
    ap.add_argument("--dry-run", action="store_true",
                   help="Show what would be created without making changes")
    
    # Direction control
    ap.add_argument("--direction", choices=["both", "obs-to-rem", "rem-to-obs"], 
                   default="both", help="Direction of counterpart creation")
    
    # Filters
    ap.add_argument("--include-done", action="store_true",
                   help="Include completed tasks")
    ap.add_argument("--since", type=int, metavar="DAYS",
                   help="Only process tasks modified within N days")
    ap.add_argument("--max", type=int, metavar="N",
                   help="Maximum number of counterparts to create")
    
    # Output options
    ap.add_argument("--verbose", "-v", action="store_true",
                   help="Verbose output")
    ap.add_argument("--plan-out", help="Save creation plan to JSON file")
    
    args = ap.parse_args(argv)
    
    # Set up logging
    logger = get_logger("create_missing_counterparts")
    run_id = logger.start_run("create_missing_counterparts", vars(args))
    
    try:
        # Load configuration from TUI app.json, then override with command line args
        config = load_config_from_app_json()
        
        # Override with command line arguments if provided
        if args.include_done:
            config.include_done = args.include_done
        if args.since is not None:
            config.since_days = args.since
        if args.max is not None:
            config.max_creates_per_run = args.max
        creator = MissingCounterpartsCreator(config, logger)
        
        # Load data
        obs_index, rem_index, links_data = creator.load_indices_and_links(
            args.obs, args.rem, args.links
        )
        
        # Create plan
        plan = creator.create_plan(
            obs_index, rem_index, links_data,
            direction=args.direction,
            include_done=args.include_done,
            since_days=args.since,
            max_creates=args.max
        )
        
        # Save plan if requested
        if args.plan_out:
            with open(args.plan_out, 'w') as f:
                json.dump(asdict(plan), f, indent=2, default=str)
            print(f"Plan saved to {args.plan_out}")
        
        # Show plan summary
        print(f"\nCreation Plan Summary:")
        print(f"  Direction: {plan.direction}")
        print(f"  Obsidian -> Reminders: {len(plan.obs_to_rem)} tasks")
        print(f"  Reminders -> Obsidian: {len(plan.rem_to_obs)} tasks")
        print(f"  Total creations: {plan.total_creates}")
        
        if plan.total_creates == 0:
            print("No missing counterparts found.")
            logger.end_run(True)
            return 0
        
        # Execute or show dry-run
        # If --apply is specified but --dry-run is not explicitly set, do the apply
        dry_run_mode = args.dry_run or not args.apply
        if args.apply and not dry_run_mode:
            print(f"\nExecuting creation plan...")
            result = creator.execute_plan(plan, args.links, run_id)
            
            print(f"\nResults:")
            print(f"  Created Obsidian tasks: {result.created_obs}")
            print(f"  Created Reminders tasks: {result.created_rem}")
            print(f"  New links: {len(result.new_links)}")
            if result.errors:
                print(f"  Errors: {len(result.errors)}")
                for error in result.errors:
                    print(f"    - {error}")
            
            logger.end_run(result.success)
            return 0 if result.success else 1
        else:
            print(f"\nDry-run mode - no changes made.")
            print(f"Use --apply to actually create the counterparts.")
            
            if args.verbose:
                print(f"\nDetailed plan:")
                for i, item in enumerate(plan.obs_to_rem):
                    print(f"  Obs->Rem {i+1}: {item['mapped_fields']['title']}")
                for i, item in enumerate(plan.rem_to_obs):
                    print(f"  Rem->Obs {i+1}: {item['mapped_fields']['description']}")
        
        logger.end_run(True)
        return 0
        
    except Exception as e:
        logger.error(f"Command failed: {str(e)}")
        logger.end_run(False, str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())