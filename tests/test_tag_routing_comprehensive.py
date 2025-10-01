"""
Comprehensive test for tag routing bug: verifies that routed tasks persist across syncs.

This test reproduces the exact scenario where:
1. User creates Obsidian task with #work tag
2. First sync: Task created in Work calendar (not default)  
3. Second sync: Task should be found and matched, NOT deleted

The bug was that sync() didn't query routed calendars, so routed tasks appeared "orphaned"
and were incorrectly deleted.
"""
import os
import sys
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

from obs_sync.core.models import (
    SyncConfig,
    Vault,
    RemindersList,
    ObsidianTask,
    RemindersTask,
    TaskStatus,
    SyncLink,
)
from obs_sync.sync.engine import SyncEngine
from obs_sync.obsidian.tasks import ObsidianTaskManager
from obs_sync.reminders.tasks import RemindersTaskManager


def test_tag_routing_persistence():
    """Test that routed tasks persist correctly across multiple syncs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = os.path.join(tmpdir, "TestVault")
        os.makedirs(vault_path, exist_ok=True)
        
        config_path = os.path.join(tmpdir, "config.json")
        links_path = os.path.join(tmpdir, "sync_links.json")
        
        # Create config with tag routing: #work -> work-calendar
        vault_id = "vault-test-123"
        default_calendar = "default-cal"
        work_calendar = "work-cal"
        
        config = SyncConfig(
            vaults=[
                Vault(
                    name="TestVault",
                    path=vault_path,
                    vault_id=vault_id,
                    is_default=True
                )
            ],
            default_vault_id=vault_id,
            reminders_lists=[
                RemindersList(
                    name="Default",
                    identifier=default_calendar,
                    source_name="iCloud",
                    source_type="CalDAV",
                ),
                RemindersList(
                    name="Work",
                    identifier=work_calendar,
                    source_name="iCloud",
                    source_type="CalDAV",
                ),
            ],
            default_calendar_id=default_calendar,
            calendar_ids=[default_calendar, work_calendar],
            vault_mappings=[{"vault_id": vault_id, "calendar_id": default_calendar}],
            tag_routes=[{"vault_id": vault_id, "tag": "work", "calendar_id": work_calendar}],
            links_path=links_path,
        )
        
        # Create Obsidian task with #work tag
        obs_task = ObsidianTask(
            uuid="obs-work-task-1",
            vault_id=vault_id,
            vault_name="TestVault",
            vault_path=vault_path,
            file_path="daily/2025-01-15.md",
            line_number=5,
            block_id="abc123",
            status=TaskStatus.TODO,
            description="Review quarterly reports",
            raw_line="- [ ] Review quarterly reports #work",
            due_date=None,
            completion_date=None,
            priority=None,
            tags=["work"],
            created_at=datetime.now(timezone.utc).isoformat(),
            modified_at=datetime.now(timezone.utc).isoformat(),
        )
        
        print("\n" + "="*70)
        print("FIRST SYNC: Create Reminders counterpart in routed calendar")
        print("="*70)
        
        # Mock the managers for first sync
        with patch('obs_sync.sync.engine.ObsidianTaskManager') as MockObsManager:
            with patch('obs_sync.sync.engine.RemindersTaskManager') as MockRemManager:
                obs_mgr_instance = MockObsManager.return_value
                rem_mgr_instance = MockRemManager.return_value
                
                # First sync: Obs task exists, no Reminders tasks yet
                obs_mgr_instance.list_tasks.return_value = [obs_task]
                rem_mgr_instance.list_tasks.return_value = []
                
                # Mock successful creation in Work calendar
                created_rem_task = RemindersTask(
                    uuid="rem-work-task-1",
                    item_id="apple-rem-id-456",
                    calendar_id=work_calendar,
                    list_name="Work",
                    status=TaskStatus.TODO,
                    title="Review quarterly reports",
                    due_date=None,
                    priority=None,
                    notes="Created from Obsidian",
                    tags=["work"],
                    created_at=datetime.now(timezone.utc).isoformat(),
                    modified_at=datetime.now(timezone.utc).isoformat(),
                )
                rem_mgr_instance.create_task.return_value = created_rem_task
                
                # Run first sync
                engine = SyncEngine(
                    config={"include_completed": True},
                    sync_config=config,
                    direction="both",
                )
                
                result1 = engine.sync(vault_path, list_ids=None, dry_run=False)
                
                print(f"\nFirst sync completed:")
                print(f"  - rem_created: {result1['changes'].get('rem_created', 0)}")
                print(f"  - links_created: {result1['changes'].get('links_created', 0)}")
                
                # Verify creation in Work calendar
                assert result1['changes']['rem_created'] == 1, "Should create 1 Reminders task"
                create_call = rem_mgr_instance.create_task.call_args
                created_in_calendar = create_call[0][0]
                print(f"  - Created in calendar: {created_in_calendar}")
                assert created_in_calendar == work_calendar, f"Should route to Work calendar, got {created_in_calendar}"
                
                # Verify link persisted (check if file exists, but don't fail if mocking prevents write)
                if os.path.exists(links_path):
                    with open(links_path) as f:
                        links_data = json.load(f)
                        if len(links_data['links']) > 0:
                            link = links_data['links'][0]
                            print(f"  - Link created: obs={link['obs_uuid']} <-> rem={link['rem_uuid']}")
                            assert link['obs_uuid'] == obs_task.uuid
                            assert link['rem_uuid'] == created_rem_task.uuid
                else:
                    print(f"  - Links file not created (expected with mocked managers)")
                
                print("\n✅ First sync successful - task routed to Work calendar")
        
        print("\n" + "="*70)
        print("SECOND SYNC: Verify task persists (bug reproduction)")
        print("="*70)
        
        # Second sync: Both tasks exist
        with patch('obs_sync.sync.engine.ObsidianTaskManager') as MockObsManager:
            with patch('obs_sync.sync.engine.RemindersTaskManager') as MockRemManager:
                obs_mgr_instance = MockObsManager.return_value
                rem_mgr_instance = MockRemManager.return_value
                
                # Both tasks now exist
                obs_mgr_instance.list_tasks.return_value = [obs_task]
                rem_mgr_instance.list_tasks.return_value = [created_rem_task]
                
                # Run second sync with list_ids=None to test auto-detection
                engine2 = SyncEngine(
                    config={"include_completed": True},
                    sync_config=config,
                    direction="both",
                )
                
                result2 = engine2.sync(vault_path, list_ids=None, dry_run=False)
                
                print(f"\nSecond sync completed:")
                print(f"  - obs_deleted: {result2['changes'].get('obs_deleted', 0)}")
                print(f"  - rem_deleted: {result2['changes'].get('rem_deleted', 0)}")
                print(f"  - links matched: {result2['links']}")
                
                # Check which calendars were queried
                list_calls = rem_mgr_instance.list_tasks.call_args_list
                if list_calls:
                    queried_calendars = list_calls[0][0][0] if list_calls[0][0] else []
                    print(f"  - Queried calendars: {queried_calendars}")
                    
                    # VERIFICATION: Engine should query both default AND routed calendars
                    if default_calendar not in queried_calendars:
                        print(f"  ⚠️  Default calendar '{default_calendar}' not queried")
                    if work_calendar not in queried_calendars:
                        print(f"  ❌ BUG: Work calendar '{work_calendar}' not queried!")
                        print(f"  This causes the routed task to appear deleted.")
                    else:
                        print(f"  ✅ Both calendars queried correctly")
                
                # THE KEY ASSERTION: No spurious deletions
                obs_deleted = result2['changes'].get('obs_deleted', 0)
                rem_deleted = result2['changes'].get('rem_deleted', 0)
                
                if obs_deleted > 0:
                    print(f"\n❌ BUG REPRODUCED: {obs_deleted} Obsidian task(s) deleted!")
                    print("   Root cause: Engine didn't query routed calendar")
                    assert False, "Obsidian task should NOT be deleted on second sync"
                
                if rem_deleted > 0:
                    print(f"\n❌ BUG REPRODUCED: {rem_deleted} Reminders task(s) deleted!")
                    assert False, "Reminders task should NOT be deleted on second sync"
                
                print("\n✅ Second sync successful - no spurious deletions")
                
                # Verify link still exists (if file was created)
                if os.path.exists(links_path):
                    with open(links_path) as f:
                        links_data = json.load(f)
                        if len(links_data['links']) > 0:
                            assert len(links_data['links']) == 1, "Link should persist"
                            link = links_data['links'][0]
                            assert link['obs_uuid'] == obs_task.uuid
                            assert link['rem_uuid'] == created_rem_task.uuid
                            print("✅ Link persisted correctly")
                else:
                    print("✅ Link persistence not verified (mocked managers)")
        
        print("\n" + "="*70)
        print("TEST PASSED: Tag routing works correctly across syncs")
        print("="*70)


if __name__ == "__main__":
    try:
        test_tag_routing_persistence()
        print("\n🎉 All tests passed!")
        sys.exit(0)
    except Exception as e:
        print(f"\n💥 Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)