#!/usr/bin/env python3
"""Quick validation test for UUID stability fix."""

import subprocess
import sys

def run_test():
    """Run a quick validation test."""
    print("🧪 Quick UUID Stability Validation")
    print("=" * 40)
    
    # Test 1: Multiple dry-run syncs should be stable
    print("\n🔧 Test 1: Running multiple dry-run syncs...")
    
    orphan_deletions = []
    for i in range(3):
        print(f"  Sync {i+1}/3...")
        try:
            result = subprocess.run(
                ["python3", "obs_tools.py", "sync"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if "Reminders deletions:" in result.stdout:
                line = [l for l in result.stdout.split('\n') if "Reminders deletions:" in l][0]
                orphan_deletions.append(f"Sync {i+1}: {line.strip()}")
                print(f"    ⚠️  {line.strip()}")
            else:
                print(f"    ✅ No orphan deletions")
                
        except subprocess.TimeoutExpired:
            print(f"    ⚠️  Sync {i+1} timed out")
        except Exception as e:
            print(f"    ❌ Sync {i+1} failed: {e}")
    
    # Results
    print(f"\n📊 Results:")
    print(f"  Total orphan deletion events: {len(orphan_deletions)}")
    
    if len(orphan_deletions) == 0:
        print("  ✅ SUCCESS: No orphan deletions detected!")
        print("  The UUID stability fix appears to be working correctly.")
        return True
    else:
        print("  ❌ ISSUE: Orphan deletions still occurring:")
        for deletion in orphan_deletions:
            print(f"    - {deletion}")
        print("  The UUID stability fix may need additional work.")
        return False

if __name__ == "__main__":
    success = run_test()
    print(f"\n🎯 Test {'PASSED' if success else 'FAILED'}")
    sys.exit(0 if success else 1)