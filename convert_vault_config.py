#!/usr/bin/env python3
"""
Convert legacy obsidian_vaults.json format to structured format with vault_id and associated_list_id
"""

import json
import sys
import os
from datetime import datetime, timezone

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from lib.vault_organization import generate_stable_vault_id
from app_config import get_path

def convert_vault_config():
    """Convert legacy vault config to structured format."""

    print("🔄 Converting vault configuration to structured format")
    print("=" * 50)

    # Load current vault config
    vault_config_path = get_path("obsidian_vaults")
    with open(vault_config_path, 'r') as f:
        current_config = json.load(f)

    print(f"📖 Current format: {type(current_config).__name__}")

    # Load reminders config to map list names to IDs
    reminders_config_path = get_path("reminders_lists")
    with open(reminders_config_path, 'r') as f:
        reminders_data = json.load(f)

    if isinstance(reminders_data, dict):
        reminders_lists = reminders_data.get("lists", [])
    else:
        reminders_lists = reminders_data

    # Create list name to ID mapping
    list_name_to_id = {}
    print(f"\n📋 Available Reminders lists:")
    for lst in reminders_lists:
        if isinstance(lst, dict):
            name = lst.get("name")
            identifier = lst.get("identifier")
            if name and identifier:
                list_name_to_id[name] = identifier
                print(f"   - {name}: {identifier}")

    # Convert to structured format
    structured_vaults = []
    default_vault_id = None

    print(f"\n🏗️  Converting vault entries:")

    for vault in current_config:
        if not isinstance(vault, dict):
            continue

        vault_name = vault.get("name")
        vault_path = vault.get("path")
        is_default = vault.get("is_default", False)

        if not vault_name or not vault_path:
            print(f"   ⚠️  Skipping invalid vault: {vault}")
            continue

        # Generate stable vault ID
        vault_id = generate_stable_vault_id(vault_path)

        # Find associated list ID
        associated_list_id = None
        if vault_name in list_name_to_id:
            associated_list_id = list_name_to_id[vault_name]

        new_vault = {
            "vault_id": vault_id,
            "name": vault_name,
            "path": vault_path,
            "associated_list_id": associated_list_id
        }

        if is_default:
            new_vault["is_default"] = True
            default_vault_id = vault_id

        structured_vaults.append(new_vault)

        status = "✅ MAPPED" if associated_list_id else "❌ NO MATCHING LIST"
        print(f"   {vault_name} → {vault_id} [{status}]")

    # Create structured config
    structured_config = {
        "version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "default_vault_id": default_vault_id,
        "vaults": structured_vaults
    }

    print(f"\n📊 Conversion summary:")
    print(f"   - Vaults processed: {len(structured_vaults)}")
    print(f"   - Mapped to lists: {sum(1 for v in structured_vaults if v.get('associated_list_id'))}")
    print(f"   - Default vault ID: {default_vault_id}")

    # Backup original config
    backup_path = vault_config_path + ".backup." + datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(backup_path, 'w') as f:
        json.dump(current_config, f, indent=2)
    print(f"   - Backup saved: {backup_path}")

    # Write new config
    with open(vault_config_path, 'w') as f:
        json.dump(structured_config, f, indent=2, ensure_ascii=False)

    print(f"✅ Vault config converted successfully!")
    print(f"   New format: {vault_config_path}")

    return structured_config

if __name__ == "__main__":
    convert_vault_config()