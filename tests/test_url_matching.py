#!/usr/bin/env python3
"""
Test URL matching and edge cases in task synchronization.

Tests that URL-only tasks and other edge cases match correctly
between Obsidian and Reminders to prevent repeated creation attempts.
"""

import os
import sys
import tempfile
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from obs_sync.core.models import ObsidianTask, RemindersTask, TaskStatus
from obs_sync.sync.matcher import TaskMatcher
from obs_sync.sync.engine import SyncEngine
from obs_sync.utils.text import normalize_text_for_similarity, dice_similarity


def test_url_normalization():
    """Test that URLs are tokenized properly."""
    print("\n🧪 Testing URL normalization...")
    
    # Test simple URL
    url = "https://example.com/path/to/item"
    tokens = normalize_text_for_similarity(url)
    print(f"  URL: {url}")
    print(f"  Tokens: {tokens}")
    assert len(tokens) > 0, "URL should produce tokens"
    assert "example" in tokens, "Should contain domain name"
    assert "com" in tokens, "Should contain TLD"
    assert "path" in tokens, "Should contain path segments"
    assert "to" in tokens, "Should contain path segments"
    assert "item" in tokens, "Should contain path segments"
    
    # Test URL with query parameters (should be ignored)
    url_with_query = "https://example.com/path/to/item?ref=abc&source=test"
    tokens_with_query = normalize_text_for_similarity(url_with_query)
    print(f"  URL with query: {url_with_query}")
    print(f"  Tokens: {tokens_with_query}")
    # Should match the base URL tokens (query params ignored)
    assert set(tokens) == set(tokens_with_query), "Query parameters should be ignored"
    
    # Test shortened URLs
    short_url = "https://bit.ly/abc123"
    short_tokens = normalize_text_for_similarity(short_url)
    print(f"  Short URL: {short_url}")
    print(f"  Tokens: {short_tokens}")
    assert "bit" in short_tokens, "Should contain shortener domain"
    assert "ly" in short_tokens, "Should contain shortener TLD"
    assert "abc123" in short_tokens, "Should contain short code"
    
    print("  ✅ URL normalization working correctly")


def test_url_task_matching():
    """Test that tasks with identical URLs match correctly."""
    print("\n🧪 Testing URL task matching...")
    
    matcher = TaskMatcher(min_score=0.75)
    
    # Create Obsidian task with URL
    obs_task = ObsidianTask(
        uuid="obs-001",
        vault_id="vault1",
        vault_name="Test Vault",
        vault_path="/test/vault",
        file_path="test.md",
        line_number=1,
        block_id=None,
        status=TaskStatus.TODO,
        description="https://example.com/important/doc",
        raw_line="- [ ] https://example.com/important/doc",
        due_date=None,
        completion_date=None,
        priority=None,
        tags=[],
        created_at=None,
        modified_at=None
    )
    
    # Create matching Reminders task with same URL
    rem_task = RemindersTask(
        uuid="rem-001",
        item_id="item1",
        calendar_id="cal1",
        list_name="Test List",
        status=TaskStatus.TODO,
        title="https://example.com/important/doc",
        due_date=None,
        priority=None,
        notes=None,
        created_at=None,
        modified_at=None
    )
    
    score = matcher._calculate_similarity(obs_task, rem_task)
    print(f"  Identical URL tasks score: {score:.3f}")
    assert score >= matcher.min_score, f"Identical URL tasks should match (score: {score:.3f})"
    
    # Test with different query parameters (should still match)
    rem_task.title = "https://example.com/important/doc?utm=test"
    score = matcher._calculate_similarity(obs_task, rem_task)
    print(f"  URL with different query params score: {score:.3f}")
    assert score >= matcher.min_score, f"URLs differing only in query params should match (score: {score:.3f})"
    
    print("  ✅ URL task matching working correctly")


def test_reminder_url_contributes_to_matching():
    """Reminder URLs should help match against Obsidian descriptions containing the link."""
    matcher = TaskMatcher(min_score=0.6)

    obs_task = ObsidianTask(
        uuid="obs-url-123",
        vault_id="vault1",
        vault_name="Test Vault",
        vault_path="/test/vault",
        file_path="test.md",
        line_number=1,
        block_id=None,
        status=TaskStatus.TODO,
        description="Read article https://example.com/article",
        raw_line="- [ ] Read article https://example.com/article",
        due_date=None,
        completion_date=None,
        priority=None,
        tags=[],
        created_at=None,
        modified_at=None,
    )

    rem_task = RemindersTask(
        uuid="rem-url-123",
        item_id="item1",
        calendar_id="cal1",
        list_name="Test List",
        status=TaskStatus.TODO,
        title="Read article",
        url="https://example.com/article",
        due_date=None,
        priority=None,
        notes=None,
        created_at=None,
        modified_at=None,
    )

    links = matcher.find_matches([obs_task], [rem_task])
    assert links, "Reminder with matching URL should link to Obsidian task"
    assert links[0].obs_uuid == obs_task.uuid
    assert links[0].rem_uuid == rem_task.uuid


