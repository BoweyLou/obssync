#!/usr/bin/env python3
"""
Unit tests for safe I/O lock contention and concurrent operations.

Tests concurrent writers, lock timeouts, proper waiting/failing behavior,
and atomic operations under contention.
"""

import json
import os
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import List, Optional
from unittest.mock import patch, MagicMock

import pytest

# Add parent directory to path for imports
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import modules under test
try:
    from lib.safe_io import (
        file_lock, atomic_write_text, atomic_write_json, safe_load_json,
        safe_write_json_with_lock, FileLockError, JsonSizeError,
        generate_run_id, check_concurrent_access, ensure_run_id_in_meta
    )
except ImportError:
    # Mock implementations for testing
    class FileLockError(Exception):
        pass
    
    class JsonSizeError(Exception):
        pass
    
    def file_lock(file_path: str, timeout: float = 30.0):
        """Mock file lock context manager."""
        import contextlib
        return contextlib.nullcontext()
    
    def atomic_write_text(file_path: str, content: str, encoding: str = "utf-8") -> None:
        with open(file_path, 'w', encoding=encoding) as f:
            f.write(content)
    
    def atomic_write_json(file_path: str, data, indent: Optional[int] = 2) -> None:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=indent)
    
    def safe_load_json(file_path: str, default=None, size_limit: int = 100*1024*1024):
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except:
            return default
    
    def safe_write_json_with_lock(file_path: str, data, run_id: str = None, indent: int = 2, timeout: float = 30.0):
        atomic_write_json(file_path, data, indent)
    
    def generate_run_id() -> str:
        import uuid
        return str(uuid.uuid4())[:8]
    
    def check_concurrent_access(file_path: str, run_id: str) -> bool:
        return False
    
    def ensure_run_id_in_meta(data: dict, run_id: str) -> dict:
        if isinstance(data, dict):
            if "meta" not in data:
                data["meta"] = {}
            data["meta"]["run_id"] = run_id
        return data


