"""
Test case to reproduce tag routing bug where newly created Obsidian tasks
with routed tags cause spurious deletions on subsequent sync runs.

Bug: When an Obsidian task has a tag route (e.g., #work -> Work calendar),
the first sync creates it in the routed calendar, but subsequent syncs only
query the default calendar, causing the routed task to appear "deleted" and
triggering orphan cleanup that deletes the Obsidian task.
"""
import os
import json
import tempfile
import logging
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import Mock, patch
from obs_sync.core.models import (
    SyncConfig,
    Vault,
    RemindersList,
    ObsidianTask,
    RemindersTask,
    TaskStatus,
)
from obs_sync.sync.engine import SyncEngine
from obs_sync.commands.sync import _run_deduplication


def test_tag_routing_second_sync_bug():
    """
    Reproduce bug: Second sync deletes Obsidian task because routed Reminders
    task isn't queried from its routed calendar.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = os.path.join(tmpdir, "test_vault")
        os.makedirs(vault_path)
        
        # Setup config with tag route: #work -> work-calendar
        config = SyncConfig(
            vaults=[Vault(name="Test", path=vault_path, vault_id="test-vault-id")],
            default_vault_id="test-vault-id",
            reminders_lists=[
                RemindersList(name="Inbox", identifier="inbox-id", source_name="", source_type=""),
                RemindersList(name="Work", identifier="work-id", source_name="", source_type=""),
            ],
            default_calendar_id="inbox-id",
            calendar_ids=["inbox-id", "work-id"],
            vault_mappings=[{"vault_id": "test-vault-id", "calendar_id": "inbox-id"}],
            tag_routes=[{"vault_id": "test-vault-id", "tag": "#work", "calendar_id": "work-id"}],
            links_path=os.path.join(tmpdir, "links.json"),
        )
        
        # Mock managers
        obs_manager = Mock()
        rem_manager = Mock()
        
        # Obsidian task with routed tag
        obs_task = ObsidianTask(
            uuid="obs-123",
            vault_id="test-vault-id",
            vault_name="Test",
            vault_path=vault_path,
            file_path="test.md",
            line_number=1,
            block_id=None,
            status=TaskStatus.TODO,
            description="Task with work tag",
            raw_line="- [ ] Task with work tag #work",
            due_date=None,
            completion_date=None,
            priority=None,
            tags=["#work"],
            created_at="2025-01-01T00:00:00Z",
            modified_at="2025-01-01T00:00:00Z",
        )
        
        # First sync: Obsidian task exists, no Reminders counterpart yet
        obs_manager.list_tasks.return_value = [obs_task]
        rem_manager.list_tasks.return_value = []  # Empty initially
        
        # Create engine
        engine = SyncEngine(
            config={"include_completed": True, "links_path": config.links_path},
            sync_config=config,
        )
        engine.obs_manager = obs_manager
        engine.rem_manager = rem_manager
        
        # Mock Reminders creation to return created task in routed calendar
        created_rem_task = RemindersTask(
            uuid="rem-456",
            item_id="rem-456",
            calendar_id="work-id",  # Routed to Work calendar
            list_name="Work",
            status=TaskStatus.TODO,
            title="Task with work tag",
            due_date=None,
            priority=None,
            notes="Created from Obsidian",
            tags=["#work"],
            created_at="2025-01-01T00:00:00Z",
            modified_at="2025-01-01T00:00:00Z",
        )
        rem_manager.create_task.return_value = created_rem_task
        
        # First sync run - should create Reminders task in Work calendar
        # Pass None for list_ids to use auto-detection with routes
        result1 = engine.sync(vault_path, list_ids=None, dry_run=False)
        
        print("\n=== First Sync ===")
        print(f"Result: {result1}")
        assert result1["changes"]["rem_created"] == 1, "Should create 1 Reminders task"
        assert result1["changes"]["links_created"] == 1, "Should create 1 link"
        
        # Verify link was persisted
        with open(config.links_path) as f:
            links_data = json.load(f)
            print(f"Links persisted: {links_data}")
            assert len(links_data["links"]) == 1
            link = links_data["links"][0]
            assert link["obs_uuid"] == "obs-123"
            assert link["rem_uuid"] == "rem-456"
        
        # Second sync: Obsidian task still exists, Reminders task in Work calendar
        # BUG: Engine only queries inbox-id, not work-id where task was routed
        obs_manager.list_tasks.return_value = [obs_task]
        rem_manager.list_tasks.side_effect = lambda list_ids, **kw: (
            [created_rem_task] if "work-id" in list_ids else []
        )
        
        # Reset counters
        rem_manager.delete_task.reset_mock()
        obs_manager.delete_task.reset_mock()
        
        # Second sync - should auto-detect both default and routed calendars
        # Pass None to trigger auto-detection logic
        result2 = engine.sync(vault_path, list_ids=None, dry_run=False)
        
        print("\n=== Second Sync (Bug Reproduction) ===")
        print(f"Result: {result2}")
        print(f"rem_manager.list_tasks called with: {rem_manager.list_tasks.call_args_list}")
        print(f"Obsidian delete called: {obs_manager.delete_task.called}")
        print(f"Reminders delete called: {rem_manager.delete_task.called}")
        
        # Verify fix: Engine should query both inbox-id AND work-id, find task, no deletions
        assert result2["changes"].get("obs_deleted", 0) == 0, "Should not delete Obsidian task"
        assert result2["changes"].get("rem_deleted", 0) == 0, "Should not delete Reminders task"
        assert not obs_manager.delete_task.called, "Should not call Obsidian delete"
        assert not rem_manager.delete_task.called, "Should not call Reminders delete"
        
        # Verify list_ids includes routed calendars
        list_calls = rem_manager.list_tasks.call_args_list
        for call in list_calls:
            queried_list_ids = call[0][0]
            assert "inbox-id" in queried_list_ids, "Should query default calendar"
            assert "work-id" in queried_list_ids, "Should query routed calendar"
        
        print("\n✅ Fix verified: Engine correctly queries routed calendars!")
        print(f"   First sync queried: {list_calls[0][0][0]}")
        print(f"   Second sync queried: {list_calls[1][0][0]}")
        print(f"   Result: No spurious deletions")


def test_routed_task_preserved_when_list_ids_provided_without_route():
    """Ensure routed calendars are queried even when caller supplies list_ids."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = os.path.join(tmpdir, "vault")
        os.makedirs(vault_path)
        links_path = os.path.join(tmpdir, "links.json")

        config = SyncConfig(
            vaults=[Vault(name="Personal", path=vault_path, vault_id="vault-1", is_default=True)],
            default_vault_id="vault-1",
            reminders_lists=[
                RemindersList(
                    name="Inbox",
                    identifier="inbox-id",
                    source_name="",
                    source_type="",
                ),
                RemindersList(
                    name="01 PhD",
                    identifier="phd-id",
                    source_name="",
                    source_type="",
                ),
            ],
            default_calendar_id="inbox-id",
            calendar_ids=["inbox-id"],
            vault_mappings=[{"vault_id": "vault-1", "calendar_id": "inbox-id"}],
            tag_routes=[{"vault_id": "vault-1", "tag": "#phd", "calendar_id": "phd-id"}],
            links_path=links_path,
        )
        config.enable_deduplication = False

        now = "2025-01-01T00:00:00Z"
        obs_task = ObsidianTask(
            uuid="obs-phd",
            vault_id="vault-1",
            vault_name="Personal",
            vault_path=vault_path,
            file_path="tasks.md",
            line_number=1,
            block_id="task-1",
            status=TaskStatus.TODO,
            description="Write thesis summary",
            raw_line="- [ ] Write thesis summary #phd",
            due_date=None,
            completion_date=None,
            priority=None,
            tags=["#phd"],
            created_at=now,
            modified_at=now,
        )

        class StubObsManager:
            def __init__(self, logger=None):
                self.logger = logger

            def list_tasks(self, vault_path_arg, include_completed=None):
                return [obs_task]

            def delete_task(self, task):
                raise AssertionError("Obsidian delete should not be called for routed task preservation test")

        class StubRemManager:
            def __init__(self, logger=None):
                self.logger = logger
                self.tasks: List[RemindersTask] = []
                self.list_calls: List[Optional[List[str]]] = []

            def list_tasks(self, list_ids_arg, include_completed=None):
                recorded = list(list_ids_arg) if list_ids_arg else list_ids_arg
                self.list_calls.append(recorded)
                if not list_ids_arg:
                    return list(self.tasks)
                if list_ids_arg and "phd-id" in list_ids_arg:
                    return list(self.tasks)
                return []

            def create_task(self, list_id, task):
                created = RemindersTask(
                    uuid="rem-phd",
                    item_id="rem-phd",
                    calendar_id=list_id,
                    list_name="01 PhD" if list_id == "phd-id" else "Inbox",
                    status=task.status,
                    title=task.title,
                    due_date=task.due_date,
                    priority=task.priority,
                    notes=task.notes,
                    tags=list(task.tags or []),
                    created_at=now,
                    modified_at=now,
                )
                self.tasks = [created]
                return created

            def update_task(self, task, changes):
                calendar_id = changes.get("calendar_id")
                if calendar_id:
                    task.calendar_id = calendar_id
                return task

            def delete_task(self, task):
                self.tasks = [t for t in self.tasks if t.uuid != task.uuid]
                return True

        engine = SyncEngine(
            config={"include_completed": True, "links_path": links_path},
            sync_config=config,
        )
        engine.obs_manager = StubObsManager()
        rem_manager = StubRemManager()
        engine.rem_manager = rem_manager

        # First sync: caller provides only the default calendar, engine must augment with routed list
        result1 = engine.sync(vault_path, list_ids=["inbox-id"], dry_run=False)

        assert result1["changes"]["rem_created"] == 1, "Should create routed Reminders counterpart"
        assert result1["changes"].get("rem_deleted", 0) == 0
        assert any(call and "phd-id" in call for call in rem_manager.list_calls), "Engine should query routed calendar"
        assert rem_manager.tasks and rem_manager.tasks[0].calendar_id == "phd-id"

        rem_manager.list_calls.clear()

        # Second sync: ensure routed reminder is loaded and no orphan deletion occurs
        result2 = engine.sync(vault_path, list_ids=["inbox-id"], dry_run=False)

        assert result2["changes"].get("obs_deleted", 0) == 0, "Obsidian task should be preserved"
        assert result2["changes"].get("rem_deleted", 0) == 0, "Reminders task should be preserved"
        assert any(call and "phd-id" in call for call in rem_manager.list_calls), "Routed calendar must be queried on subsequent runs"


