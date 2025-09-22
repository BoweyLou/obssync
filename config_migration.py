#!/usr/bin/env python3
"""
Configuration Migration Helper

Migrates from old app_config.py based configuration to new simplified
obs_sync configuration format.
"""

import json
import os
from pathlib import Path


def migrate_config():
    """Migrate old configuration to new format."""
    
    # Try to load old config
    old_config_path = Path.home() / ".config" / "obs-tools" / "app.json"
    new_config_path = Path.home() / ".config" / "obs-sync" / "config.json"
    
    if not old_config_path.exists():
        print("No old configuration found to migrate")
        return False
        
    print(f"Migrating configuration from {old_config_path}")
    
    try:
        with open(old_config_path) as f:
            old_config = json.load(f)
            
        # Create new config structure
        new_config = {
            "vaults": [],
            "reminders_lists": [],
            "sync": {
                "min_score": old_config.get("min_score", 0.75),
                "days_tolerance": old_config.get("days_tolerance", 1),
                "include_completed": old_config.get("include_done", False)
            }
        }
        
        # Migrate vault configuration
        vaults_file = Path.home() / ".config" / "obsidian_vaults.json"
        if vaults_file.exists():
            with open(vaults_file) as f:
                vaults_data = json.load(f)
                if isinstance(vaults_data, list):
                    new_config["vaults"] = vaults_data
                elif isinstance(vaults_data, dict) and "vaults" in vaults_data:
                    new_config["vaults"] = vaults_data["vaults"]
                    
        # Migrate reminders lists
        lists_file = Path.home() / ".config" / "reminders_lists.json"
        if lists_file.exists():
            with open(lists_file) as f:
                lists_data = json.load(f)
                if isinstance(lists_data, list):
                    new_config["reminders_lists"] = lists_data
                elif isinstance(lists_data, dict) and "lists" in lists_data:
                    new_config["reminders_lists"] = lists_data["lists"]
                    
        # Create new config directory
        new_config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write new config
        with open(new_config_path, 'w') as f:
            json.dump(new_config, f, indent=2)
            
        print(f"Configuration migrated to {new_config_path}")
        print("Old configuration files have been preserved")
        return True
        
    except Exception as e:
        print(f"Error migrating configuration: {e}")
        return False


if __name__ == "__main__":
    migrate_config()