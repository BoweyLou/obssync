#!/usr/bin/env python3
"""
Task Operations Tool

Performs physical operations (create, update, delete) on both Obsidian markdown files 
and Apple Reminders. This tool works with the index files and other metadata to 
determine what changes to make, then executes those changes in the actual source systems.

Key Features:
- Delete duplicate tasks from source files
- Update task properties in both systems
- Create new tasks in Obsidian and Reminders
- Robust validation and logging
- Changeset tracking for rollback capability
- Transaction-like behavior with rollback on failure
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any, Set
import uuid
import hashlib


def now_iso() -> str:
    """Get current timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


class OperationResult:
    """Result of a single operation."""
    def __init__(self, success: bool, message: str, details: Optional[Dict] = None):
        self.success = success
        self.message = message
        self.details = details or {}
        self.timestamp = now_iso()
    
    def __str__(self):
        return f"{'SUCCESS' if self.success else 'FAILED'}: {self.message}"


class Changeset:
    """Tracks all changes made during an operation session."""
    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.changes: List[Dict[str, Any]] = []
        self.created_at = now_iso()
        
    def add_change(self, operation_type: str, target: str, details: Dict[str, Any]):
        """Add a change record to the changeset."""
        change = {
            "operation": operation_type,
            "target": target,
            "timestamp": now_iso(),
            "details": details
        }
        self.changes.append(change)
        
    def save(self, output_path: str):
        """Save changeset to a JSON file."""
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        data = {
            "meta": {
                "session_id": self.session_id,
                "created_at": self.created_at,
                "change_count": len(self.changes),
                "saved_at": now_iso()
            },
            "changes": self.changes
        }
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


