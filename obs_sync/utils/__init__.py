"""
Utility functions for obs-sync.
"""

from .io import safe_read_json, safe_write_json, atomic_write
from .date import parse_date, format_date, dates_equal
from .text import normalize_text, calculate_similarity
from .prompts import (
    format_task_for_display, display_duplicate_cluster,
    confirm_deduplication, prompt_for_keeps, show_deduplication_summary
)
from .launchd import (
    is_macos, get_launchagent_path, install_agent, uninstall_agent,
    load_agent, unload_agent, is_agent_loaded, get_obs_sync_executable,
    describe_interval
)
from .macos import set_process_name

__all__ = [
    # I/O utilities
    'safe_read_json',
    'safe_write_json',
    'atomic_write',
    # Date utilities
    'parse_date',
    'format_date',
    'dates_equal',
    # Text utilities
    'normalize_text',
    'calculate_similarity',
    # Prompt utilities
    'format_task_for_display',
    'display_duplicate_cluster',
    'confirm_deduplication',
    'prompt_for_keeps',
    'show_deduplication_summary',
    # LaunchAgent utilities (macOS)
    'is_macos',
    'get_launchagent_path',
    'install_agent',
    'uninstall_agent',
    'load_agent',
    'unload_agent',
    'is_agent_loaded',
    'get_obs_sync_executable',
    'describe_interval',
    # macOS helpers
    'set_process_name'
]