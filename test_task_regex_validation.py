#!/usr/bin/env python3
"""
Comprehensive validation script for Obsidian task identification accuracy.
Tests all regex patterns against real examples and edge cases.
"""

import re
import sys
import os
from pathlib import Path

# Add the project root to the path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# Import the actual regex patterns from the collector
from obs_tools.commands.collect_obsidian_tasks import (
    TASK_RE, HEADING_RE, BLOCK_ID_RE, 
    DUE_RE, SCHED_RE, START_RE, DONE_RE, 
    RECUR_RE, PRIORITY_RE, TAG_RE,
    parse_tasks_from_file, extract_tokens
)

def test_task_regex_comprehensive():
    """Test TASK_RE against various task formats"""
    print("=== TASK_RE Pattern Validation ===")
    print(f"Pattern: {TASK_RE.pattern}")
    
    # Test cases: (input_line, should_match, expected_status, expected_rest)
    test_cases = [
        # Standard formats
        ("- [ ] Basic task", True, " ", "Basic task"),
        ("- [x] Completed task", True, "x", "Completed task"),
        ("- [X] Completed task uppercase", True, "X", "Completed task uppercase"),
        
        # With indentation
        ("  - [ ] Indented task", True, " ", "Indented task"),
        ("    - [x] Double indented", True, "x", "Double indented"),
        ("\t- [ ] Tab indented", True, " ", "Tab indented"),
        
        # Using asterisk instead of dash
        ("* [ ] Asterisk task", True, " ", "Asterisk task"),
        ("* [x] Completed asterisk", True, "x", "Completed asterisk"),
        
        # With extra spaces
        ("- [  ] Extra space in brackets", False, None, None),  # Should fail - invalid checkbox
        ("-  [ ] Extra space after dash", False, None, None),  # Extra spaces after dash should be rejected
        ("- [ ]  Extra space before text", True, " ", "Extra space before text"),
        
        # Edge cases
        ("- [ ]", True, " ", ""),
        ("- [x]", True, "x", ""),
        ("- [ ] Task with 📅 2025-01-01", True, " ", "Task with 📅 2025-01-01"),
        ("- [ ] Task with ^block-id", True, " ", "Task with ^block-id"),
        
        # Should NOT match
        ("- [] Missing space in brackets", False, None, None),
        ("- [y] Invalid status", False, None, None),
        ("- [!] Alternative status", False, None, None),
        ("- [?] Question status", False, None, None),
        ("- [-] Cancelled status", False, None, None),
        ("- [*] Star status", False, None, None),
        ("Task without list marker [ ]", False, None, None),
        ("Not a task - just text", False, None, None),
        
        # Real examples from vault
        ("- [ ] Send out notes and actions out of the digital call on next steps #digital #FutureCasting ➕ 2025-08-13 ^t-5e877b4446f0", True, " ", "Send out notes and actions out of the digital call on next steps #digital #FutureCasting ➕ 2025-08-13 ^t-5e877b4446f0"),
        ("- [x] Incremental collectors with 16x performance improvement ^t-c276a9ef2375", True, "x", "Incremental collectors with 16x performance improvement ^t-c276a9ef2375"),
    ]
    
    failed = 0
    for i, (line, should_match, expected_status, expected_rest) in enumerate(test_cases):
        match = TASK_RE.match(line)
        
        if should_match and not match:
            print(f"❌ Test {i+1}: Expected match but got none")
            print(f"   Input: {repr(line)}")
            failed += 1
        elif not should_match and match:
            print(f"❌ Test {i+1}: Expected no match but got: {match.groups()}")
            print(f"   Input: {repr(line)}")
            failed += 1
        elif should_match and match:
            actual_status = match.group("status")
            actual_rest = match.group("rest")
            if actual_status != expected_status or actual_rest != expected_rest:
                print(f"❌ Test {i+1}: Match but wrong groups")
                print(f"   Input: {repr(line)}")
                print(f"   Expected status: {repr(expected_status)}, rest: {repr(expected_rest)}")
                print(f"   Actual status: {repr(actual_status)}, rest: {repr(actual_rest)}")
                failed += 1
            else:
                print(f"✅ Test {i+1}: Correct match")
        else:
            print(f"✅ Test {i+1}: Correct non-match")
    
    print(f"\nTASK_RE Results: {len(test_cases) - failed}/{len(test_cases)} passed")
    return failed == 0