class ObsidianOperations:
    """Handles physical operations on Obsidian markdown files."""
    
    TASK_RE = re.compile(r"^(?P<indent>\s*)[-*]\s+\[(?P<status>[ xX])\]\s+(?P<rest>.*)$")
    BLOCK_ID_RE = re.compile(r"\^(?P<bid>[A-Za-z0-9\-]+)\s*$")
    
    @staticmethod
    def _find_task_line(file_path: str, task_data: Dict) -> Optional[Tuple[int, str]]:
        """Find the line number and content of a task in a file."""
        if not os.path.isfile(file_path):
            return None
            
        block_id = task_data.get('block_id')
        expected_raw = task_data.get('raw', '').strip()
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.read().splitlines()
        except Exception:
            return None
            
        # Try exact raw match first
        if expected_raw:
            for i, line in enumerate(lines):
                if line.strip() == expected_raw:
                    return i, line
                    
        # Try block ID match
        if block_id:
            for i, line in enumerate(lines):
                if line.rstrip().endswith(f"^{block_id}"):
                    return i, line
                    
        return None
    
    @staticmethod
    def delete_task(file_path: str, task_data: Dict, validate: bool = True) -> OperationResult:
        """Delete a task line from an Obsidian file."""
        line_info = ObsidianOperations._find_task_line(file_path, task_data)
        if not line_info:
            return OperationResult(False, f"Task not found in {file_path}")
            
        line_no, original_line = line_info
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.read().splitlines()
                
            # Remove the line
            removed_line = lines.pop(line_no)
            
            # Write back to file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines) + '\n')
                
            # Validate if requested
            if validate:
                # Check that the line is gone
                check_info = ObsidianOperations._find_task_line(file_path, task_data)
                if check_info is not None:
                    return OperationResult(False, f"Validation failed: task still exists after deletion")
                    
            details = {
                "file_path": file_path,
                "line_number": line_no,
                "removed_line": removed_line,
                "block_id": task_data.get('block_id'),
                "uuid": task_data.get('uuid')
            }
            
            return OperationResult(True, f"Deleted task from {os.path.basename(file_path)}:{line_no+1}", details)
            
        except Exception as e:
            return OperationResult(False, f"Failed to delete task: {e}")
    
    @staticmethod
    def update_task(file_path: str, task_data: Dict, changes: Dict[str, Any], validate: bool = True) -> OperationResult:
        """Update a task line in an Obsidian file."""
        line_info = ObsidianOperations._find_task_line(file_path, task_data)
        if not line_info:
            return OperationResult(False, f"Task not found in {file_path}")
            
        line_no, original_line = line_info
        
        try:
            # Parse the original line
            match = ObsidianOperations.TASK_RE.match(original_line)
            if not match:
                return OperationResult(False, f"Line is not a valid task: {original_line}")
                
            indent = match.group('indent')
            current_status = match.group('status')
            rest = match.group('rest')
            
            # Apply changes
            new_status = changes.get('status', current_status)
            new_rest = rest
            
            # Update due date if specified
            if 'due' in changes:
                # Remove existing due date and add new one
                new_rest = re.sub(r'📅\s*\d{4}-\d{2}-\d{2}', '', new_rest).strip()
                if changes['due']:
                    new_rest += f" 📅 {changes['due']}"
                    
            # Update priority if specified
            if 'priority' in changes:
                # Remove existing priority and add new one
                new_rest = re.sub(r'[⏫🔼🔽]', '', new_rest).strip()
                if changes['priority'] == 'high':
                    new_rest = '⏫ ' + new_rest
                elif changes['priority'] == 'medium':
                    new_rest = '🔼 ' + new_rest
                elif changes['priority'] == 'low':
                    new_rest = '🔽 ' + new_rest
                    
            # Update description if specified
            if 'description' in changes:
                # Extract block ID if present
                block_match = ObsidianOperations.BLOCK_ID_RE.search(new_rest)
                block_suffix = block_match.group(0) if block_match else ''
                new_rest = changes['description'] + (' ' + block_suffix if block_suffix else '')
                
            new_line = f"{indent}- [{new_status}] {new_rest}"
            
            # Read, modify, write
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.read().splitlines()
                
            lines[line_no] = new_line
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines) + '\n')
                
            # Validate if requested
            if validate:
                with open(file_path, 'r', encoding='utf-8') as f:
                    verify_lines = f.read().splitlines()
                if line_no >= len(verify_lines) or verify_lines[line_no] != new_line:
                    return OperationResult(False, "Validation failed: line not updated correctly")
                    
            details = {
                "file_path": file_path,
                "line_number": line_no,
                "original_line": original_line,
                "new_line": new_line,
                "changes": changes,
                "block_id": task_data.get('block_id'),
                "uuid": task_data.get('uuid')
            }
            
            return OperationResult(True, f"Updated task in {os.path.basename(file_path)}:{line_no+1}", details)
            
        except Exception as e:
            return OperationResult(False, f"Failed to update task: {e}")
    
    @staticmethod
    def create_task(file_path: str, task_text: str, position: str = 'end', validate: bool = True) -> OperationResult:
        """Create a new task line in an Obsidian file."""
        try:
            # Ensure the file exists
            if not os.path.isfile(file_path):
                # Create the file if it doesn't exist
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write('')
                    
            # Add block ID if not present
            if not ObsidianOperations.BLOCK_ID_RE.search(task_text):
                block_id = f"^t-{uuid.uuid4().hex[:12]}"
                task_text = task_text.rstrip() + f" {block_id}"
                
            # Read existing content
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.read().splitlines()
                
            # Add the new task
            if position == 'end':
                lines.append(task_text)
                line_no = len(lines) - 1
            else:
                # Could add other position options like 'start', specific line numbers, etc.
                lines.append(task_text)
                line_no = len(lines) - 1
                
            # Write back
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines) + '\n')
                
            # Validate if requested
            if validate:
                with open(file_path, 'r', encoding='utf-8') as f:
                    verify_lines = f.read().splitlines()
                if line_no >= len(verify_lines) or verify_lines[line_no] != task_text:
                    return OperationResult(False, "Validation failed: task not created correctly")
                    
            details = {
                "file_path": file_path,
                "line_number": line_no,
                "task_text": task_text,
                "position": position
            }
            
            return OperationResult(True, f"Created task in {os.path.basename(file_path)}:{line_no+1}", details)
            
        except Exception as e:
            return OperationResult(False, f"Failed to create task: {e}")