@patch("obs_sync.sync.engine.get_path_manager")
def test_sync_engine_creates_obs_task_with_url(mock_path_manager):
    """SyncEngine should inject reminder URLs into newly created Obsidian tasks."""
    mock_path_manager.return_value = Mock(sync_links_path=Path("/tmp/links.json"))
    engine = SyncEngine(config={"obsidian_inbox_path": "Inbox.md"})
    engine.vault_path = "/vault"
    engine.vault_id = "vault"
    engine.vault_name = "Vault"
    engine.inbox_path = "Inbox.md"

    captured_tasks = []

    def fake_create_task(vault_path, inbox_path, obs_task):
        captured_tasks.append(obs_task)
        return obs_task

    engine.obs_manager = Mock()
    engine.obs_manager.create_task.side_effect = fake_create_task

    reminder_url = "https://example.com/article"
    created_at_dt = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    modified_at_dt = created_at_dt + timedelta(hours=2)

    rem_task = RemindersTask(
        uuid="rem-sync-1",
        item_id="item-sync-1",
        calendar_id="cal-1",
        list_name="Work",
        status=TaskStatus.TODO,
        title="Read article",
        url=reminder_url,
        due_date=None,
        priority=None,
        notes=None,
        created_at=created_at_dt,
        modified_at=modified_at_dt,
    )

    new_links, created_obs_tasks, _ = engine._create_counterparts(
        unmatched_obs=[],
        unmatched_rem=[rem_task],
        list_ids=["cal-1"],
        dry_run=False,
    )

    assert created_obs_tasks, "Expected an Obsidian task to be created"
    assert len(new_links) == 1, "Expected new link for created task"
    assert captured_tasks, "create_task should have been invoked"

    created_task = captured_tasks[0]
    expected_created_iso = created_at_dt.astimezone(timezone.utc).isoformat()
    expected_modified_iso = modified_at_dt.astimezone(timezone.utc).isoformat()

    assert reminder_url in created_task.description
    assert created_task.created_at == expected_created_iso
    assert created_task.modified_at == expected_modified_iso
    assert engine.rem_to_obs_creations[-1]["url"] == reminder_url


def test_edge_case_matching():
    """Test matching for various edge cases."""
    print("\n🧪 Testing edge case matching...")
    
    matcher = TaskMatcher(min_score=0.75)
    
    # Test 1: Single hashtag tasks
    obs_task = ObsidianTask(
        uuid="obs-002",
        vault_id="vault1",
        vault_name="Test Vault",
        vault_path="/test/vault",
        file_path="test.md",
        line_number=2,
        block_id=None,
        status=TaskStatus.TODO,
        description="#",
        raw_line="- [ ] #",
        due_date=None,
        completion_date=None,
        priority=None,
        tags=[],
        created_at=None,
        modified_at=None
    )
    
    rem_task = RemindersTask(
        uuid="rem-002",
        item_id="item2",
        calendar_id="cal1",
        list_name="Test List",
        status=TaskStatus.TODO,
        title="#",
        due_date=None,
        priority=None,
        notes=None,
        created_at=None,
        modified_at=None
    )
    
    score = matcher._calculate_similarity(obs_task, rem_task)
    print(f"  Single '#' tasks score: {score:.3f}")
    assert score == 1.0, f"Identical '#' tasks should have perfect match (score: {score:.3f})"
    
    # Test 2: Empty/whitespace tasks
    obs_task.description = "   "
    rem_task.title = "   "
    score = matcher._calculate_similarity(obs_task, rem_task)
    print(f"  Whitespace-only tasks score: {score:.3f}")
    assert score >= matcher.min_score, f"Identical whitespace tasks should match (score: {score:.3f})"
    
    # Test 3: Mixed content with URL
    obs_task.description = "Check out https://example.com/doc for details"
    rem_task.title = "Check out https://example.com/doc for details"
    score = matcher._calculate_similarity(obs_task, rem_task)
    print(f"  Mixed content with URL score: {score:.3f}")
    assert score >= matcher.min_score, f"Identical mixed content should match (score: {score:.3f})"
    
    print("  ✅ Edge case matching working correctly")


