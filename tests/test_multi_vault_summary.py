#!/usr/bin/env python3
"""Test multi-vault summary aggregation functionality."""

import os
import sys
import tempfile
import json
from io import StringIO
from contextlib import redirect_stdout
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from obs_sync.core.models import (
    SyncConfig,
    Vault,
    RemindersList,
    ObsidianTask,
    RemindersTask,
    TaskStatus,
)
from obs_sync.commands.sync import SyncCommand, sync_command


def test_multi_vault_summary_aggregation():
    """Test that multi-vault runs aggregate stats correctly in final summary."""
    
    # Create mock configuration with multiple vaults
    config = SyncConfig(
        vaults=[
            Vault(name="Vault1", path="/tmp/vault1", vault_id="vault1", is_default=True),
            Vault(name="Vault2", path="/tmp/vault2", vault_id="vault2", is_default=False),
        ],
        reminders_lists=[
            RemindersList(name="List1", identifier="list1", source_name="Reminders", source_type="local"),
            RemindersList(name="List2", identifier="list2", source_name="Reminders", source_type="local"),
        ],
        vault_mappings=[
            {"vault_id": "vault1", "calendar_id": "list1"},
            {"vault_id": "vault2", "calendar_id": "list2"},
        ],
        enable_deduplication=True,
        dedup_auto_apply=True,
    )
    
    # Mock sync_command to return controlled results
    def mock_sync_command(vault_path, list_ids=None, dry_run=True, direction="both", config=None, show_summary=True):
        vault_name = os.path.basename(vault_path)
        
        if vault_name == "vault1":
            return {
                'success': True,
                'vault_path': vault_path,
                'vault_name': vault_name,
                'results': {
                    'obs_tasks': 10,
                    'rem_tasks': 8,
                    'links': 5,
                    'changes': {
                        'obs_updated': 2,
                        'rem_updated': 1,
                        'obs_created': 3,
                        'rem_created': 2,
                        'obs_deleted': 0,
                        'rem_deleted': 0,
                        'links_created': 5,
                        'links_deleted': 0,
                        'conflicts_resolved': 1,
                    },
                    'tag_summary': {
                        'work': {'List1': 5},
                        'personal': {'List1': 3},
                    }
                },
                'dedup_stats': {'obs_deleted': 1, 'rem_deleted': 0},
                'has_changes': True
            }
        elif vault_name == "vault2":
            return {
                'success': True,
                'vault_path': vault_path,
                'vault_name': vault_name,
                'results': {
                    'obs_tasks': 15,
                    'rem_tasks': 12,
                    'links': 8,
                    'changes': {
                        'obs_updated': 1,
                        'rem_updated': 2,
                        'obs_created': 1,
                        'rem_created': 3,
                        'obs_deleted': 0,
                        'rem_deleted': 1,
                        'links_created': 8,
                        'links_deleted': 1,
                        'conflicts_resolved': 0,
                    },
                    'tag_summary': {
                        'work': {'List2': 7},
                        'home': {'List2': 4},
                    }
                },
                'dedup_stats': {'obs_deleted': 0, 'rem_deleted': 2},
                'has_changes': True
            }
        else:
            return {
                'success': False,
                'vault_path': vault_path,
                'vault_name': vault_name,
                'error': f'Vault not found at {vault_path}'
            }
    
    # Create directories for mock vaults
    with tempfile.TemporaryDirectory() as temp_dir:
        vault1_path = os.path.join(temp_dir, "vault1")
        vault2_path = os.path.join(temp_dir, "vault2")
        os.makedirs(vault1_path)
        os.makedirs(vault2_path)
        
        # Update config with real paths
        config.vaults[0].path = vault1_path
        config.vaults[1].path = vault2_path
        
        # Capture stdout to test output
        captured_output = StringIO()
        
        with patch('obs_sync.commands.sync.sync_command', side_effect=mock_sync_command):
            with redirect_stdout(captured_output):
                sync_cmd = SyncCommand(config, verbose=False)
                result = sync_cmd.run(apply_changes=False, direction="both")
        
        output = captured_output.getvalue()
        
        # Verify successful completion
        assert result is True, "Multi-vault sync should succeed"
        
        # Verify per-vault progress indicators are shown
        assert "Vault 1/2: Vault1" in output, "Should show vault 1 progress"
        assert "Vault 2/2: Vault2" in output, "Should show vault 2 progress"
        assert "🔄 Running sync..." in output, "Should show per-vault sync progress"
        assert "✅ Sync completed" in output, "Should show completion status"
        
        # Verify consolidated summary is shown
        assert "🔄 Sync summary" in output, "Should show consolidated summary header"
        assert "Overall statistics:" in output, "Should show overall stats section"
        
        # Check aggregated totals
        assert "Total Obsidian tasks: 25" in output, "Should aggregate obs tasks (10+15)"
        assert "Total Reminders tasks: 20" in output, "Should aggregate rem tasks (8+12)"
        assert "Total matched pairs: 13" in output, "Should aggregate links (5+8)"
        assert "Vaults processed: 2 — 2 successful / 0 failed" in output, "Should show vault processing stats"
        
        # Check aggregated changes
        assert "Total changes to make:" in output, "Should show aggregated changes header"
        assert "Obsidian updates: 3" in output, "Should aggregate obs updates (2+1)"
        assert "Reminders updates: 3" in output, "Should aggregate rem updates (1+2)"
        assert "Obsidian creations: 4" in output, "Should aggregate obs creations (3+1)"
        assert "Reminders creations: 5" in output, "Should aggregate rem creations (2+3)"
        assert "New sync links: 13" in output, "Should aggregate links created (5+8)"
        assert "Conflicts resolved: 1" in output, "Should aggregate conflicts (1+0)"
        
        # Check aggregated tag routing
        assert "📊 Tag routing summary (all vaults):" in output, "Should show aggregated tag routing"
        assert "work:" in output, "Should aggregate work tag across vaults"
        assert "→ List1: 5 task(s)" in output, "Should show List1 work tasks"
        assert "→ List2: 7 task(s)" in output, "Should show List2 work tasks"
        
        # Check aggregated deduplication
        assert "Deduplication to perform:" in output, "Should show dedup section"
        assert "Obsidian deletions: 1" in output, "Should aggregate obs dedup (1+0)"
        assert "Reminders deletions: 2" in output, "Should aggregate rem dedup (0+2)"
        
        # Check dry-run reminder
        assert "💡 Dry run only—rerun with --apply to apply these changes." in output, "Should show dry-run reminder"
        
        # Verify final status message
        assert "✅ All vaults synced successfully!" in output, "Should show final success message"


