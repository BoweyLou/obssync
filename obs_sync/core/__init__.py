"""
Core module for obs-sync - contains domain models, configuration, and exceptions.
"""

from .models import (
    ObsidianTask,
    RemindersTask,
    Vault,
    RemindersList,
    SyncLink,
    TaskStatus,
    Priority,
    SyncConfig
)

from .exceptions import (
    ObsSyncError,
    ConfigurationError,
    VaultNotFoundError,
    RemindersError,
    SyncError
)

__all__ = [
    # Models
    'ObsidianTask',
    'RemindersTask',
    'Vault',
    'RemindersList',
    'SyncLink',
    'TaskStatus',
    'Priority',
    'SyncConfig',
    # Exceptions
    'ObsSyncError',
    'ConfigurationError',
    'VaultNotFoundError',
    'RemindersError',
    'SyncError'
]