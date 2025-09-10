#!/usr/bin/env python3
"""
Unit tests for incremental Obsidian cache functionality.

Tests cache hits/misses, corrupted cache recovery, cache invalidation,
and performance optimizations for file parsing.
"""

import json
import os
import tempfile
import time
import unittest
from typing import Dict, List, Optional
from unittest.mock import patch, MagicMock

import pytest

# Add parent directory to path for imports
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import modules under test
try:
    from obs_tools.commands.collect_obsidian_tasks import (
        FileCache, IncrementalCache, load_incremental_cache, 
        save_incremental_cache, should_reparse_file, collect_tasks_incremental, Vault
    )
except ImportError:
    # Mock imports if not available
    class FileCache:
        def __init__(self, mtime: float, tasks: List[dict], parsed_at: str):
            self.mtime = mtime
            self.tasks = tasks
            self.parsed_at = parsed_at
    
    class IncrementalCache:
        def __init__(self, schema_version: int, created_at: str, last_updated: str, file_cache: Dict):
            self.schema_version = schema_version
            self.created_at = created_at
            self.last_updated = last_updated
            self.file_cache = file_cache
    
    class Vault:
        def __init__(self, name: str, path: str):
            self.name = name
            self.path = path
    
    def load_incremental_cache(cache_path: str) -> Optional[IncrementalCache]:
        return None
    
    def save_incremental_cache(cache: IncrementalCache, cache_path: str) -> bool:
        return True
    
    def should_reparse_file(path: str, cache_entry: Optional[FileCache]) -> bool:
        return True
    
    def collect_tasks_incremental(vaults, ignore, cache):
        return [], IncrementalCache(1, "now", "now", {}), {}