def test_block_id_regex():
    """Test BLOCK_ID_RE pattern"""
    print("\n=== BLOCK_ID_RE Pattern Validation ===")
    print(f"Pattern: {BLOCK_ID_RE.pattern}")
    
    test_cases = [
        # Valid block IDs
        ("Some text ^block-id", True, "block-id"),
        ("Task ^t-5e877b4446f0", True, "t-5e877b4446f0"),
        ("^simple", True, "simple"),
        ("Text ^ABC123", True, "ABC123"),
        ("Text ^with-dashes", True, "with-dashes"),
        ("Text ^a1b2c3", True, "a1b2c3"),
        
        # Edge cases
        ("^trailing-space ", True, "trailing-space"),
        ("Multiple ^first ^second", True, "second"),  # Should match the last one
        
        # Should NOT match
        ("No block id here", False, None),
        ("Text ^with_underscore", False, None),  # Underscores not allowed
        ("Text ^with.dot", False, None),  # Dots not allowed
        ("Text ^", False, None),  # Empty block ID
        ("Text ^ space-after-caret", False, None),
    ]
    
    failed = 0
    for i, (text, should_match, expected_bid) in enumerate(test_cases):
        match = BLOCK_ID_RE.search(text)
        
        if should_match and not match:
            print(f"❌ Test {i+1}: Expected match but got none")
            print(f"   Input: {repr(text)}")
            failed += 1
        elif not should_match and match:
            print(f"❌ Test {i+1}: Expected no match but got: {match.group('bid')}")
            print(f"   Input: {repr(text)}")
            failed += 1
        elif should_match and match:
            actual_bid = match.group("bid")
            if actual_bid != expected_bid:
                print(f"❌ Test {i+1}: Match but wrong block ID")
                print(f"   Input: {repr(text)}")
                print(f"   Expected: {repr(expected_bid)}, Actual: {repr(actual_bid)}")
                failed += 1
            else:
                print(f"✅ Test {i+1}: Correct match")
        else:
            print(f"✅ Test {i+1}: Correct non-match")
    
    print(f"\nBLOCK_ID_RE Results: {len(test_cases) - failed}/{len(test_cases)} passed")
    return failed == 0

def test_date_patterns():
    """Test date extraction patterns"""
    print("\n=== Date Pattern Validation ===")
    
    test_cases = [
        # Due dates
        ("Task 📅 2025-01-01", "due", "2025-01-01"),
        ("Task (due: 2025-12-31)", "due", "2025-12-31"),
        
        # Scheduled dates  
        ("Task ⏳ 2025-06-15", "scheduled", "2025-06-15"),
        ("Task (scheduled: 2025-06-15)", "scheduled", "2025-06-15"),
        
        # Start dates
        ("Task 🛫 2025-03-01", "start", "2025-03-01"),
        ("Task (start: 2025-03-01)", "start", "2025-03-01"),
        
        # Done dates
        ("Task ✅ 2025-02-28", "done", "2025-02-28"),
        ("Task (done: 2025-02-28)", "done", "2025-02-28"),
    ]
    
    patterns = {
        "due": DUE_RE,
        "scheduled": SCHED_RE, 
        "start": START_RE,
        "done": DONE_RE
    }
    
    failed = 0
    for i, (text, date_type, expected_date) in enumerate(test_cases):
        pattern = patterns[date_type]
        match = pattern.search(text)
        
        if not match:
            print(f"❌ Test {i+1}: Expected {date_type} match but got none")
            print(f"   Input: {repr(text)}")
            failed += 1
        else:
            actual_date = match.group(date_type)
            if actual_date != expected_date:
                print(f"❌ Test {i+1}: Wrong {date_type} date")
                print(f"   Input: {repr(text)}")
                print(f"   Expected: {expected_date}, Actual: {actual_date}")
                failed += 1
            else:
                print(f"✅ Test {i+1}: Correct {date_type} date")
    
    print(f"\nDate Pattern Results: {len(test_cases) - failed}/{len(test_cases)} passed")
    return failed == 0

