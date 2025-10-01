"""
Exception classes for obs-sync.
"""


class ObsSyncError(Exception):
    """Base exception for all obs-sync errors."""
    pass


class ConfigurationError(ObsSyncError):
    """Raised when configuration is invalid or missing."""
    pass


class VaultNotFoundError(ObsSyncError):
    """Raised when an Obsidian vault cannot be found."""
    pass


class RemindersError(ObsSyncError):
    """Base exception for Reminders-related errors."""
    pass


class AuthorizationError(RemindersError):
    """Raised when EventKit authorization fails."""
    pass


class EventKitImportError(RemindersError):
    """Raised when EventKit/PyObjC dependencies are not available."""
    pass


class SyncError(ObsSyncError):
    """Raised when sync operations fail."""
    pass


class TaskNotFoundError(ObsSyncError):
    """Raised when a task cannot be found."""
    pass