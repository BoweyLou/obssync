"""
Comprehensive tests for task deduplication functionality.

Tests the deduplication module, prompting utilities, and integration with sync command.
"""

import os
import sys
import tempfile
import json
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch
import traceback

# Add the project root to Python path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from obs_sync.core.models import ObsidianTask, RemindersTask, TaskStatus, SyncConfig
from obs_sync.sync.deduplicator import TaskDeduplicator, DuplicateCluster, DeduplicationResults
from obs_sync.utils.prompts import (
    format_task_for_display, 
    display_duplicate_cluster,
    confirm_deduplication,
    prompt_for_keeps
)
from obs_sync.commands.sync import _run_deduplication


def test_duplicate_cluster_creation():
    """Test DuplicateCluster data structure."""
    print("🧪 Testing DuplicateCluster creation...")
    
    # Create sample tasks
    obs_task1 = ObsidianTask(
        uuid="obs-1",
        vault_id="vault1",
        vault_name="Test Vault",
        vault_path="/test/vault",
        file_path="test.md",
        line_number=1,
        block_id=None,
        status=TaskStatus.TODO,
        description="Review PR #123",
        raw_line="- [ ] Review PR #123",
        due_date=None,
        completion_date=None,
        priority=None,
        tags=[],
        created_at=datetime.now(timezone.utc),
        modified_at=datetime.now(timezone.utc)
    )
    
    obs_task2 = ObsidianTask(
        uuid="obs-2", 
        vault_id="vault1",
        vault_name="Test Vault",
        vault_path="/test/vault",
        file_path="test.md",
        line_number=2,
        block_id=None,
        status=TaskStatus.TODO,
        description="Review PR #123",
        raw_line="- [ ] Review PR #123",
        due_date=None,
        completion_date=None,
        priority=None,
        tags=[],
        created_at=datetime.now(timezone.utc),
        modified_at=datetime.now(timezone.utc)
    )
    
    rem_task = RemindersTask(
        uuid="rem-1",
        item_id="item-1", 
        calendar_id="cal-1",
        list_name="Work",
        status=TaskStatus.TODO,
        title="Review PR #123",
        created_at=datetime.now(timezone.utc),
        modified_at=datetime.now(timezone.utc)
    )
    
    # Create cluster
    cluster = DuplicateCluster(
        description="Review PR #123",
        obsidian_tasks=[obs_task1, obs_task2],
        reminders_tasks=[rem_task]
    )
    
    # Test properties
    assert cluster.total_count == 3, f"Expected 3 tasks, got {cluster.total_count}"
    assert cluster.has_duplicates == True, "Should detect duplicates"
    
    all_tasks = cluster.get_all_tasks()
    assert len(all_tasks) == 3, f"Expected 3 tasks in get_all_tasks(), got {len(all_tasks)}"
    
    # Test task retrieval by index
    task_0 = cluster.get_task_by_index(0)
    assert task_0 is not None, "Should retrieve task at index 0"
    assert task_0.uuid == "obs-1", f"Expected obs-1, got {task_0.uuid}"
    
    task_invalid = cluster.get_task_by_index(10)
    assert task_invalid is None, "Should return None for invalid index"
    
    print("✅ DuplicateCluster tests passed")


