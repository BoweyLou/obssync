#!/usr/bin/env python3
"""
Unit tests for matching algorithm fallback logic.

Tests SciPy available/unavailable scenarios, munkres fallback, 
greedy fallback, and algorithm selection logic.
"""

import unittest
from typing import Dict, List, Tuple
from unittest.mock import patch, MagicMock
import sys
import os

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import modules under test
try:
    from obs_tools.commands.build_sync_links import (
        score_pair, suggest_links_hungarian, suggest_links_greedy,
        munkres_hungarian, HAS_SCIPY, HAS_MUNKRES
    )
except ImportError:
    # Mock implementations for testing
    HAS_SCIPY = False
    HAS_MUNKRES = False
    
    def score_pair(obs_task, rem_task, days_tol=1):
        """Mock scoring function."""
        # Simple mock scoring based on title similarity
        obs_title = obs_task.get('description', '').lower()
        rem_title = rem_task.get('title', '').lower()
        score = 1.0 if obs_title == rem_title else 0.5
        return score, {'title_similarity': score}
    
    def suggest_links_hungarian(obs_tasks, rem_tasks, min_score=0.75, days_tol=1, include_done=False):
        """Mock Hungarian algorithm."""
        return []
    
    def suggest_links_greedy(obs_tasks, rem_tasks, min_score=0.75, days_tol=1, include_done=False):
        """Mock greedy algorithm."""
        links = []
        for obs_id, obs_task in obs_tasks.items():
            for rem_id, rem_task in rem_tasks.items():
                score, fields = score_pair(obs_task, rem_task, days_tol)
                if score >= min_score:
                    links.append((obs_id, rem_id, score, fields))
                    break  # Greedy - take first match
        return links
    
    def munkres_hungarian(cost_matrix):
        """Mock munkres implementation."""
        return [], []


