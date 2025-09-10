#!/usr/bin/env python3
"""
Path Validation and Cleanup Script for obs-tools

This script addresses the path inconsistencies found during the audit:
1. Validates that all configuration files are consistent
2. Identifies and reports stale index files in the wrong locations
3. Provides options to clean up duplicate/outdated files
4. Ensures all tools are using the centralized path configuration
"""

import os
import json
import shutil
import argparse
from datetime import datetime
from typing import List, Dict, Tuple, Optional

import app_config as cfg


def check_file_consistency(file1: str, file2: str) -> Dict[str, any]:
    """Compare two files and return consistency information."""
    result = {
        "both_exist": False,
        "sizes_differ": False,
        "newer_file": None,
        "file1_size": 0,
        "file2_size": 0,
        "file1_mtime": None,
        "file2_mtime": None,
        "recommendation": ""
    }
    
    file1_exists = os.path.exists(file1)
    file2_exists = os.path.exists(file2)
    
    result["both_exist"] = file1_exists and file2_exists
    
    if not result["both_exist"]:
        if file1_exists and not file2_exists:
            result["recommendation"] = f"Only {file1} exists - this is expected"
        elif file2_exists and not file1_exists:
            result["recommendation"] = f"Only {file2} exists - should move to {file1}"
        else:
            result["recommendation"] = "Neither file exists"
        return result
    
    # Both files exist - compare them
    stat1 = os.stat(file1)
    stat2 = os.stat(file2)
    
    result["file1_size"] = stat1.st_size
    result["file2_size"] = stat2.st_size
    result["file1_mtime"] = datetime.fromtimestamp(stat1.st_mtime)
    result["file2_mtime"] = datetime.fromtimestamp(stat2.st_mtime)
    
    result["sizes_differ"] = result["file1_size"] != result["file2_size"]
    
    if stat1.st_mtime > stat2.st_mtime:
        result["newer_file"] = file1
        result["recommendation"] = f"{file1} is newer - keep this one"
    elif stat2.st_mtime > stat1.st_mtime:
        result["newer_file"] = file2
        result["recommendation"] = f"{file2} is newer - consider moving to {file1}"
    else:
        result["recommendation"] = "Files have same timestamp - check content"
    
    return result


def find_problematic_files() -> Dict[str, Dict]:
    """Find files that exist in wrong locations or are duplicated."""
    paths = cfg.default_paths()
    
    # Current working directory (vault root)
    cwd = os.getcwd()
    
    # Files that might exist in wrong locations
    problematic_patterns = {
        "obsidian_index": {
            "correct": paths["obsidian_index"],
            "wrong_locations": [
                os.path.join(cwd, "obsidian_tasks_index.json"),
                os.path.join(cwd, "_tmp_obsidian_tasks_index.json")
            ]
        },
        "reminders_index": {
            "correct": paths["reminders_index"],
            "wrong_locations": [
                os.path.join(cwd, "reminders_tasks_index.json"),
                os.path.join(cwd, "_tmp_reminders_tasks_index.json")
            ]
        },
        "links": {
            "correct": paths["links"],
            "wrong_locations": [
                os.path.join(cwd, "sync_links.json")
            ]
        }
    }
    
    results = {}
    
    for key, info in problematic_patterns.items():
        correct_path = info["correct"]
        wrong_paths = info["wrong_locations"]
        
        results[key] = {
            "correct_path": correct_path,
            "issues": []
        }
        
        for wrong_path in wrong_paths:
            if os.path.exists(wrong_path):
                consistency = check_file_consistency(correct_path, wrong_path)
                results[key]["issues"].append({
                    "wrong_path": wrong_path,
                    "consistency": consistency
                })
    
    return results


def print_analysis(problems: Dict[str, Dict]) -> None:
    """Print detailed analysis of path problems."""
    print("=== Path Consistency Analysis ===\n")
    
    for file_type, info in problems.items():
        correct_path = info["correct_path"]
        issues = info["issues"]
        
        if not issues:
            print(f"✓ {file_type}: No issues found")
            print(f"  Correct location: {correct_path}")
            if os.path.exists(correct_path):
                size = os.path.getsize(correct_path)
                mtime = datetime.fromtimestamp(os.path.getmtime(correct_path))
                print(f"  Size: {size:,} bytes, Modified: {mtime}")
            else:
                print(f"  Status: File does not exist")
            print()
            continue
            
        print(f"⚠ {file_type}: {len(issues)} issue(s) found")
        print(f"  Correct location: {correct_path}")
        
        for i, issue in enumerate(issues, 1):
            wrong_path = issue["wrong_path"]
            consistency = issue["consistency"]
            
            print(f"\n  Issue {i}: File found at {wrong_path}")
            print(f"    Recommendation: {consistency['recommendation']}")
            
            if consistency["both_exist"]:
                print(f"    Size comparison: {consistency['file1_size']:,} vs {consistency['file2_size']:,} bytes")
                print(f"    Modified: {consistency['file1_mtime']} vs {consistency['file2_mtime']}")
                if consistency["sizes_differ"]:
                    print(f"    ⚠ Files have different sizes!")
        print()