def test_task_deduplicator_analysis():
    """Test TaskDeduplicator duplicate analysis."""
    print("🧪 Testing TaskDeduplicator analysis...")
    
    # Mock task managers
    obs_manager = Mock()
    rem_manager = Mock()
    
    deduplicator = TaskDeduplicator(obs_manager, rem_manager)
    
    # Create test tasks with duplicates
    obs_tasks = [
        ObsidianTask(
            uuid="obs-1",
            vault_id="vault1", 
            vault_name="Test Vault",
            vault_path="/test/vault",
            file_path="test.md",
            line_number=1,
            block_id=None,
            status=TaskStatus.TODO,
            description="Buy milk",
            raw_line="- [ ] Buy milk",
            due_date=None,
            completion_date=None,
            priority=None,
            tags=[],
            created_at=datetime.now(timezone.utc),
            modified_at=datetime.now(timezone.utc)
        ),
        ObsidianTask(
            uuid="obs-2",
            vault_id="vault1",
            vault_name="Test Vault", 
            vault_path="/test/vault",
            file_path="test.md",
            line_number=2,
            block_id=None,
            status=TaskStatus.TODO,
            description="Buy milk",  # Duplicate
            raw_line="- [ ] Buy milk",
            due_date=None,
            completion_date=None,
            priority=None,
            tags=[],
            created_at=datetime.now(timezone.utc),
            modified_at=datetime.now(timezone.utc)
        ),
        ObsidianTask(
            uuid="obs-3",
            vault_id="vault1",
            vault_name="Test Vault",
            vault_path="/test/vault", 
            file_path="test.md",
            line_number=3,
            block_id=None,
            status=TaskStatus.TODO,
            description="Walk the dog",  # Unique
            raw_line="- [ ] Walk the dog",
            due_date=None,
            completion_date=None,
            priority=None,
            tags=[],
            created_at=datetime.now(timezone.utc),
            modified_at=datetime.now(timezone.utc)
        )
    ]
    
    rem_tasks = [
        RemindersTask(
            uuid="rem-1",
            item_id="item-1",
            calendar_id="cal-1", 
            list_name="Personal",
            status=TaskStatus.TODO,
            title="Buy milk",  # Cross-system duplicate
            created_at=datetime.now(timezone.utc),
            modified_at=datetime.now(timezone.utc)
        ),
        RemindersTask(
            uuid="rem-2",
            item_id="item-2",
            calendar_id="cal-1",
            list_name="Personal", 
            status=TaskStatus.TODO,
            title="Call dentist",  # Unique
            created_at=datetime.now(timezone.utc),
            modified_at=datetime.now(timezone.utc)
        )
    ]
    
    # Analyze duplicates
    results = deduplicator.analyze_duplicates(obs_tasks, rem_tasks)
    
    # Verify results
    assert isinstance(results, DeduplicationResults), "Should return DeduplicationResults"
    assert results.total_tasks == 5, f"Expected 5 total tasks, got {results.total_tasks}"
    assert results.duplicate_clusters == 1, f"Expected 1 duplicate cluster, got {results.duplicate_clusters}"
    assert results.duplicate_tasks == 3, f"Expected 3 duplicate tasks, got {results.duplicate_tasks}"
    
    duplicate_clusters = results.get_duplicate_clusters()
    assert len(duplicate_clusters) == 1, f"Expected 1 duplicate cluster, got {len(duplicate_clusters)}"
    
    cluster = duplicate_clusters[0]
    assert cluster.description.lower() == "buy milk", f"Expected 'buy milk', got '{cluster.description}'"
    assert len(cluster.obsidian_tasks) == 2, f"Expected 2 Obsidian tasks, got {len(cluster.obsidian_tasks)}"
    assert len(cluster.reminders_tasks) == 1, f"Expected 1 Reminders task, got {len(cluster.reminders_tasks)}"
    
    print("✅ TaskDeduplicator analysis tests passed")


def test_task_formatting():
    """Test task formatting for display."""
    print("🧪 Testing task formatting...")
    
    obs_task = ObsidianTask(
        uuid="obs-1",
        vault_id="vault1",
        vault_name="Work Vault",
        vault_path="/work/vault",
        file_path="tasks/daily.md",
        line_number=42,
        block_id=None,
        status=TaskStatus.TODO,
        description="Review quarterly report",
        raw_line="- [ ] Review quarterly report",
        due_date=None,
        completion_date=None,
        priority=None,
        tags=[],
        created_at=datetime(2023, 10, 15, 10, 30, tzinfo=timezone.utc),
        modified_at=datetime.now(timezone.utc)
    )
    
    rem_task = RemindersTask(
        uuid="rem-1",
        item_id="item-1",
        calendar_id="cal-1",
        list_name="Work Tasks",
        status=TaskStatus.DONE,
        title="Review quarterly report", 
        created_at=datetime(2023, 10, 16, 9, 15, tzinfo=timezone.utc),
        modified_at=datetime.now(timezone.utc)
    )
    
    # Test formatting
    obs_formatted = format_task_for_display(obs_task, 1)
    rem_formatted = format_task_for_display(rem_task, 2)
    
    # Verify Obsidian task formatting
    assert "1." in obs_formatted, "Should include index number"
    assert "[Obsidian]" in obs_formatted, "Should include system identifier"
    assert "⭕" in obs_formatted, "Should show TODO status symbol"
    assert "Review quarterly report" in obs_formatted, "Should include description"
    assert "Work Vault:tasks/daily.md:42" in obs_formatted, "Should include location"
    assert "2023-10-15" in obs_formatted, "Should include creation date"
    
    # Verify Reminders task formatting
    assert "2." in rem_formatted, "Should include index number"
    assert "[Reminders]" in rem_formatted, "Should include system identifier"
    assert "✅" in rem_formatted, "Should show DONE status symbol"
    assert "Review quarterly report" in rem_formatted, "Should include title"
    assert "Work Tasks" in rem_formatted, "Should include list name"
    assert "2023-10-16" in rem_formatted, "Should include creation date"
    
    print("✅ Task formatting tests passed")


