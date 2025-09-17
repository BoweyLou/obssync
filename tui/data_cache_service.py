#!/usr/bin/env python3
"""
Data Cache Service - Manages caching and diffing of task indices and links.

This service handles loading, caching, and computing differences for
Obsidian tasks, Reminders tasks, and sync links.
"""

from __future__ import annotations

import json
import os
import time
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime


class DataCacheService:
    """Manages data caching and difference computation."""

    def __init__(self):
        self._data_cache = {
            'obs': {'data': None, 'mtime': 0},
            'rem': {'data': None, 'mtime': 0},
            'links': {'data': None, 'mtime': 0}
        }
        self._last_diff_cache = None
        self._last_diff_time = 0
        self.last_diff = {"obs": None, "rem": None, "links": None}
        self.last_link_changes = {"new": [], "replaced": []}
        self._prev_link_pairs: set[tuple[str, str]] = set()

    def load_cached_data(self, data_type: str, path: str) -> Optional[Dict[str, Any]]:
        """
        Load data with caching based on file modification time.

        Args:
            data_type: Type of data ('obs', 'rem', or 'links')
            path: Path to the data file

        Returns:
            Loaded data or None if not available
        """
        if data_type not in self._data_cache:
            return None

        expanded_path = os.path.expanduser(path)
        if not os.path.exists(expanded_path):
            return None

        try:
            current_mtime = os.path.getmtime(expanded_path)
            cache_entry = self._data_cache[data_type]

            # Check if cache is still valid
            if cache_entry['data'] is not None and cache_entry['mtime'] == current_mtime:
                return cache_entry['data']

            # Load fresh data
            if data_type in ('obs', 'rem'):
                data = self._load_index(expanded_path)
            elif data_type == 'links':
                data = self._load_links(expanded_path)
            else:
                return None

            # Update cache
            cache_entry['data'] = data
            cache_entry['mtime'] = current_mtime
            return data

        except Exception:
            return None

    def _load_index(self, path: str) -> Optional[Dict[str, Any]]:
        """Load a task index file."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    def _load_links(self, path: str) -> Optional[List[Dict[str, Any]]]:
        """Load a sync links file."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('links', [])
        except Exception:
            return None

    def count_tasks(self, path: str) -> int:
        """Count tasks in an index file."""
        expanded_path = os.path.expanduser(path)
        if not os.path.exists(expanded_path):
            return 0

        try:
            with open(expanded_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return len(data.get('tasks', {}))
        except Exception:
            return 0

    def count_links(self, path: str) -> int:
        """Count links in a sync links file."""
        expanded_path = os.path.expanduser(path)
        if not os.path.exists(expanded_path):
            return 0

        try:
            with open(expanded_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return len(data.get('links', []))
        except Exception:
            return 0

    def compute_diff(self, prev_data: Dict[str, Any], curr_data: Dict[str, Any],
                     system: str) -> Dict[str, Any]:
        """
        Compute differences between two task indices.

        Args:
            prev_data: Previous index data
            curr_data: Current index data
            system: System name ('obs' or 'rem')

        Returns:
            Dictionary with diff information
        """
        if not prev_data or not curr_data:
            return None

        prev_tasks = prev_data.get('tasks', {})
        curr_tasks = curr_data.get('tasks', {})

        added = []
        modified = []
        removed = []

        # Find added and modified
        for uid, task in curr_tasks.items():
            if uid not in prev_tasks:
                added.append(self._digest_task(task, system))
            elif self._task_changed(prev_tasks[uid], task):
                modified.append(self._digest_task(task, system))

        # Find removed
        for uid, task in prev_tasks.items():
            if uid not in curr_tasks:
                removed.append(self._digest_task(task, system))

        return {
            'added': added,
            'modified': modified,
            'removed': removed,
            'total_before': len(prev_tasks),
            'total_after': len(curr_tasks)
        }

    def _digest_task(self, task: Dict[str, Any], system: str) -> str:
        """Create a digest string for a task."""
        if system == 'obs':
            return self._digest_obs(task)
        elif system == 'rem':
            return self._digest_rem(task)
        return str(task.get('uuid', 'unknown'))

    def _digest_obs(self, rec: dict) -> str:
        """Create a digest string for an Obsidian task."""
        d = rec.get("description", "")
        if len(d) > 50:
            d = d[:50] + "..."
        fn = rec.get("source", {}).get("file", "")
        if "/" in fn:
            fn = fn.split("/")[-1]
        if len(fn) > 20:
            fn = fn[:20] + "..."
        return f"{d} [{fn}]"

    def _digest_rem(self, rec: dict) -> str:
        """Create a digest string for a Reminders task."""
        d = rec.get("description", "")
        if len(d) > 50:
            d = d[:50] + "..."
        lst = rec.get("list", {}).get("title", "")
        if len(lst) > 20:
            lst = lst[:20] + "..."
        return f"{d} [{lst}]"

    def _task_changed(self, old_task: Dict[str, Any], new_task: Dict[str, Any]) -> bool:
        """Check if a task has changed between versions."""
        # Compare key fields
        fields_to_check = ['description', 'status', 'due', 'priority', 'notes']
        for field in fields_to_check:
            if old_task.get(field) != new_task.get(field):
                return True
        return False

    def compute_link_diff(self, prev_links: List[Dict[str, Any]],
                          curr_links: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """
        Compute differences between link sets.

        Args:
            prev_links: Previous links
            curr_links: Current links

        Returns:
            Dictionary with 'new' and 'replaced' link descriptions
        """
        if not prev_links:
            prev_links = []
        if not curr_links:
            curr_links = []

        # Use repository standard 'obs_uuid' with backwards compatibility fallback
        prev_map = {(link.get('obs_uuid') or link.get('obsidian_uuid')): link for link in prev_links}
        curr_map = {(link.get('obs_uuid') or link.get('obsidian_uuid')): link for link in curr_links}

        new_links = []
        replaced_links = []

        for obs_id, curr_link in curr_map.items():
            if obs_id not in prev_map:
                new_links.append(self._format_link(curr_link))
            else:
                prev_link = prev_map[obs_id]
                # Use repository standard 'rem_uuid' with backwards compatibility fallback
                prev_rem_uuid = prev_link.get('rem_uuid') or prev_link.get('reminders_uuid')
                curr_rem_uuid = curr_link.get('rem_uuid') or curr_link.get('reminders_uuid')
                if prev_rem_uuid != curr_rem_uuid:
                    replaced_links.append(self._format_link(curr_link))

        return {'new': new_links, 'replaced': replaced_links}

    def _format_link(self, link: Dict[str, Any]) -> str:
        """Format a link for display."""
        obs_desc = link.get('obsidian_description', '')[:40]
        rem_desc = link.get('reminders_description', '')[:40]
        confidence = link.get('confidence', 0)
        return f"[{confidence:.0%}] {obs_desc} <-> {rem_desc}"

    def clear_cache(self, data_type: Optional[str] = None):
        """Clear cached data."""
        if data_type:
            if data_type in self._data_cache:
                self._data_cache[data_type] = {'data': None, 'mtime': 0}
        else:
            # Clear all caches
            for key in self._data_cache:
                self._data_cache[key] = {'data': None, 'mtime': 0}
            self._last_diff_cache = None
            self._last_diff_time = 0