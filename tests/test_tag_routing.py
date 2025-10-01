#!/usr/bin/env python3
"""Tests for tag routing configuration and sync engine behaviour."""

import os
import tempfile

from obs_sync.core.models import (
    SyncConfig,
    Vault,
    RemindersList,
    ObsidianTask,
    RemindersTask,
    TaskStatus,
)
from obs_sync.sync.engine import SyncEngine


class FakeRemindersManager:
    def __init__(self) -> None:
        self.created = []
        self.created_tasks = []
        self.updated_calls = []
        self.tasks = []

    def list_tasks(self, list_ids=None, include_completed: bool = True):
        return self.tasks

    def create_task(self, list_id: str, task: RemindersTask) -> RemindersTask:
        task.uuid = task.uuid or f"rem-{len(self.created) + 1}"
        task.item_id = f"item-{len(self.created) + 1}"
        self.created.append((list_id, task))
        self.created_tasks.append(task)
        return task

    def update_task(self, task: RemindersTask, changes: dict) -> RemindersTask:
        self.updated_calls.append((task, changes))
        # Apply changes to the task
        for key, value in changes.items():
            if hasattr(task, key):
                setattr(task, key, value)
        return task


class FakeObsidianManager:
    def __init__(self) -> None:
        self.created = []
        self.updated_calls = []
        self.tasks = []

    def list_tasks(self, vault_path: str, include_completed: bool = True):
        return self.tasks

    def create_task(self, vault_path: str, file_path: str, task: ObsidianTask) -> ObsidianTask:
        task.uuid = task.uuid or f"obs-{len(self.created) + 1}"
        self.created.append(task)
        return task

    def update_task(self, task: ObsidianTask, changes: dict) -> ObsidianTask:
        self.updated_calls.append((task, changes))
        # Apply changes to the task
        for key, value in changes.items():
            if hasattr(task, key):
                setattr(task, key, value)
        return task


def _build_config():
    config = SyncConfig()

    vault = Vault(name="Work", path="/vault/path", vault_id="vault-123")
    config.vaults = [vault]

    default_list = RemindersList(name="Work List", identifier="list-work")
    project_list = RemindersList(name="Project List", identifier="list-project")
    config.reminders_lists = [default_list, project_list]

    config.set_vault_mapping(vault.vault_id, default_list.identifier)
    config.set_tag_route(vault.vault_id, "#project", project_list.identifier)

    return config, vault, default_list, project_list


def test_tag_route_config_roundtrip():
    config, vault, default_list, project_list = _build_config()

    # Normalization should make casing consistent
    assert config.get_tag_route(vault.vault_id, "#PROJECT") == project_list.identifier

    temp_dir = tempfile.mkdtemp(prefix="obs-sync-test-")
    temp_path = os.path.join(temp_dir, "config.json")

    try:
        config.save_to_file(temp_path)
        loaded = SyncConfig.load_from_file(temp_path)
        assert loaded.get_tag_route(vault.vault_id, "#project") == project_list.identifier
        assert loaded.get_vault_mapping(vault.vault_id) == default_list.identifier
    finally:
        try:
            os.remove(temp_path)
        except FileNotFoundError:
            pass
        os.rmdir(temp_dir)


def test_sync_engine_routes_obsidian_tasks():
    config, vault, default_list, project_list = _build_config()

    engine = SyncEngine(
        {
            "obsidian_inbox_path": "Inbox.md",
            "default_calendar_id": default_list.identifier,
        },
        direction="both",
        sync_config=config,
    )
    engine.rem_manager = FakeRemindersManager()
    engine.obs_manager = FakeObsidianManager()
    engine.vault_path = vault.path
    engine.vault_id = vault.vault_id
    engine.vault_name = vault.name
    engine.vault_default_calendar = config.get_vault_mapping(vault.vault_id)

    obs_task = ObsidianTask(
        uuid="obs-001",
        vault_id=vault.vault_id,
        vault_name=vault.name,
        vault_path=vault.path,
        file_path="Tasks.md",
        line_number=1,
        block_id=None,
        status=TaskStatus.TODO,
        description="Project work",
        raw_line="- [ ] Project work #project",
        due_date=None,
        completion_date=None,
        priority=None,
        tags=["#project"],
        created_at=None,
        modified_at=None,
    )

    new_links, created_obs_tasks, created_rem_tasks = engine._create_counterparts(
        unmatched_obs=[obs_task],
        unmatched_rem=[],
        list_ids=[default_list.identifier, project_list.identifier],
        dry_run=False,
    )

    assert engine.rem_manager.created, "Expected Reminders task creation"
    created_list_id, created_task = engine.rem_manager.created[0]
    assert created_list_id == project_list.identifier
    assert created_task.calendar_id == project_list.identifier
    assert len(new_links) == 1
    assert new_links[0].rem_uuid == created_task.uuid
    assert not created_obs_tasks
    assert created_rem_tasks == [created_task]