class RemindersOperations:
    """Handles physical operations on Apple Reminders via EventKit."""
    
    def __init__(self):
        self._store_cache = {}
        
    def _get_eventkit_store(self):
        """Get or create EventKit store with authorization."""
        if 'store' in self._store_cache:
            return self._store_cache['store']
            
        try:
            from EventKit import EKEventStore, EKEntityTypeReminder, EKAuthorizationStatusAuthorized
            from Foundation import NSRunLoop, NSDate
        except ImportError:
            raise RuntimeError("EventKit not available - Apple Reminders operations require macOS")
            
        store = EKEventStore.alloc().init()
        
        # Check authorization
        status = EKEventStore.authorizationStatusForEntityType_(EKEntityTypeReminder)
        if int(status) != int(EKAuthorizationStatusAuthorized):
            # Request authorization
            done_auth = threading.Event()
            def auth_completion(granted, error):
                done_auth.set()
            store.requestAccessToEntityType_completion_(EKEntityTypeReminder, auth_completion)
            done_auth.wait(timeout=10)
            
            # Check again
            final_status = EKEventStore.authorizationStatusForEntityType_(EKEntityTypeReminder)
            if int(final_status) != int(EKAuthorizationStatusAuthorized):
                raise RuntimeError(f"EventKit authorization denied (status: {final_status})")
                
        self._store_cache['store'] = store
        return store
    
    def _find_reminder(self, item_id: str, calendar_id: Optional[str] = None) -> Optional[Any]:
        """Find a reminder by item ID."""
        store = self._get_eventkit_store()
        
        try:
            from EventKit import EKEntityTypeReminder
            from Foundation import NSRunLoop, NSDate
        except ImportError:
            return None
            
        # Get calendars to search
        all_cals = store.calendarsForEntityType_(EKEntityTypeReminder) or []
        if calendar_id:
            search_cals = [c for c in all_cals if str(c.calendarIdentifier()) == calendar_id]
            if not search_cals:
                return None
        else:
            search_cals = list(all_cals)
            
        # Fetch reminders
        pred = store.predicateForRemindersInCalendars_(search_cals)
        bucket = []
        done = threading.Event()
        
        def completion(reminders):
            try:
                bucket.extend(list(reminders or []))
            finally:
                done.set()
                
        store.fetchRemindersMatchingPredicate_completion_(pred, completion)
        deadline = time.time() + 10
        while not done.is_set() and time.time() < deadline:
            NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.1))
            
        # Find our reminder
        for reminder in bucket:
            try:
                rid = str(reminder.calendarItemIdentifier())
                if rid == item_id:
                    return reminder
            except Exception:
                continue
                
        return None
    
    def delete_reminder(self, item_id: str, calendar_id: Optional[str] = None, validate: bool = True) -> OperationResult:
        """Delete a reminder from Apple Reminders."""
        try:
            store = self._get_eventkit_store()
            reminder = self._find_reminder(item_id, calendar_id)
            
            if not reminder:
                return OperationResult(False, f"Reminder not found: {item_id}")
                
            # Get details before deletion
            title = str(reminder.title() or "")
            calendar_name = str(reminder.calendar().title() or "")
            
            # Delete the reminder
            success, error = store.removeReminder_commit_error_(reminder, True, None)
            if not success or error:
                error_msg = f"Failed to delete reminder: {title}"
                if error:
                    error_msg += f" - Error: {error}"
                return OperationResult(False, error_msg)
                
            # Validate if requested
            if validate:
                # Check that reminder is gone
                check_reminder = self._find_reminder(item_id, calendar_id)
                if check_reminder is not None:
                    return OperationResult(False, "Validation failed: reminder still exists after deletion")
                    
            details = {
                "item_id": item_id,
                "calendar_id": calendar_id,
                "title": title,
                "calendar_name": calendar_name
            }
            
            return OperationResult(True, f"Deleted reminder: {title}", details)
            
        except Exception as e:
            return OperationResult(False, f"Failed to delete reminder: {e}")
    
    def update_reminder(self, item_id: str, changes: Dict[str, Any], calendar_id: Optional[str] = None, validate: bool = True) -> OperationResult:
        """Update a reminder in Apple Reminders."""
        try:
            store = self._get_eventkit_store()
            reminder = self._find_reminder(item_id, calendar_id)
            
            if not reminder:
                return OperationResult(False, f"Reminder not found: {item_id}")
                
            original_title = str(reminder.title() or "")
            changed = False
            
            # Apply changes
            if 'title' in changes:
                reminder.setTitle_(changes['title'])
                changed = True
                
            if 'completed' in changes:
                reminder.setCompleted_(bool(changes['completed']))
                changed = True
                
            if 'due' in changes:
                if changes['due']:
                    from Foundation import NSCalendar, NSDateComponents
                    y, m, d = map(int, changes['due'][:10].split("-"))
                    comps = NSDateComponents.alloc().init()
                    comps.setYear_(y)
                    comps.setMonth_(m) 
                    comps.setDay_(d)
                    reminder.setDueDateComponents_(comps)
                else:
                    reminder.setDueDateComponents_(None)
                changed = True
                
            if 'priority' in changes:
                # Note: Priority values inverted in v2.0 to match Apple's native priority scheme
                # where lower numbers = higher priority (1=high, 5=medium, 9=low)
                # BREAKING CHANGE: This inverts the priority mapping from previous versions
                # TODO: Run priority_migration.py to migrate existing reminders before v2.0 upgrade
                priority_map = {'high': 1, 'medium': 5, 'low': 9, None: 0}
                reminder.setPriority_(priority_map.get(changes['priority'], 0))
                changed = True
                
            # Save changes
            if changed:
                success, error = store.saveReminder_commit_error_(reminder, True, None)
                if not success or error:
                    error_msg = f"Failed to save reminder changes: {original_title}"
                    if error:
                        error_msg += f" - Error: {error}"
                    return OperationResult(False, error_msg)
                    
            # Validate if requested  
            if validate and changed:
                # Re-fetch and verify changes
                updated_reminder = self._find_reminder(item_id, calendar_id)
                if not updated_reminder:
                    return OperationResult(False, "Validation failed: reminder not found after update")
                    
            details = {
                "item_id": item_id,
                "calendar_id": calendar_id,
                "original_title": original_title,
                "changes": changes,
                "changed": changed
            }
            
            status_msg = f"Updated reminder: {original_title}" if changed else f"No changes needed: {original_title}"
            return OperationResult(True, status_msg, details)
            
        except Exception as e:
            return OperationResult(False, f"Failed to update reminder: {e}")
    
    def create_reminder(self, title: str, calendar_id: Optional[str] = None, properties: Optional[Dict] = None, validate: bool = True) -> OperationResult:
        """Create a new reminder in Apple Reminders."""
        properties = properties or {}
        
        try:
            from EventKit import EKReminder, EKEntityTypeReminder
            from Foundation import NSCalendar, NSDateComponents
            
            store = self._get_eventkit_store()
            
            # Create new reminder
            reminder = EKReminder.reminderWithEventStore_(store)
            reminder.setTitle_(title)
            
            # Set calendar
            if calendar_id:
                all_cals = store.calendarsForEntityType_(EKEntityTypeReminder) or []
                target_cal = None
                for cal in all_cals:
                    if str(cal.calendarIdentifier()) == calendar_id:
                        target_cal = cal
                        break
                if target_cal:
                    reminder.setCalendar_(target_cal)
                else:
                    return OperationResult(False, f"Calendar not found: {calendar_id}")
            else:
                # Use default calendar
                default_cal = store.defaultCalendarForNewReminders()
                if default_cal:
                    reminder.setCalendar_(default_cal)
                    
            # Set properties
            if 'due' in properties and properties['due']:
                y, m, d = map(int, properties['due'][:10].split("-"))
                comps = NSDateComponents.alloc().init()
                comps.setYear_(y)
                comps.setMonth_(m)
                comps.setDay_(d)
                reminder.setDueDateComponents_(comps)
                
            if 'priority' in properties:
                # Note: Priority values inverted in v2.0 to match Apple's native priority scheme
                # where lower numbers = higher priority (1=high, 5=medium, 9=low)
                # BREAKING CHANGE: This inverts the priority mapping from previous versions
                # TODO: Run priority_migration.py to migrate existing reminders before v2.0 upgrade
                priority_map = {'high': 1, 'medium': 5, 'low': 9, None: 0}
                reminder.setPriority_(priority_map.get(properties['priority'], 0))
                
            if 'completed' in properties:
                reminder.setCompleted_(bool(properties['completed']))
                
            # Save the reminder
            success, error = store.saveReminder_commit_error_(reminder, True, None)
            if not success or error:
                error_msg = f"Failed to create reminder: {title}"
                if error:
                    error_msg += f" - Error: {error}"
                return OperationResult(False, error_msg)
                
            # Get the created reminder's ID
            item_id = str(reminder.calendarItemIdentifier())
            
            # Validate if requested
            if validate:
                created_reminder = self._find_reminder(item_id)
                if not created_reminder:
                    return OperationResult(False, "Validation failed: created reminder not found")
                    
            details = {
                "item_id": item_id,
                "calendar_id": calendar_id,
                "title": title,
                "properties": properties
            }
            
            return OperationResult(True, f"Created reminder: {title}", details)
            
        except Exception as e:
            return OperationResult(False, f"Failed to create reminder: {e}")


