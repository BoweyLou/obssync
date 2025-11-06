"""
Markdown task parsing utilities.
"""

import re
from datetime import date
from typing import Optional, Dict, Any, Tuple

from obs_sync.core.models import TaskStatus, Priority
from obs_sync.utils.date import parse_date


# Regular expressions for parsing tasks
TASK_RE = re.compile(r'^(\s*)[-*]\s+\[([xX\- ])\]\s+(.*)$')
BLOCK_ID_RE = re.compile(r'\^([a-zA-Z0-9-]+)\s*$')
DUE_DATE_RE = re.compile(r'📅\s*(\d{4}-\d{1,2}-\d{1,2})')
COMPLETION_DATE_RE = re.compile(r'✅\s*(\d{4}-\d{1,2}-\d{1,2})')
PRIORITY_RE = re.compile(r'([⏫🔼🔽])')
# Allow hyphenated tags so markers like #from-reminders stick together
TAG_RE = re.compile(r'#([a-zA-Z0-9_\-/]+)')


def parse_markdown_task(line: str) -> Optional[Dict[str, Any]]:
    """
    Parse a markdown task line into components.
    
    Args:
        line: Raw markdown line
    
    Returns:
        Dictionary with parsed task data or None if not a task
    """
    match = TASK_RE.match(line)
    if not match:
        return None
    
    indent = match.group(1)
    status_char = match.group(2)
    content = match.group(3)
    
    # Parse status
    if status_char.lower() == 'x':
        status = TaskStatus.DONE
    elif status_char == '-':
        status = TaskStatus.CANCELLED
    else:
        status = TaskStatus.TODO
    
    # Extract block ID if present
    block_id = None
    block_match = BLOCK_ID_RE.search(content)
    if block_match:
        block_id = block_match.group(1)
        # Remove block ID from content
        content = content[:block_match.start()].rstrip()
    
    # Extract completion date
    completion_date = None
    completion_match = COMPLETION_DATE_RE.search(content)
    if completion_match:
        completion_date = parse_date(completion_match.group(1))
        # Remove completion date from content
        content = COMPLETION_DATE_RE.sub('', content).strip()
    
    # Extract due date
    due_date = None
    due_match = DUE_DATE_RE.search(content)
    if due_match:
        due_date = parse_date(due_match.group(1))
        # Remove due date from content
        content = DUE_DATE_RE.sub('', content).strip()
    
    # Extract priority
    priority = None
    priority_match = PRIORITY_RE.search(content)
    if priority_match:
        symbol = priority_match.group(1)
        priority_map = {
            '⏫': Priority.HIGH,
            '🔼': Priority.MEDIUM,
            '🔽': Priority.LOW
        }
        priority = priority_map.get(symbol)
        # Remove priority from content
        content = PRIORITY_RE.sub('', content).strip()
    
    # Extract tags
    tags = []
    for tag_match in TAG_RE.finditer(content):
        tags.append(f"#{tag_match.group(1)}")

    # Derive cancelled status from tag marker
    if any(tag.lower() == "#cancelled" for tag in tags):
        status = TaskStatus.CANCELLED
    
    # Remove tags from description
    description = TAG_RE.sub('', content).strip()
    
    return {
        'status': status,
        'description': description,
        'block_id': block_id,
        'due_date': due_date,
        'completion_date': completion_date,
        'priority': priority,
        'tags': tags,
        'indent': indent,
        'raw_line': line
    }


def format_task_line(
    description: str,
    status: TaskStatus = TaskStatus.TODO,
    due_date: Optional[date] = None,
    completion_date: Optional[date] = None,
    priority: Optional[Priority] = None,
    tags: Optional[list] = None,
    block_id: Optional[str] = None,
    indent: str = ""
) -> str:
    """
    Format a task into markdown line format.
    
    Args:
        description: Task description
        status: Task status
        due_date: Optional due date
        priority: Optional priority
        tags: Optional list of tags
        block_id: Optional block ID
        indent: Indentation string
    
    Returns:
        Formatted markdown task line
    """
    # Status checkbox
    if status == TaskStatus.DONE:
        status_char = 'x'
    elif status == TaskStatus.CANCELLED:
        status_char = '-'
    else:
        status_char = ' '
    parts = [f"{indent}- [{status_char}]"]
    
    # Description
    parts.append(description)
    
    # Completion date
    if completion_date:
        parts.append(f"✅ {completion_date.strftime('%Y-%m-%d')}")
    
    # Priority
    if priority:
        priority_symbols = {
            Priority.HIGH: '⏫',
            Priority.MEDIUM: '🔼',
            Priority.LOW: '🔽'
        }
        if priority in priority_symbols:
            parts.append(priority_symbols[priority])
    
    # Due date
    if due_date:
        parts.append(f"📅 {due_date.strftime('%Y-%m-%d')}")
    
    # Tags
    normalized_tags = list(tags or [])
    if status == TaskStatus.CANCELLED:
        if not any(tag.lower() == "#cancelled" for tag in normalized_tags):
            normalized_tags.append("#cancelled")

    if normalized_tags:
        for tag in normalized_tags:
            if not tag.startswith('#'):
                tag = f"#{tag}"
            parts.append(tag)
    
    # Block ID
    if block_id:
        parts.append(f"^{block_id}")
    
    return ' '.join(parts)