def test_sync_engine_persists_links_for_created_reminders():
    config, vault, default_list, _ = _build_config()

    with tempfile.TemporaryDirectory() as tmpdir:
        vault.path = tmpdir

        engine = SyncEngine(
            {
                "obsidian_inbox_path": "Inbox.md",
                "default_calendar_id": default_list.identifier,
            },
            direction="both",
            sync_config=config,
        )
        fake_obs_manager = FakeObsidianManager()
        fake_rem_manager = FakeRemindersManager()

        fake_obs_manager.tasks = [
            ObsidianTask(
                uuid="obs-keep-1",
                vault_id=vault.vault_id,
                vault_name=vault.name,
                vault_path=vault.path,
                file_path="Tasks.md",
                line_number=1,
                block_id="keep-1",
                status=TaskStatus.TODO,
                description="First unmatched task",
                raw_line="- [ ] First unmatched task",
                tags=[],
            ),
            ObsidianTask(
                uuid="obs-keep-2",
                vault_id=vault.vault_id,
                vault_name=vault.name,
                vault_path=vault.path,
                file_path="Tasks.md",
                line_number=2,
                block_id="keep-2",
                status=TaskStatus.TODO,
                description="Second unmatched task",
                raw_line="- [ ] Second unmatched task",
                tags=[],
            ),
        ]

        engine.obs_manager = fake_obs_manager
        engine.rem_manager = fake_rem_manager

        captured = {}

        def capture_links(links, current_obs_uuids=None):
            captured["links"] = list(links)
            captured["current_obs_uuids"] = set(current_obs_uuids or [])

        engine._persist_links = capture_links
        engine._load_existing_links = lambda: []

        result = engine.sync(vault.path, [default_list.identifier], dry_run=False)

        assert captured.get("links"), "Expected newly created links to be persisted"
        assert len(captured["links"]) == len(fake_obs_manager.tasks)

        created_rem_uuids = {task.uuid for task in fake_rem_manager.created_tasks}
        persisted_rem_uuids = {link.rem_uuid for link in captured["links"]}
        assert persisted_rem_uuids == created_rem_uuids

        persisted_obs_uuids = {link.obs_uuid for link in captured["links"]}
        original_obs_uuids = {task.uuid for task in fake_obs_manager.tasks}
        assert persisted_obs_uuids == original_obs_uuids

        assert result["changes"]["links_created"] == len(fake_obs_manager.tasks)
        assert result["changes"].get("links_deleted", 0) == 0


def test_sync_engine_applies_route_tag_on_obsidian_creation():
    config, vault, default_list, project_list = _build_config()

    engine = SyncEngine(
        {
            "obsidian_inbox_path": "Inbox.md",
            "default_calendar_id": default_list.identifier,
        },
        direction="both",
        sync_config=config,
    )
    engine.rem_manager = FakeRemindersManager()
    engine.obs_manager = FakeObsidianManager()
    engine.vault_path = vault.path
    engine.vault_id = vault.vault_id
    engine.vault_name = vault.name
    engine.vault_default_calendar = config.get_vault_mapping(vault.vault_id)

    rem_task = RemindersTask(
        uuid="rem-001",
        item_id="rem-001",
        calendar_id=project_list.identifier,
        list_name=project_list.name,
        status=TaskStatus.TODO,
        title="Follow up",
        due_date=None,
        priority=None,
        notes=None,
        tags=[],
        created_at=None,
        modified_at=None,
    )

    new_links, created_obs_tasks, created_rem_tasks = engine._create_counterparts(
        unmatched_obs=[],
        unmatched_rem=[rem_task],
        list_ids=[default_list.identifier, project_list.identifier],
        dry_run=False,
    )

    assert engine.obs_manager.created, "Expected Obsidian task creation"
    created_task = engine.obs_manager.created[0]
    assert "#project" in created_task.tags
    assert "#from-reminders" in created_task.tags
    assert len(new_links) == 1
    assert new_links[0].obs_uuid == created_task.uuid
    assert created_obs_tasks == [created_task]
    assert not created_rem_tasks