def test_no_false_positives():
    """Test that different tasks don't incorrectly match."""
    print("\n🧪 Testing for false positives...")
    
    matcher = TaskMatcher(min_score=0.75)
    
    # Test different URLs shouldn't match highly
    obs_task = ObsidianTask(
        uuid="obs-003",
        vault_id="vault1",
        vault_name="Test Vault",
        vault_path="/test/vault",
        file_path="test.md",
        line_number=3,
        block_id=None,
        status=TaskStatus.TODO,
        description="https://example.com/doc1",
        raw_line="- [ ] https://example.com/doc1",
        due_date=None,
        completion_date=None,
        priority=None,
        tags=[],
        created_at=None,
        modified_at=None
    )
    
    rem_task = RemindersTask(
        uuid="rem-003",
        item_id="item3",
        calendar_id="cal1",
        list_name="Test List",
        status=TaskStatus.TODO,
        title="https://different.com/doc2",
        due_date=None,
        priority=None,
        notes=None,
        created_at=None,
        modified_at=None
    )
    
    score = matcher._calculate_similarity(obs_task, rem_task)
    print(f"  Different URLs score: {score:.3f}")
    assert score < matcher.min_score, f"Different URLs should not match highly (score: {score:.3f})"
    
    # Test empty vs non-empty shouldn't match
    obs_task.description = ""
    rem_task.title = "https://example.com/doc"
    score = matcher._calculate_similarity(obs_task, rem_task)
    print(f"  Empty vs URL score: {score:.3f}")
    assert score < matcher.min_score, f"Empty vs URL should not match (score: {score:.3f})"
    
    print("  ✅ No false positives detected")


def test_full_sync_scenario():
    """Test a full sync scenario with URL tasks."""
    print("\n🧪 Testing full sync scenario...")
    
    matcher = TaskMatcher(min_score=0.75)
    
    # Simulate multiple Obsidian tasks including URLs
    obs_tasks = [
        ObsidianTask(
            uuid=f"obs-{i:03d}",
            vault_id="vault1",
            vault_name="Test Vault",
            vault_path="/test/vault",
            file_path="test.md",
            line_number=i,
            block_id=None,
            status=TaskStatus.TODO,
            description=desc,
            raw_line=f"- [ ] {desc}",
            due_date=None,
            completion_date=None,
            priority=None,
            tags=[],
            created_at=None,
            modified_at=None
        )
        for i, desc in enumerate([
            "Regular task description",
            "https://github.com/user/repo",
            "#",
            "Another task with https://example.com/link embedded",
            "https://docs.python.org/3/library/index.html"
        ], 1)
    ]
    
    # Simulate matching Reminders tasks
    rem_tasks = [
        RemindersTask(
            uuid=f"rem-{i:03d}",
            item_id=f"item{i}",
            calendar_id="cal1",
            list_name="Test List",
            status=TaskStatus.TODO,
            title=title,
            due_date=None,
            priority=None,
            notes=None,
            created_at=None,
            modified_at=None
        )
        for i, title in enumerate([
            "Regular task description",
            "https://github.com/user/repo",
            "#",
            "Another task with https://example.com/link embedded",
            "https://docs.python.org/3/library/index.html"
        ], 1)
    ]
    
    # Find matches
    links = matcher.find_matches(obs_tasks, rem_tasks)
    
    print(f"  Found {len(links)} matches out of {len(obs_tasks)} tasks")
    for link in links:
        obs_idx = next(i for i, t in enumerate(obs_tasks) if t.uuid == link.obs_uuid)
        rem_idx = next(i for i, t in enumerate(rem_tasks) if t.uuid == link.rem_uuid)
        print(f"    Match: '{obs_tasks[obs_idx].description[:30]}...' <-> '{rem_tasks[rem_idx].title[:30]}...' (score: {link.score:.3f})")
    
    # All tasks should match their counterparts
    assert len(links) == len(obs_tasks), f"All tasks should match (got {len(links)}/{len(obs_tasks)})"
    
    # Verify correct pairing
    for i, (obs_task, rem_task) in enumerate(zip(obs_tasks, rem_tasks)):
        link = next((l for l in links if l.obs_uuid == obs_task.uuid), None)
        assert link is not None, f"Task {i} should have a match"
        assert link.rem_uuid == rem_task.uuid, f"Task {i} matched incorrectly"
        assert link.score >= matcher.min_score, f"Task {i} score too low: {link.score:.3f}"
    
    print("  ✅ Full sync scenario working correctly")


def main():
    """Run all tests."""
    print("=" * 60)
    print("🚀 Running URL Matching and Edge Case Tests")
    print("=" * 60)
    
    try:
        test_url_normalization()
        test_url_task_matching()
        test_edge_case_matching()
        test_no_false_positives()
        test_full_sync_scenario()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED - URL matching fix is working!")
        print("=" * 60)
        return 0
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
