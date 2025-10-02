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
        self.deleted = []
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

    def delete_task(self, task: RemindersTask) -> bool:
        self.deleted.append(task)
        return True


class FakeObsidianManager:
    def __init__(self) -> None:
        self.created = []
        self.updated_calls = []
        self.deleted = []
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

    def delete_task(self, task: ObsidianTask) -> bool:
        self.deleted.append(task)
        return True


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


def test_import_mode_persistence_roundtrip():
    """Test that import_mode is preserved when saving and loading config."""
    config = SyncConfig()
    vault = Vault(name="Work", path="/vault/path", vault_id="vault-123")
    config.vaults = [vault]
    
    project_list = RemindersList(name="Project List", identifier="list-project")
    personal_list = RemindersList(name="Personal List", identifier="list-personal")
    config.reminders_lists = [project_list, personal_list]
    
    # Set routes with different import modes
    config.set_tag_route(vault.vault_id, "#project", project_list.identifier, "full_import")
    config.set_tag_route(vault.vault_id, "#personal", personal_list.identifier, "existing_only")
    
    # Verify modes are set correctly
    assert config.get_tag_route_import_mode(vault.vault_id, "#project") == "full_import"
    assert config.get_tag_route_import_mode(vault.vault_id, "#personal") == "existing_only"
    
    # Test round-trip persistence
    temp_dir = tempfile.mkdtemp(prefix="obs-sync-test-")
    temp_path = os.path.join(temp_dir, "config.json")
    
    try:
        config.save_to_file(temp_path)
        loaded = SyncConfig.load_from_file(temp_path)
        
        # Verify routes and modes are preserved
        assert loaded.get_tag_route(vault.vault_id, "#project") == project_list.identifier
        assert loaded.get_tag_route_import_mode(vault.vault_id, "#project") == "full_import"
        assert loaded.get_tag_route(vault.vault_id, "#personal") == personal_list.identifier
        assert loaded.get_tag_route_import_mode(vault.vault_id, "#personal") == "existing_only"
        
        # Test default mode for legacy routes (missing import_mode)
        assert loaded.get_tag_route_import_mode(vault.vault_id, "#nonexistent") == "existing_only"
    finally:
        try:
            os.remove(temp_path)
        except FileNotFoundError:
            pass
        os.rmdir(temp_dir)


def test_existing_only_mode_filters_new_reminders_tasks():
    """Test that existing_only mode prevents importing new Reminders tasks."""
    from obs_sync.core.models import SyncLink
    
    config = SyncConfig()
    vault = Vault(name="Work", path="/vault/path", vault_id="vault-123")
    config.vaults = [vault]
    
    project_list = RemindersList(name="Project List", identifier="list-project")
    config.reminders_lists = [project_list]
    
    # Set route with existing_only mode
    config.set_tag_route(vault.vault_id, "#project", project_list.identifier, "existing_only")
    
    # Create fake managers
    fake_obs_manager = FakeObsidianManager()
    fake_rem_manager = FakeRemindersManager()
    
    # Create two Reminders tasks with #project tag
    rem_task_existing = RemindersTask(
        uuid="rem-existing",
        item_id="item-1",
        calendar_id=project_list.identifier,
        list_name=project_list.name,
        status=TaskStatus.TODO,
        title="Existing task",
        tags=["#project"],
    )
    
    rem_task_new = RemindersTask(
        uuid="rem-new",
        item_id="item-2",
        calendar_id=project_list.identifier,
        list_name=project_list.name,
        status=TaskStatus.TODO,
        title="New task",
        tags=["#project"],
    )
    
    fake_rem_manager.tasks = [rem_task_existing, rem_task_new]
    
    # Create a corresponding Obsidian task only for the existing one
    obs_task_existing = ObsidianTask(
        uuid="obs-existing",
        vault_id=vault.vault_id,
        vault_name=vault.name,
        vault_path=vault.path,
        file_path="test.md",
        line_number=1,
        block_id="",
        status=TaskStatus.TODO,
        description="Existing task",
        raw_line="- [ ] Existing task",
        tags=["#project"],
    )
    
    fake_obs_manager.tasks = [obs_task_existing]
    
    # Create existing link for the existing task
    existing_link = SyncLink(
        obs_uuid="obs-existing",
        rem_uuid="rem-existing",
        score=1.0,
        vault_id=vault.vault_id,
    )
    
    # Create sync engine
    temp_dir = tempfile.mkdtemp(prefix="obs-sync-test-")
    links_path = os.path.join(temp_dir, "links.jsonl")
    
    try:
        # Write the existing link
        import json
        with open(links_path, 'w') as f:
            f.write(json.dumps(existing_link.to_dict()) + '\n')
        
        config.links_path = links_path
        
        engine = SyncEngine(
            config={},
            sync_config=config,
        )
        engine.obs_manager = fake_obs_manager
        engine.rem_manager = fake_rem_manager
        
        # Run sync
        result = engine.sync(vault.path, [project_list.identifier], dry_run=True)
        
        # Verify results
        assert result['success']
        
        # Should skip the new task due to existing_only mode
        assert result['skipped_rem_count'] == 1
        
        # Should not create Obsidian task for new Reminders task
        assert len(fake_obs_manager.created) == 0
        
    finally:
        try:
            os.remove(links_path)
        except FileNotFoundError:
            pass
        os.rmdir(temp_dir)


