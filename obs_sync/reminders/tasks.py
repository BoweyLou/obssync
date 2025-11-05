"""Task manager for Reminders CRUD operations."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import logging

from ..core.models import Priority, RemindersTask, TaskStatus
from ..utils.date import format_date, parse_date
from .gateway import RemindersGateway


class RemindersTaskManager:
    """Manages CRUD operations for Reminders tasks."""

    CANCELLED_TAG = "cancelled"
    CANCELLED_LIST_NAME = "Cancelled"

    def __init__(
        self,
        gateway: Optional[RemindersGateway] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.gateway = gateway or RemindersGateway(logger=logger)
        self.logger = logger or logging.getLogger(__name__)
        self.include_completed = True  # Default to including completed tasks
        self._cancelled_list_id: Optional[str] = None

    def get_cancelled_list_id(self) -> Optional[str]:
        """Get the ID of the Cancelled list, creating it if necessary.

        Returns:
            The list ID if found or created, None if creation fails
        """
        if self._cancelled_list_id:
            return self._cancelled_list_id

        # Check if the Cancelled list exists
        try:
            all_lists = self.gateway.get_lists()
            for lst in all_lists:
                if lst.get('name') == self.CANCELLED_LIST_NAME:
                    self._cancelled_list_id = lst.get('id')
                    self.logger.debug(f"Found existing Cancelled list: {self._cancelled_list_id}")
                    return self._cancelled_list_id

            # List doesn't exist - log a warning
            # Note: EventKit doesn't provide an API to create lists programmatically
            # Users must create the 'Cancelled' list manually in the Reminders app
            self.logger.warning(
                f"Cancelled list '{self.CANCELLED_LIST_NAME}' not found. "
                "Please create this list manually in the Reminders app."
            )
            return None

        except Exception as e:
            self.logger.error(f"Failed to get Cancelled list: {e}")
            return None

    def list_tasks(self, list_ids: Optional[List[str]] = None, include_completed: Optional[bool] = None) -> List[RemindersTask]:
        """List all tasks from specified lists.
        
        Args:
            list_ids: Optional list of calendar IDs to fetch from
            include_completed: Whether to include completed tasks. If None, uses instance default.
        """
        reminders = self.gateway.get_reminders(list_ids)

        # Get the Cancelled list ID for status detection
        cancelled_list_id = self.get_cancelled_list_id()

        tasks: List[RemindersTask] = []
        for rem in reminders:
            # Determine status: check for cancelled tasks first
            # A task is cancelled if it's in the Cancelled list AND has the cancelled tag
            is_cancelled = (
                cancelled_list_id is not None
                and rem.list_id == cancelled_list_id
                and self.CANCELLED_TAG in rem.tags
            )

            if is_cancelled:
                status = TaskStatus.CANCELLED
            elif rem.completed:
                status = TaskStatus.DONE
            else:
                status = TaskStatus.TODO

            priority = None
            if rem.priority == "high":
                priority = Priority.HIGH
            elif rem.priority == "medium":
                priority = Priority.MEDIUM
            elif rem.priority == "low":
                priority = Priority.LOW

            # Parse datetime fields from ISO strings
            created_at_dt = None
            if rem.created_at:
                try:
                    created_at_dt = datetime.fromisoformat(rem.created_at)
                except (ValueError, TypeError):
                    pass
            
            modified_at_dt = None
            if rem.modified_at:
                try:
                    modified_at_dt = datetime.fromisoformat(rem.modified_at)
                except (ValueError, TypeError):
                    pass
            
            # For completed tasks, use modified_at as completion_date proxy
            completion_date = None
            if status == TaskStatus.DONE and modified_at_dt:
                completion_date = modified_at_dt.date()
            
            task = RemindersTask(
                uuid=rem.uuid,
                item_id=rem.uuid,
                calendar_id=rem.list_id or "",
                list_name=rem.list_name or "Reminders",
                status=status,
                title=rem.title,
                due_date=parse_date(rem.due_date),
                priority=priority,
                url=rem.url,
                notes=rem.notes,
                tags=rem.tags,  # Include tags from gateway
                created_at=created_at_dt,
                modified_at=modified_at_dt,
                completion_date=completion_date,
            )
            tasks.append(task)
        
        # Filter out completed and cancelled tasks if requested
        if include_completed is None:
            include_completed = self.include_completed

        if not include_completed:
            tasks = [t for t in tasks if t.status not in (TaskStatus.DONE, TaskStatus.CANCELLED)]
            self.logger.debug(f"Filtered to {len(tasks)} active tasks (excluded completed and cancelled)")

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
            url=task.url,
            notes=task.notes,
            tags=task.tags,  # Include tags for creation
        )

        self.logger.debug(f"RemindersGateway.create_reminder returned uuid: {uuid_value}")
        
        if uuid_value:
            now = datetime.now(timezone.utc)
            task.uuid = uuid_value
            task.item_id = uuid_value
            task.calendar_id = list_id
            task.created_at = now
            task.modified_at = now
            self.logger.debug(f"Returning created task with uuid: {task.uuid}")
            return task

        self.logger.warning(f"Failed to create Reminders task: {task.title}")
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
                # Handle cancelled status specially
                if status == TaskStatus.CANCELLED:
                    # For cancelled tasks:
                    # 1. Remove due date
                    # 2. Add cancelled tag
                    # 3. Move to Cancelled list
                    updates["completed"] = False
                    updates["due_date"] = None
                    task.due_date = None

                    # Add cancelled tag if not already present
                    if self.CANCELLED_TAG not in task.tags:
                        task.tags.append(self.CANCELLED_TAG)
                    updates["tags"] = task.tags

                    # Move to Cancelled list
                    cancelled_list_id = self.get_cancelled_list_id()
                    if cancelled_list_id:
                        updates["calendar_id"] = cancelled_list_id
                        task.calendar_id = cancelled_list_id
                    else:
                        self.logger.warning(
                            f"Cannot move task '{task.title}' to Cancelled list - list not found. "
                            "Please create a 'Cancelled' list in the Reminders app."
                        )

                    task.status = status
                else:
                    # For DONE or TODO status
                    updates["completed"] = status == TaskStatus.DONE
                    task.status = status

                    # Remove cancelled tag if task is no longer cancelled
                    if self.CANCELLED_TAG in task.tags:
                        task.tags.remove(self.CANCELLED_TAG)
                        updates["tags"] = task.tags
            elif isinstance(status, str):
                if status == "cancelled":
                    # Handle string "cancelled" status
                    updates["completed"] = False
                    updates["due_date"] = None
                    task.due_date = None

                    if self.CANCELLED_TAG not in task.tags:
                        task.tags.append(self.CANCELLED_TAG)
                    updates["tags"] = task.tags

                    cancelled_list_id = self.get_cancelled_list_id()
                    if cancelled_list_id:
                        updates["calendar_id"] = cancelled_list_id
                        task.calendar_id = cancelled_list_id

                    task.status = TaskStatus.CANCELLED
                else:
                    updates["completed"] = status == "done"
                    task.status = TaskStatus.DONE if status == "done" else TaskStatus.TODO

                    # Remove cancelled tag
                    if self.CANCELLED_TAG in task.tags:
                        task.tags.remove(self.CANCELLED_TAG)
                        updates["tags"] = task.tags

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

        if "url" in changes:
            updates["url"] = changes["url"]
            task.url = changes["url"]

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
            task.modified_at = datetime.now(timezone.utc)
            # Capture completion_date when status flips to done
            if "completed" in updates and updates["completed"] and task.status == TaskStatus.DONE:
                if not task.completion_date:
                    task.completion_date = datetime.now(timezone.utc).date()
            return task

        return None
    
    def delete_task(self, task: RemindersTask) -> bool:
        """Delete a task from Reminders."""
        return self.gateway.delete_reminder(task.uuid)
