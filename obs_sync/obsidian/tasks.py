"""Task manager for Obsidian CRUD operations."""

import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
import logging

from ..core.models import ObsidianTask, Priority, TaskStatus
from .parser import format_task_line, parse_markdown_task


class ObsidianTaskManager:
    """Manages CRUD operations for Obsidian tasks."""

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self.include_completed = True  # Default to including completed tasks

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

            for line_num, raw_line in enumerate(lines, 1):
                task_data = parse_markdown_task(raw_line.rstrip())
                if not task_data:
                    continue

                block_id = task_data.get("block_id")
                uuid_value = block_id or uuid.uuid4().hex[:8]

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

        if not task.block_id:
            task.block_id = f"t-{uuid.uuid4().hex[:12]}"

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