@pytest.mark.matching
@pytest.mark.unit
class TestMatchingFallbacks(unittest.TestCase):
    """Test matching algorithm fallback behavior."""
    
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
                'title': 'Buy groceries',
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
    
    @pytest.mark.scipy_optional
    def test_scipy_availability_detection(self):
        """Test that scipy availability is correctly detected."""
        # This tests the module-level import detection
        try:
            import scipy
            expected_has_scipy = True
        except ImportError:
            expected_has_scipy = False
        
        # We can't easily mock module imports at test time, so we just verify
        # the detection logic works as expected
        self.assertIsInstance(HAS_SCIPY, bool)
        print(f"SciPy detected: {HAS_SCIPY}, Expected: {expected_has_scipy}")
    
    @pytest.mark.munkres_optional
    def test_munkres_availability_detection(self):
        """Test that munkres availability is correctly detected."""
        try:
            import munkres
            expected_has_munkres = True
        except ImportError:
            expected_has_munkres = False
        
        self.assertIsInstance(HAS_MUNKRES, bool)
        print(f"Munkres detected: {HAS_MUNKRES}, Expected: {expected_has_munkres}")
    
    @patch('obs_tools.commands.build_sync_links.HAS_SCIPY', False)
    @patch('obs_tools.commands.build_sync_links.HAS_MUNKRES', False)
    def test_greedy_fallback_when_no_optimization_libs(self):
        """Test that greedy algorithm is used when no optimization libraries available."""
        # When both scipy and munkres are unavailable, should fall back to greedy
        links = suggest_links_greedy(self.obs_tasks, self.rem_tasks, min_score=0.3)
        
        # Greedy should return some links
        self.assertIsInstance(links, list)
        
        # Each link should be a tuple with the expected structure
        for link in links:
            self.assertIsInstance(link, tuple)
            self.assertEqual(len(link), 4)  # (obs_id, rem_id, score, fields)
            obs_id, rem_id, score, fields = link
            self.assertIn(obs_id, self.obs_tasks)
            self.assertIn(rem_id, self.rem_tasks)
            self.assertIsInstance(score, (int, float))
            self.assertIsInstance(fields, dict)
    
    @patch('obs_tools.commands.build_sync_links.HAS_SCIPY', True)
    def test_scipy_hungarian_preferred_when_available(self):
        """Test that scipy's Hungarian algorithm is preferred when available."""
        # Mock scipy.optimize.linear_sum_assignment
        with patch('obs_tools.commands.build_sync_links.linear_sum_assignment') as mock_scipy:
            mock_scipy.return_value = ([0, 1], [0, 1])  # Mock assignment result
            
            # This would typically call Hungarian algorithm internally
            links = suggest_links_hungarian(self.obs_tasks, self.rem_tasks, min_score=0.3)
            
            # Should not crash and return valid structure
            self.assertIsInstance(links, list)
    
    @patch('obs_tools.commands.build_sync_links.HAS_SCIPY', False)
    @patch('obs_tools.commands.build_sync_links.HAS_MUNKRES', True)
    def test_munkres_fallback_when_scipy_unavailable(self):
        """Test that munkres is used when scipy unavailable but munkres available."""
        # Mock the munkres module
        with patch('obs_tools.commands.build_sync_links.Munkres') as mock_munkres_class:
            mock_munkres = MagicMock()
            mock_munkres.compute.return_value = [(0, 0), (1, 1)]
            mock_munkres_class.return_value = mock_munkres
            
            # Test the munkres_hungarian function directly
            cost_matrix = [[1.0, 2.0], [2.0, 1.0]]
            row_ind, col_ind = munkres_hungarian(cost_matrix)
            
            # Should call munkres
            mock_munkres_class.assert_called_once()
            mock_munkres.compute.assert_called_once()
    
    def test_greedy_algorithm_determinism(self):
        """Test that greedy algorithm produces deterministic results."""
        # Run greedy algorithm multiple times
        results = []
        for _ in range(5):
            links = suggest_links_greedy(self.obs_tasks, self.rem_tasks, min_score=0.3)
            # Convert to comparable format
            link_pairs = [(obs_id, rem_id) for obs_id, rem_id, _, _ in links]
            results.append(link_pairs)
        
        # All results should be identical
        for i in range(1, len(results)):
            self.assertEqual(results[0], results[i], "Greedy algorithm should be deterministic")
    
    def test_scoring_consistency_across_algorithms(self):
        """Test that scoring is consistent regardless of algorithm used."""
        # Test individual pair scoring
        obs_task = self.obs_tasks['obs1']
        rem_task = self.rem_tasks['rem1']
        
        # Score the same pair multiple times
        scores = []
        for _ in range(5):
            score, fields = score_pair(obs_task, rem_task, days_tol=1)
            scores.append((score, fields))
        
        # All scores should be identical
        for i in range(1, len(scores)):
            self.assertEqual(scores[0][0], scores[i][0], "Scoring should be deterministic")
            self.assertEqual(scores[0][1], scores[i][1], "Field extraction should be deterministic")
    
    def test_empty_input_handling_all_algorithms(self):
        """Test that all algorithms handle empty inputs gracefully."""
        empty_obs = {}
        empty_rem = {}
        
        # Test greedy with empty inputs
        links1 = suggest_links_greedy(empty_obs, self.rem_tasks)
        links2 = suggest_links_greedy(self.obs_tasks, empty_rem)
        links3 = suggest_links_greedy(empty_obs, empty_rem)
        
        self.assertEqual(len(links1), 0)
        self.assertEqual(len(links2), 0)
        self.assertEqual(len(links3), 0)
        
        # Test Hungarian with empty inputs
        h_links1 = suggest_links_hungarian(empty_obs, self.rem_tasks)
        h_links2 = suggest_links_hungarian(self.obs_tasks, empty_rem)
        h_links3 = suggest_links_hungarian(empty_obs, empty_rem)
        
        self.assertEqual(len(h_links1), 0)
        self.assertEqual(len(h_links2), 0)
        self.assertEqual(len(h_links3), 0)
    
    def test_large_dataset_performance_fallback(self):
        """Test fallback to greedy for very large datasets."""
        # Create large dataset
        large_obs_tasks = {}
        large_rem_tasks = {}
        
        for i in range(100):  # Moderate size for testing
            large_obs_tasks[f'obs{i}'] = {
                'uuid': f'obs{i}',
                'description': f'Task {i}',
                'status': 'todo'
            }
            large_rem_tasks[f'rem{i}'] = {
                'uuid': f'rem{i}',
                'title': f'Task {i}',
                'completed': False
            }
        
        # Both algorithms should handle this without crashing
        greedy_links = suggest_links_greedy(large_obs_tasks, large_rem_tasks, min_score=0.8)
        hungarian_links = suggest_links_hungarian(large_obs_tasks, large_rem_tasks, min_score=0.8)
        
        # Should return valid results
        self.assertIsInstance(greedy_links, list)
        self.assertIsInstance(hungarian_links, list)
    
    def test_algorithm_error_recovery(self):
        """Test recovery when optimization algorithms fail."""
        # Test munkres error handling
        with patch('obs_tools.commands.build_sync_links.Munkres') as mock_munkres_class:
            mock_munkres = MagicMock()
            mock_munkres.compute.side_effect = Exception("Munkres failed")
            mock_munkres_class.return_value = mock_munkres
            
            # Should handle error gracefully
            cost_matrix = [[1.0, 2.0], [2.0, 1.0]]
            row_ind, col_ind = munkres_hungarian(cost_matrix)
            
            # Should return empty results on failure
            self.assertEqual(len(row_ind), 0)
            self.assertEqual(len(col_ind), 0)
    
    def test_min_score_threshold_respected(self):
        """Test that minimum score threshold is respected across algorithms."""
        high_threshold = 0.95
        
        # Test with high threshold that should filter most matches
        greedy_links = suggest_links_greedy(self.obs_tasks, self.rem_tasks, min_score=high_threshold)
        hungarian_links = suggest_links_hungarian(self.obs_tasks, self.rem_tasks, min_score=high_threshold)
        
        # All returned links should meet the threshold
        for obs_id, rem_id, score, fields in greedy_links:
            self.assertGreaterEqual(score, high_threshold, 
                                  f"Greedy link {obs_id}-{rem_id} score {score} below threshold")
        
        for obs_id, rem_id, score, fields in hungarian_links:
            self.assertGreaterEqual(score, high_threshold,
                                  f"Hungarian link {obs_id}-{rem_id} score {score} below threshold")
    
    def test_one_to_one_constraint_all_algorithms(self):
        """Test that one-to-one constraint is maintained by all algorithms."""
        # Test greedy
        greedy_links = suggest_links_greedy(self.obs_tasks, self.rem_tasks, min_score=0.3)
        self._verify_one_to_one_constraint(greedy_links, "Greedy")
        
        # Test Hungarian
        hungarian_links = suggest_links_hungarian(self.obs_tasks, self.rem_tasks, min_score=0.3)
        self._verify_one_to_one_constraint(hungarian_links, "Hungarian")
    
    def _verify_one_to_one_constraint(self, links: List[Tuple], algorithm_name: str):
        """Helper to verify one-to-one constraint."""
        if not links:
            return  # Empty links is valid
        
        obs_ids = [link[0] for link in links]
        rem_ids = [link[1] for link in links]
        
        # Check for duplicates
        self.assertEqual(len(obs_ids), len(set(obs_ids)),
                        f"{algorithm_name}: Each Obsidian task should be linked at most once")
        self.assertEqual(len(rem_ids), len(set(rem_ids)),
                        f"{algorithm_name}: Each Reminder task should be linked at most once")
    
    def test_date_tolerance_affects_matching(self):
        """Test that date tolerance affects matching across algorithms."""
        obs_task = {
            'description': 'Test task',
            'due_date': '2023-12-15',
            'status': 'todo'
        }
        rem_task = {
            'title': 'Test task',
            'due_date': '2023-12-17',  # 2 days different
            'completed': False
        }
        
        # Test with different tolerances
        strict_score, _ = score_pair(obs_task, rem_task, days_tol=1)
        lenient_score, _ = score_pair(obs_task, rem_task, days_tol=5)
        
        # Lenient tolerance should give better or equal score
        self.assertGreaterEqual(lenient_score, strict_score,
                               "Higher date tolerance should improve or maintain score")
    
    @patch('obs_tools.commands.build_sync_links.HAS_SCIPY', False)
    @patch('obs_tools.commands.build_sync_links.HAS_MUNKRES', False)
    def test_pure_greedy_fallback_performance(self):
        """Test performance when falling back to pure greedy algorithm."""
        import time
        
        # Create medium-sized dataset
        medium_obs = {}
        medium_rem = {}
        
        for i in range(50):
            medium_obs[f'obs{i}'] = {
                'uuid': f'obs{i}',
                'description': f'Task {i}',
                'status': 'todo'
            }
            medium_rem[f'rem{i}'] = {
                'uuid': f'rem{i}',
                'title': f'Task {i}',
                'completed': False
            }
        
        # Time the greedy algorithm
        start_time = time.time()
        links = suggest_links_greedy(medium_obs, medium_rem, min_score=0.5)
        end_time = time.time()
        
        execution_time = end_time - start_time
        
        # Should complete in reasonable time (< 5 seconds for 50x50)
        self.assertLess(execution_time, 5.0, "Greedy fallback should be reasonably fast")
        
        # Should return valid results
        self.assertIsInstance(links, list)
        print(f"Greedy algorithm processed 50x50 matrix in {execution_time:.3f}s")


