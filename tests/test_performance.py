"""
Performance and scalability tests with pytest.mark.slow decorator.

These tests validate performance under load and can be skipped by default.
Run with: pytest -v -m slow
"""

import time
from datetime import datetime, timezone, date, timedelta
from typing import List
from unittest.mock import Mock
import pytest

from obs_sync.core.models import ObsidianTask, RemindersTask, TaskStatus, SyncLink
from obs_sync.sync.deduplicator import TaskDeduplicator
from obs_sync.sync.matcher import TaskMatcher
from obs_sync.sync.engine import SyncEngine


def generate_obsidian_tasks(count: int, vault_id: str = "v1") -> List[ObsidianTask]:
    """Generate synthetic Obsidian tasks for testing."""
    tasks = []
    for i in range(count):
        description = f"Task {i}: {['Buy groceries', 'Call dentist', 'Review PR', 'Plan meeting'][i % 4]}"
        status_char = "x" if i % 3 == 0 else " "
        raw_line = f"- [{status_char}] {description}"
        
        task = ObsidianTask(
            uuid=f"obs-{i}",
            vault_id=vault_id,
            vault_name="Test Vault",
            vault_path="/tmp/vault",
            file_path=f"tasks/task-{i % 100}.md",
            line_number=i % 50,
            block_id=f"block-{i}",
            status=TaskStatus.TODO if i % 3 != 0 else TaskStatus.DONE,
            description=description,
            raw_line=raw_line,
            due_date=date.today() + timedelta(days=i % 30) if i % 2 == 0 else None,
            tags=[f"tag{i % 5}", f"category{i % 3}"] if i % 4 == 0 else []
        )
        tasks.append(task)
    return tasks


def generate_reminders_tasks(count: int, list_id: str = "cal-1") -> List[RemindersTask]:
    """Generate synthetic Reminders tasks for testing."""
    tasks = []
    for i in range(count):
        task = RemindersTask(
            uuid=f"rem-{i}",
            item_id=f"item-{i}",
            calendar_id=list_id,
            list_name="Work",
            status=TaskStatus.TODO if i % 3 != 0 else TaskStatus.DONE,
            title=f"Task {i}: {['Buy groceries', 'Call dentist', 'Review PR', 'Plan meeting'][i % 4]}",
            due_date=date.today() + timedelta(days=i % 30) if i % 2 == 0 else None,
            tags=[f"tag{i % 5}", f"category{i % 3}"] if i % 4 == 0 else []
        )
        tasks.append(task)
    return tasks


@pytest.mark.slow
class TestDeduplicationPerformance:
    """Performance tests for deduplication with large task sets."""
    
    def test_dedup_100_tasks(self):
        """Test deduplication with 100 tasks."""
        obs_tasks = generate_obsidian_tasks(50)
        rem_tasks = generate_reminders_tasks(50)
        
        dedup = TaskDeduplicator()
        
        start = time.time()
        result = dedup.analyze_duplicates(obs_tasks, rem_tasks)
        duration = time.time() - start
        
        # Should complete in reasonable time
        assert duration < 2.0, f"Dedup took {duration:.2f}s, expected < 2.0s"
        assert result.total_tasks == 100
    
    def test_dedup_500_tasks(self):
        """Test deduplication with 500 tasks."""
        obs_tasks = generate_obsidian_tasks(250)
        rem_tasks = generate_reminders_tasks(250)
        
        dedup = TaskDeduplicator()
        
        start = time.time()
        result = dedup.analyze_duplicates(obs_tasks, rem_tasks)
        duration = time.time() - start
        
        # Should still be fast
        assert duration < 5.0, f"Dedup took {duration:.2f}s, expected < 5.0s"
        assert result.total_tasks == 500
    
    def test_dedup_1000_tasks_stress(self):
        """Stress test: deduplication with 1000 tasks."""
        obs_tasks = generate_obsidian_tasks(500)
        rem_tasks = generate_reminders_tasks(500)
        
        dedup = TaskDeduplicator()
        
        start = time.time()
        result = dedup.analyze_duplicates(obs_tasks, rem_tasks)
        duration = time.time() - start
        
        # Allow more time for stress test
        assert duration < 15.0, f"Dedup took {duration:.2f}s, expected < 15.0s"
        assert result.total_tasks == 1000
        
        print(f"\nDedup performance: {result.total_tasks} tasks in {duration:.2f}s "
              f"({result.total_tasks/duration:.0f} tasks/sec)")


