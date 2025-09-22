"""
Configuration management for obs-sync.
"""

import json
import os
from pathlib import Path
from typing import Optional

from .models import SyncConfig


DEFAULT_CONFIG_DIR = Path.home() / ".config" / "obs-sync"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"


def get_default_config_path() -> Path:
    """Get the default configuration file path."""
    return DEFAULT_CONFIG_FILE


def load_config(config_path: Optional[str] = None) -> SyncConfig:
    """
    Load configuration from file or return defaults.
    
    Args:
        config_path: Optional path to config file. Uses default if not provided.
    
    Returns:
        SyncConfig object
    """
    if config_path is None:
        config_path = str(get_default_config_path())
    
    return SyncConfig.load_from_file(config_path)


def save_config(config: SyncConfig, config_path: Optional[str] = None):
    """
    Save configuration to file.
    
    Args:
        config: SyncConfig object to save
        config_path: Optional path to save to. Uses default if not provided.
    """
    if config_path is None:
        config_path = str(get_default_config_path())
    
    # Ensure config directory exists
    config_dir = os.path.dirname(config_path)
    os.makedirs(config_dir, exist_ok=True)
    
    config.save_to_file(config_path)


def get_data_dir() -> Path:
    """Get the data directory for indices and links."""
    data_dir = DEFAULT_CONFIG_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_backup_dir() -> Path:
    """Get the backup directory."""
    backup_dir = DEFAULT_CONFIG_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def get_log_dir() -> Path:
    """Get the log directory."""
    log_dir = DEFAULT_CONFIG_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir