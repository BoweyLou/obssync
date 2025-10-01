"""Sync module for bidirectional task synchronization."""

from .engine import SyncEngine
from .matcher import TaskMatcher
from .resolver import ConflictResolver
from .deduplicator import TaskDeduplicator, DuplicateCluster, DeduplicationResults

__all__ = ['SyncEngine', 'TaskMatcher', 'ConflictResolver', 'TaskDeduplicator', 'DuplicateCluster', 'DeduplicationResults']