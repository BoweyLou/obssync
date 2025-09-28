"""Task manager for Reminders CRUD operations."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import logging

from ..core.models import Priority, RemindersTask, TaskStatus
from ..utils.date import format_date, parse_date
from .gateway import RemindersGateway


class RemindersTaskManager:
    """Manages CRUD operations for Reminders tasks."""

    def __init__(
        self,
        gateway: Optional[RemindersGateway] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.gateway = gateway or RemindersGateway(logger=logger)
        self.logger = logger or logging.getLogger(__name__)
        self.include_completed = True  # Default to including completed tasks

    def list_tasks(self, list_ids: Optional[List[str]] = None, include_completed: Optional[bool] = None) -> List[RemindersTask]:
        """List all tasks from specified lists.
        
        Args:
            list_ids: Optional list of calendar IDs to fetch from
            include_completed: Whether to include completed tasks. If None, uses instance default.
        """
        reminders = self.gateway.get_reminders(list_ids)

        tasks: List[RemindersTask] = []
        for rem in reminders:
            status = TaskStatus.DONE if rem.completed else TaskStatus.TODO

            priority = None
            if rem.priority == "high":
                priority = Priority.HIGH
            elif rem.priority == "medium":
                priority = Priority.MEDIUM
            elif rem.priority == "low":
                priority = Priority.LOW

            task = RemindersTask(
                uuid=rem.uuid,
                item_id=rem.uuid,
                calendar_id=rem.list_id or "",
                list_name=rem.list_name or "Reminders",
                status=status,
                title=rem.title,
                due_date=parse_date(rem.due_date),
                priority=priority,
                notes=rem.notes,
                tags=rem.tags,  # Include tags from gateway
                created_at=rem.created_at,
                modified_at=rem.modified_at,
            )
            tasks.append(task)
        
        # Filter out completed tasks if requested
        if include_completed is None:
            include_completed = self.include_completed
            
        if not include_completed:
            tasks = [t for t in tasks if t.status != TaskStatus.DONE]
            self.logger.debug(f"Filtered to {len(tasks)} active tasks (excluded completed)")

        return tasks
    
    def create_task(
        self, list_id: str, task: RemindersTask
    ) -> Optional[RemindersTask]:
        """Create a new task in Reminders."""
        priority = None
        if task.priority == Priority.HIGH:
            priority = "high"
        elif task.priority == Priority.MEDIUM:
            priority = "medium"
        elif task.priority == Priority.LOW:
            priority = "low"

        due_str = format_date(task.due_date)

        uuid_value = self.gateway.create_reminder(
            title=task.title,
            list_id=list_id,
            due_date=due_str,
            priority=priority,
            notes=task.notes,
            tags=task.tags,  # Include tags for creation
        )

        if uuid_value:
            now = datetime.now(timezone.utc).isoformat()
            task.uuid = uuid_value
            task.item_id = uuid_value
            task.calendar_id = list_id
            task.created_at = now
            task.modified_at = now
            return task

        return None
    
    def update_task(
        self, task: RemindersTask, changes: Dict
    ) -> Optional[RemindersTask]:
        """Update an existing task."""
        updates: Dict[str, Any] = {}

        if "title" in changes:
            updates["title"] = changes["title"]
            task.title = changes["title"]

        if "status" in changes:
            status = changes["status"]
            if isinstance(status, TaskStatus):
                updates["completed"] = status == TaskStatus.DONE
                task.status = status
            elif isinstance(status, str):
                updates["completed"] = status == "done"
                task.status = TaskStatus.DONE if status == "done" else TaskStatus.TODO

        if "due_date" in changes:
            task.due_date = changes["due_date"]
            updates["due_date"] = format_date(task.due_date)

        if "priority" in changes:
            priority = changes["priority"]
            if isinstance(priority, Priority):
                task.priority = priority
                if priority == Priority.HIGH:
                    updates["priority"] = "high"
                elif priority == Priority.MEDIUM:
                    updates["priority"] = "medium"
                elif priority == Priority.LOW:
                    updates["priority"] = "low"
            elif isinstance(priority, str):
                normalized = priority.lower()
                if normalized in ("high", "medium", "low"):
                    task.priority = {
                        "high": Priority.HIGH,
                        "medium": Priority.MEDIUM,
                        "low": Priority.LOW,
                    }[normalized]
                    updates["priority"] = normalized
                else:
                    task.priority = None
                    updates["priority"] = None
            else:
                task.priority = None
                updates["priority"] = None

        if "notes" in changes:
            updates["notes"] = changes["notes"]
            task.notes = changes["notes"]
        
        if "tags" in changes:
            updates["tags"] = changes["tags"]
            task.tags = changes["tags"]  # Update tags

        if "calendar_id" in changes:
            new_calendar_id = changes["calendar_id"]
            updates["calendar_id"] = new_calendar_id
            task.calendar_id = new_calendar_id

        if not updates:
            return task

        if self.gateway.update_reminder(task.uuid, **updates):
            task.modified_at = datetime.now(timezone.utc).isoformat()
            return task

        return None
    
    def delete_task(self, task: RemindersTask) -> bool:
        """Delete a task from Reminders."""
        return self.gateway.delete_reminder(task.uuid)