def test_cross_vault_routed_task_not_deleted_by_other_vault():
    """Ensure links from other vaults do not trigger orphan deletions when syncing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        personal_path = os.path.join(tmpdir, "Personal")
        work_path = os.path.join(tmpdir, "Work")
        os.makedirs(personal_path)
        os.makedirs(work_path)
        links_path = os.path.join(tmpdir, "links.json")

        personal_vault_id = "vault-personal"
        work_vault_id = "vault-work"

        config = SyncConfig(
            vaults=[
                Vault(name="Personal", path=personal_path, vault_id=personal_vault_id, is_default=True),
                Vault(name="Work", path=work_path, vault_id=work_vault_id, is_default=False),
            ],
            default_vault_id=personal_vault_id,
            reminders_lists=[
                RemindersList(name="01 Personal", identifier="personal-id"),
                RemindersList(name="01 Work", identifier="work-id"),
                RemindersList(name="01 PhD", identifier="phd-id"),
            ],
            default_calendar_id="personal-id",
            calendar_ids=["personal-id", "work-id", "phd-id"],
            vault_mappings=[
                {"vault_id": personal_vault_id, "calendar_id": "personal-id"},
                {"vault_id": work_vault_id, "calendar_id": "work-id"},
            ],
            tag_routes=[
                {"vault_id": personal_vault_id, "tag": "#phd", "calendar_id": "phd-id"},
                {"vault_id": work_vault_id, "tag": "#phd", "calendar_id": "phd-id"},
            ],
            links_path=links_path,
        )
        config.enable_deduplication = False

        now = "2025-01-01T00:00:00Z"
        personal_task = ObsidianTask(
            uuid="obs-personal",
            vault_id=personal_vault_id,
            vault_name="Personal",
            vault_path=personal_path,
            file_path="tasks.md",
            line_number=1,
            block_id="personal-task",
            status=TaskStatus.TODO,
            description="Write thesis outline",
            raw_line="- [ ] Write thesis outline #phd",
            due_date=None,
            completion_date=None,
            priority=None,
            tags=["#phd"],
            created_at=now,
            modified_at=now,
        )

        class StubObsidianManager:
            def __init__(self, mapping: Dict[str, List[ObsidianTask]]):
                self.mapping = mapping
                self.deleted: List[str] = []
                self.include_completed = True

            def list_tasks(self, vault_path_arg, include_completed=None):
                return list(self.mapping.get(vault_path_arg, []))

            def delete_task(self, task):
                self.deleted.append(task.uuid)
                return True

            def create_task(self, vault_path_arg, file_path, task):
                self.mapping.setdefault(vault_path_arg, []).append(task)
                return task

        class SharedStubRemindersManager:
            def __init__(self):
                self.tasks: Dict[str, RemindersTask] = {}
                self.deleted: List[str] = []
                self.list_calls: List[List[str]] = []
                self.include_completed = True

            def list_tasks(self, list_ids_arg, include_completed=None):
                if list_ids_arg:
                    self.list_calls.append(list(list_ids_arg))
                    return [task for task in self.tasks.values() if task.calendar_id in list_ids_arg]
                self.list_calls.append([])
                return list(self.tasks.values())

            def create_task(self, list_id, task):
                new_uuid = f"rem-{len(self.tasks)+1}"
                created = RemindersTask(
                    uuid=new_uuid,
                    item_id=new_uuid,
                    calendar_id=list_id,
                    list_name=task.list_name or list_id,
                    status=task.status,
                    title=task.title,
                    due_date=task.due_date,
                    priority=task.priority,
                    notes=task.notes,
                    tags=list(task.tags or []),
                    created_at=now,
                    modified_at=now,
                )
                self.tasks[created.uuid] = created
                return created

            def update_task(self, task, changes):
                return task

            def delete_task(self, task):
                self.deleted.append(task.uuid)
                self.tasks.pop(task.uuid, None)
                return True

        obs_manager = StubObsidianManager({personal_path: [personal_task], work_path: []})
        rem_manager = SharedStubRemindersManager()

        engine_personal = SyncEngine(
            config={"include_completed": True, "links_path": links_path},
            sync_config=config,
        )
        engine_personal.obs_manager = obs_manager
        engine_personal.rem_manager = rem_manager

        result_personal = engine_personal.sync(personal_path, list_ids=None, dry_run=False)
        assert result_personal["changes"]["rem_created"] == 1
        assert rem_manager.tasks, "Reminders task should be stored after creation"

        engine_work = SyncEngine(
            config={"include_completed": True, "links_path": links_path},
            sync_config=config,
        )
        engine_work.obs_manager = obs_manager
        engine_work.rem_manager = rem_manager

        result_work = engine_work.sync(work_path, list_ids=None, dry_run=False)
        assert result_work["changes"].get("rem_deleted", 0) == 0, "Cross-vault sync should not delete routed task"
        assert not rem_manager.deleted, "No reminders should be deleted by other vault"
        assert rem_manager.tasks, "Routed reminder must still exist after other vault sync"

        # Ensure the Obsidian task was not deleted either
        assert not obs_manager.deleted, "Obsidian task should remain untouched"


def test_deduplication_skips_newly_created_tasks():
    """Ensure deduplication ignores tasks created in the same sync run."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = os.path.join(tmpdir, "vault")
        os.makedirs(vault_path)
        links_path = os.path.join(tmpdir, "links.json")

        config = SyncConfig(
            vaults=[Vault(name="Personal", path=vault_path, vault_id="vault-1", is_default=True)],
            default_vault_id="vault-1",
            reminders_lists=[
                RemindersList(
                    name="01 PhD",
                    identifier="list-phd",
                    source_name=None,
                    source_type=None,
                    color=None,
                    allows_modification=True,
                )
            ],
            default_calendar_id="list-phd",
            calendar_ids=["list-phd"],
            vault_mappings=[{"vault_id": "vault-1", "calendar_id": "list-phd"}],
            tag_routes=[],
            links_path=links_path,
        )
        config.enable_deduplication = True
        config.dedup_auto_apply = False

        now = "2025-01-01T00:00:00Z"
        obs_existing = ObsidianTask(
            uuid="obs-existing",
            vault_id="vault-1",
            vault_name="Personal",
            vault_path=vault_path,
            file_path="existing.md",
            line_number=1,
            block_id=None,
            status=TaskStatus.TODO,
            description="Existing task",
            raw_line="- [ ] Existing task",
            due_date=None,
            completion_date=None,
            priority=None,
            tags=["#phd"],
            created_at=now,
            modified_at=now,
        )
        obs_new = ObsidianTask(
            uuid="obs-new",
            vault_id="vault-1",
            vault_name="Personal",
            vault_path=vault_path,
            file_path="new.md",
            line_number=1,
            block_id=None,
            status=TaskStatus.TODO,
            description="New task",
            raw_line="- [ ] New task",
            due_date=None,
            completion_date=None,
            priority=None,
            tags=["#phd"],
            created_at=now,
            modified_at=now,
        )
        rem_existing = RemindersTask(
            uuid="rem-existing",
            item_id="rem-existing",
            calendar_id="list-phd",
            list_name="01 PhD",
            status=TaskStatus.TODO,
            title="Existing task",
            due_date=None,
            priority=None,
            notes="",
            tags=["#phd"],
            created_at=now,
            modified_at=now,
        )
        rem_new = RemindersTask(
            uuid="rem-new",
            item_id="rem-new",
            calendar_id="list-phd",
            list_name="01 PhD",
            status=TaskStatus.TODO,
            title="New task",
            due_date=None,
            priority=None,
            notes="",
            tags=["#phd"],
            created_at=now,
            modified_at=now,
        )

        with open(links_path, "w") as handle:
            json.dump(
                {
                    "links": [
                        {
                            "obs_uuid": "obs-new",
                            "rem_uuid": "rem-new",
                            "score": 1.0,
                            "vault_id": "vault-1",
                            "last_synced": now,
                            "created_at": now,
                        }
                    ]
                },
                handle,
                indent=2,
            )

        captured = {}

        class StubObsidianManager:
            def __init__(self, logger=None):
                self.logger = logger

            def list_tasks(self, vault_path_arg, include_completed=None):
                return [obs_existing, obs_new]

            def delete_task(self, task):
                return True

        class StubRemindersManager:
            def __init__(self, logger=None):
                self.logger = logger

            def list_tasks(self, list_ids_arg, include_completed=None):
                return [rem_existing, rem_new]

            def delete_task(self, task):
                return True

        class StubTaskDeduplicator:
            def __init__(self, obs_manager, rem_manager, logger=None, links_path=None):
                captured["obs_manager"] = obs_manager
                captured["rem_manager"] = rem_manager

            def analyze_duplicates(self, obs_tasks, rem_tasks, existing_links):
                captured["obs_tasks"] = list(obs_tasks)
                captured["rem_tasks"] = list(rem_tasks)
                captured["existing_links"] = list(existing_links or [])
                from obs_sync.sync.deduplicator import DeduplicationResults

                return DeduplicationResults(
                    clusters=[], total_tasks=0, duplicate_tasks=0, duplicate_clusters=0
                )

            def delete_tasks(self, tasks_to_delete, dry_run=True):  # pragma: no cover - stub
                return {"obs_deleted": 0, "rem_deleted": 0}

        with patch("obs_sync.obsidian.tasks.ObsidianTaskManager", StubObsidianManager), patch(
            "obs_sync.reminders.tasks.RemindersTaskManager", StubRemindersManager
        ), patch("obs_sync.commands.sync.TaskDeduplicator", StubTaskDeduplicator), patch(
            "obs_sync.commands.sync.confirm_deduplication", return_value=False
        ) as mock_confirm:
            stats = _run_deduplication(
                vault_path=vault_path,
                list_ids=["list-phd"],
                dry_run=False,
                config=config,
                logger=logging.getLogger("test"),
                show_summary=False,
                created_obs_ids=[obs_new.uuid],
                created_rem_ids=[rem_new.uuid],
            )

        assert stats == {"obs_deleted": 0, "rem_deleted": 0}
        assert "obs_tasks" not in captured
        assert "rem_tasks" not in captured
        assert "existing_links" not in captured
        mock_confirm.assert_not_called()


if __name__ == "__main__":
    test_tag_routing_second_sync_bug()
    test_deduplication_skips_newly_created_tasks()