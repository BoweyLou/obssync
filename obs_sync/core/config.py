"""
Configuration management for obs-sync.
"""

import json
import os
from pathlib import Path
from typing import Optional

from .models import SyncConfig
from .paths import get_path_manager


def get_default_config_path() -> Path:
    """Get the default configuration file path."""
    manager = get_path_manager()
    # Trigger migration on first access if needed
    manager.migrate_from_legacy()
    return manager.config_path


def load_config(config_path: Optional[str] = None) -> SyncConfig:
    """
    Load configuration from file or return defaults.

    Args:
        config_path: Optional path to config file. Uses default if not provided.

    Returns:
        SyncConfig object
    """
    if config_path is None:
        manager = get_path_manager()
        # Try migration first
        manager.migrate_from_legacy()
        # Get config file with fallback to legacy location
        config_file = manager.get_file_with_fallback(manager.CONFIG_FILE)
        config_path = str(config_file) if config_file and config_file.exists() else str(manager.config_path)

    return SyncConfig.load_from_file(config_path)


def save_config(config: SyncConfig, config_path: Optional[str] = None):
    """
    Save configuration to file.

    Args:
        config: SyncConfig object to save
        config_path: Optional path to save to. Uses default if not provided.
    """
    if config_path is None:
        manager = get_path_manager()
        # Ensure working directories exist
        manager.ensure_directories()
        config_path = str(manager.config_path)

    # Ensure config directory exists
    config_dir = os.path.dirname(config_path)
    os.makedirs(config_dir, exist_ok=True)

    config.save_to_file(config_path)


def get_data_dir() -> Path:
    """Get the data directory for indices and links."""
    manager = get_path_manager()
    manager.ensure_directories()
    return manager.data_dir


def get_backup_dir() -> Path:
    """Get the backup directory."""
    manager = get_path_manager()
    manager.ensure_directories()
    return manager.backup_dir


def get_log_dir() -> Path:
    """Get the log directory."""
    manager = get_path_manager()
    manager.ensure_directories()
    return manager.log_dir