def test_full_import_mode_imports_all_tasks():
    """Test that full_import mode imports all Reminders tasks."""
    config = SyncConfig()
    vault = Vault(name="Work", path="/vault/path", vault_id="vault-123")
    config.vaults = [vault]
    
    default_list = RemindersList(name="Default List", identifier="list-default")
    project_list = RemindersList(name="Project List", identifier="list-project")
    config.reminders_lists = [default_list, project_list]
    
    # Set default vault mapping
    config.set_vault_mapping(vault.vault_id, default_list.identifier)
    
    # Set route with full_import mode
    config.set_tag_route(vault.vault_id, "#project", project_list.identifier, "full_import")
    
    # Create fake managers
    fake_obs_manager = FakeObsidianManager()
    fake_rem_manager = FakeRemindersManager()
    
    # Create a Reminders task with #project tag
    rem_task = RemindersTask(
        uuid="rem-1",
        item_id="item-1",
        calendar_id=project_list.identifier,
        list_name=project_list.name,
        status=TaskStatus.TODO,
        title="New project task",
        tags=["#project"],
    )
    
    fake_rem_manager.tasks = [rem_task]
    fake_obs_manager.tasks = []  # No existing Obsidian tasks
    
    # Create sync engine
    temp_dir = tempfile.mkdtemp(prefix="obs-sync-test-")
    links_path = os.path.join(temp_dir, "links.jsonl")
    
    try:
        config.links_path = links_path
        config.obsidian_inbox_path = "inbox.md"
        
        engine = SyncEngine(
            config={"obsidian_inbox_path": "inbox.md"},
            sync_config=config,
        )
        engine.obs_manager = fake_obs_manager
        engine.rem_manager = fake_rem_manager
        
        # Run sync - use dry_run=True to test
        result = engine.sync(vault.path, [project_list.identifier], dry_run=True)
        
        # Verify results
        assert result['success'], f"Sync failed: {result}"
        
        # The key test: full_import mode should not skip any tasks from routed calendars
        assert result['skipped_rem_count'] == 0, f"full_import should not skip tasks, got: {result['skipped_rem_count']}"
        
    finally:
        try:
            os.remove(links_path)
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
    
    # This test validates that completed tasks are filtered before counterpart creation
    # The filtering logic is in sync engine lines 320-322
    config, vault, default_list, project_list = _build_config()
    
    # Set up active and completed tasks
    active_task = ObsidianTask(
        uuid="obs-active",
        vault_id=vault.vault_id,
        vault_name=vault.name,
        vault_path=vault.path,
        file_path="test.md",
        line_number=1,
        block_id="",
        status=TaskStatus.TODO,
        description="Active task",
        raw_line="- [ ] Active task",
        tags=[],
    )
    
    completed_task = ObsidianTask(
        uuid="obs-completed",
        vault_id=vault.vault_id,
        vault_name=vault.name,
        vault_path=vault.path,
        file_path="test.md",
        line_number=2,
        block_id="",
        status=TaskStatus.DONE,
        description="Completed task",
        raw_line="- [x] Completed task",
        tags=[],
    )
    
    fake_obs_manager = FakeObsidianManager()
    fake_obs_manager.tasks = [active_task, completed_task]
    
    fake_rem_manager = FakeRemindersManager()
    
    # Create sync engine with include_completed=False
    engine = SyncEngine(
        config={"include_completed": False},
        sync_config=config,
    )
    engine.obs_manager = fake_obs_manager
    engine.rem_manager = fake_rem_manager
    
    # Run sync
    result = engine.sync(vault.path, [default_list.identifier], dry_run=True)
    
    # Verify: Only the active task should be considered for counterpart creation
    # The completed task should be filtered out at line 320-322 of sync/engine.py
    assert result['success']
    assert result['changes']['rem_created'] == 1, f"Expected 1 reminder to be created, got {result['changes']['rem_created']}"
    
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
        
        # Set tag routes properly with import modes
        config.set_tag_route(vault.vault_id, "#work", default_list.identifier, "full_import")
        config.set_tag_route(vault.vault_id, "#project", project_list.identifier, "full_import")
        
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