def test_multi_vault_with_failures():
    """Test multi-vault summary when some vaults fail."""
    
    config = SyncConfig(
        vaults=[
            Vault(name="GoodVault", path="/tmp/good", vault_id="good", is_default=True),
            Vault(name="BadVault", path="/tmp/bad", vault_id="bad", is_default=False),
        ],
        reminders_lists=[
            RemindersList(name="List1", identifier="list1", source_name="Reminders", source_type="local"),
        ],
        vault_mappings=[
            {"vault_id": "good", "calendar_id": "list1"},
            {"vault_id": "bad", "calendar_id": "list1"},
        ],
    )
    
    def mock_sync_command(vault_path, list_ids=None, dry_run=True, direction="both", config=None, show_summary=True):
        vault_name = os.path.basename(vault_path)
        
        if vault_name == "good":
            return {
                'success': True,
                'vault_path': vault_path,
                'vault_name': vault_name,
                'results': {
                    'obs_tasks': 5,
                    'rem_tasks': 3,
                    'links': 2,
                    'changes': {
                        'obs_updated': 1,
                        'rem_updated': 0,
                        'obs_created': 0,
                        'rem_created': 1,
                        'obs_deleted': 0,
                        'rem_deleted': 0,
                        'links_created': 2,
                        'links_deleted': 0,
                        'conflicts_resolved': 0,
                    },
                    'tag_summary': {}
                },
                'dedup_stats': {'obs_deleted': 0, 'rem_deleted': 0},
                'has_changes': True
            }
        else:  # bad vault
            return {
                'success': False,
                'vault_path': vault_path,
                'vault_name': vault_name,
                'error': 'Vault not found at /tmp/bad'
            }
    
    with tempfile.TemporaryDirectory() as temp_dir:
        good_path = os.path.join(temp_dir, "good")
        os.makedirs(good_path)
        # Don't create bad_path to simulate failure
        
        config.vaults[0].path = good_path
        config.vaults[1].path = "/tmp/bad"  # Non-existent path
        
        captured_output = StringIO()
        
        with patch('obs_sync.commands.sync.sync_command', side_effect=mock_sync_command):
            with redirect_stdout(captured_output):
                sync_cmd = SyncCommand(config, verbose=False)
                result = sync_cmd.run(apply_changes=False, direction="both")
        
        output = captured_output.getvalue()
        
        # Should return False due to vault failure
        assert result is False, "Should return False when some vaults fail"
        
        # Check failure handling
        assert "⚠️  Vault 2/2: BadVault" in output, "Should show vault failure header"
        assert "Vault path does not exist: /tmp/bad" in output, "Should show vault path error"
        assert "Vaults processed: 2 — 1 successful / 1 failed" in output, "Should show correct failure count"
        assert "⚠️  Some vaults had sync errors" in output, "Should show warning about errors"
        
        # Should still show stats for successful vault
        assert "Total Obsidian tasks: 5" in output, "Should show stats from successful vault"


