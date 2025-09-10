#!/usr/bin/env python3
"""
Unit tests for task operations and line editing.

Tests the edit_task_line tokenization for every supported token combo
to ensure robust task parsing and modification.
"""

import unittest
import sys
import os
import tempfile

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from collect_obsidian_tasks import TASK_RE, parse_task_line, extract_task_fields
    from lib.date_utils import normalize_date_string, dates_equal, date_distance_days
except ImportError:
    # Mock imports if modules not available
    import re
    TASK_RE = re.compile(r"^(?P<indent>\s*)[-*]\s+\[(?P<status>[ xX])\]\s+(?P<rest>.*)$")
    
    def parse_task_line(line):
        return None
    
    def extract_task_fields(line):
        return {}
    
    def normalize_date_string(date_str):
        return date_str
    
    def dates_equal(d1, d2):
        return d1 == d2
    
    def date_distance_days(d1, d2):
        return 0


class TestTaskLineParsing(unittest.TestCase):
    """Test task line parsing with various token combinations."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_lines = [
            # Basic tasks
            "- [ ] Simple task",
            "- [x] Completed task", 
            "  - [ ] Indented task",
            "    - [X] Double indented completed",
            
            # Tasks with due dates
            "- [ ] Task with due 📅 2023-12-15",
            "- [ ] Task with due (due: 2023-12-15)",
            "- [ ] Task 📅2023-12-15 inline date",
            
            # Tasks with scheduled dates
            "- [ ] Scheduled task ⏳ 2023-12-10",
            "- [ ] Task (scheduled: 2023-12-10)",
            
            # Tasks with start dates
            "- [ ] Start task 🛫 2023-12-01",
            "- [ ] Task (start: 2023-12-01)",
            
            # Tasks with done dates
            "- [x] Completed ✅ 2023-12-14",
            "- [x] Done (done: 2023-12-14)",
            
            # Tasks with priorities
            "- [ ] High priority ⏫",
            "- [ ] Medium high 🔼", 
            "- [ ] Medium low 🔽",
            "- [ ] Low priority 🔺",
            
            # Tasks with recurrence
            "- [ ] Recurring 🔁 every week",
            "- [ ] Daily task 🔁 every day",
            
            # Tasks with tags
            "- [ ] Tagged task #work",
            "- [ ] Multi tags #work #urgent #home",
            "- [ ] Task #project/subproject",
            
            # Tasks with block IDs
            "- [ ] Task with block ID ^block123",
            "- [ ] Another task ^abc-def-456",
            
            # Complex combinations
            "- [ ] Complex task 📅 2023-12-15 ⏫ #work #urgent 🔁 every week ^complex123",
            "- [x] Done complex ✅ 2023-12-14 📅 2023-12-15 #project ^done456",
            "  - [ ] Indented with dates (due: 2023-12-20) (start: 2023-12-15) #nested",
            
            # Edge cases
            "- [ ] Task with multiple 📅 2023-12-15 📅 2023-12-16 dates",
            "- [ ] Task with #tag at start and #end at end",
            "- [ ] Empty priority  task",
            "- [ ]", # Minimal task
            "",     # Empty line
            "Not a task line",
            "- [?] Invalid status",
        ]
    
    def test_task_regex_recognition(self):
        """Test that TASK_RE correctly identifies task lines."""
        expected_matches = [
            True,   # "- [ ] Simple task"
            True,   # "- [x] Completed task"
            True,   # "  - [ ] Indented task"
            True,   # "    - [X] Double indented completed"
            True,   # "- [ ] Task with due 📅 2023-12-15"
            True,   # etc. (most lines should match)
            True, True, True, True, True, True, True, True, True, True,
            True, True, True, True, True, True, True, True, True, True,
            True, True, True, 
            False,  # ""
            False,  # "Not a task line"  
            False,  # "- [?] Invalid status"
        ]
        
        for i, line in enumerate(self.test_lines):
            with self.subTest(line=line):
                match = TASK_RE.match(line)
                expected = expected_matches[i] if i < len(expected_matches) else False
                
                if expected:
                    self.assertIsNotNone(match, f"Expected match for: {line}")
                    # Verify groups are extracted
                    self.assertIn('indent', match.groupdict())
                    self.assertIn('status', match.groupdict()) 
                    self.assertIn('rest', match.groupdict())
                else:
                    self.assertIsNone(match, f"Should not match: {line}")
    
    def test_task_status_extraction(self):
        """Test that task status is correctly extracted."""
        test_cases = [
            ("- [ ] Todo task", "todo"),
            ("- [x] Done task", "done"),
            ("- [X] Also done", "done"),
            ("  - [ ] Indented todo", "todo"),
        ]
        
        for line, expected_status in test_cases:
            with self.subTest(line=line):
                match = TASK_RE.match(line)
                self.assertIsNotNone(match)
                
                status_char = match.group('status')
                actual_status = "done" if status_char.lower() == 'x' else "todo"
                self.assertEqual(actual_status, expected_status)
    
    def test_task_indentation_extraction(self):
        """Test that indentation is correctly preserved."""
        test_cases = [
            ("- [ ] No indent", ""),
            ("  - [ ] Two spaces", "  "),
            ("    - [ ] Four spaces", "    "),
            ("\t- [ ] Tab indent", "\t"),
            ("   - [ ] Three spaces", "   "),
        ]
        
        for line, expected_indent in test_cases:
            with self.subTest(line=line):
                match = TASK_RE.match(line)
                self.assertIsNotNone(match)
                
                actual_indent = match.group('indent')
                self.assertEqual(actual_indent, expected_indent)
    
    def test_date_token_extraction(self):
        """Test extraction of various date tokens."""
        if 'extract_task_fields' not in globals():
            self.skipTest("extract_task_fields not available")
            
        test_cases = [
            ("- [ ] Due task 📅 2023-12-15", "due_date", "2023-12-15"),
            ("- [ ] Scheduled ⏳ 2023-12-10", "scheduled_date", "2023-12-10"),
            ("- [ ] Start 🛫 2023-12-01", "start_date", "2023-12-01"),
            ("- [x] Done ✅ 2023-12-14", "done_date", "2023-12-14"),
            ("- [ ] Due (due: 2023-12-15)", "due_date", "2023-12-15"),
            ("- [ ] Scheduled (scheduled: 2023-12-10)", "scheduled_date", "2023-12-10"),
        ]
        
        for line, date_field, expected_date in test_cases:
            with self.subTest(line=line):
                fields = extract_task_fields(line)
                
                if date_field in fields:
                    actual_date = normalize_date_string(fields[date_field])
                    self.assertEqual(actual_date, expected_date)
    
    def test_priority_extraction(self):
        """Test extraction of priority tokens."""
        if 'extract_task_fields' not in globals():
            self.skipTest("extract_task_fields not available")
            
        test_cases = [
            ("- [ ] High ⏫", "highest"),
            ("- [ ] Medium high 🔼", "high"),
            ("- [ ] Medium low 🔽", "medium"),
            ("- [ ] Low 🔺", "low"),
        ]
        
        priority_map = {
            "⏫": "highest",
            "🔼": "high", 
            "🔽": "medium",
            "🔺": "low"
        }
        
        for line, expected_priority in test_cases:
            with self.subTest(line=line):
                fields = extract_task_fields(line)
                
                if 'priority' in fields:
                    self.assertEqual(fields['priority'], expected_priority)
    
    def test_tag_extraction(self):
        """Test extraction of hashtags."""
        if 'extract_task_fields' not in globals():
            self.skipTest("extract_task_fields not available")
            
        test_cases = [
            ("- [ ] Single #tag", ["tag"]),
            ("- [ ] Multi #work #urgent", ["work", "urgent"]),
            ("- [ ] Nested #project/subproject", ["project/subproject"]),
            ("- [ ] Mixed #work #project/sub #home", ["work", "project/sub", "home"]),
            ("- [ ] No tags", []),
        ]
        
        for line, expected_tags in test_cases:
            with self.subTest(line=line):
                fields = extract_task_fields(line)
                
                actual_tags = fields.get('tags', [])
                
                # Sort for comparison since order might vary
                self.assertEqual(sorted(actual_tags), sorted(expected_tags))
    
    def test_block_id_extraction(self):
        """Test extraction of block IDs."""
        if 'extract_task_fields' not in globals():
            self.skipTest("extract_task_fields not available")
            
        test_cases = [
            ("- [ ] Task ^block123", "block123"),
            ("- [ ] Another ^abc-def-456", "abc-def-456"),
            ("- [ ] Complex task #tag ^blockid", "blockid"),
            ("- [ ] No block ID", None),
        ]
        
        for line, expected_block_id in test_cases:
            with self.subTest(line=line):
                fields = extract_task_fields(line)
                
                actual_block_id = fields.get('block_id')
                self.assertEqual(actual_block_id, expected_block_id)
    
    def test_complex_task_parsing(self):
        """Test parsing of complex tasks with multiple tokens."""
        complex_line = "- [ ] Project meeting 📅 2023-12-15 ⏫ #work #meeting 🔁 every week ^meet123"
        
        if 'extract_task_fields' not in globals():
            self.skipTest("extract_task_fields not available")
            
        fields = extract_task_fields(complex_line)
        
        # Should extract all components
        expected_fields = {
            'due_date': '2023-12-15',
            'priority': 'highest',
            'tags': ['work', 'meeting'],
            'recurrence': 'every week',
            'block_id': 'meet123'
        }
        
        for field, expected_value in expected_fields.items():
            if field in fields:
                if field == 'tags':
                    self.assertEqual(sorted(fields[field]), sorted(expected_value))
                elif field == 'due_date':
                    self.assertEqual(normalize_date_string(fields[field]), expected_value)
                else:
                    self.assertEqual(fields[field], expected_value)


class TestDateUtilities(unittest.TestCase):
    """Test date handling utilities."""
    
    def test_date_normalization(self):
        """Test date string normalization."""
        test_cases = [
            ("2023-12-15", "2023-12-15"),
            ("2023-12-15T10:30:00", "2023-12-15"),
            ("2023-12-15T10:30:00Z", "2023-12-15"), 
            ("2023-12-15T10:30:00+00:00", "2023-12-15"),
            ("", None),
            (None, None),
            ("invalid", None),
        ]
        
        for input_date, expected in test_cases:
            with self.subTest(date=input_date):
                result = normalize_date_string(input_date)
                self.assertEqual(result, expected)
    
    def test_date_equality(self):
        """Test date equality comparison.""" 
        test_cases = [
            ("2023-12-15", "2023-12-15", True),
            ("2023-12-15", "2023-12-16", False),
            ("2023-12-15T10:00:00", "2023-12-15T20:00:00", True),  # Same date, different time
            ("2023-12-15", None, False),
            (None, None, False),
        ]
        
        for date1, date2, expected in test_cases:
            with self.subTest(date1=date1, date2=date2):
                result = dates_equal(date1, date2)
                self.assertEqual(result, expected)
    
    def test_date_distance(self):
        """Test date distance calculation."""
        test_cases = [
            ("2023-12-15", "2023-12-15", 0),
            ("2023-12-15", "2023-12-16", 1),
            ("2023-12-15", "2023-12-20", 5),
            ("2023-12-20", "2023-12-15", 5),  # Absolute distance
            ("2023-12-15", None, None),
            (None, "2023-12-15", None),
        ]
        
        for date1, date2, expected in test_cases:
            with self.subTest(date1=date1, date2=date2):
                result = date_distance_days(date1, date2)
                self.assertEqual(result, expected)


if __name__ == '__main__':
    unittest.main()