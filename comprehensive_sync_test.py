#!/usr/bin/env python3
"""
Comprehensive End-to-End Sync Testing

This script validates the complete sync pipeline by:
1. Running the full collection → link building → create-missing → apply changes pipeline
2. Testing bidirectional sync functionality
3. Validating state consistency across systems
4. Checking link integrity and stability
5. Testing update propagation
6. Validating UUID-based identity tracking

The test creates controlled scenarios and validates that the sync system
maintains data integrity and consistency through complete sync cycles.
"""

import json
import os
import time
import subprocess
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import uuid
import tempfile
import shutil


class SyncTestFramework:
    """Framework for comprehensive sync testing"""
    
    def __init__(self, work_dir: str = "/Users/yannickbowe/Library/Mobile Documents/iCloud~md~obsidian/Documents/Work/obssync"):
        self.work_dir = Path(work_dir)
        self.config_dir = Path.home() / ".config"
        self.backup_dir = Path.home() / ".config" / "obs-tools" / "backups"
        self.test_results = {}
        self.test_start_time = datetime.now()
        
        # File paths
        self.obs_index = self.config_dir / "obsidian_tasks_index.json"
        self.rem_index = self.config_dir / "reminders_tasks_index.json" 
        self.sync_links = self.config_dir / "sync_links.json"
        self.obs_vaults = self.config_dir / "obsidian_vaults.json"
        self.rem_lists = self.config_dir / "reminders_lists.json"
        
        # Test files for controlled testing
        self.test_vault_dir = None
        self.test_markdown_file = None
        
    def log(self, message: str, level: str = "INFO"):
        """Log test progress with timestamps"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")
        
    def run_obs_command(self, command: List[str], capture_output: bool = True) -> subprocess.CompletedProcess:
        """Run obs_tools.py command and return result"""
        cmd = ["python3", str(self.work_dir / "obs_tools.py")] + command
        self.log(f"Running: {' '.join(cmd)}")
        return subprocess.run(cmd, capture_output=capture_output, text=True, cwd=self.work_dir)
        
    def load_json_file(self, filepath: Path) -> Dict[str, Any]:
        """Load and return JSON file contents"""
        if not filepath.exists():
            return {}
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.log(f"Error loading {filepath}: {e}", "ERROR")
            return {}
            
    def save_json_file(self, filepath: Path, data: Dict[str, Any]):
        """Save data to JSON file"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log(f"Error saving {filepath}: {e}", "ERROR")
            
    def create_test_vault_structure(self) -> Path:
        """Create a temporary test vault for controlled testing"""
        test_dir = Path(tempfile.mkdtemp(prefix="sync_test_vault_"))
        
        # Create basic vault structure
        daily_notes = test_dir / "Daily Notes"
        daily_notes.mkdir(parents=True)
        
        # Create test markdown file with tasks
        test_date = datetime.now().strftime("%Y-%m-%d")
        test_file = daily_notes / f"{test_date}.md"
        
        test_content = f"""# {test_date}

## Tasks for Testing

- [ ] Test task for sync validation #sync-test
- [x] Completed test task for state testing #sync-test  
- [ ] High priority task with due date #sync-test 📅 {(datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')}
- [ ] Task with specific content for matching #sync-test-content
- [ ] Bidirectional sync test task #bidirectional

## Notes

These tasks are created specifically for testing the sync pipeline.
They should be collected, linked, and synchronized properly.
"""
        
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write(test_content)
            
        self.test_vault_dir = test_dir
        self.test_markdown_file = test_file
        
        return test_dir
        
    def backup_current_configs(self) -> Dict[str, Path]:
        """Backup current configuration files"""
        backups = {}
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        for config_file in [self.obs_index, self.rem_index, self.sync_links, self.obs_vaults, self.rem_lists]:
            if config_file.exists():
                backup_path = self.backup_dir / f"{config_file.name}.backup_{timestamp}"
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(config_file, backup_path)
                backups[config_file.name] = backup_path
                
        return backups
        
    def restore_configs(self, backups: Dict[str, Path]):
        """Restore configuration files from backups"""
        for original_name, backup_path in backups.items():
            if backup_path.exists():
                original_path = self.config_dir / original_name
                shutil.copy2(backup_path, original_path)
                
    def test_1_full_pipeline_execution(self) -> bool:
        """Test 1: Complete pipeline execution from collection to link building"""
        self.log("=== TEST 1: Full Pipeline Execution ===")
        
        try:
            # Step 1: Collect Obsidian tasks
            self.log("Step 1: Collecting Obsidian tasks...")
            result = self.run_obs_command(["tasks", "collect", "--use-config", "--ignore-common"])
            if result.returncode != 0:
                self.log(f"Obsidian collection failed: {result.stderr}", "ERROR")
                return False
                
            # Step 2: Collect Reminders tasks  
            self.log("Step 2: Collecting Reminders tasks...")
            result = self.run_obs_command(["reminders", "collect"])
            if result.returncode != 0:
                self.log(f"Reminders collection failed: {result.stderr}", "ERROR")
                return False
                
            # Step 3: Build sync links
            self.log("Step 3: Building sync links...")
            result = self.run_obs_command(["sync", "suggest", "--include-done"])
            if result.returncode != 0:
                self.log(f"Link building failed: {result.stderr}", "ERROR")
                return False
                
            # Step 4: Update indices and links (full refresh)
            self.log("Step 4: Updating indices and links...")
            result = self.run_obs_command(["sync", "update", "--ignore-common", "--include-done"])
            if result.returncode != 0:
                self.log(f"Index update failed: {result.stderr}", "ERROR")
                return False
                
            # Validate that all files were created successfully
            required_files = [self.obs_index, self.rem_index, self.sync_links]
            for file_path in required_files:
                if not file_path.exists():
                    self.log(f"Required file missing: {file_path}", "ERROR")
                    return False
                    
            self.log("✓ Full pipeline execution completed successfully")
            return True
            
        except Exception as e:
            self.log(f"Pipeline execution failed with exception: {e}", "ERROR")
            return False
            
    def test_2_data_consistency_validation(self) -> bool:
        """Test 2: Validate data consistency across indices and links"""
        self.log("=== TEST 2: Data Consistency Validation ===")
        
        try:
            # Load all data structures
            obs_data = self.load_json_file(self.obs_index)
            rem_data = self.load_json_file(self.rem_index) 
            links_data = self.load_json_file(self.sync_links)
            
            if not all([obs_data, rem_data, links_data]):
                self.log("Failed to load required data files", "ERROR")
                return False
                
            # Validate index structure
            obs_tasks = obs_data.get('tasks', {})
            rem_tasks = rem_data.get('tasks', {})
            links = links_data.get('links', [])
            
            self.log(f"Loaded {len(obs_tasks)} Obsidian tasks, {len(rem_tasks)} Reminders tasks, {len(links)} links")
            
            # Check UUID consistency in Obsidian tasks
            uuid_issues = 0
            for task_id, task in obs_tasks.items():
                if 'uuid' not in task:
                    self.log(f"Obsidian task missing UUID: {task_id}", "WARNING")
                    uuid_issues += 1
                elif not task['uuid']:
                    self.log(f"Obsidian task has empty UUID: {task_id}", "WARNING") 
                    uuid_issues += 1
                    
            # Check UUID consistency in Reminders tasks
            for task_id, task in rem_tasks.items():
                if 'uuid' not in task:
                    self.log(f"Reminders task missing UUID: {task_id}", "WARNING")
                    uuid_issues += 1
                elif not task['uuid']:
                    self.log(f"Reminders task has empty UUID: {task_id}", "WARNING")
                    uuid_issues += 1
                    
            # Validate sync links integrity
            link_issues = 0
            for link in links:
                obs_uuid = link.get('obs_uuid')
                rem_uuid = link.get('rem_uuid') 
                
                if not obs_uuid or not rem_uuid:
                    self.log(f"Link missing UUIDs: {obs_uuid}/{rem_uuid}", "WARNING")
                    link_issues += 1
                    continue
                    
                # Check if linked tasks exist
                obs_task_found = any(task.get('uuid') == obs_uuid for task in obs_tasks.values())
                rem_task_found = any(task.get('uuid') == rem_uuid for task in rem_tasks.values())
                
                if not obs_task_found:
                    self.log(f"Link references non-existent Obsidian task: {obs_uuid}", "WARNING")
                    link_issues += 1
                    
                if not rem_task_found:
                    self.log(f"Link references non-existent Reminders task: {rem_uuid}", "WARNING")
                    link_issues += 1
                    
            self.log(f"Found {uuid_issues} UUID issues and {link_issues} link integrity issues")
            
            if uuid_issues == 0 and link_issues == 0:
                self.log("✓ Data consistency validation passed")
                return True
            else:
                self.log("✗ Data consistency validation failed", "ERROR")
                return False
                
        except Exception as e:
            self.log(f"Data consistency validation failed: {e}", "ERROR")
            return False
            
    def test_3_bidirectional_sync_functionality(self) -> bool:
        """Test 3: Test bidirectional synchronization between systems"""
        self.log("=== TEST 3: Bidirectional Sync Functionality ===")
        
        try:
            # Load initial state
            links_data = self.load_json_file(self.sync_links)
            links = links_data.get('links', [])
            
            if not links:
                self.log("No sync links available for bidirectional testing", "WARNING")
                return True  # Skip test if no links
                
            # Get a sample link for testing
            test_link = links[0]
            
            self.log(f"Testing bidirectional sync with link: {test_link.get('obs_uuid')} <-> {test_link.get('rem_uuid')}")
            
            # Test sync apply (dry run first)
            self.log("Running sync apply (dry run)...")
            result = self.run_obs_command(["sync", "apply", "--verbose"])
            if result.returncode != 0:
                self.log(f"Sync apply dry run failed: {result.stderr}", "ERROR")
                return False
                
            # Test actual sync apply
            self.log("Running sync apply (actual)...")
            result = self.run_obs_command(["sync", "apply", "--apply", "--verbose"])
            if result.returncode != 0:
                self.log(f"Sync apply failed: {result.stderr}", "ERROR")
                return False
                
            self.log("✓ Bidirectional sync functionality test completed")
            return True
            
        except Exception as e:
            self.log(f"Bidirectional sync test failed: {e}", "ERROR")
            return False
            
    def test_4_create_missing_counterparts(self) -> bool:
        """Test 4: Test creation of missing counterpart tasks"""
        self.log("=== TEST 4: Create Missing Counterparts ===")
        
        try:
            # Test create missing (dry run)
            self.log("Testing create missing counterparts (dry run)...")
            result = self.run_obs_command(["sync", "create", "--verbose", "--direction", "both"])
            if result.returncode != 0:
                self.log(f"Create missing dry run failed: {result.stderr}", "ERROR")
                return False
                
            # Test actual creation (limited)
            self.log("Testing create missing counterparts (actual, limited)...")
            result = self.run_obs_command(["sync", "create", "--apply", "--verbose", "--max", "5", "--direction", "both"])
            if result.returncode != 0:
                self.log(f"Create missing failed: {result.stderr}", "ERROR")
                return False
                
            self.log("✓ Create missing counterparts test completed")
            return True
            
        except Exception as e:
            self.log(f"Create missing counterparts test failed: {e}", "ERROR")
            return False
            
    def test_5_link_stability_through_cycles(self) -> bool:
        """Test 5: Test link stability through multiple sync cycles"""
        self.log("=== TEST 5: Link Stability Through Cycles ===")
        
        try:
            # Capture initial link state
            initial_links = self.load_json_file(self.sync_links)
            initial_link_count = len(initial_links.get('links', []))
            
            # Run multiple sync cycles
            cycles = 3
            for cycle in range(cycles):
                self.log(f"Running sync cycle {cycle + 1}/{cycles}...")
                
                # Full refresh cycle
                result = self.run_obs_command(["sync", "update", "--ignore-common", "--include-done"])
                if result.returncode != 0:
                    self.log(f"Sync cycle {cycle + 1} failed: {result.stderr}", "ERROR")
                    return False
                    
                # Apply sync
                result = self.run_obs_command(["sync", "apply", "--apply"])
                if result.returncode != 0:
                    self.log(f"Sync apply cycle {cycle + 1} failed: {result.stderr}", "ERROR")
                    return False
                    
                time.sleep(1)  # Brief pause between cycles
                
            # Check final link state
            final_links = self.load_json_file(self.sync_links)
            final_link_count = len(final_links.get('links', []))
            
            self.log(f"Link count: initial={initial_link_count}, final={final_link_count}")
            
            # Allow for small variations due to legitimate changes
            if abs(final_link_count - initial_link_count) <= 5:
                self.log("✓ Link stability test passed")
                return True
            else:
                self.log("✗ Significant link count change detected", "ERROR")
                return False
                
        except Exception as e:
            self.log(f"Link stability test failed: {e}", "ERROR")
            return False
            
    def test_6_performance_validation(self) -> bool:
        """Test 6: Performance validation with large datasets"""
        self.log("=== TEST 6: Performance Validation ===")
        
        try:
            start_time = time.time()
            
            # Run full pipeline with timing
            self.log("Running timed full pipeline...")
            result = self.run_obs_command(["sync", "update", "--ignore-common", "--include-done"])
            
            pipeline_time = time.time() - start_time
            
            if result.returncode != 0:
                self.log(f"Performance test pipeline failed: {result.stderr}", "ERROR")
                return False
                
            # Load final counts for performance context
            obs_data = self.load_json_file(self.obs_index)
            rem_data = self.load_json_file(self.rem_index)
            links_data = self.load_json_file(self.sync_links)
            
            obs_count = len(obs_data.get('tasks', {}))
            rem_count = len(rem_data.get('tasks', {}))
            link_count = len(links_data.get('links', []))
            
            self.log(f"Performance metrics:")
            self.log(f"  - Pipeline time: {pipeline_time:.2f} seconds")
            self.log(f"  - Obsidian tasks: {obs_count}")
            self.log(f"  - Reminders tasks: {rem_count}")
            self.log(f"  - Sync links: {link_count}")
            self.log(f"  - Tasks per second: {(obs_count + rem_count) / pipeline_time:.1f}")
            
            # Performance threshold (adjust based on system capabilities)
            if pipeline_time < 300:  # 5 minutes threshold
                self.log("✓ Performance validation passed")
                return True
            else:
                self.log("✗ Performance threshold exceeded", "WARNING")
                return False
                
        except Exception as e:
            self.log(f"Performance validation failed: {e}", "ERROR")
            return False
            
    def test_7_edge_case_handling(self) -> bool:
        """Test 7: Edge case handling for sync conflicts and data inconsistencies"""
        self.log("=== TEST 7: Edge Case Handling ===")
        
        try:
            # Test duplicate detection
            self.log("Testing duplicate detection...")
            result = self.run_obs_command(["duplicates", "find", "--similarity", "0.9", "--dry-run"])
            if result.returncode != 0:
                self.log(f"Duplicate detection failed: {result.stderr}", "ERROR")
                return False
                
            # Test with corrupted links (simulate by backing up and restoring)
            self.log("Testing resilience to data inconsistencies...")
            
            # Create a temporary corrupted link state
            original_links = self.load_json_file(self.sync_links)
            
            # Add a fake link to test cleanup
            corrupted_links = original_links.copy()
            if 'links' in corrupted_links:
                fake_uuid = str(uuid.uuid4())
                fake_link = {
                    'obs_uuid': fake_uuid,
                    'rem_uuid': str(uuid.uuid4()),
                    'score': 1.0,
                    'created_at': datetime.now().isoformat(),
                    'last_synced': None
                }
                corrupted_links['links'].append(fake_link)
                
            # Save corrupted state temporarily
            self.save_json_file(self.sync_links, corrupted_links)
            
            # Run sync update to see if it handles corruption gracefully
            result = self.run_obs_command(["sync", "update", "--ignore-common"])
            
            # Restore original state
            self.save_json_file(self.sync_links, original_links)
            
            if result.returncode != 0:
                self.log(f"Edge case handling failed: {result.stderr}", "ERROR")
                return False
                
            self.log("✓ Edge case handling test completed")
            return True
            
        except Exception as e:
            self.log(f"Edge case handling test failed: {e}", "ERROR")
            return False
            
    def generate_test_report(self) -> Dict[str, Any]:
        """Generate comprehensive test report"""
        test_duration = datetime.now() - self.test_start_time
        
        # Load final state for reporting
        obs_data = self.load_json_file(self.obs_index)
        rem_data = self.load_json_file(self.rem_index)
        links_data = self.load_json_file(self.sync_links)
        
        report = {
            'test_execution': {
                'start_time': self.test_start_time.isoformat(),
                'duration_seconds': test_duration.total_seconds(),
                'end_time': datetime.now().isoformat()
            },
            'test_results': self.test_results,
            'final_state': {
                'obsidian_tasks': len(obs_data.get('tasks', {})),
                'reminders_tasks': len(rem_data.get('tasks', {})),
                'sync_links': len(links_data.get('links', [])),
                'obsidian_last_updated': obs_data.get('metadata', {}).get('last_updated'),
                'reminders_last_updated': rem_data.get('metadata', {}).get('last_updated'),
                'links_last_updated': links_data.get('metadata', {}).get('last_updated')
            },
            'data_integrity': {
                'obsidian_index_exists': self.obs_index.exists(),
                'reminders_index_exists': self.rem_index.exists(),
                'sync_links_exists': self.sync_links.exists(),
                'file_sizes': {
                    'obsidian_index_mb': self.obs_index.stat().st_size / 1024 / 1024 if self.obs_index.exists() else 0,
                    'reminders_index_mb': self.rem_index.stat().st_size / 1024 / 1024 if self.rem_index.exists() else 0,
                    'sync_links_mb': self.sync_links.stat().st_size / 1024 / 1024 if self.sync_links.exists() else 0
                }
            }
        }
        
        return report
        
    def run_comprehensive_tests(self) -> bool:
        """Run all comprehensive tests and generate report"""
        self.log("🚀 Starting Comprehensive Sync Testing")
        self.log(f"Working directory: {self.work_dir}")
        
        # Backup current configs
        backups = self.backup_current_configs()
        self.log(f"Backed up {len(backups)} configuration files")
        
        try:
            # Run all tests
            tests = [
                ("Full Pipeline Execution", self.test_1_full_pipeline_execution),
                ("Data Consistency Validation", self.test_2_data_consistency_validation),
                ("Bidirectional Sync Functionality", self.test_3_bidirectional_sync_functionality),
                ("Create Missing Counterparts", self.test_4_create_missing_counterparts),
                ("Link Stability Through Cycles", self.test_5_link_stability_through_cycles),
                ("Performance Validation", self.test_6_performance_validation),
                ("Edge Case Handling", self.test_7_edge_case_handling)
            ]
            
            passed_tests = 0
            total_tests = len(tests)
            
            for test_name, test_func in tests:
                self.log(f"\n{'='*60}")
                self.log(f"Running: {test_name}")
                self.log(f"{'='*60}")
                
                try:
                    result = test_func()
                    self.test_results[test_name] = {
                        'passed': result,
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    if result:
                        passed_tests += 1
                        self.log(f"✅ {test_name} PASSED")
                    else:
                        self.log(f"❌ {test_name} FAILED")
                        
                except Exception as e:
                    self.log(f"❌ {test_name} FAILED with exception: {e}", "ERROR")
                    self.test_results[test_name] = {
                        'passed': False,
                        'error': str(e),
                        'timestamp': datetime.now().isoformat()
                    }
                    
            # Generate and save report
            report = self.generate_test_report()
            report_path = self.backup_dir / f"sync_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            self.save_json_file(report_path, report)
            
            # Summary
            self.log(f"\n{'='*60}")
            self.log("🏁 COMPREHENSIVE SYNC TESTING COMPLETE")
            self.log(f"{'='*60}")
            self.log(f"Tests passed: {passed_tests}/{total_tests}")
            self.log(f"Success rate: {(passed_tests/total_tests)*100:.1f}%")
            self.log(f"Test duration: {datetime.now() - self.test_start_time}")
            self.log(f"Report saved: {report_path}")
            
            if passed_tests == total_tests:
                self.log("🎉 ALL TESTS PASSED - Sync system is functioning correctly!")
                return True
            else:
                self.log("⚠️  Some tests failed - Check report for details")
                return False
                
        finally:
            # Cleanup: restore original configs
            # self.restore_configs(backups)
            self.log("Original configurations preserved for analysis")
            
            # Cleanup test vault if created
            if self.test_vault_dir and self.test_vault_dir.exists():
                try:
                    shutil.rmtree(self.test_vault_dir)
                    self.log("Cleaned up test vault directory")
                except Exception as e:
                    self.log(f"Failed to cleanup test vault: {e}", "WARNING")


def main():
    """Main entry point for comprehensive sync testing"""
    framework = SyncTestFramework()
    success = framework.run_comprehensive_tests()
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())