def cleanup_files(problems: Dict[str, Dict], dry_run: bool = True) -> None:
    """Clean up problematic files based on analysis."""
    print("=== Cleanup Actions ===\n")
    
    actions_taken = 0
    
    for file_type, info in problems.items():
        issues = info["issues"]
        if not issues:
            continue
            
        correct_path = info["correct_path"]
        
        for issue in issues:
            wrong_path = issue["wrong_path"]
            consistency = issue["consistency"]
            
            action = None
            
            if not consistency["both_exist"]:
                if os.path.exists(wrong_path) and not os.path.exists(correct_path):
                    action = f"MOVE {wrong_path} → {correct_path}"
                    if not dry_run:
                        os.makedirs(os.path.dirname(correct_path), exist_ok=True)
                        shutil.move(wrong_path, correct_path)
                        actions_taken += 1
            else:
                # Both exist - need to decide which to keep
                if consistency["newer_file"] == correct_path:
                    action = f"DELETE {wrong_path} (older)"
                    if not dry_run:
                        os.remove(wrong_path)
                        actions_taken += 1
                elif consistency["newer_file"] == wrong_path:
                    if not consistency["sizes_differ"]:
                        # Newer file in wrong location, same size - move it
                        action = f"REPLACE {correct_path} with {wrong_path}, then DELETE {wrong_path}"
                        if not dry_run:
                            shutil.move(wrong_path, correct_path)
                            actions_taken += 1
                    else:
                        action = f"MANUAL REVIEW NEEDED - {wrong_path} is newer but different size"
                else:
                    action = f"MANUAL REVIEW NEEDED - identical timestamps"
            
            if action:
                prefix = "[DRY RUN] " if dry_run else "[EXECUTING] "
                print(f"{prefix}{action}")
    
    print(f"\nActions {'planned' if dry_run else 'completed'}: {actions_taken if not dry_run else 'N/A'}")


def validate_script_imports() -> List[str]:
    """Validate that all scripts can properly import centralized paths."""
    scripts_to_check = [
        "sync_links_apply.py",
        "task_operations.py", 
        "find_duplicate_tasks.py",
        "build_sync_links.py",
        "collect_obsidian_tasks.py",
        "collect_reminders_tasks.py",
        "update_indices_and_links.py"
    ]
    
    issues = []
    
    for script in scripts_to_check:
        script_path = os.path.join(os.getcwd(), script)
        if not os.path.exists(script_path):
            issues.append(f"Script not found: {script}")
            continue
            
        try:
            # Try to import the script's module to see if it can access app_config
            with open(script_path, 'r') as f:
                content = f.read()
                
            if "from app_config import" in content or "import app_config" in content:
                # Script uses centralized config - good!
                continue
            elif "expanduser(" in content and "~/.config/" in content:
                issues.append(f"{script}: Still uses hardcoded paths - needs update")
        
        except Exception as e:
            issues.append(f"{script}: Error checking imports - {e}")
    
    return issues


def main():
    parser = argparse.ArgumentParser(description="Validate and clean up obs-tools path configurations")
    parser.add_argument("--cleanup", action="store_true", help="Actually perform cleanup operations")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without doing it")
    parser.add_argument("--check-imports", action="store_true", help="Check script imports for centralized paths")
    
    args = parser.parse_args()
    
    # Always show path configuration first
    cfg.print_paths_debug()
    
    # Validate paths can be created
    errors = cfg.validate_paths()
    if errors:
        print("Path validation errors:")
        for error in errors:
            print(f"  ❌ {error}")
        print()
    else:
        print("✓ All paths can be created successfully\n")
    
    # Find and analyze problematic files
    problems = find_problematic_files()
    print_analysis(problems)
    
    # Check script imports if requested
    if args.check_imports:
        print("=== Script Import Analysis ===\n")
        import_issues = validate_script_imports()
        if import_issues:
            for issue in import_issues:
                print(f"⚠ {issue}")
        else:
            print("✓ All scripts properly use centralized path configuration")
        print()
    
    # Perform cleanup if requested
    if args.cleanup or args.dry_run:
        cleanup_files(problems, dry_run=not args.cleanup)
    
    if not (args.cleanup or args.dry_run):
        print("Use --dry-run to see what cleanup actions would be taken")
        print("Use --cleanup to actually perform cleanup operations")


if __name__ == "__main__":
    main()