def test_normalization():
    """Test task description normalization."""
    print("🧪 Testing description normalization...")
    
    deduplicator = TaskDeduplicator()
    
    # Test cases
    test_cases = [
        ("Buy milk", "buy milk"),
        ("  Buy milk  ", "buy milk"),
        ("- [ ] Buy milk", "buy milk"),
        ("* [x] Buy milk", "buy milk"), 
        ("Buy    milk", "buy milk"),
        ("", ""),
        (None, "")
    ]
    
    for input_desc, expected in test_cases:
        result = deduplicator._normalize_description(input_desc)
        assert result == expected, f"Expected '{expected}', got '{result}' for input '{input_desc}'"
    
    print("✅ Description normalization tests passed")


@patch('obs_sync.utils.prompts.input')
def test_confirmation_prompts(mock_input):
    """Test user confirmation prompts."""
    print("🧪 Testing confirmation prompts...")
    
    # Test deduplication confirmation - yes
    mock_input.return_value = 'y'
    result = confirm_deduplication()
    assert result == True, "Should return True for 'y' input"
    
    # Test deduplication confirmation - no
    mock_input.return_value = 'n'
    result = confirm_deduplication()
    assert result == False, "Should return False for 'n' input"
    
    # Test deduplication confirmation - default (empty)
    mock_input.return_value = ''
    result = confirm_deduplication()
    assert result == False, "Should return False for empty input (default)"
    
    print("✅ Confirmation prompt tests passed")


@patch('obs_sync.utils.prompts.input')
def test_keep_selection_prompts(mock_input):
    """Test task selection prompts."""
    print("🧪 Testing task selection prompts...")
    
    # Create test cluster
    obs_task = ObsidianTask(
        uuid="obs-1",
        vault_id="vault1",
        vault_name="Test Vault",
        vault_path="/test/vault", 
        file_path="test.md",
        line_number=1,
        block_id=None,
        status=TaskStatus.TODO,
        description="Test task",
        raw_line="- [ ] Test task",
        due_date=None,
        completion_date=None,
        priority=None,
        tags=[],
        created_at=datetime.now(timezone.utc),
        modified_at=datetime.now(timezone.utc)
    )
    
    rem_task = RemindersTask(
        uuid="rem-1",
        item_id="item-1",
        calendar_id="cal-1",
        list_name="Test List",
        status=TaskStatus.TODO,
        title="Test task",
        created_at=datetime.now(timezone.utc),
        modified_at=datetime.now(timezone.utc)
    )
    
    cluster = DuplicateCluster(
        description="Test task",
        obsidian_tasks=[obs_task],
        reminders_tasks=[rem_task]
    )
    
    # Test various inputs
    test_cases = [
        ('1', [0]),  # Keep first task
        ('2', [1]),  # Keep second task
        ('1,2', [0, 1]),  # Keep both tasks
        ('skip', None),  # Skip cluster
        ('', None),  # Empty input (skip)
        ('all', None),  # Keep all
        ('none', []),  # Delete all
        ('n', [])  # Delete all (shortcut)
    ]
    
    for input_val, expected in test_cases:
        mock_input.return_value = input_val
        result = prompt_for_keeps(cluster)
        assert result == expected, f"Expected {expected}, got {result} for input '{input_val}'"
    
    print("✅ Task selection prompt tests passed")


