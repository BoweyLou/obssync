#!/usr/bin/env python3
"""
Configuration Service - Handles application configuration and preferences.

This service manages loading, saving, and updating application configuration,
providing a clean separation of concerns for configuration management.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from typing import Dict, Any, Tuple

import app_config as cfg


class ConfigurationService:
    """Manages application configuration and preferences."""

    def __init__(self):
        self._prefs = None
        self._paths = None
        self._config_loaded = False

    def load_config(self) -> Tuple[Any, Dict[str, str]]:
        """Load application configuration and paths."""
        self._prefs, self._paths = cfg.load_app_config()
        self._config_loaded = True
        return self._prefs, self._paths

    def get_preferences(self) -> Any:
        """Get current preferences, loading if necessary."""
        if not self._config_loaded:
            self.load_config()
        return self._prefs

    def get_paths(self) -> Dict[str, str]:
        """Get configured paths, loading if necessary."""
        if not self._config_loaded:
            self.load_config()
        return self._paths

    def save_preferences(self, prefs: Any = None) -> None:
        """Save preferences to disk."""
        if prefs:
            self._prefs = prefs
        if self._prefs:
            cfg.save_app_config(self._prefs)

    def update_preference(self, key: str, value: Any) -> None:
        """Update a single preference value."""
        if not self._config_loaded:
            self.load_config()
        setattr(self._prefs, key, value)
        self.save_preferences()

    def get_managed_python_path(self) -> str:
        """Get the path to the managed Python environment."""
        return os.path.expanduser("~/Library/Application Support/obs-tools/venv/bin/python3")

    def get_vault_configs(self) -> list:
        """Load Obsidian vault configurations."""
        vault_config_path = self.get_paths().get("obsidian_config", "~/.config/obsidian_vaults.json")
        vault_config_path = os.path.expanduser(vault_config_path)

        if not os.path.exists(vault_config_path):
            return []

        try:
            with open(vault_config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("vaults", [])
        except Exception:
            return []

    def get_current_vault_name(self) -> str:
        """Get the name of the currently selected vault."""
        vaults = self.get_vault_configs()
        prefs = self.get_preferences()

        if not vaults:
            return "No vaults configured"

        vault_idx = getattr(prefs, 'vault_index', 0)
        if 0 <= vault_idx < len(vaults):
            vault = vaults[vault_idx]
            return vault.get("name", "Unknown")

        return "Invalid vault selection"