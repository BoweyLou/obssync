#!/usr/bin/env python3
"""
Final Sync Validation Script

This script provides the definitive test of the end-to-end sync functionality by:
1. Using the managed virtual environment to ensure EventKit works
2. Testing all sync operations with real data
3. Validating bidirectional synchronization
4. Measuring sync performance and stability
5. Providing comprehensive validation results

This serves as the final validation that the sync system works correctly
and maintains data integrity through complete sync cycles.
"""

import json
import os
import time
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import tempfile


class FinalSyncValidator:
    """Final comprehensive validator for sync system"""
    
    def __init__(self, work_dir: str = "/Users/yannickbowe/Library/Mobile Documents/iCloud~md~obsidian/Documents/Work/obssync"):
        self.work_dir = Path(work_dir)
        self.config_dir = Path.home() / ".config"
        
        # Use managed venv python
        self.venv_python = Path.home() / "Library" / "Application Support" / "obs-tools" / "venv" / "bin" / "python3"
        
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
        
    def run_obs_command_venv(self, command: List[str]) -> subprocess.CompletedProcess:
        """Run obs_tools.py command using managed venv"""
        cmd = [str(self.venv_python), str(self.work_dir / "obs_tools.py")] + command
        self.log(f"Running (venv): {' '.join(cmd)}")
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
            
    def test_eventkit_availability(self) -> bool:
        """Test that EventKit is available in the managed venv"""
        self.log("=== Testing EventKit Availability ===")
        
        result = subprocess.run([
            str(self.venv_python), "-c", 
            "import EventKit; print('EventKit successfully imported')"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            self.log("✓ EventKit is available in managed venv")
            return True
        else:
            self.log(f"✗ EventKit not available: {result.stderr}", "ERROR")
            return False
            
    def test_full_collection_pipeline(self) -> Dict[str, Any]:
        """Test complete collection pipeline"""
        self.log("=== Testing Full Collection Pipeline ===")
        
        results = {
            'obsidian_collection': False,
            'reminders_collection': False,
            'link_building': False,
            'issues': []
        }
        
        # Test Obsidian collection
        self.log("Testing Obsidian task collection...")
        result = self.run_obs_command_venv(["tasks", "collect", "--use-config", "--ignore-common"])
        
        if result.returncode == 0:
            results['obsidian_collection'] = True
            self.log("✓ Obsidian collection successful")
        else:
            results['issues'].append(f"Obsidian collection failed: {result.stderr}")
            self.log(f"✗ Obsidian collection failed", "ERROR")
            
        # Test Reminders collection
        self.log("Testing Reminders task collection...")
        result = self.run_obs_command_venv(["reminders", "collect"])
        
        if result.returncode == 0:
            results['reminders_collection'] = True
            self.log("✓ Reminders collection successful")
        else:
            results['issues'].append(f"Reminders collection failed: {result.stderr}")
            self.log(f"✗ Reminders collection failed", "ERROR")
            
        # Test link building (only if collections succeeded)
        if results['obsidian_collection'] and results['reminders_collection']:
            self.log("Testing sync link building...")
            result = self.run_obs_command_venv(["sync", "suggest", "--include-done"])
            
            if result.returncode == 0:
                results['link_building'] = True
                self.log("✓ Link building successful")
            else:
                results['issues'].append(f"Link building failed: {result.stderr}")
                self.log(f"✗ Link building failed", "ERROR")
        else:
            results['issues'].append("Skipped link building due to collection failures")
            
        return results
        
    def test_sync_operations(self) -> Dict[str, Any]:
        """Test sync apply and create operations"""
        self.log("=== Testing Sync Operations ===")
        
        results = {
            'sync_apply_dry': False,
            'sync_apply_actual': False,
            'create_missing_dry': False,
            'create_missing_actual': False,
            'issues': []
        }
        
        # Test sync apply dry run
        self.log("Testing sync apply (dry run)...")
        result = self.run_obs_command_venv(["sync", "apply", "--verbose"])
        
        if result.returncode == 0:
            results['sync_apply_dry'] = True
            self.log("✓ Sync apply dry run successful")
        else:
            results['issues'].append(f"Sync apply dry run failed: {result.stderr}")
            self.log(f"✗ Sync apply dry run failed", "ERROR")
            
        # Test sync apply actual
        self.log("Testing sync apply (actual)...")
        result = self.run_obs_command_venv(["sync", "apply", "--apply", "--verbose"])
        
        if result.returncode == 0:
            results['sync_apply_actual'] = True
            self.log("✓ Sync apply actual successful")
        else:
            results['issues'].append(f"Sync apply actual failed: {result.stderr}")
            self.log(f"✗ Sync apply actual failed", "ERROR")
            
        # Test create missing dry run
        self.log("Testing create missing (dry run)...")
        result = self.run_obs_command_venv([
            "sync", "create", "--verbose", "--direction", "both", "--max", "3"
        ])
        
        if result.returncode == 0:
            results['create_missing_dry'] = True
            self.log("✓ Create missing dry run successful")
        else:
            results['issues'].append(f"Create missing dry run failed: {result.stderr}")
            self.log(f"✗ Create missing dry run failed", "ERROR")
            
        # Test create missing actual (limited)
        self.log("Testing create missing (actual, limited)...")
        result = self.run_obs_command_venv([
            "sync", "create", "--apply", "--verbose", "--direction", "both", "--max", "1"
        ])
        
        if result.returncode == 0:
            results['create_missing_actual'] = True
            self.log("✓ Create missing actual successful")
        else:
            results['issues'].append(f"Create missing actual failed: {result.stderr}")
            self.log(f"✗ Create missing actual failed", "ERROR")
            
        return results
        
    def test_pipeline_stability(self) -> Dict[str, Any]:
        """Test pipeline stability through multiple iterations"""
        self.log("=== Testing Pipeline Stability ===")
        
        results = {
            'iterations_completed': 0,
            'stable': True,
            'initial_state': {},
            'final_state': {},
            'issues': []
        }
        
        # Capture initial state
        initial_links = self.load_json_file(self.sync_links)
        results['initial_state'] = {
            'links': len(initial_links.get('links', [])),
            'timestamp': datetime.now().isoformat()
        }
        
        # Run multiple pipeline iterations
        iterations = 3
        for i in range(iterations):
            self.log(f"Pipeline iteration {i + 1}/{iterations}...")
            
            # Full update pipeline
            result = self.run_obs_command_venv([
                "sync", "update", "--ignore-common", "--include-done"
            ])
            
            if result.returncode != 0:
                results['stable'] = False
                results['issues'].append(f"Pipeline iteration {i + 1} failed: {result.stderr}")
                break
                
            results['iterations_completed'] += 1
            
            # Brief pause between iterations
            time.sleep(1)
            
        # Capture final state
        final_links = self.load_json_file(self.sync_links)
        results['final_state'] = {
            'links': len(final_links.get('links', [])),
            'timestamp': datetime.now().isoformat()
        }
        
        # Check stability
        initial_count = results['initial_state']['links']
        final_count = results['final_state']['links']
        
        # Allow for small variations due to legitimate changes
        if abs(final_count - initial_count) > 10:
            results['stable'] = False
            results['issues'].append(f"Large link count change: {initial_count} -> {final_count}")
        else:
            self.log(f"✓ Pipeline stable: {initial_count} -> {final_count} links")
            
        return results
        
    def test_data_consistency(self) -> Dict[str, Any]:
        """Test data consistency after sync operations"""
        self.log("=== Testing Data Consistency ===")
        
        results = {
            'consistent': True,
            'checks_performed': 0,
            'inconsistencies': [],
            'sample_links': []
        }
        
        # Load current data
        obs_data = self.load_json_file(self.obs_index)
        rem_data = self.load_json_file(self.rem_index)
        links_data = self.load_json_file(self.sync_links)
        
        obs_tasks = obs_data.get('tasks', {})
        rem_tasks = rem_data.get('tasks', {})
        links = links_data.get('links', [])
        
        # Check a sample of linked tasks for consistency
        checked_links = 0
        for link in links[:50]:  # Check first 50 links
            obs_uuid = link.get('obs_uuid')
            rem_uuid = link.get('rem_uuid')
            
            if not obs_uuid or not rem_uuid:
                continue
                
            # Find corresponding tasks
            obs_task = None
            rem_task = None
            
            for task in obs_tasks.values():
                if task.get('uuid') == obs_uuid:
                    obs_task = task
                    break
                    
            for task in rem_tasks.values():
                if task.get('uuid') == rem_uuid:
                    rem_task = task
                    break
                    
            if not obs_task or not rem_task:
                results['inconsistencies'].append(f"Link references missing task: {obs_uuid}/{rem_uuid}")
                continue
                
            checked_links += 1
            
            # Check completion consistency
            obs_completed = obs_task.get('completed', False)
            rem_completed = rem_task.get('completed', False)
            
            if obs_completed != rem_completed:
                results['inconsistencies'].append(
                    f"Completion mismatch: {obs_task.get('title', '')[:30]} - Obs:{obs_completed}, Rem:{rem_completed}"
                )
                
            # Record sample for reporting
            if len(results['sample_links']) < 5:
                results['sample_links'].append({
                    'obs_title': obs_task.get('title', '')[:50],
                    'rem_title': rem_task.get('title', '')[:50],
                    'obs_completed': obs_completed,
                    'rem_completed': rem_completed,
                    'score': link.get('score', 0)
                })
                
        results['checks_performed'] = checked_links
        
        if results['inconsistencies']:
            results['consistent'] = False
            self.log(f"✗ Found {len(results['inconsistencies'])} inconsistencies")
        else:
            self.log(f"✓ All {checked_links} checked links are consistent")
            
        return results
        
    def measure_performance(self) -> Dict[str, Any]:
        """Measure sync performance metrics"""
        self.log("=== Measuring Performance ===")
        
        results = {
            'pipeline_time': 0,
            'collection_time': 0,
            'link_building_time': 0,
            'sync_apply_time': 0,
            'tasks_processed': 0,
            'links_processed': 0,
            'performance_acceptable': False
        }
        
        # Measure collection performance
        collection_start = time.time()
        
        # Obsidian collection
        result = self.run_obs_command_venv(["tasks", "collect", "--use-config", "--ignore-common"])
        if result.returncode != 0:
            results['issues'] = ['Collection failed during performance test']
            return results
            
        # Reminders collection
        result = self.run_obs_command_venv(["reminders", "collect"])
        if result.returncode != 0:
            results['issues'] = ['Reminders collection failed during performance test']
            return results
            
        results['collection_time'] = time.time() - collection_start
        
        # Measure link building performance
        link_start = time.time()
        result = self.run_obs_command_venv(["sync", "suggest", "--include-done"])
        if result.returncode == 0:
            results['link_building_time'] = time.time() - link_start
            
        # Measure sync apply performance
        sync_start = time.time()
        result = self.run_obs_command_venv(["sync", "apply", "--apply"])
        if result.returncode == 0:
            results['sync_apply_time'] = time.time() - sync_start
            
        # Calculate total pipeline time
        results['pipeline_time'] = results['collection_time'] + results['link_building_time'] + results['sync_apply_time']
        
        # Get final counts
        obs_data = self.load_json_file(self.obs_index)
        rem_data = self.load_json_file(self.rem_index)
        links_data = self.load_json_file(self.sync_links)
        
        results['tasks_processed'] = len(obs_data.get('tasks', {})) + len(rem_data.get('tasks', {}))
        results['links_processed'] = len(links_data.get('links', []))
        
        # Performance assessment
        results['performance_acceptable'] = results['pipeline_time'] < 180  # 3 minutes
        
        self.log(f"Performance metrics:")
        self.log(f"  - Total pipeline: {results['pipeline_time']:.2f}s")
        self.log(f"  - Collection: {results['collection_time']:.2f}s")
        self.log(f"  - Link building: {results['link_building_time']:.2f}s")
        self.log(f"  - Sync apply: {results['sync_apply_time']:.2f}s")
        self.log(f"  - Tasks processed: {results['tasks_processed']:,}")
        self.log(f"  - Links processed: {results['links_processed']:,}")
        
        return results
        
    def run_final_validation(self) -> Dict[str, Any]:
        """Run complete final validation"""
        self.log("🚀 FINAL SYNC SYSTEM VALIDATION")
        self.log("="*80)
        
        # Check prerequisites
        if not self.test_eventkit_availability():
            return {'error': 'EventKit not available'}
            
        validation_results = {}
        
        # Test 1: Full Collection Pipeline
        self.log(f"\n{'='*60}")
        validation_results['collection_pipeline'] = self.test_full_collection_pipeline()
        
        # Test 2: Sync Operations
        self.log(f"\n{'='*60}")
        validation_results['sync_operations'] = self.test_sync_operations()
        
        # Test 3: Pipeline Stability
        self.log(f"\n{'='*60}")
        validation_results['pipeline_stability'] = self.test_pipeline_stability()
        
        # Test 4: Data Consistency
        self.log(f"\n{'='*60}")
        validation_results['data_consistency'] = self.test_data_consistency()
        
        # Test 5: Performance Measurement
        self.log(f"\n{'='*60}")
        validation_results['performance'] = self.measure_performance()
        
        # Overall assessment
        duration = datetime.now() - self.start_time
        
        # Count successful tests
        all_tests = []
        
        # Collection tests
        collection = validation_results['collection_pipeline']
        all_tests.extend([
            collection['obsidian_collection'],
            collection['reminders_collection'],
            collection['link_building']
        ])
        
        # Sync operation tests
        sync_ops = validation_results['sync_operations']
        all_tests.extend([
            sync_ops['sync_apply_dry'],
            sync_ops['sync_apply_actual'],
            sync_ops['create_missing_dry'],
            sync_ops['create_missing_actual']
        ])
        
        # Other tests
        all_tests.extend([
            validation_results['pipeline_stability']['stable'],
            validation_results['data_consistency']['consistent'],
            validation_results['performance']['performance_acceptable']
        ])
        
        passed_tests = sum(all_tests)
        total_tests = len(all_tests)
        success_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
        
        # Determine overall status
        if success_rate >= 90:
            overall_status = 'EXCELLENT'
        elif success_rate >= 75:
            overall_status = 'GOOD'
        elif success_rate >= 50:
            overall_status = 'PARTIAL'
        else:
            overall_status = 'FAILED'
            
        summary = {
            'overall_status': overall_status,
            'success_rate': success_rate,
            'tests_passed': passed_tests,
            'total_tests': total_tests,
            'duration_seconds': duration.total_seconds(),
            'detailed_results': validation_results
        }
        
        # Print final summary
        self.log(f"\n{'='*80}")
        self.log("🎯 FINAL VALIDATION SUMMARY")
        self.log(f"{'='*80}")
        self.log(f"Overall Status: {overall_status}")
        self.log(f"Success Rate: {success_rate:.1f}% ({passed_tests}/{total_tests} tests passed)")
        self.log(f"Validation Duration: {duration.total_seconds():.2f} seconds")
        
        # Test category breakdown
        self.log(f"\nTest Category Results:")
        self.log(f"  Collection Pipeline: {'✓' if all(collection.values()) else '✗'}")
        self.log(f"  Sync Operations: {'✓' if all(sync_ops.values()) else '✗'}")
        self.log(f"  Pipeline Stability: {'✓' if validation_results['pipeline_stability']['stable'] else '✗'}")
        self.log(f"  Data Consistency: {'✓' if validation_results['data_consistency']['consistent'] else '✗'}")
        self.log(f"  Performance: {'✓' if validation_results['performance']['performance_acceptable'] else '✗'}")
        
        # Performance summary
        perf = validation_results['performance']
        self.log(f"\nPerformance Summary:")
        self.log(f"  Pipeline Time: {perf['pipeline_time']:.2f}s")
        self.log(f"  Tasks Processed: {perf['tasks_processed']:,}")
        self.log(f"  Links Processed: {perf['links_processed']:,}")
        
        # Data consistency summary
        consistency = validation_results['data_consistency']
        self.log(f"\nData Consistency:")
        self.log(f"  Links Checked: {consistency['checks_performed']}")
        self.log(f"  Inconsistencies: {len(consistency['inconsistencies'])}")
        
        if overall_status == 'EXCELLENT':
            self.log(f"\n🎉 SYNC SYSTEM VALIDATION COMPLETE - SYSTEM PERFORMING EXCELLENTLY!")
        elif overall_status == 'GOOD':
            self.log(f"\n✅ SYNC SYSTEM VALIDATION COMPLETE - SYSTEM PERFORMING WELL!")
        else:
            self.log(f"\n⚠️  SYNC SYSTEM VALIDATION COMPLETE - ISSUES DETECTED")
            
        # Save detailed results
        results_file = self.config_dir / "obs-tools" / "backups" / f"final_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
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
    validator = FinalSyncValidator()
    results = validator.run_final_validation()
    
    if 'error' in results:
        print(f"Validation failed: {results['error']}")
        return 2
        
    # Return appropriate exit code
    status = results.get('overall_status', 'FAILED')
    if status == 'EXCELLENT':
        return 0
    elif status == 'GOOD':
        return 0
    elif status == 'PARTIAL':
        return 1
    else:
        return 2


if __name__ == "__main__":
    exit(main())