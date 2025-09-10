#!/usr/bin/env python3
"""
Comprehensive test runner for obs-tools.

This script demonstrates the comprehensive test suite we've implemented,
including platform-specific tests, dependency fallbacks, and various
test categories.
"""

import subprocess
import sys
import platform
import os
from typing import List, Dict, Tuple

def run_command(cmd: List[str], description: str) -> Tuple[bool, str]:
    """Run a command and return success status and output."""
    try:
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)

def print_section(title: str):
    """Print a section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def main():
    """Run comprehensive test suite."""
    print("Comprehensive Test Suite for obs-tools")
    print(f"Platform: {platform.system()} {platform.release()}")
    print(f"Python: {sys.version}")
    
    # Test categories and their descriptions
    test_categories = [
        {
            "name": "Cache Tests",
            "description": "Incremental Obsidian cache functionality",
            "command": ["python", "-m", "pytest", "tests/test_incremental_cache.py", "-v", "--tb=short"],
            "markers": ["cache"]
        },
        {
            "name": "Matching Algorithm Tests", 
            "description": "Algorithm fallbacks (SciPy/Munkres/Greedy)",
            "command": ["python", "-m", "pytest", "tests/test_matching_fallbacks.py", "-v", "--tb=short"],
            "markers": ["matching", "scipy_optional", "munkres_optional"]
        },
        {
            "name": "Safe I/O Tests",
            "description": "Lock contention and concurrent operations", 
            "command": ["python", "-m", "pytest", "tests/test_safe_io_concurrency.py", "-v", "--tb=short"],
            "markers": ["io", "concurrency"]
        },
        {
            "name": "Platform-Specific Tests",
            "description": "macOS/EventKit tests with proper markers",
            "command": ["python", "-m", "pytest", "tests/test_eventkit_macos.py", "-v", "--tb=short"],
            "markers": ["macos", "eventkit"]
        },
        {
            "name": "Integration Tests",
            "description": "End-to-end workflow tests",
            "command": ["python", "-m", "pytest", "tests/test_integration.py", "-v", "--tb=short"],
            "markers": ["integration"]
        },
        {
            "name": "Unit Tests (Fast)",
            "description": "Fast unit tests across all modules",
            "command": ["python", "-m", "pytest", "-m", "unit and not slow", "-v", "--tb=short"],
            "markers": ["unit"]
        }
    ]
    
    results = {}
    
    for category in test_categories:
        print_section(category["name"])
        print(f"Description: {category['description']}")
        print(f"Markers: {', '.join(category['markers'])}")
        print(f"Command: {' '.join(category['command'])}")
        print()
        
        success, output = run_command(category["command"], category["name"])
        results[category["name"]] = success
        
        if success:
            print("✅ PASSED")
        else:
            print("❌ FAILED")
        
        # Show summary line from output
        lines = output.strip().split('\n')
        summary_lines = [line for line in lines if 'passed' in line and ('failed' in line or 'skipped' in line)]
        if summary_lines:
            print(f"Summary: {summary_lines[-1]}")
        
        # Show any critical errors
        error_lines = [line for line in lines if 'ERROR' in line.upper() or 'CRITICAL' in line.upper()]
        if error_lines:
            print("Errors:")
            for error in error_lines[:3]:  # Show first 3 errors
                print(f"  {error}")
    
    # Overall summary
    print_section("Test Suite Summary")
    
    total_categories = len(test_categories)
    passed_categories = sum(1 for success in results.values() if success)
    
    print(f"Total test categories: {total_categories}")
    print(f"Passed categories: {passed_categories}")
    print(f"Failed categories: {total_categories - passed_categories}")
    print()
    
    for category_name, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {category_name}")
    
    # Feature demonstration
    print_section("Implemented Features")
    
    features = [
        "✅ Platform-specific test markers (@pytest.mark.macos)",
        "✅ Automatic test skipping on non-Darwin platforms", 
        "✅ Incremental cache testing (hits/misses/corruption recovery)",
        "✅ Algorithm fallback testing (SciPy → Munkres → Greedy)",
        "✅ Safe I/O lock contention testing",
        "✅ Concurrent writer coordination testing",
        "✅ Optional dependency handling",
        "✅ Comprehensive pytest configuration",
        "✅ CI/CD GitHub Actions workflow",
        "✅ Test categorization with markers"
    ]
    
    for feature in features:
        print(feature)
    
    # Usage examples
    print_section("Usage Examples")
    
    examples = [
        "# Run all unit tests (fast)",
        "pytest -m 'unit and not slow'",
        "",
        "# Run only cache tests", 
        "pytest -m cache",
        "",
        "# Run tests excluding macOS-specific ones",
        "pytest -m 'not macos'",
        "",
        "# Run with coverage",
        "pytest --cov=lib --cov=obs_tools",
        "",
        "# Run fallback tests for missing dependencies",
        "pytest -m 'scipy_optional or munkres_optional'",
        "",
        "# Run concurrency tests",
        "pytest -m concurrency --durations=10",
    ]
    
    for example in examples:
        print(example)
    
    print_section("CI Configuration")
    print("Created .github/workflows/ci.yml with:")
    print("• Multi-platform testing (Linux, macOS, Windows)")
    print("• Python version matrix (3.8, 3.9, 3.10, 3.11)")
    print("• Optional dependency testing")
    print("• Platform-specific test execution")
    print("• Performance and security testing")
    print("• Code quality checks")
    
    return passed_categories == total_categories

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)