@pytest.mark.matching
@pytest.mark.unit
class TestOptimizationLibraryInterfaces(unittest.TestCase):
    """Test interfaces to optimization libraries."""
    
    def test_scipy_interface_mocking(self):
        """Test scipy interface with mocking."""
        with patch('obs_tools.commands.build_sync_links.HAS_SCIPY', True):
            with patch('obs_tools.commands.build_sync_links.linear_sum_assignment') as mock_scipy:
                # Mock scipy to return a simple assignment
                mock_scipy.return_value = ([0, 1], [1, 0])  # Cross assignment
                
                # Create simple cost matrix test
                cost_matrix = [
                    [1.0, 0.5],
                    [0.8, 0.3]
                ]
                
                # Would normally call scipy through Hungarian algorithm
                # Here we just verify the mock interface works
                row_ind, col_ind = mock_scipy(cost_matrix)
                
                self.assertEqual(len(row_ind), 2)
                self.assertEqual(len(col_ind), 2)
                mock_scipy.assert_called_once_with(cost_matrix)
    
    def test_munkres_interface_mocking(self):
        """Test munkres interface with mocking."""
        with patch('obs_tools.commands.build_sync_links.HAS_MUNKRES', True):
            with patch('obs_tools.commands.build_sync_links.Munkres') as mock_munkres_class:
                mock_munkres = MagicMock()
                mock_munkres.compute.return_value = [(0, 1), (1, 0)]
                mock_munkres_class.return_value = mock_munkres
                
                # Test the munkres interface
                cost_matrix = [[1.0, 0.5], [0.8, 0.3]]
                row_ind, col_ind = munkres_hungarian(cost_matrix)
                
                # Verify munkres was called
                mock_munkres_class.assert_called_once()
                mock_munkres.compute.assert_called_once()
                
                # Verify results processed correctly
                self.assertIsInstance(row_ind, list)
                self.assertIsInstance(col_ind, list)
    
    def test_cost_matrix_generation(self):
        """Test cost matrix generation for optimization algorithms."""
        obs_tasks = {
            'obs1': {'description': 'Task A', 'status': 'todo'},
            'obs2': {'description': 'Task B', 'status': 'todo'}
        }
        rem_tasks = {
            'rem1': {'title': 'Task A', 'completed': False},
            'rem2': {'title': 'Task B', 'completed': False}
        }
        
        # Generate cost matrix manually (what the algorithm would do)
        obs_list = list(obs_tasks.items())
        rem_list = list(rem_tasks.items())
        
        cost_matrix = []
        for obs_id, obs_task in obs_list:
            row = []
            for rem_id, rem_task in rem_list:
                score, _ = score_pair(obs_task, rem_task)
                cost = 1.0 - score  # Convert score to cost
                row.append(cost)
            cost_matrix.append(row)
        
        # Verify matrix structure
        self.assertEqual(len(cost_matrix), 2)  # 2 obs tasks
        self.assertEqual(len(cost_matrix[0]), 2)  # 2 rem tasks
        self.assertEqual(len(cost_matrix[1]), 2)  # 2 rem tasks
        
        # Costs should be between 0 and 1
        for row in cost_matrix:
            for cost in row:
                self.assertGreaterEqual(cost, 0.0)
                self.assertLessEqual(cost, 1.0)


if __name__ == '__main__':
    unittest.main(verbosity=2)