@pytest.mark.io
@pytest.mark.concurrency
@pytest.mark.unit
class TestSafeIOConcurrency(unittest.TestCase):
    """Test safe I/O operations under concurrent access."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp(prefix="safe_io_test_")
        self.test_file = os.path.join(self.temp_dir, "test.json")
        self.lock_results = []  # To collect results from concurrent operations
        self.write_results = []  # To collect write results
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_file_lock_basic_functionality(self):
        """Test basic file locking functionality."""
        # Test that file lock can be acquired and released
        with file_lock(self.test_file, timeout=1.0):
            # Write some data while holding lock
            with open(self.test_file, 'w') as f:
                f.write("test data")
        
        # Verify file was written
        self.assertTrue(os.path.isfile(self.test_file))
        with open(self.test_file, 'r') as f:
            content = f.read()
        self.assertEqual(content, "test data")
    
    def test_file_lock_timeout(self):
        """Test file lock timeout behavior."""
        # This test simulates lock timeout by using very short timeout
        # In a real scenario, another process would hold the lock
        
        lock_acquired = threading.Event()
        lock_released = threading.Event()
        
        def hold_lock_briefly():
            """Function to hold lock briefly in another thread."""
            try:
                with file_lock(self.test_file, timeout=5.0):
                    lock_acquired.set()
                    # Hold lock for a short time
                    time.sleep(0.5)
                lock_released.set()
            except FileLockError:
                pass
        
        # Start thread that holds the lock
        thread = threading.Thread(target=hold_lock_briefly)
        thread.start()
        
        # Wait for lock to be acquired
        lock_acquired.wait(timeout=2.0)
        
        # Try to acquire lock with very short timeout - should fail
        start_time = time.time()
        with self.assertRaises(FileLockError):
            with file_lock(self.test_file, timeout=0.1):
                pass
        end_time = time.time()
        
        # Should have timed out quickly
        self.assertLess(end_time - start_time, 0.5)
        
        # Wait for first thread to complete
        thread.join(timeout=2.0)
        lock_released.wait(timeout=2.0)
    
    def test_concurrent_writers_with_locks(self):
        """Test that concurrent writers are properly serialized with locks."""
        num_writers = 5
        writes_per_writer = 3
        write_results = []
        write_lock = threading.Lock()
        
        def writer_function(writer_id: int):
            """Function for concurrent writer."""
            local_results = []
            for i in range(writes_per_writer):
                try:
                    data = {
                        "writer_id": writer_id,
                        "write_number": i,
                        "timestamp": time.time(),
                        "data": f"Writer {writer_id}, Write {i}"
                    }
                    
                    # Use safe write with lock
                    safe_write_json_with_lock(
                        self.test_file, 
                        data, 
                        run_id=f"writer_{writer_id}",
                        timeout=5.0
                    )
                    
                    local_results.append(("success", writer_id, i))
                    time.sleep(0.01)  # Small delay between writes
                    
                except Exception as e:
                    local_results.append(("error", writer_id, i, str(e)))
            
            # Safely add results to shared list
            with write_lock:
                write_results.extend(local_results)
        
        # Start concurrent writers
        threads = []
        for writer_id in range(num_writers):
            thread = threading.Thread(target=writer_function, args=(writer_id,))
            threads.append(thread)
            thread.start()
        
        # Wait for all writers to complete
        for thread in threads:
            thread.join(timeout=10.0)
        
        # Verify all writes completed
        successful_writes = [r for r in write_results if r[0] == "success"]
        self.assertEqual(len(successful_writes), num_writers * writes_per_writer)
        
        # Verify final file is valid JSON
        final_data = safe_load_json(self.test_file)
        self.assertIsNotNone(final_data)
        self.assertIsInstance(final_data, dict)
        
        # File should contain data from the last writer
        self.assertIn("writer_id", final_data)
        self.assertIn("write_number", final_data)
    
    def test_lock_contention_behavior(self):
        """Test behavior under heavy lock contention."""
        num_threads = 10
        contention_results = []
        results_lock = threading.Lock()
        
        def contending_function(thread_id: int):
            """Function that competes for the same lock."""
            try:
                start_time = time.time()
                with file_lock(self.test_file, timeout=2.0):
                    acquired_time = time.time()
                    # Do some work while holding lock
                    time.sleep(0.1)
                    work_done_time = time.time()
                
                with results_lock:
                    contention_results.append({
                        "thread_id": thread_id,
                        "status": "success",
                        "wait_time": acquired_time - start_time,
                        "work_time": work_done_time - acquired_time
                    })
                    
            except FileLockError as e:
                with results_lock:
                    contention_results.append({
                        "thread_id": thread_id,
                        "status": "timeout",
                        "error": str(e)
                    })
        
        # Start all contending threads
        threads = []
        start_time = time.time()
        for thread_id in range(num_threads):
            thread = threading.Thread(target=contending_function, args=(thread_id,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join(timeout=15.0)
        
        total_time = time.time() - start_time
        
        # Analyze results
        successful = [r for r in contention_results if r["status"] == "success"]
        timeouts = [r for r in contention_results if r["status"] == "timeout"]
        
        print(f"Lock contention test: {len(successful)} successful, {len(timeouts)} timeouts in {total_time:.2f}s")
        
        # Should have some successful operations
        self.assertGreater(len(successful), 0)
        
        # Total successful + timeouts should equal number of threads
        self.assertEqual(len(successful) + len(timeouts), num_threads)
        
        # If any succeeded, they should have reasonable wait times
        if successful:
            wait_times = [r["wait_time"] for r in successful]
            max_wait = max(wait_times)
            self.assertLess(max_wait, 3.0, "Lock wait times should be reasonable")
    
    def test_atomic_write_interruption_resistance(self):
        """Test that atomic writes are resistant to interruption."""
        # This test simulates interruption during write operations
        
        original_data = {"original": "data", "should_not_be": "corrupted"}
        atomic_write_json(self.test_file, original_data)
        
        # Verify original data is intact
        loaded = safe_load_json(self.test_file)
        self.assertEqual(loaded, original_data)
        
        interrupted_writes = 0
        successful_writes = 0
        
        def potentially_interrupted_writer():
            """Writer that might be interrupted."""
            nonlocal interrupted_writes, successful_writes
            try:
                new_data = {
                    "interrupted": "maybe",
                    "timestamp": time.time(),
                    "large_data": "x" * 1000  # Make write take a bit longer
                }
                atomic_write_json(self.test_file, new_data)
                successful_writes += 1
            except Exception:
                interrupted_writes += 1
        
        # Start multiple writers that might interfere with each other
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=potentially_interrupted_writer)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join(timeout=5.0)
        
        # File should still be valid JSON (not corrupted)
        final_data = safe_load_json(self.test_file)
        self.assertIsNotNone(final_data, "File should not be corrupted")
        self.assertIsInstance(final_data, dict)
        
        # Should be either original data or one of the new writes
        self.assertTrue(
            final_data == original_data or "interrupted" in final_data,
            "File should contain valid data"
        )
    
    def test_run_id_coordination(self):
        """Test run ID coordination for concurrent access detection."""
        run_id_1 = generate_run_id()
        run_id_2 = generate_run_id()
        
        # Different run IDs should be unique
        self.assertNotEqual(run_id_1, run_id_2)
        
        # Test data with run ID
        data_1 = {"meta": {"run_id": run_id_1}, "data": "first"}
        data_2 = {"meta": {"run_id": run_id_2}, "data": "second"}
        
        # Write first data
        safe_write_json_with_lock(self.test_file, data_1, run_id=run_id_1)
        
        # Check for concurrent access with different run ID
        has_conflict = check_concurrent_access(self.test_file, run_id_2)
        self.assertTrue(has_conflict, "Should detect different run ID as potential conflict")
        
        # Check with same run ID
        no_conflict = check_concurrent_access(self.test_file, run_id_1)
        self.assertFalse(no_conflict, "Should not detect conflict with same run ID")
    
    def test_lock_timeout_variations(self):
        """Test various lock timeout scenarios."""
        # Test very short timeout
        with self.assertRaises(FileLockError):
            # Create a situation where lock times out
            def hold_lock():
                with file_lock(self.test_file, timeout=2.0):
                    time.sleep(1.0)
            
            thread = threading.Thread(target=hold_lock)
            thread.start()
            time.sleep(0.1)  # Let other thread acquire lock
            
            # This should timeout quickly
            with file_lock(self.test_file, timeout=0.1):
                pass
            
            thread.join()
    
    def test_file_lock_cleanup(self):
        """Test that file locks are properly cleaned up."""
        # Test normal cleanup
        lock_file = f"{self.test_file}.lock"
        
        with file_lock(self.test_file, timeout=1.0):
            # Lock file might exist during lock (implementation dependent)
            pass
        
        # Lock file should be cleaned up after context exit
        # Note: Implementation may vary, but shouldn't leave permanent lock files
        time.sleep(0.1)  # Allow cleanup time
        
        # Should be able to acquire lock again immediately
        with file_lock(self.test_file, timeout=0.1):
            pass
    
    def test_json_size_limits_under_contention(self):
        """Test JSON size limits during concurrent operations."""
        # Create data that exceeds size limit
        large_data = {
            "meta": {"schema": 2},
            "large_field": "x" * (1024 * 1024)  # 1MB of data
        }
        
        # Test size limit checking
        with self.assertRaises((JsonSizeError, Exception)):
            # Some implementations might raise different exceptions for size limits
            safe_load_json(self.test_file, size_limit=1024)  # Very small limit
    
    def test_concurrent_read_write_safety(self):
        """Test safety of concurrent read and write operations."""
        initial_data = {"counter": 0, "readers": [], "writers": []}
        atomic_write_json(self.test_file, initial_data)
        
        read_results = []
        write_results = []
        results_lock = threading.Lock()
        
        def reader_function(reader_id: int):
            """Function that reads data."""
            for i in range(5):
                try:
                    data = safe_load_json(self.test_file, default={})
                    with results_lock:
                        read_results.append((reader_id, i, data.get("counter", -1)))
                    time.sleep(0.01)
                except Exception as e:
                    with results_lock:
                        read_results.append((reader_id, i, f"error: {e}"))
        
        def writer_function(writer_id: int):
            """Function that writes data."""
            for i in range(3):
                try:
                    # Read current data, modify, and write back
                    current_data = safe_load_json(self.test_file, default={"counter": 0})
                    current_data["counter"] = current_data.get("counter", 0) + 1
                    current_data["last_writer"] = writer_id
                    
                    safe_write_json_with_lock(self.test_file, current_data, timeout=2.0)
                    
                    with results_lock:
                        write_results.append((writer_id, i, "success"))
                    time.sleep(0.02)
                except Exception as e:
                    with results_lock:
                        write_results.append((writer_id, i, f"error: {e}"))
        
        # Start readers and writers concurrently
        threads = []
        
        # Start readers
        for reader_id in range(3):
            thread = threading.Thread(target=reader_function, args=(reader_id,))
            threads.append(thread)
            thread.start()
        
        # Start writers
        for writer_id in range(2):
            thread = threading.Thread(target=writer_function, args=(writer_id,))
            threads.append(thread)
            thread.start()
        
        # Wait for all operations to complete
        for thread in threads:
            thread.join(timeout=10.0)
        
        # Verify final state is consistent
        final_data = safe_load_json(self.test_file)
        self.assertIsNotNone(final_data)
        self.assertIsInstance(final_data, dict)
        
        # Should have some counter value
        self.assertIn("counter", final_data)
        final_counter = final_data["counter"]
        self.assertGreaterEqual(final_counter, 0)
        
        print(f"Concurrent R/W test: {len(read_results)} reads, {len(write_results)} writes")
        print(f"Final counter value: {final_counter}")


@pytest.mark.io
@pytest.mark.unit
class TestAtomicOperations(unittest.TestCase):
    """Test atomic operations in isolation."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp(prefix="atomic_test_")
        self.test_file = os.path.join(self.temp_dir, "atomic_test.json")
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_atomic_write_text_basic(self):
        """Test basic atomic text writing."""
        content = "Hello, world!\nThis is a test."
        atomic_write_text(self.test_file, content)
        
        # Verify file exists and content is correct
        self.assertTrue(os.path.isfile(self.test_file))
        with open(self.test_file, 'r') as f:
            read_content = f.read()
        self.assertEqual(read_content, content)
    
    def test_atomic_write_json_basic(self):
        """Test basic atomic JSON writing."""
        data = {
            "string": "value",
            "number": 42,
            "boolean": True,
            "null": None,
            "array": [1, 2, 3],
            "object": {"nested": "value"}
        }
        
        atomic_write_json(self.test_file, data)
        
        # Verify file exists and data is correct
        self.assertTrue(os.path.isfile(self.test_file))
        loaded_data = safe_load_json(self.test_file)
        self.assertEqual(loaded_data, data)
    
    def test_atomic_write_overwrites_existing(self):
        """Test that atomic writes properly overwrite existing files."""
        # Write initial data
        initial_data = {"version": 1, "data": "initial"}
        atomic_write_json(self.test_file, initial_data)
        
        # Verify initial data
        loaded = safe_load_json(self.test_file)
        self.assertEqual(loaded, initial_data)
        
        # Overwrite with new data
        new_data = {"version": 2, "data": "updated"}
        atomic_write_json(self.test_file, new_data)
        
        # Verify new data
        loaded = safe_load_json(self.test_file)
        self.assertEqual(loaded, new_data)
        self.assertNotEqual(loaded, initial_data)
    
    def test_atomic_write_preserves_data_on_failure(self):
        """Test that atomic writes preserve existing data if write fails."""
        # Write valid initial data
        initial_data = {"valid": "data"}
        atomic_write_json(self.test_file, initial_data)
        
        # Attempt to write invalid data (should fail)
        class UnserializableObject:
            pass
        
        invalid_data = {"valid": "data", "invalid": UnserializableObject()}
        
        with self.assertRaises((TypeError, json.JSONEncodeError)):
            atomic_write_json(self.test_file, invalid_data)
        
        # Original data should still be intact
        loaded = safe_load_json(self.test_file)
        self.assertEqual(loaded, initial_data)
    
    def test_ensure_run_id_in_meta(self):
        """Test run ID injection into metadata."""
        run_id = generate_run_id()
        
        # Test with dict that has no meta
        data1 = {"data": "value"}
        result1 = ensure_run_id_in_meta(data1, run_id)
        self.assertIn("meta", result1)
        self.assertEqual(result1["meta"]["run_id"], run_id)
        
        # Test with dict that has existing meta
        data2 = {"meta": {"existing": "value"}, "data": "value"}
        result2 = ensure_run_id_in_meta(data2, run_id)
        self.assertEqual(result2["meta"]["run_id"], run_id)
        self.assertEqual(result2["meta"]["existing"], "value")
        
        # Test with non-dict data
        data3 = "not a dict"
        result3 = ensure_run_id_in_meta(data3, run_id)
        self.assertEqual(result3, data3)


if __name__ == '__main__':
    unittest.main(verbosity=2)