def test_deletion_stats():
    """Test task deletion statistics."""
    print("🧪 Testing deletion statistics...")
    
    # Mock task managers
    obs_manager = Mock()
    rem_manager = Mock()
    obs_manager.delete_task.return_value = True
    rem_manager.delete_task.return_value = True
    
    deduplicator = TaskDeduplicator(obs_manager, rem_manager)
    
    # Create test tasks
    obs_task = ObsidianTask(
        uuid="obs-1",
        vault_id="vault1", 
        vault_name="Test Vault",
        vault_path="/test/vault",
        file_path="test.md",
        line_number=1,
        block_id=None,
        status=TaskStatus.TODO,
        description="Test task",
        raw_line="- [ ] Test task",
        due_date=None,
        completion_date=None,
        priority=None,
        tags=[],
        created_at=datetime.now(timezone.utc),
        modified_at=datetime.now(timezone.utc)
    )
    
    rem_task = RemindersTask(
        uuid="rem-1",
        item_id="item-1",
        calendar_id="cal-1",
        list_name="Test List", 
        status=TaskStatus.TODO,
        title="Test task",
        created_at=datetime.now(timezone.utc),
        modified_at=datetime.now(timezone.utc)
    )
    
    # Test dry run (should not call delete methods)
    stats = deduplicator.delete_tasks([obs_task, rem_task], dry_run=True)
    assert stats["obs_deleted"] == 1, "Should count Obsidian task in dry run"
    assert stats["rem_deleted"] == 1, "Should count Reminders task in dry run"
    obs_manager.delete_task.assert_not_called()
    rem_manager.delete_task.assert_not_called()
    
    # Test actual deletion
    obs_manager.reset_mock()
    rem_manager.reset_mock()
    stats = deduplicator.delete_tasks([obs_task, rem_task], dry_run=False)
    assert stats["obs_deleted"] == 1, "Should count successful Obsidian deletion"
    assert stats["rem_deleted"] == 1, "Should count successful Reminders deletion" 
    obs_manager.delete_task.assert_called_once_with(obs_task)
    rem_manager.delete_task.assert_called_once_with(rem_task)
    
    print("✅ Deletion statistics tests passed")


@patch('obs_sync.obsidian.tasks.ObsidianTaskManager')
@patch('obs_sync.reminders.tasks.RemindersTaskManager')
@patch('obs_sync.utils.prompts.confirm_deduplication')
def test_integration_dry_run(mock_confirm, mock_rem_manager, mock_obs_manager):
    """Test deduplication integration in dry run mode."""
    print("🧪 Testing deduplication integration (dry run)...")
    
    # Setup mocks
    mock_obs_mgr = Mock()
    mock_rem_mgr = Mock()
    mock_obs_manager.return_value = mock_obs_mgr
    mock_rem_manager.return_value = mock_rem_mgr
    
    # Create duplicate tasks
    obs_tasks = [
        ObsidianTask(
            uuid="obs-1",
            vault_id="vault1",
            vault_name="Test Vault", 
            vault_path="/test/vault",
            file_path="test.md",
            line_number=1,
            block_id=None,
            status=TaskStatus.TODO,
            description="Duplicate task",
            raw_line="- [ ] Duplicate task",
            due_date=None,
            completion_date=None,
            priority=None,
            tags=[],
            created_at=datetime.now(timezone.utc),
            modified_at=datetime.now(timezone.utc)
        ),
        ObsidianTask(
            uuid="obs-2", 
            vault_id="vault1",
            vault_name="Test Vault",
            vault_path="/test/vault",
            file_path="test.md",
            line_number=2,
            block_id=None,
            status=TaskStatus.TODO,
            description="Duplicate task",
            raw_line="- [ ] Duplicate task",
            due_date=None,
            completion_date=None,
            priority=None,
            tags=[],
            created_at=datetime.now(timezone.utc),
            modified_at=datetime.now(timezone.utc)
        )
    ]
    
    rem_tasks = []
    
    mock_obs_mgr.list_tasks.return_value = obs_tasks
    mock_rem_mgr.list_tasks.return_value = rem_tasks
    
    config = SyncConfig()
    config.enable_deduplication = True
    
    # Run deduplication in dry run mode
    stats = _run_deduplication(
        vault_path="/test/vault",
        list_ids=None,
        dry_run=True,
        config=config
    )
    
    # In dry run, no deletions should be performed
    assert stats["obs_deleted"] == 0, "Should not delete tasks in dry run"
    assert stats["rem_deleted"] == 0, "Should not delete tasks in dry run"
    mock_confirm.assert_not_called()  # Should not prompt in dry run
    
    print("✅ Deduplication integration (dry run) tests passed")


