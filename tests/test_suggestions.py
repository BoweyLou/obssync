"""
Tests for smart routing suggestion analyzer.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from obs_sync.core.models import (
    SyncConfig,
    Vault,
    RemindersList,
    ObsidianTask,
    RemindersTask,
    TaskStatus,
    Priority,
)
from obs_sync.utils.suggestions import (
    SuggestionAnalyzer,
    VaultMappingSuggestion,
    TagRouteSuggestion,
)


def test_vault_mapping_suggestions_with_tag_overlap():
    """Test vault mapping suggestions based on tag overlap."""
    # Setup config
    vault = Vault(
        name="Work",
        path="/vaults/work",
        vault_id="vault-work",
        is_default=True,
    )
    
    config = SyncConfig(
        vaults=[vault],
        reminders_lists=[
            RemindersList(
                name="Work Tasks",
                identifier="work-list",
                source_name="iCloud",
                source_type="CalDAV",
            ),
            RemindersList(
                name="Personal",
                identifier="personal-list",
                source_name="iCloud",
                source_type="CalDAV",
            ),
        ],
        default_vault_id="vault-work",
        default_calendar_id="work-list",
    )
    
    # Mock Obsidian tasks with work-related tags
    obs_tasks = [
        ObsidianTask(
            uuid="obs-1",
            vault_id="vault-work",
            vault_name="Work",
            vault_path="/vaults/work",
            file_path="tasks.md",
            line_number=1,
            block_id=None,
            status=TaskStatus.TODO,
            description="Review PR",
            raw_line="- [ ] Review PR #coding #review",
            tags=["#coding", "#review"],
        ),
        ObsidianTask(
            uuid="obs-2",
            vault_id="vault-work",
            vault_name="Work",
            vault_path="/vaults/work",
            file_path="tasks.md",
            line_number=2,
            block_id=None,
            status=TaskStatus.DONE,
            description="Deploy feature",
            raw_line="- [x] Deploy feature #coding #deployment",
            tags=["#coding", "#deployment"],
        ),
        ObsidianTask(
            uuid="obs-3",
            vault_id="vault-work",
            vault_name="Work",
            vault_path="/vaults/work",
            file_path="tasks.md",
            line_number=3,
            block_id=None,
            status=TaskStatus.TODO,
            description="Team meeting",
            raw_line="- [ ] Team meeting #meeting",
            tags=["#meeting"],
        ),
    ]
    
    # Mock Reminders tasks with overlapping tags
    rem_tasks = [
        RemindersTask(
            uuid="rem-1",
            item_id="rem-1",
            calendar_id="work-list",
            list_name="Work Tasks",
            status=TaskStatus.DONE,
            title="Code review",
            tags=["#coding", "#review"],
        ),
        RemindersTask(
            uuid="rem-2",
            item_id="rem-2",
            calendar_id="work-list",
            list_name="Work Tasks",
            status=TaskStatus.DONE,
            title="Fix bug",
            tags=["#coding"],
        ),
        RemindersTask(
            uuid="rem-3",
            item_id="rem-3",
            calendar_id="personal-list",
            list_name="Personal",
            status=TaskStatus.TODO,
            title="Buy groceries",
            tags=["#shopping"],
        ),
    ]
    
    # Create analyzer with mocked managers
    mock_obs_manager = Mock()
    mock_obs_manager.list_tasks.return_value = obs_tasks
    
    mock_rem_manager = Mock()
    mock_rem_manager.list_tasks.return_value = rem_tasks
    
    analyzer = SuggestionAnalyzer(
        config=config,
        obs_manager=mock_obs_manager,
        rem_manager=mock_rem_manager,
    )
    
    # Analyze suggestions
    suggestions = analyzer.analyze_vault_mapping_suggestions(vault, min_confidence=0.1)
    
    # Assertions
    assert len(suggestions) > 0, "Should generate at least one suggestion"
    
    # The "Work Tasks" list should be suggested (has overlapping tags)
    work_suggestion = next(
        (s for s in suggestions if s.suggested_list_id == "work-list"),
        None
    )
    assert work_suggestion is not None, "Should suggest Work Tasks list"
    assert work_suggestion.tag_overlap >= 2, "Should have at least 2 overlapping tags"
    assert work_suggestion.confidence > 0, "Should have positive confidence"
    
    print("✓ Vault mapping suggestion test passed")


def test_tag_route_suggestions_based_on_completion():
    """Test tag route suggestions based on completion history."""
    vault = Vault(
        name="Research",
        path="/vaults/research",
        vault_id="vault-research",
        is_default=True,
    )
    
    config = SyncConfig(
        vaults=[vault],
        reminders_lists=[
            RemindersList(
                name="Inbox",
                identifier="inbox",
                source_name="iCloud",
                source_type="CalDAV",
            ),
            RemindersList(
                name="PhD Tasks",
                identifier="phd-list",
                source_name="iCloud",
                source_type="CalDAV",
            ),
        ],
        default_vault_id="vault-research",
        default_calendar_id="inbox",
    )
    
    # Mock Obsidian tasks with frequent #phd tag
    obs_tasks = [
        ObsidianTask(
            uuid=f"obs-{i}",
            vault_id="vault-research",
            vault_name="Research",
            vault_path="/vaults/research",
            file_path="tasks.md",
            line_number=i,
            block_id=None,
            status=TaskStatus.TODO if i % 2 == 0 else TaskStatus.DONE,
            description=f"Task {i}",
            raw_line=f"- [ ] Task {i} #phd",
            tags=["#phd"],
        )
        for i in range(1, 11)  # 10 tasks with #phd tag
    ]
    
    # Mock Reminders tasks showing #phd tasks are completed in "PhD Tasks" list
    rem_tasks = [
        RemindersTask(
            uuid=f"rem-{i}",
            item_id=f"rem-{i}",
            calendar_id="phd-list",
            list_name="PhD Tasks",
            status=TaskStatus.DONE,  # All completed
            title=f"PhD task {i}",
            tags=["#phd"],
        )
        for i in range(1, 8)  # 7 completed tasks
    ]
    
    # Create analyzer with mocked managers
    mock_obs_manager = Mock()
    mock_obs_manager.list_tasks.return_value = obs_tasks
    
    mock_rem_manager = Mock()
    mock_rem_manager.list_tasks.return_value = rem_tasks
    
    analyzer = SuggestionAnalyzer(
        config=config,
        obs_manager=mock_obs_manager,
        rem_manager=mock_rem_manager,
    )
    
    # Analyze suggestions (exclude inbox as it's the default)
    suggestions = analyzer.analyze_tag_route_suggestions(
        vault,
        default_list_id="inbox",
        min_frequency=3,
        min_confidence=0.3,
    )
    
    # Assertions
    assert len(suggestions) > 0, "Should generate at least one suggestion"
    
    # Should suggest routing #phd to "PhD Tasks" list
    phd_suggestion = next(
        (s for s in suggestions if s.tag == "#phd"),
        None
    )
    assert phd_suggestion is not None, "Should suggest routing #phd tag"
    assert phd_suggestion.suggested_list_id == "phd-list", "Should suggest PhD Tasks list"
    assert phd_suggestion.completion_rate == 1.0, "Should have 100% completion rate"
    assert phd_suggestion.confidence > 0.5, "Should have high confidence"
    
    print("✓ Tag route suggestion test passed")


def test_suggestions_with_no_historical_data():
    """Test that suggestions gracefully handle missing data."""
    vault = Vault(
        name="Empty",
        path="/vaults/empty",
        vault_id="vault-empty",
        is_default=True,
    )
    
    config = SyncConfig(
        vaults=[vault],
        reminders_lists=[
            RemindersList(
                name="Tasks",
                identifier="tasks",
                source_name="iCloud",
                source_type="CalDAV",
            ),
        ],
        default_vault_id="vault-empty",
        default_calendar_id="tasks",
    )
    
    # Mock empty task lists
    mock_obs_manager = Mock()
    mock_obs_manager.list_tasks.return_value = []
    
    mock_rem_manager = Mock()
    mock_rem_manager.list_tasks.return_value = []
    
    analyzer = SuggestionAnalyzer(
        config=config,
        obs_manager=mock_obs_manager,
        rem_manager=mock_rem_manager,
    )
    
    # Analyze suggestions
    vault_suggestions = analyzer.analyze_vault_mapping_suggestions(vault)
    tag_suggestions = analyzer.analyze_tag_route_suggestions(vault)
    
    # Assertions
    assert len(vault_suggestions) == 0, "Should return no vault mapping suggestions"
    assert len(tag_suggestions) == 0, "Should return no tag route suggestions"
    
    print("✓ No historical data test passed")


def test_suggestions_filter_by_confidence():
    """Test confidence threshold filtering."""
    vault = Vault(
        name="Test",
        path="/vaults/test",
        vault_id="vault-test",
        is_default=True,
    )
    
    config = SyncConfig(
        vaults=[vault],
        reminders_lists=[
            RemindersList(
                name="List1",
                identifier="list-1",
                source_name="iCloud",
                source_type="CalDAV",
            ),
            RemindersList(
                name="List2",
                identifier="list-2",
                source_name="iCloud",
                source_type="CalDAV",
            ),
        ],
        default_vault_id="vault-test",
        default_calendar_id="list-1",
    )
    
    # Create tasks with minimal overlap (low confidence)
    obs_tasks = [
        ObsidianTask(
            uuid="obs-1",
            vault_id="vault-test",
            vault_name="Test",
            vault_path="/vaults/test",
            file_path="tasks.md",
            line_number=1,
            block_id=None,
            status=TaskStatus.TODO,
            description="Task 1",
            raw_line="- [ ] Task 1 #tag1",
            tags=["#tag1"],
        ),
    ]
    
    rem_tasks = [
        RemindersTask(
            uuid="rem-1",
            item_id="rem-1",
            calendar_id="list-1",
            list_name="List1",
            status=TaskStatus.TODO,
            title="Task",
            tags=["#tag1"],
        ),
    ]
    
    mock_obs_manager = Mock()
    mock_obs_manager.list_tasks.return_value = obs_tasks
    
    mock_rem_manager = Mock()
    mock_rem_manager.list_tasks.return_value = rem_tasks
    
    analyzer = SuggestionAnalyzer(
        config=config,
        obs_manager=mock_obs_manager,
        rem_manager=mock_rem_manager,
    )
    
    # Test with low threshold
    low_threshold_suggestions = analyzer.analyze_vault_mapping_suggestions(
        vault, min_confidence=0.1
    )
    
    # Test with high threshold
    high_threshold_suggestions = analyzer.analyze_vault_mapping_suggestions(
        vault, min_confidence=0.9
    )
    
    # Low threshold should return more results
    assert len(high_threshold_suggestions) <= len(low_threshold_suggestions), \
        "High threshold should filter out low-confidence suggestions"
    
    print("✓ Confidence threshold test passed")


def test_suggestion_reasoning_messages():
    """Test that suggestions include readable reasoning."""
    vault = Vault(
        name="Work",
        path="/vaults/work",
        vault_id="vault-work",
        is_default=True,
    )
    
    config = SyncConfig(
        vaults=[vault],
        reminders_lists=[
            RemindersList(
                name="Work",
                identifier="work",
                source_name="iCloud",
                source_type="CalDAV",
            ),
        ],
        default_vault_id="vault-work",
        default_calendar_id="work",
    )
    
    obs_tasks = [
        ObsidianTask(
            uuid="obs-1",
            vault_id="vault-work",
            vault_name="Work",
            vault_path="/vaults/work",
            file_path="tasks.md",
            line_number=1,
            block_id=None,
            status=TaskStatus.TODO,
            description="Task",
            raw_line="- [ ] Task #coding #review #urgent",
            tags=["#coding", "#review", "#urgent"],
        ),
    ]
    
    rem_tasks = [
        RemindersTask(
            uuid="rem-1",
            item_id="rem-1",
            calendar_id="work",
            list_name="Work",
            status=TaskStatus.DONE,
            title="Task",
            tags=["#coding", "#review"],
        ),
    ]
    
    mock_obs_manager = Mock()
    mock_obs_manager.list_tasks.return_value = obs_tasks
    
    mock_rem_manager = Mock()
    mock_rem_manager.list_tasks.return_value = rem_tasks
    
    analyzer = SuggestionAnalyzer(
        config=config,
        obs_manager=mock_obs_manager,
        rem_manager=mock_rem_manager,
    )
    
    suggestions = analyzer.analyze_vault_mapping_suggestions(vault, min_confidence=0.1)
    
    # Check that reasoning is provided
    assert len(suggestions) > 0, "Should have suggestions"
    assert suggestions[0].reasoning, "Should have reasoning text"
    assert "tag" in suggestions[0].reasoning.lower(), "Reasoning should mention tags"
    
    print("✓ Reasoning messages test passed")


def run_all_tests():
    """Run all suggestion tests."""
    print("\n" + "=" * 60)
    print("Running Suggestion Analyzer Tests")
    print("=" * 60 + "\n")
    
    try:
        test_vault_mapping_suggestions_with_tag_overlap()
        test_tag_route_suggestions_based_on_completion()
        test_suggestions_with_no_historical_data()
        test_suggestions_filter_by_confidence()
        test_suggestion_reasoning_messages()
        
        print("\n" + "=" * 60)
        print("✅ All suggestion tests passed!")
        print("=" * 60)
        return True
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
