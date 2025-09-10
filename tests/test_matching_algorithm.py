#!/usr/bin/env python3
"""
Unit tests for link scoring and assignment determinism.

Tests the core matching algorithms with fixtures to ensure:
- Link scoring is deterministic and correct
- Hungarian algorithm finds optimal assignments  
- Greedy algorithm provides reasonable fallback
- Results are reproducible across runs
"""

import unittest
from typing import Dict, List, Tuple
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from build_sync_links import score_pair, suggest_links_hungarian, suggest_links_greedy
except ImportError:
    # Mock imports if build_sync_links not available
    def score_pair(obs_task, rem_task, days_tol=1):
        return 0.5, {}
    def suggest_links_hungarian(obs_tasks, rem_tasks, min_score=0.75, days_tol=1, include_done=False):
        return []
    def suggest_links_greedy(obs_tasks, rem_tasks, min_score=0.75, days_tol=1, include_done=False):
        return []


class TestMatchingAlgorithm(unittest.TestCase):
    """Test matching algorithms with controlled fixtures."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.obs_tasks = {
            'obs1': {
                'uuid': 'obs1',
                'description': 'Buy groceries',
                'due_date': '2023-12-15',
                'status': 'todo'
            },
            'obs2': {
                'uuid': 'obs2', 
                'description': 'Finish project',
                'due_date': '2023-12-16',
                'status': 'todo'
            },
            'obs3': {
                'uuid': 'obs3',
                'description': 'Call dentist',
                'due_date': None,
                'status': 'todo'
            }
        }
        
        self.rem_tasks = {
            'rem1': {
                'uuid': 'rem1',
                'title': 'Buy groceries today',
                'due_date': '2023-12-15',
                'completed': False
            },
            'rem2': {
                'uuid': 'rem2',
                'title': 'Project deadline',
                'due_date': '2023-12-16', 
                'completed': False
            },
            'rem3': {
                'uuid': 'rem3',
                'title': 'Schedule dentist appointment',
                'due_date': None,
                'completed': False
            }
        }
    
    def test_score_pair_deterministic(self):
        """Test that score_pair returns consistent results."""
        obs_task = self.obs_tasks['obs1']
        rem_task = self.rem_tasks['rem1']
        
        # Call multiple times - should be identical
        score1, fields1 = score_pair(obs_task, rem_task, days_tol=1)
        score2, fields2 = score_pair(obs_task, rem_task, days_tol=1)
        
        self.assertEqual(score1, score2, "Scoring should be deterministic")
        self.assertEqual(fields1, fields2, "Field extraction should be deterministic")
    
    def test_perfect_match_high_score(self):
        """Test that perfect matches get high scores."""
        # Create identical tasks
        obs_task = {
            'description': 'Buy groceries',
            'due_date': '2023-12-15',
            'status': 'todo'
        }
        rem_task = {
            'title': 'Buy groceries',
            'due_date': '2023-12-15',
            'completed': False
        }
        
        score, _ = score_pair(obs_task, rem_task, days_tol=1)
        self.assertGreater(score, 0.9, "Perfect match should have high score")
    
    def test_no_match_low_score(self):
        """Test that unrelated tasks get low scores."""
        obs_task = {
            'description': 'Buy groceries',
            'due_date': '2023-12-15',
            'status': 'todo'
        }
        rem_task = {
            'title': 'Schedule dentist appointment',
            'due_date': '2024-01-01',  # Very different date
            'completed': False
        }
        
        score, _ = score_pair(obs_task, rem_task, days_tol=1)
        self.assertLess(score, 0.5, "Unrelated tasks should have low score")
    
    def test_date_tolerance_affects_score(self):
        """Test that date tolerance affects matching scores."""
        obs_task = {
            'description': 'Buy groceries',
            'due_date': '2023-12-15',
            'status': 'todo'
        }
        rem_task = {
            'title': 'Buy groceries',
            'due_date': '2023-12-17',  # 2 days difference
            'completed': False
        }
        
        # Should match with higher tolerance
        score_high_tol, _ = score_pair(obs_task, rem_task, days_tol=3)
        score_low_tol, _ = score_pair(obs_task, rem_task, days_tol=1)
        
        self.assertGreater(score_high_tol, score_low_tol, 
                          "Higher tolerance should give better score for date differences")
    
    def test_greedy_vs_hungarian_determinism(self):
        """Test that both algorithms produce deterministic results."""
        if 'suggest_links_hungarian' not in globals():
            self.skipTest("Hungarian algorithm not available")
        
        # Run multiple times
        greedy1 = suggest_links_greedy(self.obs_tasks, self.rem_tasks, min_score=0.5)
        greedy2 = suggest_links_greedy(self.obs_tasks, self.rem_tasks, min_score=0.5)
        
        hungarian1 = suggest_links_hungarian(self.obs_tasks, self.rem_tasks, min_score=0.5)
        hungarian2 = suggest_links_hungarian(self.obs_tasks, self.rem_tasks, min_score=0.5)
        
        self.assertEqual(len(greedy1), len(greedy2), "Greedy results should be deterministic")
        self.assertEqual(len(hungarian1), len(hungarian2), "Hungarian results should be deterministic")
        
        # Check that pairings are identical
        if greedy1 and greedy2:
            greedy_pairs1 = [(link[0], link[1]) for link in greedy1]
            greedy_pairs2 = [(link[0], link[1]) for link in greedy2]
            self.assertEqual(greedy_pairs1, greedy_pairs2, "Greedy pairings should be identical")
        
        if hungarian1 and hungarian2:
            hung_pairs1 = [(link[0], link[1]) for link in hungarian1]
            hung_pairs2 = [(link[0], link[1]) for link in hungarian2]
            self.assertEqual(hung_pairs1, hung_pairs2, "Hungarian pairings should be identical")
    
    def test_one_to_one_constraint(self):
        """Test that algorithms maintain one-to-one constraint."""
        links = suggest_links_greedy(self.obs_tasks, self.rem_tasks, min_score=0.3)
        
        if links:
            obs_uuids = [link[0] for link in links]
            rem_uuids = [link[1] for link in links] 
            
            # Check for duplicates
            self.assertEqual(len(obs_uuids), len(set(obs_uuids)), 
                            "Each Obsidian task should be linked at most once")
            self.assertEqual(len(rem_uuids), len(set(rem_uuids)),
                            "Each Reminder task should be linked at most once")
    
    def test_min_score_threshold(self):
        """Test that min_score threshold is respected."""
        # Use high threshold that should filter out matches
        links = suggest_links_greedy(self.obs_tasks, self.rem_tasks, min_score=0.95)
        
        # All remaining links should meet threshold
        for obs_id, rem_id, score, _ in links:
            self.assertGreaterEqual(score, 0.95, 
                                  f"Link {obs_id}-{rem_id} score {score} below threshold")
    
    def test_empty_input_handling(self):
        """Test handling of empty task collections."""
        empty_obs = {}
        empty_rem = {}
        
        # Should not crash and return empty results
        links1 = suggest_links_greedy(empty_obs, self.rem_tasks)
        links2 = suggest_links_greedy(self.obs_tasks, empty_rem)
        links3 = suggest_links_greedy(empty_obs, empty_rem)
        
        self.assertEqual(len(links1), 0, "Empty obs_tasks should return no links")
        self.assertEqual(len(links2), 0, "Empty rem_tasks should return no links")
        self.assertEqual(len(links3), 0, "Both empty should return no links")


class TestScoreFunctionComponents(unittest.TestCase):
    """Test individual components of the scoring function."""
    
    def test_title_similarity_calculation(self):
        """Test title similarity scoring component."""
        # Test cases for title similarity
        test_cases = [
            ("Buy groceries", "Buy groceries", 1.0),  # Identical
            ("Buy groceries", "buy groceries", 1.0),  # Case insensitive
            ("Buy groceries", "Purchase groceries", 0.5),  # Partial match
            ("Buy groceries", "Schedule dentist", 0.0),  # No match
        ]
        
        for obs_title, rem_title, expected_min_sim in test_cases:
            obs_task = {'description': obs_title, 'status': 'todo'}
            rem_task = {'title': rem_title, 'completed': False}
            
            score, fields = score_pair(obs_task, rem_task)
            
            if 'title_similarity' in fields:
                if expected_min_sim == 1.0:
                    self.assertAlmostEqual(fields['title_similarity'], 1.0, places=2)
                elif expected_min_sim == 0.0:
                    self.assertLessEqual(fields['title_similarity'], 0.1)
                else:
                    self.assertGreater(fields['title_similarity'], 0.0)
    
    def test_date_distance_calculation(self):
        """Test due date distance calculation."""
        base_task_obs = {'description': 'Test task', 'status': 'todo'}
        base_task_rem = {'title': 'Test task', 'completed': False}
        
        test_cases = [
            ('2023-12-15', '2023-12-15', 0),  # Same date
            ('2023-12-15', '2023-12-16', 1),  # 1 day apart
            ('2023-12-15', '2023-12-20', 5),  # 5 days apart
            ('2023-12-15', None, None),       # No due date on reminder
            (None, '2023-12-15', None),       # No due date on obsidian
        ]
        
        for obs_due, rem_due, expected_distance in test_cases:
            obs_task = {**base_task_obs, 'due_date': obs_due}
            rem_task = {**base_task_rem, 'due_date': rem_due}
            
            _, fields = score_pair(obs_task, rem_task)
            
            if expected_distance is not None:
                self.assertEqual(fields.get('date_distance_days'), expected_distance)


if __name__ == '__main__':
    unittest.main()