"""Task manager for Obsidian CRUD operations."""

import os
import uuid
import hashlib
import base64
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set
import logging

from ..core.models import ObsidianTask, Priority, TaskStatus
from .parser import format_task_line, parse_markdown_task


class ObsidianTaskManager:
    """Manages CRUD operations for Obsidian tasks."""

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self.include_completed = True  # Default to including completed tasks

    def _stable_uuid_for_task(
        self,
        vault_path: str,
        file_path: str,
        line_number: int,
        description: str,
        existing_ids: Optional[Set[str]] = None
    ) -> str:
        """Generate a stable, deterministic UUID for a task based on its attributes.
        
        Args:
            vault_path: Path to the vault
            file_path: Relative file path within vault
            line_number: Line number in the file
            description: Task description (normalized)
            existing_ids: Set of existing block IDs to avoid collisions
            
        Returns:
            A stable block ID (without the 'obs-' prefix)
        """
        # Normalize description for consistent hashing
        normalized_desc = description.strip().lower()
        vault_id = os.path.basename(vault_path)
        
        # Create unique string from stable attributes
        unique_string = f"{vault_id}|{file_path}|{line_number}|{normalized_desc}"
        
        # Generate SHA1 hash and encode as base32 for human-friendly IDs
        hash_obj = hashlib.sha1(unique_string.encode('utf-8'))
        # Use base32 encoding for readable IDs, take first 8 chars
        base_id = base64.b32encode(hash_obj.digest()).decode('ascii')[:8].lower()
        
        # Handle collisions by appending counter if needed
        block_id = base_id
        counter = 1
        
        if existing_ids:
            while block_id in existing_ids:
                block_id = f"{base_id}-{counter}"
                counter += 1
                if counter > 100:  # Safety valve
                    self.logger.warning(f"High collision count for task ID generation: {base_id}")
                    break
        
        return block_id

    def list_tasks(self, vault_path: str, include_completed: Optional[bool] = None) -> List[ObsidianTask]:
        """List all tasks in a vault.
        
        Args:
            vault_path: Path to the vault
            include_completed: Whether to include completed tasks. If None, uses instance default.
        """
        tasks: List[ObsidianTask] = []

        for root, _dirs, files in os.walk(vault_path):
            for filename in files:
                if not filename.endswith(".md"):
                    continue
                file_path = os.path.join(root, filename)
                rel_path = os.path.relpath(file_path, vault_path)
                tasks.extend(self._parse_file(vault_path, rel_path))
        
        # Filter out completed tasks if requested
        if include_completed is None:
            include_completed = self.include_completed
            
        if not include_completed:
            tasks = [t for t in tasks if t.status != TaskStatus.DONE]
            self.logger.debug(f"Filtered to {len(tasks)} active tasks (excluded completed)")

        return tasks

    def _parse_file(self, vault_path: str, rel_file_path: str) -> List[ObsidianTask]:
        """Parse tasks from a single markdown file."""
        tasks: List[ObsidianTask] = []
        full_path = os.path.join(vault_path, rel_file_path)

        try:
            # Get file modification time for timestamp initialization
            file_stat = os.stat(full_path)
            file_modified_time = datetime.fromtimestamp(file_stat.st_mtime, tz=timezone.utc)
            
            with open(full_path, "r", encoding="utf-8") as handle:
                lines = handle.readlines()

            # Collect existing block IDs to avoid collisions
            existing_block_ids: Set[str] = set()
            for line in lines:
                task_data = parse_markdown_task(line.rstrip())
                if task_data and task_data.get("block_id"):
                    existing_block_ids.add(task_data["block_id"])

            for line_num, raw_line in enumerate(lines, 1):
                task_data = parse_markdown_task(raw_line.rstrip())
                if not task_data:
                    continue

                block_id = task_data.get("block_id")
                if block_id:
                    uuid_value = block_id
                else:
                    # Generate stable UUID for tasks without block IDs
                    uuid_value = self._stable_uuid_for_task(
                        vault_path=vault_path,
                        file_path=rel_file_path,
                        line_number=line_num,
                        description=task_data["description"],
                        existing_ids=existing_block_ids
                    )

                task = ObsidianTask(
                    uuid=f"obs-{uuid_value}",
                    vault_id=os.path.basename(vault_path),
                    vault_name=os.path.basename(vault_path),
                    vault_path=vault_path,
                    file_path=rel_file_path,
                    line_number=line_num,
                    block_id=block_id,
                    status=task_data["status"],
                    description=task_data["description"],
                    raw_line=raw_line.rstrip("\n"),
                    due_date=task_data.get("due_date"),
                    completion_date=task_data.get("completion_date"),
                    priority=task_data.get("priority"),
                    tags=task_data.get("tags", []),
                    created_at=file_modified_time.isoformat(),
                    modified_at=file_modified_time.isoformat(),
                )
                tasks.append(task)

        except Exception as exc:  # pragma: no cover - defensive
            self.logger.error("Error parsing %s: %s", rel_file_path, exc)

        return tasks
    
    def create_task(
        self,
        vault_path: str,
        file_path: str,
        task: ObsidianTask,
    ) -> Optional[ObsidianTask]:
        """Create a new task in a markdown file."""
        full_path = os.path.join(vault_path, file_path)

        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        if not os.path.exists(full_path):
            with open(full_path, "w", encoding="utf-8") as handle:
                title = os.path.basename(file_path).replace(".md", "")
                handle.write(f"# {title}\n\n")

        # Generate stable block ID if not provided
        if not task.block_id:
            # Read existing file to collect existing block IDs for collision avoidance
            existing_block_ids: Set[str] = set()
            if os.path.exists(full_path):
                with open(full_path, "r", encoding="utf-8") as handle:
                    lines = handle.readlines()
                for line in lines:
                    task_data = parse_markdown_task(line.rstrip())
                    if task_data and task_data.get("block_id"):
                        existing_block_ids.add(task_data["block_id"])
            
            # Calculate line number where new task will be added
            next_line_num = self._count_lines(full_path) + 1
            
            # Generate stable UUID based on task attributes
            task.block_id = self._stable_uuid_for_task(
                vault_path=vault_path,
                file_path=file_path,
                line_number=next_line_num,
                description=task.description,
                existing_ids=existing_block_ids
            )
            # Update UUID to match the canonical format that list_tasks will generate
            task.uuid = f"obs-{task.block_id}"
        
        # Always ensure UUID aligns with block_id, whether generated or provided
        if task.block_id:
            task.uuid = f"obs-{task.block_id}"

        new_line = format_task_line(
            description=task.description,
            status=task.status,
            due_date=task.due_date,
            completion_date=task.completion_date,
            priority=task.priority,
            tags=task.tags,
            block_id=task.block_id,
        )

        with open(full_path, "a", encoding="utf-8") as handle:
            handle.write(f"{new_line}\n")

        current_time = datetime.now(timezone.utc).isoformat()
        task.vault_path = vault_path
        task.file_path = file_path
        task.raw_line = new_line
        task.line_number = self._count_lines(full_path)
        task.created_at = current_time
        task.modified_at = current_time

        return task

    def _count_lines(self, path: str) -> int:
        with open(path, "r", encoding="utf-8") as handle:
            return sum(1 for _ in handle)

    def update_task(self, task: ObsidianTask, changes: Dict) -> Optional[ObsidianTask]:
        """Update an existing task."""
        file_path = os.path.join(task.vault_path, task.file_path)

        if not os.path.exists(file_path):
            self.logger.error("File not found for task update: %s", file_path)
            return None

        with open(file_path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()

        if task.line_number <= 0 or task.line_number > len(lines):
            return None

        line_index = task.line_number - 1
        current_line = lines[line_index].rstrip("\n")

        if task.block_id and f"^{task.block_id}" not in current_line:
            return None

        parsed = parse_markdown_task(current_line)
        if not parsed:
            return None

        indent = parsed.get("indent", "")

        if "status" in changes:
            status_value = changes["status"]
            if isinstance(status_value, TaskStatus):
                task.status = status_value
            elif status_value == "done":
                task.status = TaskStatus.DONE
            else:
                task.status = TaskStatus.TODO

        if "description" in changes:
            task.description = changes["description"]

        if "due_date" in changes:
            task.due_date = changes["due_date"]

        if "priority" in changes:
            task.priority = changes["priority"]

        if "tags" in changes:
            task.tags = list(changes["tags"])

        # Generate stable block ID if task doesn't have one (helps with migration)
        if not task.block_id:
            # Collect existing block IDs to avoid collisions
            existing_block_ids: Set[str] = set()
            for line in lines:
                task_data = parse_markdown_task(line.rstrip())
                if task_data and task_data.get("block_id"):
                    existing_block_ids.add(task_data["block_id"])
            
            # Generate stable UUID for this task
            task.block_id = self._stable_uuid_for_task(
                vault_path=task.vault_path,
                file_path=task.file_path,
                line_number=task.line_number,
                description=task.description,
                existing_ids=existing_block_ids
            )
            # Update UUID to match the canonical format that list_tasks will generate
            task.uuid = f"obs-{task.block_id}"
            self.logger.debug(f"Generated stable block ID '{task.block_id}' and updated UUID to '{task.uuid}' for task during update")

        new_line = format_task_line(
            description=task.description,
            status=task.status,
            due_date=task.due_date,
            completion_date=task.completion_date,
            priority=task.priority,
            tags=task.tags,
            block_id=task.block_id,
            indent=indent,
        )

        lines[line_index] = f"{new_line}\n"

        with open(file_path, "w", encoding="utf-8") as handle:
            handle.writelines(lines)

        task.raw_line = new_line
        task.modified_at = datetime.now(timezone.utc).isoformat()

        return task
    
    def delete_task(self, task: ObsidianTask) -> bool:
        """Delete a task from a markdown file."""
        vault_path = task.vault_path
        file_path = os.path.join(vault_path, task.file_path)
        
        if not os.path.exists(file_path):
            return False
        
        # Read file
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Find and remove task line
        if task.line_number > 0 and task.line_number <= len(lines):
            line_idx = task.line_number - 1
            line = lines[line_idx]
            
            # Verify it's the right task
            if task.block_id and f"^{task.block_id}" in line:
                lines.pop(line_idx)
                
                # Write back
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.writelines(lines)
                
                return True
        
        return False