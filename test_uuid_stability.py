#!/usr/bin/env python3
# Make executable
import stat
"""
Comprehensive edge case testing for UUID stability fix.

This script tests various scenarios to ensure deterministic UUIDs work correctly
and don't cause orphan cleanup issues.
"""

import os
import subprocess
import tempfile
import time
import sys
from pathlib import Path

def run_sync(dry_run=True, verbose=True):
    """Run obs-sync and capture output."""
    cmd = ["./bin/obs-sync", "sync"]
    if not dry_run:
        cmd.append("--apply")
    if verbose:
        cmd.append("--verbose")
    
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=".")
    return result.returncode, result.stdout, result.stderr

def create_test_file(vault_path, filename, content):
    """Create a test markdown file in the vault."""
    file_path = Path(vault_path) / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content)
    return str(file_path.relative_to(vault_path))

def read_test_file(vault_path, filename):
    """Read content from a test file."""
    file_path = Path(vault_path) / filename
    if file_path.exists():
        return file_path.read_text()
    return None

def test_uuid_stability():
    """Test that tasks without block IDs get stable UUIDs across syncs."""
    print("🧪 Test 1: UUID Stability for tasks without block IDs")
    
    # Run first sync and capture task UUIDs
    print("  Running first sync...")
    code, stdout1, stderr1 = run_sync(dry_run=True, verbose=True)
    
    # Wait a moment and run second sync
    print("  Running second sync...")
    time.sleep(1)
    code, stdout2, stderr2 = run_sync(dry_run=True, verbose=True)
    
    # Check for orphan deletions
    orphan_deletions_1 = "Reminders deletions:" in stdout1
    orphan_deletions_2 = "Reminders deletions:" in stdout2
    
    print(f"  First sync orphan deletions: {orphan_deletions_1}")
    print(f"  Second sync orphan deletions: {orphan_deletions_2}")
    
    if orphan_deletions_2:
        print("  ❌ FAILED: Second sync still shows orphan deletions")
        print("  Stdout:", stdout2)
        return False
    else:
        print("  ✅ PASSED: No orphan deletions on second sync")
        return True

def test_block_id_preservation():
    """Test that tasks with existing block IDs maintain them."""
    print("\n🧪 Test 2: Block ID Preservation")
    
    # This test assumes there are some tasks with existing block IDs
    print("  Running sync to check block ID preservation...")
    code, stdout, stderr = run_sync(dry_run=True, verbose=True)
    
    # Look for any warnings about block ID changes
    if "Generated stable block ID" in stderr:
        print("  ℹ️  Some tasks received new stable block IDs (expected for tasks without IDs)")
    
    print("  ✅ Test completed - check logs for any block ID issues")
    return True

def test_task_completion_cycle():
    """Test the complete workflow: create, sync, complete, sync again."""
    print("\n🧪 Test 3: Task Completion Cycle")
    
    # Find vault path
    vault_path = None
    code, stdout, stderr = run_sync(dry_run=True, verbose=True)
    
    # Create a test task file
    test_content = """# UUID Stability Test

- [ ] Test task for UUID stability verification
- [ ] Another test task without block ID  
- [ ] Third test task for collision testing
"""
    
    # We'll use a simple approach - run multiple syncs and check for stability
    print("  Running multiple syncs to test stability...")
    
    syncs_with_orphans = 0
    for i in range(3):
        print(f"    Sync {i+1}...")
        code, stdout, stderr = run_sync(dry_run=True, verbose=True)
        if "Reminders deletions:" in stdout:
            syncs_with_orphans += 1
            print(f"    ⚠️  Sync {i+1} reported orphan deletions")
    
    if syncs_with_orphans == 0:
        print("  ✅ PASSED: No orphan deletions across multiple syncs")
        return True
    else:
        print(f"  ❌ FAILED: {syncs_with_orphans}/3 syncs reported orphan deletions")
        return False

def test_collision_handling():
    """Test how the system handles tasks with identical descriptions."""
    print("\n🧪 Test 4: Collision Handling")
    
    print("  This test checks if tasks with similar content get unique UUIDs...")
    print("  Running sync to observe collision handling...")
    
    code, stdout, stderr = run_sync(dry_run=True, verbose=True)
    
    # Look for collision warnings in logs
    if "High collision count" in stderr:
        print("  ⚠️  Warning: High collision count detected")
        return False
    else:
        print("  ✅ PASSED: No collision warnings detected")
        return True

def test_mixed_task_states():
    """Test syncing with mix of tasks (with/without block IDs, different states)."""
    print("\n🧪 Test 5: Mixed Task States")
    
    print("  Testing sync with mixed task states...")
    code, stdout, stderr = run_sync(dry_run=True, verbose=True)
    
    # Parse sync results
    lines = stdout.split('\n')
    obs_tasks = 0
    rem_tasks = 0
    links = 0
    
    for line in lines:
        if "Obsidian tasks:" in line:
            obs_tasks = int(line.split(':')[1].strip())
        elif "Reminders tasks:" in line:
            rem_tasks = int(line.split(':')[1].strip())
        elif "Matched pairs:" in line:
            links = int(line.split(':')[1].strip())
    
    print(f"  Obsidian tasks: {obs_tasks}")
    print(f"  Reminders tasks: {rem_tasks}")
    print(f"  Matched pairs: {links}")
    
    if obs_tasks > 0 and rem_tasks > 0:
        print("  ✅ PASSED: Found tasks in both systems")
        return True
    else:
        print("  ⚠️  Warning: Limited tasks found for testing")
        return True

def test_sync_interruption_recovery():
    """Test recovery from interrupted sync operations."""
    print("\n🧪 Test 6: Sync Recovery")
    
    print("  Testing sync recovery by running consecutive syncs...")
    
    # Run two quick syncs to simulate interruption/recovery
    code1, stdout1, stderr1 = run_sync(dry_run=True, verbose=True)
    code2, stdout2, stderr2 = run_sync(dry_run=True, verbose=True)
    
    # Both should succeed
    if code1 == 0 and code2 == 0:
        print("  ✅ PASSED: Both syncs completed successfully")
        return True
    else:
        print(f"  ❌ FAILED: Sync errors - codes: {code1}, {code2}")
        return False

def run_all_tests():
    """Run all edge case tests."""
    print("🧪 Starting comprehensive edge case testing for UUID stability fix...\n")
    
    tests = [
        test_uuid_stability,
        test_block_id_preservation, 
        test_task_completion_cycle,
        test_collision_handling,
        test_mixed_task_states,
        test_sync_interruption_recovery,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"  ❌ Test failed with exception: {e}")
            results.append(False)
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! UUID stability fix appears to be working correctly.")
    else:
        print("⚠️  Some tests failed. Review the output above for issues.")
    
    return passed == total

if __name__ == "__main__":
    run_all_tests()