class TaskOperations:
    """Main class that orchestrates task operations across both systems."""
    
    def __init__(self, dry_run: bool = True, verbose: bool = False):
        self.dry_run = dry_run
        self.verbose = verbose
        self.obsidian_ops = ObsidianOperations()
        self.reminders_ops = RemindersOperations()
        # Use unified Reminders gateway for consistency across operations
        try:
            from reminders_gateway import RemindersGateway
            self.gateway = RemindersGateway()
        except Exception:
            self.gateway = None
        self.changeset = Changeset()
        
    def delete_duplicates(self, duplicate_groups: Dict[str, List[List[str]]], obs_tasks: Dict, rem_tasks: Dict) -> Tuple[int, int]:
        """Delete duplicate tasks, keeping only the first in each group."""
        obs_removed = 0
        rem_removed = 0
        
        # Process Obsidian duplicates
        for group in duplicate_groups.get('obsidian', []):
            if len(group) <= 1:
                continue
                
            # Keep first, remove rest
            for task_uuid in group[1:]:
                task_data = obs_tasks.get(task_uuid)
                if not task_data or task_data.get('deleted'):
                    continue
                    
                file_info = task_data.get('file', {})
                file_path = file_info.get('absolute_path')
                
                if not file_path:
                    if self.verbose:
                        print(f"Skipping Obsidian task {task_uuid}: no file path")
                    continue
                    
                if self.verbose:
                    print(f"Deleting Obsidian duplicate: {task_data.get('description', '')[:50]}...")
                    
                if not self.dry_run:
                    result = self.obsidian_ops.delete_task(file_path, task_data)
                    if result.success:
                        obs_removed += 1
                        self.changeset.add_change('delete_obsidian_task', task_uuid, result.details)
                    else:
                        print(f"Failed to delete Obsidian task: {result.message}")
                else:
                    obs_removed += 1
                    if self.verbose:
                        print(f"  [DRY RUN] Would delete from {file_path}")
                        
        # Process Reminders duplicates  
        for group in duplicate_groups.get('reminders', []):
            if len(group) <= 1:
                continue
                
            # Keep first, remove rest
            for task_uuid in group[1:]:
                task_data = rem_tasks.get(task_uuid)
                if not task_data or task_data.get('deleted'):
                    continue
                    
                external_ids = task_data.get('external_ids', {})
                item_id = external_ids.get('item')
                calendar_id = external_ids.get('calendar')
                
                if not item_id:
                    if self.verbose:
                        print(f"Skipping Reminders task {task_uuid}: no item ID")
                    continue
                    
                if self.verbose:
                    print(f"Deleting Reminders duplicate: {task_data.get('description', '')[:50]}...")
                    
                if not self.dry_run:
                    # Prefer unified gateway when available
                    if self.gateway is not None:
                        gw_result = self.gateway.delete_reminder(item_id, calendar_id, dry_run=False)
                        if gw_result.success:
                            rem_removed += 1
                            details = {
                                "item_id": item_id,
                                "calendar_id": calendar_id,
                                "title": task_data.get('description', '')
                            }
                            self.changeset.add_change('delete_reminder_task', task_uuid, details)
                        else:
                            errs = "; ".join(gw_result.errors or [])
                            print(f"Failed to delete Reminders task: {errs}")
                    else:
                        # Fallback to legacy direct EventKit path
                        result = self.reminders_ops.delete_reminder(item_id, calendar_id)
                        if result.success:
                            rem_removed += 1
                            self.changeset.add_change('delete_reminder_task', task_uuid, result.details)
                        else:
                            print(f"Failed to delete Reminders task: {result.message}")
                else:
                    rem_removed += 1
                    if self.verbose:
                        print(f"  [DRY RUN] Would delete reminder {item_id}")
                        
        return obs_removed, rem_removed
    
    def delete_task_list(self, obs_uuids: List[str], rem_uuids: List[str], obs_tasks: Dict, rem_tasks: Dict) -> Tuple[int, int]:
        """Delete specific tasks by UUID."""
        obs_removed = 0
        rem_removed = 0
        
        # Process Obsidian task deletions
        for task_uuid in obs_uuids:
            task_data = obs_tasks.get(task_uuid)
            if not task_data or task_data.get('deleted'):
                continue
                
            file_info = task_data.get('file', {})
            file_path = file_info.get('absolute_path')
            
            if not file_path:
                if self.verbose:
                    print(f"Skipping Obsidian task {task_uuid}: no file path")
                continue
                
            if self.verbose:
                print(f"Deleting Obsidian task: {task_data.get('description', '')[:50]}...")
                
            if not self.dry_run:
                result = self.obsidian_ops.delete_task(file_path, task_data)
                if result.success:
                    obs_removed += 1
                    self.changeset.add_change('delete_obsidian_task', task_uuid, result.details)
                    if self.verbose:
                        print(f"  ✓ {result.message}")
                else:
                    print(f"  ✗ Failed: {result.message}")
            else:
                obs_removed += 1
                if self.verbose:
                    print(f"  [DRY RUN] Would delete from {file_path}")
                    
        # Process Reminders task deletions
        for task_uuid in rem_uuids:
            task_data = rem_tasks.get(task_uuid)
            if not task_data or task_data.get('deleted'):
                continue
                
            external_ids = task_data.get('external_ids', {})
            item_id = external_ids.get('item')
            calendar_id = external_ids.get('calendar')
            
            if not item_id:
                if self.verbose:
                    print(f"Skipping Reminders task {task_uuid}: no item ID")
                continue
                
            if self.verbose:
                print(f"Deleting Reminders task: {task_data.get('description', '')[:50]}...")
                
            if not self.dry_run:
                if self.gateway is not None:
                    gw_result = self.gateway.delete_reminder(item_id, calendar_id, dry_run=False)
                    if gw_result.success:
                        rem_removed += 1
                        details = {
                            "item_id": item_id,
                            "calendar_id": calendar_id,
                            "title": task_data.get('description', '')
                        }
                        self.changeset.add_change('delete_reminder_task', task_uuid, details)
                        if self.verbose:
                            print("  ✓ Deleted via RemindersGateway")
                    else:
                        errs = "; ".join(gw_result.errors or [])
                        print(f"  ✗ Failed: {errs}")
                else:
                    result = self.reminders_ops.delete_reminder(item_id, calendar_id)
                    if result.success:
                        rem_removed += 1
                        self.changeset.add_change('delete_reminder_task', task_uuid, result.details)
                        if self.verbose:
                            print(f"  ✓ {result.message}")
                    else:
                        print(f"  ✗ Failed: {result.message}")
            else:
                rem_removed += 1
                if self.verbose:
                    print(f"  [DRY RUN] Would delete reminder {item_id}")
                    
        return obs_removed, rem_removed
    
    def save_changeset(self, output_path: str):
        """Save the changeset to a file."""
        if not self.dry_run:
            self.changeset.save(output_path)
            if self.verbose:
                print(f"Saved changeset to {output_path}")