def test_priority_patterns():
    """Test priority symbol extraction"""
    print("\n=== Priority Pattern Validation ===")
    
    test_cases = [
        ("Task ⏫ high priority", "high"),
        ("Task 🔼 medium priority", "medium"), 
        ("Task 🔽 low priority", "low"),
        ("Task 🔺 also low priority", "low"),
    ]
    
    failed = 0
    for i, (text, expected_priority) in enumerate(test_cases):
        match = PRIORITY_RE.search(text)
        
        if not match:
            print(f"❌ Test {i+1}: Expected priority match but got none")
            print(f"   Input: {repr(text)}")
            failed += 1
        else:
            symbol = match.group("prio")
            priority_map = {"⏫": "high", "🔼": "medium", "🔽": "low", "🔺": "low"}
            actual_priority = priority_map.get(symbol, symbol)
            
            if actual_priority != expected_priority:
                print(f"❌ Test {i+1}: Wrong priority")
                print(f"   Input: {repr(text)}")
                print(f"   Expected: {expected_priority}, Actual: {actual_priority}")
                failed += 1
            else:
                print(f"✅ Test {i+1}: Correct priority")
    
    print(f"\nPriority Pattern Results: {len(test_cases) - failed}/{len(test_cases)} passed")
    return failed == 0

def test_tag_extraction():
    """Test hashtag extraction"""
    print("\n=== Tag Extraction Validation ===")
    
    test_cases = [
        ("Task #work #important", ["#work", "#important"]),
        ("Task #project/subproject", ["#project/subproject"]),
        ("Task #test-tag", ["#test-tag"]),
        ("Task #123numbers", ["#123numbers"]),
        ("Task #under_score", ["#under_score"]),
        ("No tags here", []),
        ("Task #multiple #tags #everywhere", ["#multiple", "#tags", "#everywhere"]),
    ]
    
    failed = 0
    for i, (text, expected_tags) in enumerate(test_cases):
        matches = TAG_RE.finditer(text)
        actual_tags = [m.group("tag") for m in matches]
        
        if set(actual_tags) != set(expected_tags):
            print(f"❌ Test {i+1}: Wrong tags")
            print(f"   Input: {repr(text)}")
            print(f"   Expected: {expected_tags}, Actual: {actual_tags}")
            failed += 1
        else:
            print(f"✅ Test {i+1}: Correct tags")
    
    print(f"\nTag Extraction Results: {len(test_cases) - failed}/{len(test_cases)} passed")
    return failed == 0

def test_token_extraction():
    """Test the complete token extraction function"""
    print("\n=== Token Extraction Integration Test ===")
    
    test_cases = [
        # Complex task with everything
        (
            "Important task #work #urgent 📅 2025-01-01 ⏳ 2024-12-30 🛫 2024-12-29 🔁 daily ⏫",
            {
                "tags": ["#urgent", "#work"],
                "due": "2025-01-01",
                "scheduled": "2024-12-30", 
                "start": "2024-12-29",
                "recurrence": "daily",
                "priority": "high",
                "done": None
            },
            "Important task"
        ),
        
        # Real example from vault
        (
            "Send out notes and actions out of the digital call on next steps #digital #FutureCasting ➕ 2025-08-13",
            {
                "tags": ["#FutureCasting", "#digital"],
                "due": None,
                "scheduled": None,
                "start": None,
                "recurrence": None,
                "priority": None,
                "done": None
            },
            "Send out notes and actions out of the digital call on next steps ➕ 2025-08-13"
        ),
    ]
    
    failed = 0
    for i, (text, expected_meta, expected_desc) in enumerate(test_cases):
        meta, desc = extract_tokens(text)
        
        # Check each expected field
        for key, expected_value in expected_meta.items():
            actual_value = meta.get(key)
            if key == "tags":
                # Tags need set comparison since order doesn't matter
                if set(actual_value or []) != set(expected_value or []):
                    print(f"❌ Test {i+1}: Wrong {key}")
                    print(f"   Expected: {expected_value}, Actual: {actual_value}")
                    failed += 1
                    break
            else:
                if actual_value != expected_value:
                    print(f"❌ Test {i+1}: Wrong {key}")
                    print(f"   Expected: {expected_value}, Actual: {actual_value}")
                    failed += 1
                    break
        else:
            # Check description
            if desc != expected_desc:
                print(f"❌ Test {i+1}: Wrong description")
                print(f"   Expected: {repr(expected_desc)}, Actual: {repr(desc)}")
                failed += 1
            else:
                print(f"✅ Test {i+1}: Correct token extraction")
    
    print(f"\nToken Extraction Results: {len(test_cases) - failed}/{len(test_cases)} passed")
    return failed == 0

