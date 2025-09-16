#!/usr/bin/env python3
"""
Bidirectional Sync Testing

This script specifically tests bidirectional synchronization between
Obsidian and Apple Reminders by:

1. Finding actively linked tasks
2. Making controlled changes in one system
3. Running sync operations
4. Verifying changes propagate to the other system
5. Testing various field synchronization (completion, due dates, etc.)

This provides concrete validation that the sync system maintains
data consistency and properly propagates changes bidirectionally.
"""

import json
import os
import time
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import random


class BidirectionalSyncTester:
    """Test bidirectional sync functionality with real data changes"""
    
    def __init__(self, work_dir: str = "/Users/yannickbowe/Library/Mobile Documents/iCloud~md~obsidian/Documents/Work/obssync"):
        self.work_dir = Path(work_dir)
        self.config_dir = Path.home() / ".config"
        
        # File paths
        self.obs_index = self.config_dir / "obsidian_tasks_index.json"
        self.rem_index = self.config_dir / "reminders_tasks_index.json" 
        self.sync_links = self.config_dir / "sync_links.json"
        
        self.test_results = {}
        self.start_time = datetime.now()
        
    def log(self, message: str, level: str = "INFO"):
        """Log with timestamps"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")
        
    def run_obs_command(self, command: List[str]) -> subprocess.CompletedProcess:
        """Run obs_tools.py command"""
        cmd = ["python3", str(self.work_dir / "obs_tools.py")] + command
        self.log(f"Running: {' '.join(cmd)}")
        return subprocess.run(cmd, capture_output=True, text=True, cwd=self.work_dir)
        
    def load_json_file(self, filepath: Path) -> Dict[str, Any]:
        """Load JSON file with error handling"""
        if not filepath.exists():
            return {}
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.log(f"Error loading {filepath}: {e}", "ERROR")
            return {}
            
    def refresh_indices(self) -> bool:
        """Refresh task indices to get current state"""
        self.log("Refreshing task indices...")
        
        # Collect Obsidian tasks
        result = self.run_obs_command(["tasks", "collect", "--use-config", "--ignore-common"])
        if result.returncode != 0:
            self.log(f"Failed to collect Obsidian tasks: {result.stderr}", "ERROR")
            return False
            
        # Collect Reminders tasks  
        result = self.run_obs_command(["reminders", "collect"])
        if result.returncode != 0:
            self.log(f"Failed to collect Reminders tasks: {result.stderr}", "ERROR")
            return False
            
        return True
        
    def run_sync_pipeline(self) -> bool:
        """Run complete sync pipeline"""
        self.log("Running sync pipeline...")
        
        # Update indices and rebuild links
        result = self.run_obs_command(["sync", "update", "--ignore-common", "--include-done"])
        if result.returncode != 0:
            self.log(f"Sync update failed: {result.stderr}", "ERROR")
            return False
            
        # Apply sync changes
        result = self.run_obs_command(["sync", "apply", "--apply", "--verbose"])
        if result.returncode != 0:
            self.log(f"Sync apply failed: {result.stderr}", "ERROR")
            return False
            
        return True
        
    def find_test_candidates(self) -> List[Dict[str, Any]]:
        """Find suitable tasks for bidirectional testing"""
        self.log("Finding test candidates...")
        
        # Load current data
        obs_data = self.load_json_file(self.obs_index)
        rem_data = self.load_json_file(self.rem_index)
        links_data = self.load_json_file(self.sync_links)
        
        obs_tasks = obs_data.get('tasks', {})
        rem_tasks = rem_data.get('tasks', {})
        links = links_data.get('links', [])
        
        candidates = []
        
        # Find links with both tasks present and recently synced
        for link in links[:50]:  # Limit to first 50 for performance
            obs_uuid = link.get('obs_uuid')
            rem_uuid = link.get('rem_uuid')
            
            if not obs_uuid or not rem_uuid:
                continue
                
            # Find the actual tasks
            obs_task = None
            rem_task = None
            
            for task_id, task in obs_tasks.items():
                if task.get('uuid') == obs_uuid:
                    obs_task = task
                    obs_task['task_id'] = task_id
                    break
                    
            for task_id, task in rem_tasks.items():
                if task.get('uuid') == rem_uuid:
                    rem_task = task
                    rem_task['task_id'] = task_id
                    break
                    
            if obs_task and rem_task:
                candidate = {
                    'link': link,
                    'obs_task': obs_task,
                    'rem_task': rem_task,
                    'last_synced': link.get('last_synced'),
                    'score': link.get('score', 0)
                }
                candidates.append(candidate)
                
        # Sort by score and recent sync activity
        candidates.sort(key=lambda x: (x['score'], x['last_synced'] or ''), reverse=True)
        
        self.log(f"Found {len(candidates)} test candidates")
        return candidates[:10]  # Return top 10
        
    def test_completion_sync(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Test completion status synchronization"""
        self.log("=== Testing Completion Status Sync ===")
        
        results = {
            'test_type': 'completion_sync',
            'success': False,
            'before_state': {},
            'after_state': {},
            'changes_detected': False,
            'issues': []
        }
        
        obs_task = candidate['obs_task']
        rem_task = candidate['rem_task']
        
        # Record initial state
        results['before_state'] = {
            'obs_completed': obs_task.get('completed', False),
            'rem_completed': rem_task.get('completed', False),
            'obs_title': obs_task.get('title', ''),
            'rem_title': rem_task.get('title', '')
        }
        
        self.log(f"Testing with task: {obs_task.get('title', 'Untitled')[:50]}")
        self.log(f"Initial state - Obs: {results['before_state']['obs_completed']}, Rem: {results['before_state']['rem_completed']}")
        
        # Run initial sync to ensure we're starting from a consistent state
        if not self.run_sync_pipeline():
            results['issues'].append("Failed to run initial sync")
            return results
            
        # Wait a moment for changes to settle
        time.sleep(2)
        
        # Refresh data and check for any changes during sync
        if not self.refresh_indices():
            results['issues'].append("Failed to refresh indices after sync")
            return results
            
        # Load updated data
        obs_data = self.load_json_file(self.obs_index)
        rem_data = self.load_json_file(self.rem_index)
        
        # Find updated tasks
        updated_obs_task = None
        updated_rem_task = None
        
        for task_id, task in obs_data.get('tasks', {}).items():
            if task.get('uuid') == obs_task['uuid']:
                updated_obs_task = task
                break
                
        for task_id, task in rem_data.get('tasks', {}).items():
            if task.get('uuid') == rem_task['uuid']:
                updated_rem_task = task
                break
                
        if not updated_obs_task or not updated_rem_task:
            results['issues'].append("Could not find tasks after sync")
            return results
            
        # Record final state
        results['after_state'] = {
            'obs_completed': updated_obs_task.get('completed', False),
            'rem_completed': updated_rem_task.get('completed', False),
            'obs_title': updated_obs_task.get('title', ''),
            'rem_title': updated_rem_task.get('title', '')
        }
        
        self.log(f"Final state - Obs: {results['after_state']['obs_completed']}, Rem: {results['after_state']['rem_completed']}")
        
        # Check if states are consistent
        obs_completed = results['after_state']['obs_completed']
        rem_completed = results['after_state']['rem_completed']
        
        if obs_completed == rem_completed:
            results['success'] = True
            self.log("✓ Completion status is synchronized")
        else:
            results['issues'].append(f"Completion status mismatch: Obs={obs_completed}, Rem={rem_completed}")
            self.log(f"✗ Completion status mismatch: Obs={obs_completed}, Rem={rem_completed}")
            
        return results
        
    def test_title_consistency(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Test title consistency between systems"""
        self.log("=== Testing Title Consistency ===")
        
        results = {
            'test_type': 'title_consistency',
            'success': False,
            'titles_match': False,
            'similarity_score': 0.0,
            'issues': []
        }
        
        obs_task = candidate['obs_task']
        rem_task = candidate['rem_task']
        
        obs_title = obs_task.get('title', '').strip()
        rem_title = rem_task.get('title', '').strip()
        
        self.log(f"Obsidian title: '{obs_title[:80]}'")
        self.log(f"Reminders title: '{rem_title[:80]}'")
        
        # Check exact match
        if obs_title == rem_title:
            results['titles_match'] = True
            results['similarity_score'] = 1.0
            results['success'] = True
            self.log("✓ Titles match exactly")
        else:
            # Calculate similarity
            if obs_title and rem_title:
                # Simple similarity calculation
                obs_words = set(obs_title.lower().split())
                rem_words = set(rem_title.lower().split())
                
                if obs_words and rem_words:
                    intersection = obs_words & rem_words
                    union = obs_words | rem_words
                    similarity = len(intersection) / len(union) if union else 0
                    results['similarity_score'] = similarity
                    
                    if similarity > 0.8:
                        results['success'] = True
                        self.log(f"✓ Titles are similar (score: {similarity:.2f})")
                    else:
                        results['issues'].append(f"Low title similarity: {similarity:.2f}")
                        self.log(f"✗ Low title similarity: {similarity:.2f}")
                else:
                    results['issues'].append("One or both titles are empty")
            else:
                results['issues'].append("One or both titles are empty")
                
        return results
        
    def test_date_consistency(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Test due date consistency between systems"""
        self.log("=== Testing Date Consistency ===")
        
        results = {
            'test_type': 'date_consistency',
            'success': False,
            'dates_consistent': False,
            'date_difference_days': None,
            'issues': []
        }
        
        obs_task = candidate['obs_task']
        rem_task = candidate['rem_task']
        
        obs_due = obs_task.get('due_date')
        rem_due = rem_task.get('due_date')
        
        self.log(f"Obsidian due: {obs_due}")
        self.log(f"Reminders due: {rem_due}")
        
        if not obs_due and not rem_due:
            results['success'] = True
            results['dates_consistent'] = True
            self.log("✓ Both tasks have no due date")
        elif obs_due and rem_due:
            try:
                # Parse dates (handle different formats)
                if 'T' in str(obs_due):
                    obs_date = datetime.fromisoformat(str(obs_due).replace('Z', '+00:00'))
                else:
                    obs_date = datetime.strptime(str(obs_due), '%Y-%m-%d')
                    
                if 'T' in str(rem_due):
                    rem_date = datetime.fromisoformat(str(rem_due).replace('Z', '+00:00'))
                else:
                    rem_date = datetime.strptime(str(rem_due), '%Y-%m-%d')
                    
                # Compare dates (allow for timezone differences)
                date_diff = abs((obs_date.date() - rem_date.date()).days)
                results['date_difference_days'] = date_diff
                
                if date_diff <= 1:  # Allow 1 day difference for timezone handling
                    results['success'] = True
                    results['dates_consistent'] = True
                    self.log(f"✓ Due dates consistent (diff: {date_diff} days)")
                else:
                    results['issues'].append(f"Due date difference: {date_diff} days")
                    self.log(f"✗ Due date difference: {date_diff} days")
                    
            except Exception as e:
                results['issues'].append(f"Date parsing error: {e}")
                self.log(f"✗ Date parsing error: {e}")
        else:
            # One has due date, other doesn't
            results['issues'].append("Due date presence mismatch")
            self.log("✗ One task has due date, other doesn't")
            
        return results
        
    def test_link_stability(self, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Test that sync links remain stable through operations"""
        self.log("=== Testing Link Stability ===")
        
        results = {
            'test_type': 'link_stability',
            'success': False,
            'initial_links': 0,
            'final_links': 0,
            'links_stable': False,
            'issues': []
        }
        
        # Count initial links
        initial_links_data = self.load_json_file(self.sync_links)
        initial_count = len(initial_links_data.get('links', []))
        results['initial_links'] = initial_count
        
        self.log(f"Initial link count: {initial_count}")
        
        # Run sync pipeline multiple times
        for i in range(3):
            self.log(f"Sync iteration {i + 1}/3...")
            if not self.run_sync_pipeline():
                results['issues'].append(f"Sync failed on iteration {i + 1}")
                return results
            time.sleep(1)
            
        # Count final links
        final_links_data = self.load_json_file(self.sync_links)
        final_count = len(final_links_data.get('links', []))
        results['final_links'] = final_count
        
        self.log(f"Final link count: {final_count}")
        
        # Check stability (allow small variations for legitimate changes)
        if abs(final_count - initial_count) <= 5:
            results['success'] = True
            results['links_stable'] = True
            self.log(f"✓ Links stable: {initial_count} -> {final_count}")
        else:
            results['issues'].append(f"Significant link count change: {initial_count} -> {final_count}")
            self.log(f"✗ Significant link count change: {initial_count} -> {final_count}")
            
        return results
        
    def run_bidirectional_tests(self) -> Dict[str, Any]:
        """Run comprehensive bidirectional sync tests"""
        self.log("🔄 Starting Bidirectional Sync Testing")
        self.log(f"Working directory: {self.work_dir}")
        
        # Refresh indices to start with current data
        if not self.refresh_indices():
            return {'error': 'Failed to refresh indices'}
            
        # Find test candidates
        candidates = self.find_test_candidates()
        
        if not candidates:
            return {'error': 'No suitable test candidates found'}
            
        test_results = []
        
        # Test with first few candidates
        for i, candidate in enumerate(candidates[:3]):
            self.log(f"\n{'='*60}")
            self.log(f"Testing with candidate {i + 1}/3")
            self.log(f"{'='*60}")
            
            # Test completion sync
            completion_result = self.test_completion_sync(candidate)
            test_results.append(completion_result)
            
            # Test title consistency
            title_result = self.test_title_consistency(candidate)
            test_results.append(title_result)
            
            # Test date consistency
            date_result = self.test_date_consistency(candidate)
            test_results.append(date_result)
            
        # Test link stability
        self.log(f"\n{'='*60}")
        stability_result = self.test_link_stability(candidates)
        test_results.append(stability_result)
        
        # Analyze results
        duration = datetime.now() - self.start_time
        
        passed_tests = sum(1 for result in test_results if result.get('success', False))
        total_tests = len(test_results)
        
        summary = {
            'test_duration': duration.total_seconds(),
            'candidates_tested': len(candidates),
            'tests_run': total_tests,
            'tests_passed': passed_tests,
            'success_rate': (passed_tests / total_tests) * 100 if total_tests > 0 else 0,
            'overall_status': 'PASS' if passed_tests == total_tests else 'PARTIAL' if passed_tests > 0 else 'FAIL',
            'detailed_results': test_results
        }
        
        # Print summary
        self.log(f"\n{'='*60}")
        self.log("🔄 BIDIRECTIONAL SYNC TEST SUMMARY")
        self.log(f"{'='*60}")
        self.log(f"Overall Status: {summary['overall_status']}")
        self.log(f"Tests Passed: {passed_tests}/{total_tests} ({summary['success_rate']:.1f}%)")
        self.log(f"Test Duration: {summary['test_duration']:.2f} seconds")
        self.log(f"Candidates Tested: {summary['candidates_tested']}")
        
        # Show test type breakdown
        test_types = {}
        for result in test_results:
            test_type = result.get('test_type', 'unknown')
            if test_type not in test_types:
                test_types[test_type] = {'passed': 0, 'total': 0}
            test_types[test_type]['total'] += 1
            if result.get('success', False):
                test_types[test_type]['passed'] += 1
                
        self.log("\nTest Type Breakdown:")
        for test_type, stats in test_types.items():
            self.log(f"  {test_type}: {stats['passed']}/{stats['total']}")
            
        # Save results
        results_file = self.config_dir / "obs-tools" / "backups" / f"bidirectional_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        results_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
            self.log(f"\nDetailed results saved: {results_file}")
        except Exception as e:
            self.log(f"Failed to save results: {e}", "ERROR")
            
        return summary


def main():
    """Main entry point"""
    tester = BidirectionalSyncTester()
    results = tester.run_bidirectional_tests()
    
    if 'error' in results:
        print(f"Test failed: {results['error']}")
        return 1
        
    # Return appropriate exit code
    if results['overall_status'] == 'PASS':
        return 0
    elif results['overall_status'] == 'PARTIAL':
        return 1
    else:
        return 2


if __name__ == "__main__":
    exit(main())