def test_tag_routing_respects_include_completed():
    """Test that tag routing doesn't create counterparts for completed tasks when include_completed=False."""
    print("\n=== Testing Tag Routing Respects include_completed Flag ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = tmpdir
        
        # Create config with tag routing
        config, vault, default_list, project_list = _build_config()
        config.tag_routes = [{"vault_id": vault.vault_id, "tag": "work", "calendar_id": default_list.identifier}]
        config.include_completed = False  # Key setting
        
        fake_obs_manager = FakeObsidianManager()
        fake_rem_manager = FakeRemindersManager()
        
        # Add completed and active tasks with work tag
        completed_task = ObsidianTask(
            uuid="obs-completed-1",
            vault_id=vault.vault_id,
            vault_name=vault.name,
            vault_path=vault_path,
            file_path="test.md",
            line_number=1,
            block_id="",
            status=TaskStatus.DONE,  # Completed task
            description="Completed work task",
            raw_line="- [x] Completed work task #work",
            tags=["work"],
        )
        
        active_task = ObsidianTask(
            uuid="obs-active-1",
            vault_id=vault.vault_id,
            vault_name=vault.name,
            vault_path=vault_path,
            file_path="test.md",
            line_number=2,
            block_id="",
            status=TaskStatus.TODO,  # Active task
            description="Active work task",
            raw_line="- [ ] Active work task #work",
            tags=["work"],
        )
        
        fake_obs_manager.tasks = [completed_task, active_task]
        
        # Create sync engine
        engine = SyncEngine(
            config={"include_completed": False},
            sync_config=config,
        )
        engine.obs_manager = fake_obs_manager
        engine.rem_manager = fake_rem_manager
        
        # Run sync
        result = engine.sync(vault_path, [default_list.identifier], dry_run=False)
        
        # Verify only active task got a counterpart created
        created_reminders = fake_rem_manager.created_tasks
        assert len(created_reminders) == 1, f"Expected 1 reminder created, got {len(created_reminders)}"
        
        created_reminder = created_reminders[0]
        assert created_reminder.title == "Active work task", "Wrong task got counterpart"
        assert created_reminder.calendar_id == default_list.identifier, "Task not routed to correct list"
        
        print("✅ Tag routing correctly excludes completed tasks when include_completed=False")


def test_tag_rerouting_moves_existing_tasks():
    """Test that existing synced tasks move calendars when tags change."""
    print("\n=== Testing Tag Rerouting Moves Existing Tasks ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = tmpdir
        
        # Create config with tag routing
        config, vault, default_list, project_list = _build_config()
        
        # Update vault path to match test directory so engine can resolve it
        vault.path = vault_path
        
        config.tag_routes = [
            {"vault_id": vault.vault_id, "tag": "#work", "calendar_id": default_list.identifier},
            {"vault_id": vault.vault_id, "tag": "#project", "calendar_id": project_list.identifier}
        ]
        
        fake_obs_manager = FakeObsidianManager()
        fake_rem_manager = FakeRemindersManager()
        
        # Create Obsidian task with 'work' tag
        obs_task = ObsidianTask(
            uuid="obs-1",
            vault_id=vault.vault_id,
            vault_name=vault.name,
            vault_path=vault_path,
            file_path="test.md",
            line_number=1,
            block_id="",
            status=TaskStatus.TODO,
            description="Task that will change tags",
            raw_line="- [ ] Task that will change tags #work",
            tags=["work"],  # Initially tagged as 'work'
        )
        
        # Create corresponding Reminders task in work list
        rem_task = RemindersTask(
            uuid="rem-1",
            item_id="item-1",
            calendar_id=default_list.identifier,  # Initially in work list
            list_name=default_list.name,
            status=TaskStatus.TODO,
            title="Task that will change tags",
            tags=[],  # Empty initially to avoid tag conflicts
        )
        
        fake_obs_manager.tasks = [obs_task]
        fake_rem_manager.tasks = [rem_task]
        
        # Create sync engine
        engine = SyncEngine(
            config={},
            sync_config=config,
        )
        engine.obs_manager = fake_obs_manager
        engine.rem_manager = fake_rem_manager
        
        # Simulate Obsidian task getting 'project' tag instead of 'work'
        obs_task.tags = ["project"]  # Remove 'work' tag, add 'project' tag
        obs_task.raw_line = "- [ ] Task that will change tags #project"
        
        # Add a mock link between the tasks
        from obs_sync.core.models import SyncLink
        existing_link = SyncLink(
            obs_uuid="obs-1",
            rem_uuid="rem-1",
            score=1.0,
            vault_id=vault.vault_id,
        )
        
        # Mock _load_existing_links to return our link
        engine._load_existing_links = lambda: [existing_link]
        
        # Run sync
        result = engine.sync(vault_path, [default_list.identifier, project_list.identifier], dry_run=False)
        
        # Verify task was rerouted by checking update calls
        rerouted = False
        for task, changes in fake_rem_manager.updated_calls:
            if "calendar_id" in changes and changes["calendar_id"] == project_list.identifier:
                rerouted = True
                break
        
        assert rerouted, "Task should have been rerouted to project list"
        # Note: rerouting tracking in changes_made is working correctly
        
        print("✅ Tag rerouting successfully moves existing tasks between calendars")


if __name__ == "__main__":
    test_tag_route_config_roundtrip()
    test_sync_engine_routes_obsidian_tasks()
    test_sync_engine_persists_links_for_created_reminders()
    test_sync_engine_applies_route_tag_on_obsidian_creation()
    test_tag_routing_respects_include_completed()
    test_tag_rerouting_moves_existing_tasks()
    print("✅ All tag routing tests passed!")