def test_edge_cases():
    """Test edge cases that might break the parser"""
    print("\n=== Edge Case Validation ===")
    
    edge_cases = [
        # Tasks in code blocks (should be ignored by file parser context)
        "```markdown\n- [ ] This is in a code block\n```",
        
        # Tasks with unicode characters
        "- [ ] Task with émojis 🎉 and ünïcödé",
        
        # Very long tasks
        "- [ ] " + "Very long task " * 50,
        
        # Tasks with special characters
        "- [ ] Task with \"quotes\" and 'apostrophes' and <brackets>",
        
        # Malformed but common variations
        "- [ ]Task without space",
        "- [x ]Extra space in status",
        "- [ ] Task\twith\ttabs",
        
        # Empty and whitespace
        "- [ ] \t  \n",
        "- [x]",
    ]
    
    failed = 0
    for i, case in enumerate(edge_cases):
        try:
            match = TASK_RE.match(case)
            if match:
                meta, desc = extract_tokens(match.group("rest"))
                print(f"✅ Edge case {i+1}: Parsed successfully")
            else:
                print(f"ℹ️  Edge case {i+1}: No match (as expected for some cases)")
        except Exception as e:
            print(f"❌ Edge case {i+1}: Failed with exception: {e}")
            print(f"   Input: {repr(case)}")
            failed += 1
    
    print(f"\nEdge Case Results: {len(edge_cases) - failed}/{len(edge_cases)} handled")
    return failed == 0

def find_missed_tasks_sample():
    """Find potential tasks that might be missed by current regex"""
    print("\n=== Scanning for Potential Missed Tasks ===")
    
    vault_path = "/Users/yannickbowe/Library/Mobile Documents/iCloud~md~obsidian/Documents/Work"
    
    # Look for lines that might be tasks but don't match our regex
    potential_patterns = [
        r"^\s*[-*]\s*\[.\]",  # Any checkbox variant
        r"^\s*\d+\.\s*\[.\]",  # Numbered list with checkbox
        r"^\s*[-*]\s+[☐☑✓✗]",  # Unicode checkboxes
    ]
    
    missed_examples = []
    
    # Sample a few files to check
    sample_files = [
        "Digital Next Steps.md",
        "obssync/IMPLEMENTATION_SUMMARY.md",
    ]
    
    for filename in sample_files:
        filepath = os.path.join(vault_path, filename)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                for line_num, line in enumerate(lines, 1):
                    line = line.rstrip()
                    if not line:
                        continue
                        
                    # Check if any potential pattern matches but TASK_RE doesn't
                    for pattern in potential_patterns:
                        if re.match(pattern, line) and not TASK_RE.match(line):
                            missed_examples.append((filename, line_num, line))
                            break
                            
            except Exception as e:
                print(f"Warning: Could not read {filename}: {e}")
    
    if missed_examples:
        print("Found potential missed tasks:")
        for filename, line_num, line in missed_examples[:10]:  # Show first 10
            print(f"  {filename}:{line_num}: {repr(line)}")
    else:
        print("No obvious missed tasks found in sample")
    
    return len(missed_examples) == 0

def run_all_tests():
    """Run all validation tests"""
    print("🔍 Running Comprehensive Obsidian Task Regex Validation\n")
    
    tests = [
        ("Task Regex", test_task_regex_comprehensive),
        ("Block ID Regex", test_block_id_regex),
        ("Date Patterns", test_date_patterns),
        ("Priority Patterns", test_priority_patterns),
        ("Tag Extraction", test_tag_extraction),
        ("Token Extraction", test_token_extraction),
        ("Edge Cases", test_edge_cases),
        ("Missed Tasks Scan", find_missed_tasks_sample),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"❌ {test_name}: Failed with exception: {e}")
            results.append((test_name, False))
    
    print("\n" + "="*50)
    print("VALIDATION SUMMARY")
    print("="*50)
    
    passed = 0
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {test_name}")
        if success:
            passed += 1
    
    print(f"\nOverall: {passed}/{len(results)} test suites passed")
    
    if passed == len(results):
        print("🎉 All validation tests passed! Task identification appears accurate.")
    else:
        print("⚠️  Some tests failed. Review regex patterns and parsing logic.")
    
    return passed == len(results)

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)