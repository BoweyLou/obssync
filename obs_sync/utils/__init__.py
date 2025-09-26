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
    'show_deduplication_summary'
]