def test_config_integration():
    """Test SyncConfig deduplication settings."""
    print("🧪 Testing SyncConfig deduplication settings...")
    
    # Test default values
    config = SyncConfig()
    assert hasattr(config, 'enable_deduplication'), "Should have enable_deduplication field"
    assert hasattr(config, 'dedup_auto_apply'), "Should have dedup_auto_apply field"
    assert config.enable_deduplication == True, "Should enable deduplication by default"
    assert config.dedup_auto_apply == False, "Should not auto-apply by default"
    
    # Test custom values
    config2 = SyncConfig()
    config2.enable_deduplication = False
    config2.dedup_auto_apply = True
    
    assert config2.enable_deduplication == False, "Should allow disabling deduplication"
    assert config2.dedup_auto_apply == True, "Should allow enabling auto-apply"
    
    print("✅ SyncConfig deduplication settings tests passed")


def test_sync_link_exclusion():
    """Test that already-synced task pairs are excluded from duplicate detection."""
    print("🧪 Testing sync link exclusion...")
    
    deduplicator = TaskDeduplicator()
    
    # Create a synced task pair - these should NOT be flagged as duplicates
    obs_task = ObsidianTask(
        uuid="obs-synced",
        vault_id="vault1",
        vault_name="Test Vault",
        vault_path="/test/vault",
        file_path="AppleRemindersInbox.md",
        line_number=1,
        block_id=None,
        status=TaskStatus.TODO,
        description="Synced task",
        raw_line="- [ ] Synced task",
        due_date=None,
        completion_date=None,
        priority=None,
        tags=[],
        created_at=datetime.now(timezone.utc),
        modified_at=datetime.now(timezone.utc)
    )
    
    rem_task = RemindersTask(
        uuid="rem-synced",
        item_id="item-1",
        calendar_id="cal-1",
        list_name="Work",
        status=TaskStatus.TODO,
        title="Synced task",
        created_at=datetime.now(timezone.utc),
        modified_at=datetime.now(timezone.utc)
    )
    
    # Create actual duplicate tasks (not synced)
    obs_duplicate = ObsidianTask(
        uuid="obs-dup",
        vault_id="vault1",
        vault_name="Test Vault",
        vault_path="/test/vault",
        file_path="notes.md",
        line_number=5,
        block_id=None,
        status=TaskStatus.TODO,
        description="Real duplicate",
        raw_line="- [ ] Real duplicate",
        due_date=None,
        completion_date=None,
        priority=None,
        tags=[],
        created_at=datetime.now(timezone.utc),
        modified_at=datetime.now(timezone.utc)
    )
    
    obs_duplicate2 = ObsidianTask(
        uuid="obs-dup2",
        vault_id="vault1",
        vault_name="Test Vault",
        vault_path="/test/vault",
        file_path="other.md",
        line_number=3,
        block_id=None,
        status=TaskStatus.TODO,
        description="Real duplicate",  # Same as above
        raw_line="- [ ] Real duplicate",
        due_date=None,
        completion_date=None,
        priority=None,
        tags=[],
        created_at=datetime.now(timezone.utc),
        modified_at=datetime.now(timezone.utc)
    )
    
    # Create a sync link for the synced pair
    from obs_sync.core.models import SyncLink
    sync_links = [
        SyncLink(
            obs_uuid="obs-synced",
            rem_uuid="rem-synced",
            score=1.0,
            last_synced=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc)
        )
    ]
    
    obs_tasks = [obs_task, obs_duplicate, obs_duplicate2]
    rem_tasks = [rem_task]
    
    # Test WITHOUT sync links - should find 1 duplicate cluster (the two Obsidian tasks)
    # The 1 Obsidian + 1 Reminders pair is no longer considered a duplicate
    results_without_links = deduplicator.analyze_duplicates(obs_tasks, rem_tasks)
    assert results_without_links.duplicate_clusters == 1, f"Expected 1 cluster without links (Obsidian duplicates), got {results_without_links.duplicate_clusters}"
    
    # Test WITH sync links - should still find 1 duplicate cluster (the Obsidian duplicates)
    results_with_links = deduplicator.analyze_duplicates(obs_tasks, rem_tasks, sync_links)
    assert results_with_links.duplicate_clusters == 1, f"Expected 1 cluster with links, got {results_with_links.duplicate_clusters}"
    
    # Verify the remaining cluster is the real duplicate (both Obsidian tasks)
    duplicate_clusters = results_with_links.get_duplicate_clusters()
    cluster = duplicate_clusters[0]
    assert cluster.description.lower() == "real duplicate", f"Expected 'real duplicate', got '{cluster.description}'"
    assert len(cluster.obsidian_tasks) == 2, f"Expected 2 Obsidian tasks, got {len(cluster.obsidian_tasks)}"
    assert len(cluster.reminders_tasks) == 0, f"Expected 0 Reminders tasks, got {len(cluster.reminders_tasks)}"
    
    print("✅ Sync link exclusion tests passed")