def test_single_vault_legacy_behavior():
    """Test that single vault still shows summary immediately (legacy behavior)."""
    
    config = SyncConfig(
        vaults=[
            Vault(name="SingleVault", path="/tmp/single", vault_id="single", is_default=True),
        ],
        reminders_lists=[
            RemindersList(name="List1", identifier="list1", source_name="Reminders", source_type="local"),
        ],
        vault_mappings=[
            {"vault_id": "single", "calendar_id": "list1"},
        ],
    )
    
    def mock_sync_command(vault_path, list_ids=None, dry_run=True, direction="both", config=None, show_summary=True):
        # Single vault with mapping still goes through multi-vault path, so show_summary=False
        # This is correct behavior - legacy fallback only when NO mappings are configured
        
        return {
            'success': True,
            'vault_path': vault_path,
            'vault_name': os.path.basename(vault_path),
            'results': {
                'obs_tasks': 3,
                'rem_tasks': 2,
                'links': 1,
                'changes': {
                    'obs_updated': 0,
                    'rem_updated': 1,
                    'obs_created': 0,
                    'rem_created': 0,
                    'obs_deleted': 0,
                    'rem_deleted': 0,
                    'links_created': 1,
                    'links_deleted': 0,
                    'conflicts_resolved': 0,
                },
                'tag_summary': {}
            },
            'dedup_stats': {'obs_deleted': 0, 'rem_deleted': 0},
            'has_changes': True
        }
    
    with tempfile.TemporaryDirectory() as temp_dir:
        vault_path = os.path.join(temp_dir, "single")
        os.makedirs(vault_path)
        config.vaults[0].path = vault_path
        
        captured_output = StringIO()
        
        with patch('obs_sync.commands.sync.sync_command', side_effect=mock_sync_command):
            with redirect_stdout(captured_output):
                sync_cmd = SyncCommand(config, verbose=False)
                result = sync_cmd.run(apply_changes=False, direction="both")
        
        output = captured_output.getvalue()
        
        # Should succeed
        assert result is True, "Single vault sync should succeed"
        
        # Single vault with mappings still uses new consolidated summary
        assert "🔄 Sync summary" in output, "Single vault with mappings should show consolidated summary"


