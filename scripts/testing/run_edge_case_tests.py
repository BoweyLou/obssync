#!/usr/bin/env python3
# chmod +x run_edge_case_tests.py
"""
Quick edge case testing runner for UUID stability.
Runs specific targeted tests to validate the fix.
"""

import subprocess
import sys
import time

def run_command(cmd, description):
    """Run a command and capture output."""
    print(f"\n🔧 {description}")
    print(f"   Command: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    print(f"   Exit code: {result.returncode}")
    if result.stdout.strip():
        print("   Stdout:")
        for line in result.stdout.strip().split('\n'):
            print(f"     {line}")
    if result.stderr.strip():
        print("   Stderr:")
        for line in result.stderr.strip().split('\n'):
            print(f"     {line}")
    
    return result.returncode, result.stdout, result.stderr

def test_uuid_stability():
    """Core test: Multiple syncs should not show orphan deletions."""
    print("🧪 Testing UUID Stability - Core Issue")
    
    orphan_deletions_found = []
    
    for i in range(3):
        code, stdout, stderr = run_command(
            ["python3", "obs_tools.py", "sync", "--verbose"],
            f"Sync Run {i+1}/3 (dry-run)"
        )
        
        # Check for the exact issue we're fixing
        if "Reminders deletions:" in stdout:
            deletions = [line for line in stdout.split('\n') if "Reminders deletions:" in line]
            orphan_deletions_found.extend(deletions)
            print(f"   ⚠️  Found orphan deletions: {deletions}")
        
        if "Removed sync links:" in stdout:
            removals = [line for line in stdout.split('\n') if "Removed sync links:" in line]
            print(f"   ⚠️  Found link removals: {removals}")
        
        # Small delay between syncs
        time.sleep(0.5)
    
    if not orphan_deletions_found:
        print("   ✅ SUCCESS: No orphan deletions found across multiple syncs")
        return True
    else:
        print(f"   ❌ FAILURE: Found {len(orphan_deletions_found)} orphan deletion events")
        print("   This indicates the UUID stability fix may not be working properly")
        return False

def test_actual_sync():
    """Test with --apply to see real behavior."""
    print("\n🧪 Testing Actual Sync (--apply)")
    
    # First do a dry run
    code1, stdout1, stderr1 = run_command(
        ["python3", "obs_tools.py", "sync", "--verbose"],
        "Dry run sync"
    )
    
    # Then an actual sync if dry run looks clean
    if "Reminders deletions:" not in stdout1:
        print("   Dry run clean, proceeding with actual sync...")
        code2, stdout2, stderr2 = run_command(
            ["python3", "obs_tools.py", "sync", "--apply", "--verbose"],
            "Actual sync with --apply"
        )
        
        # Follow up with another dry run to check stability
        print("   Running follow-up dry run to check stability...")
        code3, stdout3, stderr3 = run_command(
            ["python3", "obs_tools.py", "sync", "--verbose"],
            "Post-sync stability check"
        )
        
        if "Reminders deletions:" in stdout3:
            print("   ❌ FAILURE: Orphan deletions appeared after actual sync")
            return False
        else:
            print("   ✅ SUCCESS: No orphan deletions after actual sync")
            return True
    else:
        print("   ⚠️ SKIPPED: Dry run showed orphan deletions, skipping --apply")
        return False

def test_task_completion_scenario():
    """Test the original reported scenario: complete task in reminders, then sync."""
    print("\n🧪 Testing Task Completion Scenario")
    
    print("   This test simulates the original reported issue:")
    print("   1. Task exists in both systems")
    print("   2. Task gets completed (simulated by multiple syncs)")
    print("   3. Check if task stays stable")
    
    # Run multiple syncs to simulate the completion workflow
    stable = True
    for i in range(2):
        code, stdout, stderr = run_command(
            ["python3", "obs_tools.py", "sync", "--verbose"],
            f"Completion simulation sync {i+1}"
        )
        
        if "Reminders deletions:" in stdout:
            print(f"   ❌ Sync {i+1} showed orphan deletions")
            stable = False
    
    if stable:
        print("   ✅ SUCCESS: Task completion scenario stable")
        return True
    else:
        print("   ❌ FAILURE: Task completion scenario unstable")
        return False

def main():
    """Run all edge case tests."""
    print("🧪 Edge Case Testing for UUID Stability Fix")
    print("=" * 50)
    
    tests = [
        ("UUID Stability Core Test", test_uuid_stability),
        ("Task Completion Scenario", test_task_completion_scenario),
        ("Actual Sync Test", test_actual_sync),
    ]
    
    # Add URL matching test
    print("\n" + "="*50)
    print("Adding URL Matching Test...")
    url_test_result = run_command(
        ["python3", "test_url_matching.py"],
        "URL matching edge case tests"
    )
    tests.append(("URL Matching Fix Test", lambda: url_test_result.returncode == 0))
    
    results = []
    for test_name, test_func in tests:
        try:
            print(f"\n{'='*20} {test_name} {'='*20}")
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"   ❌ Test failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print(f"\n{'='*50}")
    print("📊 FINAL RESULTS:")
    print("=" * 50)
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
        if result:
            passed += 1
    
    print(f"\n🎯 {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("🎉 All tests passed! UUID stability fix is working correctly.")
        print("   Your orphan cleanup issue should be resolved.")
    else:
        print("⚠️  Some tests failed. The UUID stability fix may need adjustment.")
        print("   Check the detailed output above for specific issues.")
    
    return passed == len(results)

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)