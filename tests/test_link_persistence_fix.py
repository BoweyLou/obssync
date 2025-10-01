#!/usr/bin/env python3
"""
Test to verify that the sync link persistence fix works correctly.

This test verifies:
1. Stale links are not preserved when tasks are deleted
2. Re-linked tasks don't create duplicate entries
3. Multi-vault scenarios work correctly
"""

import os
import sys
import tempfile
import json
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from obs_sync.sync.engine import SyncEngine
from obs_sync.core.models import ObsidianTask, RemindersTask, TaskStatus, SyncLink


def test_stale_links_not_preserved():
    """Test that deleted tasks' links are not preserved."""
    print("\n=== Test 1: Stale Links Not Preserved ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        links_path = Path(tmpdir) / "sync_links.json"
        
        # Create a mock sync engine
        engine = SyncEngine(
            config={"links_path": str(links_path)},
            logger=Mock(),
            sync_config=None
        )
        engine.vault_id = "vault-1"
        
        # First sync: 3 tasks linked
        initial_links = [
            SyncLink(obs_uuid="obs-1", rem_uuid="rem-1", score=1.0, 
                    vault_id=engine.vault_id,
                    last_synced=datetime.now(timezone.utc).isoformat(),
                    created_at=datetime.now(timezone.utc).isoformat()),
            SyncLink(obs_uuid="obs-2", rem_uuid="rem-2", score=1.0,
                    vault_id=engine.vault_id,
                    last_synced=datetime.now(timezone.utc).isoformat(),
                    created_at=datetime.now(timezone.utc).isoformat()),
            SyncLink(obs_uuid="obs-3", rem_uuid="rem-3", score=1.0,
                    vault_id=engine.vault_id,
                    last_synced=datetime.now(timezone.utc).isoformat(),
                    created_at=datetime.now(timezone.utc).isoformat()),
        ]
        
        # Simulate current vault's Obsidian tasks
        current_obs_uuids = {"obs-1", "obs-2", "obs-3"}
        
        # Persist initial links
        engine._persist_links(initial_links, current_obs_uuids)
        
        # Verify initial state
        with open(links_path, 'r') as f:
            data = json.load(f)
            assert len(data['links']) == 3, f"Expected 3 initial links, got {len(data['links'])}"
        
        # Second sync: task obs-2/rem-2 was deleted, only 2 tasks remain
        remaining_links = [
            SyncLink(obs_uuid="obs-1", rem_uuid="rem-1", score=1.0,
                    vault_id=engine.vault_id,
                    last_synced=datetime.now(timezone.utc).isoformat(), created_at=datetime.now(timezone.utc).isoformat()),
            SyncLink(obs_uuid="obs-3", rem_uuid="rem-3", score=1.0,
                    vault_id=engine.vault_id,
                    last_synced=datetime.now(timezone.utc).isoformat(), created_at=datetime.now(timezone.utc).isoformat()),
        ]
        
        # Update current vault's tasks (obs-2 was deleted)
        current_obs_uuids = {"obs-1", "obs-3"}
        
        # Persist updated links
        engine._persist_links(remaining_links, current_obs_uuids)
        
        # Verify the deleted task's link is gone
        with open(links_path, 'r') as f:
            data = json.load(f)
            print(f"DEBUG: Links after deletion: {data['links']}")
            assert len(data['links']) == 2, f"Expected 2 links after deletion, got {len(data['links'])}"
            
            uuids = {link['obs_uuid'] for link in data['links']}
            assert 'obs-2' not in uuids, "Deleted task obs-2 should not be in links"
            
        print("✅ Stale links correctly removed")


def test_no_duplicate_links():
    """Test that re-linking tasks doesn't create duplicates."""
    print("\n=== Test 2: No Duplicate Links ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        links_path = Path(tmpdir) / "sync_links.json"
        
        engine = SyncEngine(
            config={"links_path": str(links_path)},
            logger=Mock(),
            sync_config=None
        )
        engine.vault_id = "vault-1"
        
        # First sync: obs-1 linked to rem-1
        initial_links = [
            SyncLink(obs_uuid="obs-1", rem_uuid="rem-1", score=0.8,
                    vault_id=engine.vault_id,
                    last_synced=datetime.now(timezone.utc).isoformat(), created_at=datetime.now(timezone.utc).isoformat()),
        ]
        
        current_obs_uuids = {"obs-1"}
        engine._persist_links(initial_links, current_obs_uuids)
        
        # Second sync: obs-1 re-linked to rem-2 (rem-1 was deleted)
        new_links = [
            SyncLink(obs_uuid="obs-1", rem_uuid="rem-2", score=0.9,
                    vault_id=engine.vault_id,
                    last_synced=datetime.now(timezone.utc).isoformat(), created_at=datetime.now(timezone.utc).isoformat()),
        ]
        
        engine._persist_links(new_links, current_obs_uuids)
        
        # Verify no duplicates
        with open(links_path, 'r') as f:
            data = json.load(f)
            assert len(data['links']) == 1, f"Expected 1 link, got {len(data['links'])}"
            
            link = data['links'][0]
            assert link['obs_uuid'] == 'obs-1'
            assert link['rem_uuid'] == 'rem-2', f"Expected rem-2, got {link['rem_uuid']}"
            assert link['score'] == 0.9, f"Expected updated score 0.9, got {link['score']}"
            
        print("✅ Re-linking correctly replaces old links")


def test_multi_vault_preservation():
    """Test that links from other vaults are preserved."""
    print("\n=== Test 3: Multi-Vault Preservation ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        links_path = Path(tmpdir) / "sync_links.json"
        
        engine = SyncEngine(
            config={"links_path": str(links_path)},
            logger=Mock(),
            sync_config=None
        )
        
        # First vault sync
        engine.vault_id = "vault-1"
        vault1_links = [
            SyncLink(obs_uuid="vault1-obs-1", rem_uuid="rem-1", score=1.0,
                    vault_id="vault-1",
                    last_synced=datetime.now(timezone.utc).isoformat(), created_at=datetime.now(timezone.utc).isoformat()),
            SyncLink(obs_uuid="vault1-obs-2", rem_uuid="rem-2", score=1.0,
                    vault_id="vault-1",
                    last_synced=datetime.now(timezone.utc).isoformat(), created_at=datetime.now(timezone.utc).isoformat()),
        ]
        engine._persist_links(vault1_links, current_obs_uuids={"vault1-obs-1", "vault1-obs-2"})
        
        # Second vault sync (should preserve vault1 links)
        engine.vault_id = "vault-2"
        vault2_links = [
            SyncLink(obs_uuid="vault2-obs-1", rem_uuid="rem-3", score=1.0,
                    vault_id="vault-2",
                    last_synced=datetime.now(timezone.utc).isoformat(), created_at=datetime.now(timezone.utc).isoformat()),
        ]
        engine._persist_links(vault2_links, current_obs_uuids={"vault2-obs-1"})
        
        with open(links_path, 'r') as f:
            data = json.load(f)
            assert len(data['links']) == 3, f"Expected 3 links (two vaults), got {len(data['links'])}"
            
            obs_uuids = {link['obs_uuid'] for link in data['links']}
            assert {'vault1-obs-1', 'vault1-obs-2', 'vault2-obs-1'} == obs_uuids, "Both vaults' links should persist"
            
            vault_ids = {link.get('vault_id') for link in data['links']}
            assert vault_ids == {"vault-1", "vault-2"}, f"Unexpected vault IDs: {vault_ids}"
        
        print("✅ Multi-vault links are preserved while merging updates")


def test_migration_from_old_format():
    """Test that migration from old bloated format works."""
    print("\n=== Test 4: Migration from Old Format ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        links_path = Path(tmpdir) / "sync_links.json"
        
        # Create a bloated file like the old bug would produce
        old_data = {
            'links': [
                {'obs_uuid': 'obs-1', 'rem_uuid': 'rem-1', 'score': 0.8, 'vault_id': 'vault-legacy'},
                {'obs_uuid': 'obs-1', 'rem_uuid': 'rem-2', 'score': 0.9, 'vault_id': 'vault-legacy'},  # Duplicate obs
                {'obs_uuid': 'obs-2', 'rem_uuid': 'rem-1', 'score': 0.7, 'vault_id': 'vault-legacy'},  # Duplicate rem
                {'obs_uuid': 'obs-3', 'rem_uuid': 'rem-3', 'score': 1.0, 'vault_id': 'vault-legacy'},
            ]
        }
        
        with open(links_path, 'w') as f:
            json.dump(old_data, f)
        
        engine = SyncEngine(
            config={"links_path": str(links_path)},
            logger=Mock(),
            sync_config=None
        )
        engine.vault_id = "vault-legacy"
        
        # Perform a sync with just obs-3 (simulating other tasks were deleted)
        new_links = [
            SyncLink(obs_uuid="obs-3", rem_uuid="rem-3", score=1.0,
                    vault_id=engine.vault_id,
                    last_synced=datetime.now(timezone.utc).isoformat(), created_at=datetime.now(timezone.utc).isoformat()),
        ]
        current_obs_uuids = {"obs-3"}
        
        engine._persist_links(new_links, current_obs_uuids)
        
        # Verify cleanup happened
        with open(links_path, 'r') as f:
            data = json.load(f)
            # Should only have obs-3 link (current) 
            # Old obs-1 and obs-2 are not in current vault so treated as other vault
            # But since we pass current_obs_uuids, they should be removed as they're stale
            assert len(data['links']) == 1, f"Expected 1 link after migration, got {len(data['links'])}"
            
            link = data['links'][0]
            assert link['obs_uuid'] == 'obs-3'
            assert link['rem_uuid'] == 'rem-3'
            
        print("✅ Migration from bloated format works")


if __name__ == "__main__":
    print("Running sync link persistence fix tests...")
    
    try:
        test_stale_links_not_preserved()
        test_no_duplicate_links() 
        test_multi_vault_preservation()
        test_migration_from_old_format()
        
        print("\n✅ All tests passed!")
        print("\nThe fix correctly:")
        print("1. Removes stale links when tasks are deleted")
        print("2. Prevents duplicate links when tasks are re-linked")
        print("3. Preserves multi-vault link state during persistence")
        print("4. Migrates from old bloated format")
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)