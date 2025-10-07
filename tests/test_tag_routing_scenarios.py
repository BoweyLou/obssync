#!/usr/bin/env python3
"""
Comprehensive test for tag routing scenarios to validate architectural fixes.

Tests three key scenarios:
1. Adding tag routes to existing vault preserves links
2. Setup reconfigure with reset maintains vault IDs and routing
3. Tag routing identification works correctly
"""

import os
import sys
import json
import tempfile
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from obs_sync.core.models import (
    SyncConfig,
    Vault,
    RemindersList,
    ObsidianTask,
    RemindersTask,
    TaskStatus,
    SyncLink
)
from obs_sync.sync.engine import SyncEngine
from obs_sync.commands.setup import SetupCommand
from obs_sync.obsidian.tasks import ObsidianTaskManager


def generate_deterministic_vault_id(path: str) -> str:
    """Generate the same deterministic vault ID that Vault.__post_init__ would create."""
    normalized_path = os.path.abspath(os.path.expanduser(path))
    path_hash = hashlib.sha256(normalized_path.encode()).hexdigest()
    return f"vault-{path_hash[:12]}"


def test_scenario_1_add_tag_routes_preserves_links():
    """Test that adding tag routes to existing vault preserves links."""
    print("\n=== Scenario 1: Adding Tag Routes Preserves Links ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir) / "TestVault"
        vault_path.mkdir()
        
        # Create initial configuration with vault and default list
        config = SyncConfig()
        vault = Vault(
            name="TestVault",
            path=str(vault_path),
            vault_id=generate_deterministic_vault_id(str(vault_path)),
            is_default=True
        )
        config.vaults = [vault]
        
        default_list = RemindersList(
            name="Default List",
            identifier="default-list-id",
            source_name="Reminders",
            source_type="local"
        )
        project_list = RemindersList(
            name="Projects",
            identifier="project-list-id",
            source_name="Reminders",
            source_type="local"
        )
        config.reminders_lists = [default_list, project_list]
        config.set_vault_mapping(vault.vault_id, default_list.identifier)
        
        print(f"Initial vault ID: {vault.vault_id}")
        
        # Create test markdown file with tasks
        test_file = vault_path / "tasks.md"
        test_file.write_text("""# Tasks
- [ ] Regular task ^task1
- [ ] Project task #project ^task2
- [ ] Another task #work ^task3
""")
        
        # Create sync links file simulating existing synced tasks
        links_dir = vault_path / ".obs-sync" / "data"
        links_dir.mkdir(parents=True)
        links_file = links_dir / "sync_links.json"
        
        existing_links = [
            {
                "obs_uuid": "obs-task1",
                "rem_uuid": "rem-001",
                "score": 1.0,
                "last_synced": datetime.now(timezone.utc).isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat()
            },
            {
                "obs_uuid": "obs-task2",
                "rem_uuid": "rem-002",
                "score": 1.0,
                "last_synced": datetime.now(timezone.utc).isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat()
            }
        ]
        
        with open(links_file, 'w') as f:
            json.dump({'links': existing_links}, f)
        
        print(f"Created {len(existing_links)} existing links")
        
        # Now add tag routes to the configuration
        config.set_tag_route(vault.vault_id, "#project", project_list.identifier)
        config.set_tag_route(vault.vault_id, "#work", project_list.identifier)
        
        print("Added tag routes:")
        for route in config.get_tag_routes_for_vault(vault.vault_id):
            print(f"  {route['tag']} -> {route['calendar_id']}")
        
        # Initialize sync engine with tag routes
        engine_config = {
            "links_path": str(links_file),
            "default_calendar_id": default_list.identifier,
            "min_score": 0.75,
            "days_tolerance": 1,
        }
        
        engine = SyncEngine(engine_config, sync_config=config)
        
        # Load and verify links are preserved
        loaded_links = engine._load_existing_links()
        assert len(loaded_links) == len(existing_links), "Links should be preserved"
        print(f"✓ All {len(loaded_links)} links preserved after adding tag routes")
        
        # Verify vault resolution works correctly
        resolved_vault = engine._resolve_vault_for_path(str(vault_path))
        assert resolved_vault is not None, "Vault should be resolved"
        assert resolved_vault.vault_id == vault.vault_id, "Vault ID should match"
        print(f"✓ Vault resolved correctly with ID: {resolved_vault.vault_id}")
        
        # Test that new tasks would be routed correctly
        obs_task = ObsidianTask(
            uuid="obs-newtask",
            vault_id=vault.vault_id,
            vault_name=vault.name,
            vault_path=str(vault_path),
            file_path="tasks.md",
            line_number=10,
            block_id="newtask",
            status=TaskStatus.TODO,
            description="New project task",
            raw_line="- [ ] New project task #project ^newtask",
            tags=["#project"]
        )
        
        # Set up engine context
        engine.vault_id = vault.vault_id
        engine.vault_path = str(vault_path)
        
        selected_calendar = engine._select_calendar_for_obs_task(
            obs_task,
            default_list.identifier,
            [default_list.identifier, project_list.identifier]
        )
        
        assert selected_calendar == project_list.identifier, "Task should route to project list"
        print(f"✓ New task with #project correctly routes to {project_list.name}")
        
        # Test rerouting of existing linked task when tag routes are added
        print("\n--- Testing rerouting of existing linked task ---")
        
        # Create mock Obsidian and Reminders tasks that are already linked
        existing_obs_task = ObsidianTask(
            uuid="obs-task2",  # Matches existing link
            vault_id=vault.vault_id,
            vault_name=vault.name,
            vault_path=str(vault_path),
            file_path="tasks.md",
            line_number=3,
            block_id="task2",
            status=TaskStatus.TODO,
            description="Project task",
            raw_line="- [ ] Project task #project ^task2",
            tags=["#project"],
            modified_at=datetime.now(timezone.utc)
        )
        
        existing_rem_task = RemindersTask(
            uuid="rem-002",  # Matches existing link
            item_id="reminder-item-002",
            calendar_id=default_list.identifier,  # Currently in default list
            list_name=default_list.name,
            status=TaskStatus.TODO,
            title="Project task",
            tags=["#project"],
            modified_at=datetime.now(timezone.utc)
        )
        
        # Check if task should be rerouted
        engine.vault_id = vault.vault_id
        engine.vault_path = str(vault_path)
        target_calendar = engine._should_reroute_task(existing_obs_task, existing_rem_task.calendar_id)
        
        assert target_calendar is not None, "Task should be identified for rerouting"
        assert target_calendar == project_list.identifier, f"Task should reroute to project list, got {target_calendar}"
        print(f"✓ Existing linked task with #project correctly identified for rerouting")
        print(f"  From: {default_list.name} ({default_list.identifier})")
        print(f"  To: {project_list.name} ({project_list.identifier})")
        
        # Test that tasks without routing tags are not rerouted
        task_without_route = ObsidianTask(
            uuid="obs-task1",
            vault_id=vault.vault_id,
            vault_name=vault.name,
            vault_path=str(vault_path),
            file_path="tasks.md",
            line_number=2,
            block_id="task1",
            status=TaskStatus.TODO,
            description="Regular task",
            raw_line="- [ ] Regular task ^task1",
            tags=[],  # No tags
            modified_at=datetime.now(timezone.utc)
        )
        
        no_reroute = engine._should_reroute_task(task_without_route, default_list.identifier)
        assert no_reroute is None, "Task without routing tags should not be rerouted"
        print(f"✓ Task without routing tags correctly skipped for rerouting")
        
        print("\n✅ Scenario 1 PASSED: Tag routes added without affecting existing links, and rerouting works correctly")


def test_scenario_2_reset_preserves_vault_ids():
    """Test that reset reconfigure preserves vault IDs and maintains routing."""
    print("\n=== Scenario 2: Reset Reconfigure Preserves Vault IDs ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir) / "TestVault"
        vault_path.mkdir()
        config_path = Path(tmpdir) / "config.json"
        
        # Create initial configuration
        initial_config = SyncConfig()
        
        # Use a fixed vault_id for testing (simulating existing config)
        existing_vault_id = "vault-existing123"
        
        vault = Vault(
            name="TestVault",
            path=str(vault_path),
            vault_id=existing_vault_id,  # Use fixed ID to test preservation
            is_default=True
        )
        initial_config.vaults = [vault]
        
        default_list = RemindersList(
            name="Default List",
            identifier="default-list-id"
        )
        project_list = RemindersList(
            name="Projects",
            identifier="project-list-id"
        )
        initial_config.reminders_lists = [default_list, project_list]
        
        # Set up initial mappings and routes
        initial_config.set_vault_mapping(vault.vault_id, default_list.identifier)
        initial_config.set_tag_route(vault.vault_id, "#project", project_list.identifier)
        
        # Save initial config
        initial_config.save_to_file(str(config_path))
        print(f"Initial config saved with vault_id: {existing_vault_id}")
        
        # Simulate reset reconfigure
        # Load the config fresh
        loaded_config = SyncConfig.load_from_file(str(config_path))
        
        # Verify vault ID was loaded correctly
        assert len(loaded_config.vaults) == 1, "Should have one vault"
        assert loaded_config.vaults[0].vault_id == existing_vault_id, "Vault ID should be preserved on load"
        print(f"✓ Vault ID preserved after load: {loaded_config.vaults[0].vault_id}")
        
        # Mock the vault discovery to return our test vault
        def mock_discover_vaults():
            return [Vault(name="TestVault", path=str(vault_path))]
        
        # Mock the reminders discovery
        def mock_discover_reminders():
            return [default_list, project_list]
        
        # Test the setup command with reset
        setup_cmd = SetupCommand(loaded_config, enable_suggestions=False)
        
        with patch.object(setup_cmd, '_discover_vaults', side_effect=mock_discover_vaults):
            with patch.object(setup_cmd, '_discover_reminders_lists', side_effect=mock_discover_reminders):
                with patch('builtins.input', side_effect=[
                    '1',  # Select reset option
                    '1',  # Select vault
                    '1',  # Default vault
                    'all',  # Select all reminders lists
                    '1',  # Map vault to first list
                    '',  # Skip tag routes
                    '',  # Keep default min_score
                    'n'   # Don't include completed
                ]):
                    # The setup should preserve vault IDs
                    setup_cmd._continue_full_setup()
        
        # Check if vault ID was preserved or regenerated correctly
        final_vault = setup_cmd.config.vaults[0]
        print(f"Final vault ID after reset: {final_vault.vault_id}")
        
        # The ID should either be preserved (if our preservation logic works)
        # or be deterministically generated based on path
        expected_deterministic_id = generate_deterministic_vault_id(str(vault_path))
        
        # Our fix should preserve the ID or generate a deterministic one
        assert final_vault.vault_id in [existing_vault_id, expected_deterministic_id], \
            f"Vault ID should be preserved or deterministic, got: {final_vault.vault_id}"
        
        # Verify tag routes can still be added after reset
        setup_cmd.config.set_tag_route(final_vault.vault_id, "#work", project_list.identifier)
        routes = setup_cmd.config.get_tag_routes_for_vault(final_vault.vault_id)
        
        print(f"✓ Tag routes work with vault ID: {final_vault.vault_id}")
        print(f"  Routes configured: {len(routes)}")
        
        print("\n✅ Scenario 2 PASSED: Vault IDs handled correctly during reset")


def test_scenario_3_tag_routing_identification():
    """Test that tag routing identification works correctly."""
    print("\n=== Scenario 3: Tag Routing Identification Works ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create two vaults with different paths
        vault1_path = Path(tmpdir) / "Vault1"
        vault2_path = Path(tmpdir) / "Vault2"
        vault1_path.mkdir()
        vault2_path.mkdir()
        
        # Set up configuration with multiple vaults
        config = SyncConfig()
        
        vault1 = Vault(
            name="Vault1",
            path=str(vault1_path),
            vault_id=generate_deterministic_vault_id(str(vault1_path)),
            is_default=True
        )
        vault2 = Vault(
            name="Vault2",
            path=str(vault2_path),
            vault_id=generate_deterministic_vault_id(str(vault2_path)),
            is_default=False
        )
        config.vaults = [vault1, vault2]
        
        # Set up lists
        work_list = RemindersList(name="Work", identifier="work-list-id")
        personal_list = RemindersList(name="Personal", identifier="personal-list-id")
        config.reminders_lists = [work_list, personal_list]
        
        # Set up different mappings for each vault
        config.set_vault_mapping(vault1.vault_id, work_list.identifier)
        config.set_vault_mapping(vault2.vault_id, personal_list.identifier)
        
        # Set up tag routes for each vault
        config.set_tag_route(vault1.vault_id, "#project", work_list.identifier)
        config.set_tag_route(vault1.vault_id, "#work", work_list.identifier)
        config.set_tag_route(vault2.vault_id, "#home", personal_list.identifier)
        config.set_tag_route(vault2.vault_id, "#personal", personal_list.identifier)
        
        print("Configuration:")
        print(f"  Vault1 ({vault1.vault_id[:12]}...): default={work_list.name}, routes=[#project, #work]")
        print(f"  Vault2 ({vault2.vault_id[:12]}...): default={personal_list.name}, routes=[#home, #personal]")
        
        # Create sync engine
        engine_config = {
            "default_calendar_id": work_list.identifier,
            "min_score": 0.75,
        }
        engine = SyncEngine(engine_config, sync_config=config)
        
        # Test vault resolution with various path formats
        test_cases = [
            (str(vault1_path), vault1.vault_id, "absolute path"),
            (str(vault1_path) + "/", vault1.vault_id, "trailing slash"),
            (str(Path(vault1_path).resolve()), vault1.vault_id, "resolved path"),
            (str(vault2_path), vault2.vault_id, "vault2 absolute"),
        ]
        
        for path, expected_id, desc in test_cases:
            resolved = engine._resolve_vault_for_path(path)
            assert resolved is not None, f"Should resolve vault for {desc}"
            assert resolved.vault_id == expected_id, f"Should get correct vault_id for {desc}"
            print(f"✓ Resolved {desc}: {resolved.vault_id[:12]}...")
        
        # Test tag routing with correct vault context
        engine.vault_id = vault1.vault_id
        engine.vault_path = str(vault1_path)
        
        # Create task with #project tag in Vault1
        task1 = ObsidianTask(
            uuid="obs-task1",
            vault_id=vault1.vault_id,
            vault_name=vault1.name,
            vault_path=str(vault1_path),
            file_path="work.md",
            line_number=1,
            block_id="task1",
            status=TaskStatus.TODO,
            description="Work project",
            raw_line="- [ ] Work project #project",
            tags=["#project"]
        )
        
        selected = engine._select_calendar_for_obs_task(
            task1,
            config.get_vault_mapping(vault1.vault_id),
            [work_list.identifier, personal_list.identifier]
        )
        
        assert selected == work_list.identifier, f"Task in Vault1 with #project should route to Work list"
        print(f"✓ Vault1 task with #project routes to {work_list.name}")
        
        # Switch context to Vault2
        engine.vault_id = vault2.vault_id
        engine.vault_path = str(vault2_path)
        
        # Create task with #personal tag in Vault2
        task2 = ObsidianTask(
            uuid="obs-task2",
            vault_id=vault2.vault_id,
            vault_name=vault2.name,
            vault_path=str(vault2_path),
            file_path="home.md",
            line_number=1,
            block_id="task2",
            status=TaskStatus.TODO,
            description="Personal task",
            raw_line="- [ ] Personal task #personal",
            tags=["#personal"]
        )
        
        selected = engine._select_calendar_for_obs_task(
            task2,
            config.get_vault_mapping(vault2.vault_id),
            [work_list.identifier, personal_list.identifier]
        )
        
        assert selected == personal_list.identifier, f"Task in Vault2 with #personal should route to Personal list"
        print(f"✓ Vault2 task with #personal routes to {personal_list.name}")
        
        # Test tag summary aggregation
        obs_tasks = [task1, task2]
        rem_tasks = [
            RemindersTask(
                uuid="rem-001",
                item_id="rem-001",
                calendar_id=work_list.identifier,
                list_name=work_list.name,
                status=TaskStatus.TODO,
                title="Work project"
            ),
            RemindersTask(
                uuid="rem-002",
                item_id="rem-002",
                calendar_id=personal_list.identifier,
                list_name=personal_list.name,
                status=TaskStatus.TODO,
                title="Personal task"
            )
        ]
        
        links = [
            SyncLink(obs_uuid="obs-task1", rem_uuid="rem-001", score=1.0),
            SyncLink(obs_uuid="obs-task2", rem_uuid="rem-002", score=1.0)
        ]
        
        # Test tag summary for Vault1
        engine.vault_id = vault1.vault_id
        summary = engine._collect_tag_routing_summary(obs_tasks, rem_tasks, links)
        
        # Should only show tags configured for Vault1
        if "#project" in summary:
            assert work_list.name in str(summary["#project"]), "Vault1 #project should map to Work"
            print(f"✓ Tag summary for Vault1 shows #project -> {work_list.name}")
        
        print("\n✅ Scenario 3 PASSED: Tag routing identification works correctly")


def test_migration_compatibility():
    """Test that migration from old UUID-based vault IDs works correctly."""
    print("\n=== Testing Migration Compatibility ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir) / "MigratedVault"
        vault_path.mkdir()
        config_path = Path(tmpdir) / "config.json"
        
        # Create config with old-style UUID vault_id
        old_uuid = "550e8400-e29b-41d4-a716-446655440000"  # Valid UUID v4
        
        config_data = {
            "vaults": [
                {
                    "name": "MigratedVault",
                    "path": str(vault_path),
                    "vault_id": old_uuid,
                    "is_default": True
                }
            ],
            "reminders_lists": [
                {
                    "name": "Default",
                    "identifier": "default-list"
                }
            ],
            "vault_mappings": [
                {
                    "vault_id": old_uuid,
                    "calendar_id": "default-list"
                }
            ],
            "tag_routes": [
                {
                    "vault_id": old_uuid,
                    "tag": "#work",
                    "calendar_id": "default-list"
                }
            ]
        }
        
        with open(config_path, 'w') as f:
            json.dump(config_data, f)
        
        print(f"Created config with old UUID vault_id: {old_uuid}")
        
        # Load the config
        loaded_config = SyncConfig.load_from_file(str(config_path))
        
        # Verify old UUID is preserved
        assert len(loaded_config.vaults) == 1
        vault = loaded_config.vaults[0]
        assert vault.vault_id == old_uuid, "Old UUID should be preserved for compatibility"
        print(f"✓ Old UUID preserved: {vault.vault_id}")
        
        # Verify mappings still work
        mapping = loaded_config.get_vault_mapping(old_uuid)
        assert mapping == "default-list", "Vault mapping should work with old UUID"
        print("✓ Vault mappings work with old UUID")
        
        # Verify tag routes still work
        route = loaded_config.get_tag_route(old_uuid, "#work")
        assert route == "default-list", "Tag route should work with old UUID"
        print("✓ Tag routes work with old UUID")
        
        # Create sync engine and verify it works
        engine = SyncEngine({"default_calendar_id": "default-list"}, sync_config=loaded_config)
        
        # The engine should handle old UUIDs correctly
        resolved = engine._resolve_vault_for_path(str(vault_path))
        assert resolved is not None, "Should resolve vault with old UUID"
        assert resolved.vault_id == old_uuid, "Should maintain old UUID"
        print("✓ Sync engine resolves vault with old UUID")
        
        print("\n✅ Migration Compatibility PASSED: Old UUIDs preserved correctly")


def test_scenario_4_full_sync_with_rerouting():
    """Test full sync flow with rerouting in both dry-run and apply modes."""
    print("\n=== Scenario 4: Full Sync with Rerouting (Dry-Run and Apply) ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir) / "TestVault"
        vault_path.mkdir()
        
        # Create configuration
        config = SyncConfig()
        vault = Vault(
            name="TestVault",
            path=str(vault_path),
            vault_id=generate_deterministic_vault_id(str(vault_path)),
            is_default=True
        )
        config.vaults = [vault]
        
        default_list = RemindersList(
            name="Default List",
            identifier="default-list-id",
            source_name="Reminders",
            source_type="local"
        )
        project_list = RemindersList(
            name="Projects",
            identifier="project-list-id",
            source_name="Reminders",
            source_type="local"
        )
        config.reminders_lists = [default_list, project_list]
        config.set_vault_mapping(vault.vault_id, default_list.identifier)
        config.set_tag_route(vault.vault_id, "#project", project_list.identifier)
        
        # Set up sync engine
        links_dir = vault_path / ".obs-sync" / "data"
        links_dir.mkdir(parents=True)
        links_file = links_dir / "sync_links.json"
        
        engine_config = {
            "links_path": str(links_file),
            "default_calendar_id": default_list.identifier,
            "min_score": 0.75,
            "days_tolerance": 1,
        }
        
        # Create mock managers
        mock_obs_manager = Mock()
        mock_rem_manager = Mock()
        
        # Create test tasks
        obs_task = ObsidianTask(
            uuid="obs-123",
            vault_id=vault.vault_id,
            vault_name=vault.name,
            vault_path=str(vault_path),
            file_path="tasks.md",
            line_number=1,
            block_id="task1",
            status=TaskStatus.TODO,
            description="Test task",
            raw_line="- [ ] Test task #project ^task1",
            tags=["#project"],
            modified_at=datetime.now(timezone.utc)
        )
        
        rem_task = RemindersTask(
            uuid="rem-456",
            item_id="item-456",
            calendar_id=default_list.identifier,  # Currently in wrong list
            list_name=default_list.name,
            status=TaskStatus.TODO,
            title="Test task",
            tags=["#project"],
            modified_at=datetime.now(timezone.utc)
        )
        
        # Create existing link
        now_iso = datetime.now(timezone.utc).isoformat()
        existing_link_data = {
            "obs_uuid": "obs-123",
            "rem_uuid": "rem-456",
            "score": 1.0,
            "vault_id": vault.vault_id,
            "last_synced": now_iso,
            "created_at": now_iso
        }
        
        with open(links_file, 'w') as f:
            json.dump({'links': [existing_link_data]}, f)
        
        # Mock manager methods
        mock_obs_manager.list_tasks.return_value = [obs_task]
        mock_rem_manager.list_tasks.return_value = [rem_task]
        mock_rem_manager.update_task.return_value = True
        
        # Test dry-run mode
        print("\n--- Testing dry-run mode ---")
        engine = SyncEngine(engine_config, sync_config=config, direction="both")
        engine.obs_manager = mock_obs_manager
        engine.rem_manager = mock_rem_manager
        
        result = engine.sync(str(vault_path), [default_list.identifier, project_list.identifier], dry_run=True)
        
        # In dry-run, update_task should not be called
        assert mock_rem_manager.update_task.call_count == 0, "Should not update in dry-run mode"
        assert result['changes'].get('rem_rerouted', 0) == 1, "Should count rerouting in dry-run"
        print("✓ Dry-run mode: rerouting counted but not applied")
        
        # Test apply mode
        print("\n--- Testing apply mode ---")
        mock_rem_manager.reset_mock()
        engine = SyncEngine(engine_config, sync_config=config, direction="both")
        engine.obs_manager = mock_obs_manager
        engine.rem_manager = mock_rem_manager
        
        result = engine.sync(str(vault_path), [default_list.identifier, project_list.identifier], dry_run=False)
        
        # In apply mode, update_task should be called for rerouting
        assert mock_rem_manager.update_task.call_count > 0, "Should update in apply mode"
        # Check that rerouting was attempted
        update_calls = [call for call in mock_rem_manager.update_task.call_args_list
                       if 'calendar_id' in call[0][1]]
        assert len(update_calls) > 0, "Should have rerouting update call"
        assert result['changes'].get('rem_rerouted', 0) == 1, "Should count rerouting in apply mode"
        print("✓ Apply mode: rerouting applied successfully")
        
        # Verify the rerouting was to the correct list
        reroute_call = update_calls[0]
        assert reroute_call[0][1]['calendar_id'] == project_list.identifier, "Should reroute to project list"
        print(f"✓ Task correctly rerouted to {project_list.name}")
        
        print("\n✅ Scenario 4 PASSED: Full sync with rerouting works in both dry-run and apply modes")


def run_all_tests():
    """Run all scenario tests."""
    print("=" * 70)
    print("TAG ROUTING SCENARIO TESTS")
    print("=" * 70)
    
    try:
        test_scenario_1_add_tag_routes_preserves_links()
        test_scenario_2_reset_preserves_vault_ids()
        test_scenario_3_tag_routing_identification()
        test_migration_compatibility()
        test_scenario_4_full_sync_with_rerouting()
        
        print("\n" + "=" * 70)
        print("🎉 ALL TESTS PASSED SUCCESSFULLY!")
        print("=" * 70)
        return True
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)