def test_legacy_no_mappings_behavior():
    """Test legacy behavior when no vault mappings are configured."""
    
    config = SyncConfig(
        vaults=[
            Vault(name="LegacyVault", path="/tmp/legacy", vault_id="legacy", is_default=True),
        ],
        reminders_lists=[
            RemindersList(name="List1", identifier="list1", source_name="Reminders", source_type="local"),
        ],
        vault_mappings=[],  # No mappings - triggers legacy fallback
        default_vault_id="legacy",
    )
    
    def mock_sync_command(vault_path, list_ids=None, dry_run=True, direction="both", config=None, show_summary=True):
        # True legacy fallback should have show_summary=True
        assert show_summary is True, "Legacy fallback should use immediate summary"
        
        return {
            'success': True,
            'vault_path': vault_path,
            'vault_name': os.path.basename(vault_path),
            'results': {
                'obs_tasks': 3,
                'rem_tasks': 2,
                'links': 1,
                'changes': {
                    'obs_updated': 0,
                    'rem_updated': 1,
                    'obs_created': 0,
                    'rem_created': 0,
                    'obs_deleted': 0,
                    'rem_deleted': 0,
                    'links_created': 1,
                    'links_deleted': 0,
                    'conflicts_resolved': 0,
                },
                'tag_summary': {}
            },
            'dedup_stats': {'obs_deleted': 0, 'rem_deleted': 0},
            'has_changes': True
        }
    
    with tempfile.TemporaryDirectory() as temp_dir:
        vault_path = os.path.join(temp_dir, "legacy")
        os.makedirs(vault_path)
        config.vaults[0].path = vault_path
        
        captured_output = StringIO()
        
        with patch('obs_sync.commands.sync.sync_command', side_effect=mock_sync_command):
            with redirect_stdout(captured_output):
                sync_cmd = SyncCommand(config, verbose=False)
                result = sync_cmd.run(apply_changes=False, direction="both")
        
        output = captured_output.getvalue()
        
        # Should succeed
        assert result is True, "Legacy sync should succeed"
        
        # Should use true legacy path (no consolidated summary)
        assert "🔄 Sync summary" not in output, "Legacy fallback should not show consolidated summary"
        assert "📁 Syncing vault: legacy" in output, "Should show legacy vault sync message"


def test_no_changes_summary():
    """Test summary when no changes are needed across multiple vaults."""
    
    config = SyncConfig(
        vaults=[
            Vault(name="Vault1", path="/tmp/vault1", vault_id="vault1", is_default=True),
            Vault(name="Vault2", path="/tmp/vault2", vault_id="vault2", is_default=False),
        ],
        reminders_lists=[
            RemindersList(name="List1", identifier="list1", source_name="Reminders", source_type="local"),
        ],
        vault_mappings=[
            {"vault_id": "vault1", "calendar_id": "list1"},
            {"vault_id": "vault2", "calendar_id": "list1"},
        ],
    )
    
    def mock_sync_command(vault_path, list_ids=None, dry_run=True, direction="both", config=None, show_summary=True):
        return {
            'success': True,
            'vault_path': vault_path,
            'vault_name': os.path.basename(vault_path),
            'results': {
                'obs_tasks': 5,
                'rem_tasks': 5,
                'links': 5,
                'changes': {
                    'obs_updated': 0,
                    'rem_updated': 0,
                    'obs_created': 0,
                    'rem_created': 0,
                    'obs_deleted': 0,
                    'rem_deleted': 0,
                    'links_created': 0,
                    'links_deleted': 0,
                    'conflicts_resolved': 0,
                },
                'tag_summary': {}
            },
            'dedup_stats': {'obs_deleted': 0, 'rem_deleted': 0},
            'has_changes': False
        }
    
    with tempfile.TemporaryDirectory() as temp_dir:
        for i, vault in enumerate(config.vaults):
            vault_path = os.path.join(temp_dir, f"vault{i+1}")
            os.makedirs(vault_path)
            vault.path = vault_path
        
        captured_output = StringIO()
        
        with patch('obs_sync.commands.sync.sync_command', side_effect=mock_sync_command):
            with redirect_stdout(captured_output):
                sync_cmd = SyncCommand(config, verbose=False)
                result = sync_cmd.run(apply_changes=False, direction="both")
        
        output = captured_output.getvalue()
        
        assert result is True, "Sync should succeed even with no changes"
        assert "No changes needed - everything is in sync across all vaults!" in output, "Should show no changes message"


if __name__ == "__main__":
    test_multi_vault_summary_aggregation()
    print("✅ test_multi_vault_summary_aggregation passed")
    
    test_multi_vault_with_failures()
    print("✅ test_multi_vault_with_failures passed")
    
    test_single_vault_legacy_behavior()
    print("✅ test_single_vault_legacy_behavior passed")
    
    test_legacy_no_mappings_behavior()
    print("✅ test_legacy_no_mappings_behavior passed")
    
    test_no_changes_summary()
    print("✅ test_no_changes_summary passed")
    
    print("🎉 All tests passed!")