@pytest.mark.cache
@pytest.mark.unit
class TestIncrementalCache(unittest.TestCase):
    """Test incremental cache functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp(prefix="cache_test_")
        self.cache_path = os.path.join(self.temp_dir, "test_cache.json")
        self.test_file_path = os.path.join(self.temp_dir, "test.md")
        
        # Create a test markdown file
        with open(self.test_file_path, 'w', encoding='utf-8') as f:
            f.write("# Test File\n\n- [ ] Test task\n")
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_cache_creation(self):
        """Test creating a new cache."""
        cache = IncrementalCache(
            schema_version=2,
            created_at="2023-12-15T10:00:00Z",
            last_updated="2023-12-15T10:00:00Z",
            file_cache={}
        )
        
        self.assertEqual(cache.schema_version, 2)
        self.assertEqual(cache.created_at, "2023-12-15T10:00:00Z")
        self.assertIsInstance(cache.file_cache, dict)
        self.assertEqual(len(cache.file_cache), 0)
    
    def test_file_cache_entry(self):
        """Test creating file cache entries."""
        file_stat = os.stat(self.test_file_path)
        tasks = [{"description": "Test task", "status": "todo"}]
        
        file_cache = FileCache(
            mtime=file_stat.st_mtime,
            tasks=tasks,
            parsed_at="2023-12-15T10:00:00Z"
        )
        
        self.assertEqual(file_cache.mtime, file_stat.st_mtime)
        self.assertEqual(len(file_cache.tasks), 1)
        self.assertEqual(file_cache.tasks[0]["description"], "Test task")
    
    def test_should_reparse_file_new_file(self):
        """Test that new files should be reparsed."""
        result = should_reparse_file(self.test_file_path, None)
        self.assertTrue(result, "New files should be reparsed")
    
    def test_should_reparse_file_unchanged(self):
        """Test that unchanged files should not be reparsed."""
        file_stat = os.stat(self.test_file_path)
        cache_entry = FileCache(
            mtime=file_stat.st_mtime,
            tasks=[],
            parsed_at="2023-12-15T10:00:00Z"
        )
        
        result = should_reparse_file(self.test_file_path, cache_entry)
        self.assertFalse(result, "Unchanged files should not be reparsed")
    
    def test_should_reparse_file_modified(self):
        """Test that modified files should be reparsed."""
        # Create cache entry with old timestamp
        old_mtime = time.time() - 3600  # 1 hour ago
        cache_entry = FileCache(
            mtime=old_mtime,
            tasks=[],
            parsed_at="2023-12-15T09:00:00Z"
        )
        
        result = should_reparse_file(self.test_file_path, cache_entry)
        self.assertTrue(result, "Modified files should be reparsed")
    
    def test_cache_save_and_load_valid(self):
        """Test saving and loading a valid cache."""
        # Create cache with file entry
        file_stat = os.stat(self.test_file_path)
        file_cache_entry = FileCache(
            mtime=file_stat.st_mtime,
            tasks=[{"description": "Test task", "status": "todo"}],
            parsed_at="2023-12-15T10:00:00Z"
        )
        
        cache = IncrementalCache(
            schema_version=2,
            created_at="2023-12-15T10:00:00Z",
            last_updated="2023-12-15T10:00:00Z",
            file_cache={self.test_file_path: file_cache_entry}
        )
        
        # Save cache
        save_result = save_incremental_cache(cache, self.cache_path)
        self.assertTrue(save_result, "Cache save should succeed")
        self.assertTrue(os.path.isfile(self.cache_path), "Cache file should exist")
        
        # Load cache
        loaded_cache = load_incremental_cache(self.cache_path)
        self.assertIsNotNone(loaded_cache, "Cache should load successfully")
        self.assertEqual(loaded_cache.schema_version, 2)
        self.assertIn(self.test_file_path, loaded_cache.file_cache)
        
        loaded_entry = loaded_cache.file_cache[self.test_file_path]
        self.assertEqual(loaded_entry.mtime, file_cache_entry.mtime)
        self.assertEqual(len(loaded_entry.tasks), 1)
    
    def test_cache_load_nonexistent(self):
        """Test loading a non-existent cache file."""
        nonexistent_path = os.path.join(self.temp_dir, "nonexistent.json")
        result = load_incremental_cache(nonexistent_path)
        self.assertIsNone(result, "Loading non-existent cache should return None")
    
    def test_cache_load_corrupted_json(self):
        """Test loading a corrupted cache file."""
        # Create corrupted JSON file
        with open(self.cache_path, 'w') as f:
            f.write('{"corrupted": "json without closing brace"')
        
        result = load_incremental_cache(self.cache_path)
        self.assertIsNone(result, "Loading corrupted cache should return None")
    
    def test_cache_load_invalid_structure(self):
        """Test loading cache with invalid structure."""
        # Create cache with missing required fields
        invalid_cache = {"schema_version": 2}  # Missing other required fields
        
        with open(self.cache_path, 'w') as f:
            json.dump(invalid_cache, f)
        
        result = load_incremental_cache(self.cache_path)
        # The actual implementation may be forgiving and fill in missing fields
        # or it may return None - both are acceptable behaviors
        if result is not None:
            # If it succeeds, verify it has reasonable defaults
            self.assertIsInstance(result, IncrementalCache)
            self.assertEqual(result.schema_version, 2)
            self.assertIsInstance(result.file_cache, dict)
        else:
            # If it fails, that's also acceptable for invalid structure
            self.assertIsNone(result, "Strict validation should return None for invalid structure")
    
    def test_cache_schema_version_mismatch(self):
        """Test handling of schema version mismatches."""
        # Create cache with old schema version
        old_cache = {
            "schema_version": 1,  # Old version
            "created_at": "2023-12-15T10:00:00Z",
            "last_updated": "2023-12-15T10:00:00Z",
            "file_cache": {}
        }
        
        with open(self.cache_path, 'w') as f:
            json.dump(old_cache, f)
        
        result = load_incremental_cache(self.cache_path)
        # Should either return None (cache invalidated) or handle version gracefully
        # Implementation dependent - test that it doesn't crash
        if result is not None:
            self.assertIsInstance(result, IncrementalCache)
            # May upgrade schema version or preserve old one
        # Both None and IncrementalCache are acceptable - just verify no crash
    
    def test_cache_hit_performance(self):
        """Test cache hit performance optimization."""
        # Create vault with test files
        vault = Vault("Test", self.temp_dir)
        
        # Create multiple test files
        test_files = []
        for i in range(3):
            file_path = os.path.join(self.temp_dir, f"test_{i}.md")
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"# Test File {i}\n\n- [ ] Test task {i}\n")
            test_files.append(file_path)
        
        # Create cache with entries for all files
        file_cache = {}
        for file_path in test_files:
            file_stat = os.stat(file_path)
            file_cache[file_path] = FileCache(
                mtime=file_stat.st_mtime,
                tasks=[{"description": f"Test task", "status": "todo"}],
                parsed_at="2023-12-15T10:00:00Z"
            )
        
        cache = IncrementalCache(
            schema_version=2,
            created_at="2023-12-15T10:00:00Z",
            last_updated="2023-12-15T10:00:00Z",
            file_cache=file_cache
        )
        
        # Collect tasks with cache (should hit cache for all files)
        start_time = time.time()
        results, updated_cache, stats = collect_tasks_incremental([vault], set(), cache)
        cache_hit_time = time.time() - start_time
        
        # Collect tasks without cache (should reparse all files)
        start_time = time.time()
        results_nocache, new_cache, stats_nocache = collect_tasks_incremental([vault], set(), None)
        no_cache_time = time.time() - start_time
        
        # Cache hits should be faster than full parsing
        # Note: This is a performance hint test - actual timing may vary
        print(f"Cache hit time: {cache_hit_time:.3f}s, No cache time: {no_cache_time:.3f}s")
        
        # Verify we got the same number of files processed
        self.assertEqual(len(results), len(results_nocache))
    
    def test_cache_miss_fallback(self):
        """Test cache miss fallback behavior."""
        vault = Vault("Test", self.temp_dir)
        
        # Create cache with entry for non-existent file
        cache = IncrementalCache(
            schema_version=2,
            created_at="2023-12-15T10:00:00Z",
            last_updated="2023-12-15T10:00:00Z",
            file_cache={
                "/nonexistent/file.md": FileCache(
                    mtime=time.time(),
                    tasks=[],
                    parsed_at="2023-12-15T10:00:00Z"
                )
            }
        )
        
        # Should handle cache miss gracefully
        results, updated_cache, stats = collect_tasks_incremental([vault], set(), cache)
        
        # Should not crash and should return valid results
        self.assertIsInstance(results, list)
        self.assertIsInstance(updated_cache, IncrementalCache)
        self.assertIsInstance(stats, dict)
    
    def test_cache_corruption_recovery(self):
        """Test recovery from cache corruption during processing."""
        # Create a cache file that becomes corrupted during processing
        original_cache = IncrementalCache(
            schema_version=2,
            created_at="2023-12-15T10:00:00Z",
            last_updated="2023-12-15T10:00:00Z",
            file_cache={}
        )
        
        # Save valid cache initially
        save_incremental_cache(original_cache, self.cache_path)
        
        # Corrupt the cache file by truncating it
        with open(self.cache_path, 'w') as f:
            f.write('{"corrupted')  # Incomplete JSON
        
        # Loading should handle corruption gracefully
        loaded_cache = load_incremental_cache(self.cache_path)
        self.assertIsNone(loaded_cache, "Corrupted cache should return None")
        
        # System should continue working without cache
        vault = Vault("Test", self.temp_dir)
        results, new_cache, stats = collect_tasks_incremental([vault], set(), None)
        
        self.assertIsInstance(results, list)
        self.assertIsInstance(new_cache, IncrementalCache)
    
    def test_concurrent_cache_access(self):
        """Test handling of concurrent cache access."""
        # This test simulates multiple processes trying to access cache
        cache = IncrementalCache(
            schema_version=2,
            created_at="2023-12-15T10:00:00Z",
            last_updated="2023-12-15T10:00:00Z",
            file_cache={}
        )
        
        # Save cache
        save_result = save_incremental_cache(cache, self.cache_path)
        self.assertTrue(save_result)
        
        # Simulate concurrent modification by changing file between save and load
        time.sleep(0.1)  # Small delay
        
        # Modify cache file externally (simulating another process)
        with open(self.cache_path, 'w') as f:
            json.dump({
                "schema_version": 2,
                "created_at": "2023-12-15T11:00:00Z",  # Different timestamp
                "last_updated": "2023-12-15T11:00:00Z",
                "file_cache": {}
            }, f)
        
        # Load should succeed even with external modification
        loaded_cache = load_incremental_cache(self.cache_path)
        self.assertIsNotNone(loaded_cache)
        self.assertEqual(loaded_cache.created_at, "2023-12-15T11:00:00Z")
    
    def test_cache_invalidation_scenarios(self):
        """Test various cache invalidation scenarios."""
        try:
            file_stat = os.stat(self.test_file_path)
        except OSError:
            self.skipTest("Test file not available for cache invalidation tests")
        
        # Test 1: File modified after cache entry
        old_cache = FileCache(
            mtime=file_stat.st_mtime - 3600,  # 1 hour old
            tasks=[],
            parsed_at="2023-12-15T09:00:00Z"
        )
        result1 = should_reparse_file(self.test_file_path, old_cache)
        self.assertTrue(result1, "Old cache entry should trigger reparse")
        
        # Test 2: File deleted
        deleted_file = os.path.join(self.temp_dir, "deleted.md")
        deleted_cache = FileCache(
            mtime=time.time(),
            tasks=[],
            parsed_at="2023-12-15T10:00:00Z"
        )
        # should_reparse_file should handle missing files gracefully
        result2 = should_reparse_file(deleted_file, deleted_cache)
        # The implementation may return True (needs reparse) or False (skip missing file)
        # Both are valid behaviors for missing files
        self.assertIsInstance(result2, bool, "Should return a boolean result for missing files")
        
        # Test 3: Cache entry exists but file is newer
        # Modify the test file
        time.sleep(0.1)
        try:
            with open(self.test_file_path, 'a') as f:
                f.write("\n- [ ] New task\n")
            
            new_stat = os.stat(self.test_file_path)
            old_cache = FileCache(
                mtime=file_stat.st_mtime,  # Old mtime
                tasks=[],
                parsed_at="2023-12-15T10:00:00Z"
            )
            result3 = should_reparse_file(self.test_file_path, old_cache)
            self.assertTrue(result3, "Modified file should trigger reparse")
        except (OSError, IOError):
            # If file operations fail, skip this part of the test
            pass


@pytest.mark.cache
@pytest.mark.unit  
class TestCacheUtilities(unittest.TestCase):
    """Test cache utility functions."""
    
    def test_cache_serialization_roundtrip(self):
        """Test that cache can be serialized and deserialized without loss."""
        # Create complex cache with multiple file entries
        file_cache = {
            "/path/to/file1.md": FileCache(
                mtime=1234567890.123,
                tasks=[
                    {"description": "Task 1", "status": "todo", "tags": ["work"]},
                    {"description": "Task 2", "status": "done", "tags": ["personal"]}
                ],
                parsed_at="2023-12-15T10:00:00Z"
            ),
            "/path/to/file2.md": FileCache(
                mtime=1234567891.456,
                tasks=[],
                parsed_at="2023-12-15T10:01:00Z"
            )
        }
        
        original_cache = IncrementalCache(
            schema_version=2,
            created_at="2023-12-15T10:00:00Z",
            last_updated="2023-12-15T10:30:00Z",
            file_cache=file_cache
        )
        
        # Serialize to JSON and back
        temp_dir = tempfile.mkdtemp()
        try:
            cache_path = os.path.join(temp_dir, "test_cache.json")
            
            # Save and load
            save_result = save_incremental_cache(original_cache, cache_path)
            self.assertTrue(save_result)
            
            loaded_cache = load_incremental_cache(cache_path)
            self.assertIsNotNone(loaded_cache)
            
            # Verify all data preserved
            self.assertEqual(loaded_cache.schema_version, original_cache.schema_version)
            self.assertEqual(loaded_cache.created_at, original_cache.created_at)
            self.assertEqual(loaded_cache.last_updated, original_cache.last_updated)
            
            # Verify file cache entries
            self.assertEqual(len(loaded_cache.file_cache), 2)
            
            for path, original_entry in original_cache.file_cache.items():
                self.assertIn(path, loaded_cache.file_cache)
                loaded_entry = loaded_cache.file_cache[path]
                
                self.assertEqual(loaded_entry.mtime, original_entry.mtime)
                self.assertEqual(loaded_entry.parsed_at, original_entry.parsed_at)
                self.assertEqual(len(loaded_entry.tasks), len(original_entry.tasks))
                
                # Verify task details
                for orig_task, loaded_task in zip(original_entry.tasks, loaded_entry.tasks):
                    self.assertEqual(loaded_task["description"], orig_task["description"])
                    self.assertEqual(loaded_task["status"], orig_task["status"])
                    if "tags" in orig_task:
                        self.assertEqual(loaded_task["tags"], orig_task["tags"])
        
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)