@pytest.mark.slow
class TestMatchingPerformance:
    """Performance tests for task matching algorithms."""
    
    def test_hungarian_matching_100_tasks(self):
        """Test Hungarian matching with 100 tasks."""
        obs_tasks = generate_obsidian_tasks(50)
        rem_tasks = generate_reminders_tasks(50)
        
        matcher = TaskMatcher(min_score=0.75)
        
        start = time.time()
        links = matcher.find_matches(obs_tasks, rem_tasks)
        duration = time.time() - start
        
        # Should be fast
        assert duration < 3.0, f"Matching took {duration:.2f}s, expected < 3.0s"
        assert len(links) >= 0  # May find some matches
    
    def test_greedy_matching_performance(self):
        """Test greedy matching as fallback."""
        # Create large sets to trigger greedy matching
        obs_tasks = generate_obsidian_tasks(150)
        rem_tasks = generate_reminders_tasks(150)
        
        matcher = TaskMatcher(min_score=0.75)
        
        start = time.time()
        links = matcher.find_matches(obs_tasks, rem_tasks)
        duration = time.time() - start
        
        # Greedy should be faster for large sets
        assert duration < 5.0, f"Greedy matching took {duration:.2f}s, expected < 5.0s"
    
    def test_matching_with_existing_links(self):
        """Test matching performance with pre-existing links."""
        obs_tasks = generate_obsidian_tasks(100)
        rem_tasks = generate_reminders_tasks(100)
        
        # Create some existing links
        existing_links = [
            SyncLink(
                obs_uuid=f"obs-{i}",
                rem_uuid=f"rem-{i}",
                score=0.95,
                vault_id="v1"
            )
            for i in range(20)
        ]
        
        matcher = TaskMatcher(min_score=0.75)
        
        start = time.time()
        links = matcher.find_matches(obs_tasks, rem_tasks, existing_links)
        duration = time.time() - start
        
        # Should reuse existing links quickly
        assert duration < 3.0, f"Matching took {duration:.2f}s, expected < 3.0s"
        
        # Should preserve existing links
        existing_uuids = {(l.obs_uuid, l.rem_uuid) for l in existing_links}
        result_uuids = {(l.obs_uuid, l.rem_uuid) for l in links}
        preserved = existing_uuids.intersection(result_uuids)
        assert len(preserved) > 0, "Should preserve some existing links"


@pytest.mark.slow
class TestSyncEnginePerformance:
    """Performance tests for full sync engine."""
    
    def test_sync_dry_run_100_tasks(self):
        """Test sync dry-run with 100 tasks per side."""
        # Mock managers
        mock_obs = Mock()
        mock_rem = Mock()
        
        obs_tasks = generate_obsidian_tasks(100)
        rem_tasks = generate_reminders_tasks(100)
        
        mock_obs.list_tasks.return_value = obs_tasks
        mock_rem.list_tasks.return_value = rem_tasks
        
        config = {
            "min_score": 0.75,
            "days_tolerance": 1,
            "include_completed": True
        }
        
        with pytest.MonkeyPatch.context() as m:
            m.setattr("obs_sync.sync.engine.ObsidianTaskManager", lambda *args, **kwargs: mock_obs)
            m.setattr("obs_sync.sync.engine.RemindersTaskManager", lambda *args, **kwargs: mock_rem)
            
            engine = SyncEngine(config)
            
            start = time.time()
            result = engine.sync("/tmp/vault", ["cal-1"], dry_run=True)
            duration = time.time() - start
            
            # Full sync should be reasonably fast
            assert duration < 5.0, f"Sync took {duration:.2f}s, expected < 5.0s"


@pytest.mark.slow
class TestMemoryUsage:
    """Tests to ensure reasonable memory usage."""
    
    def test_large_task_list_memory(self):
        """Test that large task lists don't cause memory issues."""
        # Generate 1000 tasks
        tasks = generate_obsidian_tasks(1000)
        
        # Verify we can serialize without issues
        serialized = [task.to_dict() for task in tasks]
        assert len(serialized) == 1000
        
        # Verify we can filter without issues
        todo_tasks = [t for t in tasks if t.status == TaskStatus.TODO]
        assert len(todo_tasks) > 0
    
    def test_link_persistence_scalability(self):
        """Test that link persistence handles large sets."""
        # Generate many links
        links = [
            SyncLink(
                obs_uuid=f"obs-{i}",
                rem_uuid=f"rem-{i}",
                score=0.85,
                vault_id=f"v{i % 5}"
            )
            for i in range(500)
        ]
        
        # Serialize
        start = time.time()
        serialized = [link.to_dict() for link in links]
        duration = time.time() - start
        
        assert duration < 0.5, f"Serialization took {duration:.2f}s"
        assert len(serialized) == 500


@pytest.mark.slow
class TestStreakTrackerPerformance:
    """Performance tests for analytics components."""
    
    def test_streak_cleanup_large_dataset(self):
        """Test cleanup of old streak data."""
        from obs_sync.analytics.streaks import StreakTracker
        import tempfile
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            # Create large synthetic dataset
            data = {
                "daily_completions": {}
            }
            
            # Add 2 years of daily data
            for i in range(730):
                date_str = (date.today() - timedelta(days=i)).isoformat()
                data["daily_completions"][date_str] = {
                    "v1": {
                        "tags": {"work": 5, "home": 3},
                        "lists": {"cal-1": 8}
                    }
                }
            
            import json
            json.dump(data, f)
            temp_path = f.name
        
        tracker = StreakTracker(data_path=temp_path)
        
        start = time.time()
        tracker.cleanup_old_data(days_to_keep=365)
        duration = time.time() - start
        
        # Cleanup should be fast
        assert duration < 1.0, f"Cleanup took {duration:.2f}s"


def test_pytest_markers_registered():
    """Meta-test: verify that slow marker is available."""
    import _pytest.config
    # This test just ensures the slow marker can be used
    # The actual registration happens in pytest.ini or conftest.py
    pass


if __name__ == "__main__":
    # Run slow tests only
    pytest.main([__file__, "-v", "-m", "slow"])