def test_sync_pair_not_duplicate():
    """Test that a single Obsidian + single Reminders task is not considered a duplicate."""
    print("🧪 Testing sync pair exclusion from duplicates...")
    
    deduplicator = TaskDeduplicator()
    
    # Create a single Obsidian task
    obs_task = ObsidianTask(
        uuid="obs-1",
        vault_id="vault1",
        vault_name="Test Vault",
        vault_path="/test/vault",
        file_path="test.md",
        line_number=1,
        block_id=None,
        status=TaskStatus.TODO,
        description="Sync pair test",
        raw_line="- [ ] Sync pair test",
        due_date=None,
        completion_date=None,
        priority=None,
        tags=[],
        created_at=datetime.now(timezone.utc),
        modified_at=datetime.now(timezone.utc)
    )
    
    # Create a single Reminders task with same title
    rem_task = RemindersTask(
        uuid="rem-1",
        item_id="item-1",
        calendar_id="cal-1",
        list_name="Test List",
        status=TaskStatus.TODO,
        title="Sync pair test",  # Same as Obsidian
        created_at=datetime.now(timezone.utc),
        modified_at=datetime.now(timezone.utc)
    )
    
    # Analyze - should NOT be considered duplicates
    results = deduplicator.analyze_duplicates([obs_task], [rem_task])
    
    # Should have 0 duplicate clusters (1+1 is likely a sync pair)
    assert results.duplicate_clusters == 0, f"Expected 0 duplicate clusters for sync pair, got {results.duplicate_clusters}"
    
    # Now add another Obsidian task with same description
    obs_task2 = ObsidianTask(
        uuid="obs-2",
        vault_id="vault1",
        vault_name="Test Vault",
        vault_path="/test/vault",
        file_path="other.md",
        line_number=2,
        block_id=None,
        status=TaskStatus.TODO,
        description="Sync pair test",  # Duplicate
        raw_line="- [ ] Sync pair test",
        due_date=None,
        completion_date=None,
        priority=None,
        tags=[],
        created_at=datetime.now(timezone.utc),
        modified_at=datetime.now(timezone.utc)
    )
    
    # Now with 2 Obsidian + 1 Reminders, it SHOULD be duplicates
    results = deduplicator.analyze_duplicates([obs_task, obs_task2], [rem_task])
    assert results.duplicate_clusters == 1, f"Expected 1 duplicate cluster with 2+1 tasks, got {results.duplicate_clusters}"
    
    print("✅ Sync pair exclusion tests passed")


