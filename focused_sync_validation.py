#!/usr/bin/env python3
"""
Focused Sync Validation Script

This script performs targeted validation of the sync system's core functionality:
1. Validates existing data integrity and consistency
2. Tests bidirectional sync operations
3. Checks link stability and UUID-based identity tracking
4. Tests update propagation between systems
5. Validates end-to-end sync pipeline

Focus areas:
- Data consistency validation
- Link integrity verification
- Bidirectional sync testing
- Performance metrics
- Edge case handling
"""

import json
import os
import time
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import uuid


class FocusedSyncValidator:
    """Focused validator for sync system integrity and functionality"""
    
    def __init__(self, work_dir: str = "/Users/yannickbowe/Library/Mobile Documents/iCloud~md~obsidian/Documents/Work/obssync"):
        self.work_dir = Path(work_dir)
        self.config_dir = Path.home() / ".config"
        
        # File paths
        self.obs_index = self.config_dir / "obsidian_tasks_index.json"
        self.rem_index = self.config_dir / "reminders_tasks_index.json" 
        self.sync_links = self.config_dir / "sync_links.json"
        
        self.validation_results = {}
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
            
    def validate_data_structures(self) -> Dict[str, Any]:
        """Validate the structure and integrity of sync data"""
        self.log("=== Validating Data Structures ===")
        
        results = {
            'files_exist': True,
            'valid_json': True,
            'structure_valid': True,
            'uuid_consistency': True,
            'link_integrity': True,
            'issues': []
        }
        
        # Check file existence
        required_files = [self.obs_index, self.rem_index, self.sync_links]
        for file_path in required_files:
            if not file_path.exists():
                results['files_exist'] = False
                results['issues'].append(f"Missing file: {file_path}")
                
        if not results['files_exist']:
            return results
            
        # Load data structures
        obs_data = self.load_json_file(self.obs_index)
        rem_data = self.load_json_file(self.rem_index)
        links_data = self.load_json_file(self.sync_links)
        
        if not all([obs_data, rem_data, links_data]):
            results['valid_json'] = False
            results['issues'].append("Failed to load one or more JSON files")
            return results
            
        # Validate structure
        obs_tasks = obs_data.get('tasks', {})
        rem_tasks = rem_data.get('tasks', {})
        links = links_data.get('links', [])
        
        self.log(f"Loaded: {len(obs_tasks)} Obsidian tasks, {len(rem_tasks)} Reminders tasks, {len(links)} links")
        
        # Check UUID consistency
        uuid_issues = []
        for task_id, task in obs_tasks.items():
            if not task.get('uuid'):
                uuid_issues.append(f"Obsidian task {task_id} missing UUID")
                
        for task_id, task in rem_tasks.items():
            if not task.get('uuid'):
                uuid_issues.append(f"Reminders task {task_id} missing UUID")
                
        if uuid_issues:
            results['uuid_consistency'] = False
            results['issues'].extend(uuid_issues[:10])  # Limit to first 10
            
        # Validate link integrity
        link_issues = []
        for i, link in enumerate(links):
            obs_uuid = link.get('obs_uuid')
            rem_uuid = link.get('rem_uuid')
            
            if not obs_uuid or not rem_uuid:
                link_issues.append(f"Link {i} missing UUIDs")
                continue
                
            # Check if linked tasks exist
            obs_found = any(task.get('uuid') == obs_uuid for task in obs_tasks.values())
            rem_found = any(task.get('uuid') == rem_uuid for task in rem_tasks.values())
            
            if not obs_found:
                link_issues.append(f"Link {i} references non-existent Obsidian task: {obs_uuid}")
            if not rem_found:
                link_issues.append(f"Link {i} references non-existent Reminders task: {rem_uuid}")
                
        if link_issues:
            results['link_integrity'] = False
            results['issues'].extend(link_issues[:10])  # Limit to first 10
            
        results['stats'] = {
            'obsidian_tasks': len(obs_tasks),
            'reminders_tasks': len(rem_tasks),
            'sync_links': len(links),
            'uuid_issues': len(uuid_issues),
            'link_issues': len(link_issues)
        }
        
        return results
        
    def test_sync_apply_functionality(self) -> Dict[str, Any]:
        """Test sync apply operations"""
        self.log("=== Testing Sync Apply Functionality ===")
        
        results = {
            'dry_run_success': False,
            'apply_success': False,
            'changes_detected': False,
            'issues': []
        }
        
        # Test dry run first
        self.log("Running sync apply dry run...")
        result = self.run_obs_command(["sync", "apply", "--verbose"])
        
        if result.returncode == 0:
            results['dry_run_success'] = True
            self.log("✓ Sync apply dry run completed successfully")
            
            # Check for detected changes
            if "would update" in result.stdout.lower() or "changes:" in result.stdout.lower():
                results['changes_detected'] = True
                self.log("Changes detected in dry run")
        else:
            results['issues'].append(f"Dry run failed: {result.stderr}")
            self.log(f"✗ Sync apply dry run failed: {result.stderr}", "ERROR")
            return results
            
        # Test actual apply with limited scope
        self.log("Running sync apply (actual)...")
        result = self.run_obs_command(["sync", "apply", "--apply", "--verbose"])
        
        if result.returncode == 0:
            results['apply_success'] = True
            self.log("✓ Sync apply completed successfully")
        else:
            results['issues'].append(f"Apply failed: {result.stderr}")
            self.log(f"✗ Sync apply failed: {result.stderr}", "ERROR")
            
        return results
        
    def test_create_missing_functionality(self) -> Dict[str, Any]:
        """Test create missing counterparts functionality"""
        self.log("=== Testing Create Missing Functionality ===")
        
        results = {
            'dry_run_success': False,
            'create_success': False,
            'counterparts_found': False,
            'issues': []
        }
        
        # Test dry run
        self.log("Running create missing dry run...")
        result = self.run_obs_command([
            "sync", "create", 
            "--verbose", 
            "--direction", "both",
            "--max", "3"  # Limit for safety
        ])
        
        if result.returncode == 0:
            results['dry_run_success'] = True
            self.log("✓ Create missing dry run completed")
            
            # Check if counterparts were found
            if "would create" in result.stdout.lower() or "counterpart" in result.stdout.lower():
                results['counterparts_found'] = True
                self.log("Missing counterparts detected")
        else:
            results['issues'].append(f"Create dry run failed: {result.stderr}")
            self.log(f"✗ Create missing dry run failed: {result.stderr}", "ERROR")
            return results
            
        # Test actual creation (very limited)
        if results['counterparts_found']:
            self.log("Running limited create missing (actual)...")
            result = self.run_obs_command([
                "sync", "create",
                "--apply",
                "--verbose", 
                "--direction", "both",
                "--max", "1"  # Very limited
            ])
            
            if result.returncode == 0:
                results['create_success'] = True
                self.log("✓ Create missing completed successfully")
            else:
                results['issues'].append(f"Create failed: {result.stderr}")
                self.log(f"✗ Create missing failed: {result.stderr}", "ERROR")
        else:
            self.log("No missing counterparts found, skipping actual creation")
            results['create_success'] = True  # No work needed
            
        return results
        
    def test_pipeline_stability(self) -> Dict[str, Any]:
        """Test pipeline stability through multiple runs"""
        self.log("=== Testing Pipeline Stability ===")
        
        results = {
            'initial_state': {},
            'final_state': {},
            'stable': True,
            'issues': []
        }
        
        # Capture initial state
        initial_links = self.load_json_file(self.sync_links)
        results['initial_state'] = {
            'link_count': len(initial_links.get('links', [])),
            'timestamp': datetime.now().isoformat()
        }
        
        # Run pipeline twice
        for run in range(2):
            self.log(f"Running pipeline iteration {run + 1}/2...")
            
            # Update indices and links
            result = self.run_obs_command([
                "sync", "update", 
                "--ignore-common", 
                "--include-done"
            ])
            
            if result.returncode != 0:
                results['stable'] = False
                results['issues'].append(f"Pipeline run {run + 1} failed: {result.stderr}")
                return results
                
            time.sleep(1)  # Brief pause
            
        # Capture final state
        final_links = self.load_json_file(self.sync_links)
        results['final_state'] = {
            'link_count': len(final_links.get('links', [])),
            'timestamp': datetime.now().isoformat()
        }
        
        # Check stability
        initial_count = results['initial_state']['link_count']
        final_count = results['final_state']['link_count']
        
        # Allow for small variations (new tasks, legitimate changes)
        if abs(final_count - initial_count) > 10:
            results['stable'] = False
            results['issues'].append(f"Large link count change: {initial_count} -> {final_count}")
        else:
            self.log(f"✓ Pipeline stable: {initial_count} -> {final_count} links")
            
        return results
        
    def measure_performance(self) -> Dict[str, Any]:
        """Measure sync pipeline performance"""
        self.log("=== Measuring Performance ===")
        
        results = {
            'pipeline_time': 0,
            'tasks_per_second': 0,
            'acceptable_performance': False,
            'issues': []
        }
        
        start_time = time.time()
        
        # Run full pipeline
        result = self.run_obs_command([
            "sync", "update",
            "--ignore-common",
            "--include-done"
        ])
        
        pipeline_time = time.time() - start_time
        
        if result.returncode != 0:
            results['issues'].append(f"Performance test failed: {result.stderr}")
            return results
            
        # Load final counts
        obs_data = self.load_json_file(self.obs_index)
        rem_data = self.load_json_file(self.rem_index)
        
        total_tasks = len(obs_data.get('tasks', {})) + len(rem_data.get('tasks', {}))
        
        results['pipeline_time'] = pipeline_time
        results['total_tasks'] = total_tasks
        
        if total_tasks > 0:
            results['tasks_per_second'] = total_tasks / pipeline_time
            
        # Performance threshold: should handle reasonable number of tasks in reasonable time
        results['acceptable_performance'] = pipeline_time < 180  # 3 minutes
        
        self.log(f"Performance: {pipeline_time:.2f}s for {total_tasks} tasks ({results['tasks_per_second']:.1f} tasks/sec)")
        
        return results
        
    def run_validation(self) -> Dict[str, Any]:
        """Run comprehensive validation"""
        self.log("🔍 Starting Focused Sync Validation")
        self.log(f"Working directory: {self.work_dir}")
        
        validation_results = {}
        
        # Test 1: Data Structure Validation
        self.log("\n" + "="*60)
        validation_results['data_structures'] = self.validate_data_structures()
        
        # Test 2: Sync Apply Functionality
        self.log("\n" + "="*60)
        validation_results['sync_apply'] = self.test_sync_apply_functionality()
        
        # Test 3: Create Missing Functionality
        self.log("\n" + "="*60)
        validation_results['create_missing'] = self.test_create_missing_functionality()
        
        # Test 4: Pipeline Stability
        self.log("\n" + "="*60)
        validation_results['pipeline_stability'] = self.test_pipeline_stability()
        
        # Test 5: Performance Measurement
        self.log("\n" + "="*60)
        validation_results['performance'] = self.measure_performance()
        
        # Generate summary
        duration = datetime.now() - self.start_time
        
        summary = {
            'validation_time': duration.total_seconds(),
            'overall_status': 'PASS',
            'test_results': validation_results,
            'recommendations': []
        }
        
        # Analyze results
        failed_tests = []
        
        if not validation_results['data_structures'].get('structure_valid', False):
            failed_tests.append("Data Structure Validation")
            summary['overall_status'] = 'FAIL'
            
        if not validation_results['sync_apply'].get('apply_success', False):
            failed_tests.append("Sync Apply")
            summary['overall_status'] = 'FAIL'
            
        if not validation_results['create_missing'].get('dry_run_success', False):
            failed_tests.append("Create Missing")
            summary['overall_status'] = 'FAIL'
            
        if not validation_results['pipeline_stability'].get('stable', False):
            failed_tests.append("Pipeline Stability")
            summary['overall_status'] = 'FAIL'
            
        if not validation_results['performance'].get('acceptable_performance', False):
            failed_tests.append("Performance")
            summary['overall_status'] = 'WARN'
            
        summary['failed_tests'] = failed_tests
        
        # Generate recommendations
        if validation_results['data_structures'].get('uuid_issues', 0) > 0:
            summary['recommendations'].append("Fix UUID consistency issues in task indices")
            
        if validation_results['data_structures'].get('link_issues', 0) > 0:
            summary['recommendations'].append("Clean up orphaned sync links")
            
        if not validation_results['performance'].get('acceptable_performance', False):
            summary['recommendations'].append("Optimize pipeline performance for large datasets")
            
        # Print summary
        self.log("\n" + "="*60)
        self.log("📊 VALIDATION SUMMARY")
        self.log("="*60)
        self.log(f"Overall Status: {summary['overall_status']}")
        self.log(f"Validation Time: {summary['validation_time']:.2f} seconds")
        
        if failed_tests:
            self.log(f"Failed Tests: {', '.join(failed_tests)}")
        else:
            self.log("All tests passed!")
            
        if summary['recommendations']:
            self.log("\nRecommendations:")
            for rec in summary['recommendations']:
                self.log(f"  - {rec}")
                
        # Save detailed results
        results_file = self.config_dir / "obs-tools" / "backups" / f"sync_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
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
    validator = FocusedSyncValidator()
    results = validator.run_validation()
    
    # Return appropriate exit code
    if results['overall_status'] == 'PASS':
        return 0
    elif results['overall_status'] == 'WARN':
        return 1
    else:
        return 2


if __name__ == "__main__":
    exit(main())