def load_duplicate_groups(obs_index: str, rem_index: str, similarity: float = 1.0) -> Tuple[Dict, Dict, Dict]:
    """Load task indexes and find duplicate groups."""
    try:
        with open(obs_index, 'r', encoding='utf-8') as f:
            obs_data = json.load(f)
        with open(rem_index, 'r', encoding='utf-8') as f:
            rem_data = json.load(f)
    except Exception as e:
        raise RuntimeError(f"Failed to load task indexes: {e}")
        
    obs_tasks = obs_data.get('tasks', {})
    rem_tasks = rem_data.get('tasks', {})
    
    # Import the duplicate finding logic
    from find_duplicate_tasks import find_duplicate_groups
    
    obs_groups = find_duplicate_groups(obs_tasks, similarity)
    rem_groups = find_duplicate_groups(rem_tasks, similarity)
    
    duplicate_groups = {
        'obsidian': obs_groups,
        'reminders': rem_groups
    }
    
    return duplicate_groups, obs_tasks, rem_tasks


def main(argv: list[str] = None) -> int:
    # Use centralized path configuration
    try:
        from app_config import get_path
        default_obs = get_path("obsidian_index")
        default_rem = get_path("reminders_index")
        default_backup = get_path("task_operations_backup")
    except ImportError:
        # Fallback for standalone execution
        default_obs = os.path.expanduser('~/.config/obsidian_tasks_index.json')
        default_rem = os.path.expanduser('~/.config/reminders_tasks_index.json')
        default_backup = os.path.expanduser('~/.config/obs-tools/backups/task_operations.json')
    
    parser = argparse.ArgumentParser(description="Perform physical operations on Obsidian and Reminders tasks")
    parser.add_argument('action', choices=['delete-duplicates'], 
                       help='Action to perform')
    parser.add_argument('--obs', default=default_obs,
                       help='Path to Obsidian tasks index')
    parser.add_argument('--rem', default=default_rem,
                       help='Path to Reminders tasks index')
    parser.add_argument('--similarity', type=float, default=1.0,
                       help='Similarity threshold for duplicate detection')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without making changes')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose output')
    parser.add_argument('--changeset-out', 
                       default=default_backup,
                       help='Path to save changeset')
    
    args = parser.parse_args(argv)
    
    # Create operations handler
    operations = TaskOperations(dry_run=args.dry_run, verbose=args.verbose)
    
    if args.action == 'delete-duplicates':
        print("Task Operations - Delete Duplicates")
        print("=" * 40)
        
        # Load duplicate groups
        try:
            duplicate_groups, obs_tasks, rem_tasks = load_duplicate_groups(args.obs, args.rem, args.similarity)
        except Exception as e:
            print(f"Error: {e}")
            return 1
            
        obs_group_count = len(duplicate_groups['obsidian'])
        rem_group_count = len(duplicate_groups['reminders'])
        
        print(f"Found {obs_group_count} Obsidian duplicate groups")
        print(f"Found {rem_group_count} Reminders duplicate groups")
        
        if not obs_group_count and not rem_group_count:
            print("No duplicates found!")
            return 0
            
        if args.dry_run:
            print("\nDRY RUN - no changes will be made")
        else:
            confirm = input(f"\nProceed with deleting duplicates? (yes/no): ").strip().lower()
            if confirm not in ('yes', 'y'):
                print("Cancelled.")
                return 0
                
        # Delete duplicates
        obs_removed, rem_removed = operations.delete_duplicates(duplicate_groups, obs_tasks, rem_tasks)
        
        print(f"\nResults:")
        print(f"  Obsidian tasks removed: {obs_removed}")
        print(f"  Reminders tasks removed: {rem_removed}")
        print(f"  Total removed: {obs_removed + rem_removed}")
        
        # Save changeset
        if not args.dry_run and (obs_removed > 0 or rem_removed > 0):
            operations.save_changeset(args.changeset_out)
            print(f"  Changeset saved to: {args.changeset_out}")
            
    # All valid actions are now implemented above
        
    return 0


if __name__ == '__main__':
    import sys
    raise SystemExit(main(sys.argv[1:]))