def test_same_list_reminder_duplicates():
    """Test detection of duplicate reminders within the same list even when synced."""
    print("🧪 Testing same-list reminder duplicate detection...")
    
    deduplicator = TaskDeduplicator()
    
    # Create reminder duplicates in the same list
    rem_dup1 = RemindersTask(
        uuid="rem-dup1",
        item_id="item-1",
        calendar_id="work-list",
        list_name="Work Tasks",
        status=TaskStatus.TODO,
        title="Review budget report",
        created_at=datetime.now(timezone.utc),
        modified_at=datetime.now(timezone.utc)
    )
    
    rem_dup2 = RemindersTask(
        uuid="rem-dup2",
        item_id="item-2",
        calendar_id="work-list",  # Same list
        list_name="Work Tasks",
        status=TaskStatus.TODO,
        title="Review budget report",  # Same title
        created_at=datetime.now(timezone.utc),
        modified_at=datetime.now(timezone.utc)
    )
    
    # Create a synced Obsidian task for one of them
    obs_synced = ObsidianTask(
        uuid="obs-synced",
        vault_id="vault1",
        vault_name="Test Vault",
        vault_path="/test/vault",
        file_path="inbox.md",
        line_number=1,
        block_id=None,
        status=TaskStatus.TODO,
        description="Review budget report",
        raw_line="- [ ] Review budget report",
        due_date=None,
        completion_date=None,
        priority=None,
        tags=[],
        created_at=datetime.now(timezone.utc),
        modified_at=datetime.now(timezone.utc)
    )
    
    # Create a reminder in a different list with same title (should NOT be grouped)
    rem_diff_list = RemindersTask(
        uuid="rem-diff",
        item_id="item-3",
        calendar_id="personal-list",  # Different list
        list_name="Personal",
        status=TaskStatus.TODO,
        title="Review budget report",  # Same title but different list
        created_at=datetime.now(timezone.utc),
        modified_at=datetime.now(timezone.utc)
    )
    
    from obs_sync.core.models import SyncLink
    # Create sync link for one reminder
    sync_links = [
        SyncLink(
            obs_uuid="obs-synced",
            rem_uuid="rem-dup1",  # One reminder is synced
            score=1.0,
            last_synced=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc)
        )
    ]
    
    obs_tasks = [obs_synced]
    rem_tasks = [rem_dup1, rem_dup2, rem_diff_list]
    
    # Analyze with sync links
    results = deduplicator.analyze_duplicates(obs_tasks, rem_tasks, sync_links)
    
    # Should find 1 duplicate cluster for the same-list reminders
    assert results.duplicate_clusters == 1, f"Expected 1 duplicate cluster, got {results.duplicate_clusters}"
    
    clusters = results.get_duplicate_clusters()
    cluster = clusters[0]
    
    # Verify the cluster contains both reminders from the same list
    assert len(cluster.reminders_tasks) == 2, f"Expected 2 reminder duplicates, got {len(cluster.reminders_tasks)}"
    assert len(cluster.obsidian_tasks) == 0, f"Expected 0 Obsidian tasks in same-list duplicate, got {len(cluster.obsidian_tasks)}"
    
    # Verify both are from the same list
    for task in cluster.reminders_tasks:
        assert task.calendar_id == "work-list", f"Expected work-list, got {task.calendar_id}"
    
    # Verify the different-list reminder is not included
    task_uuids = [t.uuid for t in cluster.reminders_tasks]
    assert "rem-diff" not in task_uuids, "Different-list reminder should not be in duplicate cluster"
    
    print("✅ Same-list reminder duplicate tests passed")


def run_all_tests():
    """Run all deduplication tests."""
    print("🚀 Running comprehensive deduplication tests...\n")
    
    try:
        test_duplicate_cluster_creation()
        test_task_deduplicator_analysis()
        test_task_formatting()
        test_normalization()
        test_confirmation_prompts()
        test_keep_selection_prompts()
        test_deletion_stats()
        test_integration_dry_run()
        test_config_integration()
        test_sync_link_exclusion()
        test_sync_pair_not_duplicate()
        test_same_list_reminder_duplicates()
        
        print(f"\n🎉 All deduplication tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)