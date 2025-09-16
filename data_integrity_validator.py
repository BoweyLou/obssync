#!/usr/bin/env python3
"""
Data Integrity Validator

This script performs comprehensive data integrity validation including:
- UUID consistency and uniqueness validation
- Timestamp integrity and chronological validation
- Referential integrity between linked tasks
- Corruption detection and recovery recommendations
- Index consistency verification
"""

import json
import os
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime, timezone
import uuid as uuid_module
import re


class DataIntegrityValidator:
    """Comprehensive data integrity validator"""
    
    def __init__(self, work_dir: str = "/Users/yannickbowe/Library/Mobile Documents/iCloud~md~obsidian/Documents/Work/obssync"):
        self.work_dir = Path(work_dir)
        self.config_dir = Path.home() / ".config"
        
        # File paths
        self.obs_index = self.config_dir / "obsidian_tasks_index.json"
        self.rem_index = self.config_dir / "reminders_tasks_index.json"
        self.sync_links = self.config_dir / "sync_links.json"
        self.obs_cache = self.config_dir / "obsidian_tasks_cache.json"
        
        # Validation results
        self.validation_results = {}
        
    def log(self, message: str, level: str = "INFO"):
        """Log with timestamps"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] {level}: {message}")
        
    def validate_uuid_integrity(self) -> Dict[str, Any]:
        """Validate UUID consistency and uniqueness across all systems"""
        self.log("=== Validating UUID Integrity ===")
        
        results = {
            'uuid_validation': {
                'obsidian_uuids': {'total': 0, 'valid': 0, 'invalid': [], 'duplicates': []},
                'reminders_uuids': {'total': 0, 'valid': 0, 'invalid': [], 'duplicates': []},
                'cross_system_conflicts': [],
                'orphaned_references': []
            },
            'overall_integrity': True,
            'critical_issues': []
        }
        
        try:
            # Load all data
            obs_data = json.loads(self.obs_index.read_text()) if self.obs_index.exists() else {}
            rem_data = json.loads(self.rem_index.read_text()) if self.rem_index.exists() else {}
            links_data = json.loads(self.sync_links.read_text()) if self.sync_links.exists() else {}
            
            obs_tasks = obs_data.get('tasks', {})
            rem_tasks = rem_data.get('tasks', {})
            links = links_data.get('links', [])
            
            # Validate Obsidian UUIDs
            self.log("Validating Obsidian task UUIDs...")
            obs_uuid_counts = {}
            for task_id, task in obs_tasks.items():
                task_uuid = task.get('uuid')
                results['uuid_validation']['obsidian_uuids']['total'] += 1
                
                if not task_uuid:
                    results['uuid_validation']['obsidian_uuids']['invalid'].append(f"Task {task_id}: No UUID")
                    continue
                    
                # Validate UUID format
                try:
                    uuid_module.UUID(task_uuid)
                    results['uuid_validation']['obsidian_uuids']['valid'] += 1
                except ValueError:
                    results['uuid_validation']['obsidian_uuids']['invalid'].append(f"Task {task_id}: Invalid UUID format: {task_uuid}")
                    continue
                    
                # Track for duplicates
                obs_uuid_counts[task_uuid] = obs_uuid_counts.get(task_uuid, 0) + 1
                
            # Check for duplicate Obsidian UUIDs
            for uuid_val, count in obs_uuid_counts.items():
                if count > 1:
                    results['uuid_validation']['obsidian_uuids']['duplicates'].append(f"UUID {uuid_val} appears {count} times")
                    
            # Validate Reminders UUIDs
            self.log("Validating Reminders task UUIDs...")
            rem_uuid_counts = {}
            for task_id, task in rem_tasks.items():
                task_uuid = task.get('uuid')
                results['uuid_validation']['reminders_uuids']['total'] += 1
                
                if not task_uuid:
                    results['uuid_validation']['reminders_uuids']['invalid'].append(f"Task {task_id}: No UUID")
                    continue
                    
                # Validate UUID format
                try:
                    uuid_module.UUID(task_uuid)
                    results['uuid_validation']['reminders_uuids']['valid'] += 1
                except ValueError:
                    results['uuid_validation']['reminders_uuids']['invalid'].append(f"Task {task_id}: Invalid UUID format: {task_uuid}")
                    continue
                    
                # Track for duplicates
                rem_uuid_counts[task_uuid] = rem_uuid_counts.get(task_uuid, 0) + 1
                
            # Check for duplicate Reminders UUIDs
            for uuid_val, count in rem_uuid_counts.items():
                if count > 1:
                    results['uuid_validation']['reminders_uuids']['duplicates'].append(f"UUID {uuid_val} appears {count} times")
                    
            # Check for cross-system UUID conflicts
            obs_uuid_set = set(obs_uuid_counts.keys())
            rem_uuid_set = set(rem_uuid_counts.keys())
            conflicts = obs_uuid_set & rem_uuid_set
            
            for conflict_uuid in conflicts:
                results['uuid_validation']['cross_system_conflicts'].append(f"UUID {conflict_uuid} exists in both systems")
                
            # Validate link references
            self.log("Validating link UUID references...")
            for link in links:
                obs_uuid = link.get('obs_uuid')
                rem_uuid = link.get('rem_uuid')
                
                if obs_uuid and obs_uuid not in obs_uuid_set:
                    results['uuid_validation']['orphaned_references'].append(f"Link references non-existent Obsidian UUID: {obs_uuid}")
                    
                if rem_uuid and rem_uuid not in rem_uuid_set:
                    results['uuid_validation']['orphaned_references'].append(f"Link references non-existent Reminders UUID: {rem_uuid}")
                    
            # Assess overall integrity
            total_issues = (
                len(results['uuid_validation']['obsidian_uuids']['invalid']) +
                len(results['uuid_validation']['reminders_uuids']['invalid']) +
                len(results['uuid_validation']['obsidian_uuids']['duplicates']) +
                len(results['uuid_validation']['reminders_uuids']['duplicates']) +
                len(results['uuid_validation']['cross_system_conflicts']) +
                len(results['uuid_validation']['orphaned_references'])
            )
            
            if total_issues > 0:
                results['overall_integrity'] = False
                results['critical_issues'].append(f"Found {total_issues} UUID integrity issues")
                
            self.log(f"UUID Validation: Obs({results['uuid_validation']['obsidian_uuids']['valid']}/{results['uuid_validation']['obsidian_uuids']['total']}), Rem({results['uuid_validation']['reminders_uuids']['valid']}/{results['uuid_validation']['reminders_uuids']['total']})")
            
        except Exception as e:
            self.log(f"Error in UUID validation: {e}", "ERROR")
            results['overall_integrity'] = False
            results['critical_issues'].append(f"UUID validation failed: {e}")
            
        return results
        
    def validate_timestamp_integrity(self) -> Dict[str, Any]:
        """Validate timestamp consistency and chronological integrity"""
        self.log("=== Validating Timestamp Integrity ===")
        
        results = {
            'timestamp_validation': {
                'total_tasks_checked': 0,
                'valid_timestamps': 0,
                'invalid_timestamps': [],
                'chronological_issues': [],
                'timezone_inconsistencies': []
            },
            'temporal_consistency': True,
            'issues_found': []
        }
        
        try:
            # Load data
            obs_data = json.loads(self.obs_index.read_text()) if self.obs_index.exists() else {}
            rem_data = json.loads(self.rem_index.read_text()) if self.rem_index.exists() else {}
            
            obs_tasks = obs_data.get('tasks', {})
            rem_tasks = rem_data.get('tasks', {})
            
            # Validate Obsidian timestamps
            self.log("Validating Obsidian task timestamps...")
            for task_id, task in obs_tasks.items():
                results['timestamp_validation']['total_tasks_checked'] += 1
                
                # Check creation time
                created = task.get('created')
                modified = task.get('modified')
                completed_time = task.get('completed_time')
                
                if created:
                    if self._validate_timestamp_format(created):
                        results['timestamp_validation']['valid_timestamps'] += 1
                    else:
                        results['timestamp_validation']['invalid_timestamps'].append(f"Obs {task_id}: Invalid created timestamp: {created}")
                        
                # Check chronological consistency
                if created and modified:
                    try:
                        created_dt = self._parse_timestamp(created)
                        modified_dt = self._parse_timestamp(modified)
                        
                        if created_dt and modified_dt and created_dt > modified_dt:
                            results['timestamp_validation']['chronological_issues'].append(
                                f"Obs {task_id}: Created time ({created}) after modified time ({modified})"
                            )
                    except Exception:
                        pass  # Already logged as invalid timestamp
                        
            # Validate Reminders timestamps
            self.log("Validating Reminders task timestamps...")
            for task_id, task in rem_tasks.items():
                results['timestamp_validation']['total_tasks_checked'] += 1
                
                # Check various timestamp fields
                creation_date = task.get('creation_date')
                modification_date = task.get('modification_date')
                completion_date = task.get('completion_date')
                
                if creation_date:
                    if self._validate_timestamp_format(creation_date):
                        results['timestamp_validation']['valid_timestamps'] += 1
                    else:
                        results['timestamp_validation']['invalid_timestamps'].append(f"Rem {task_id}: Invalid creation timestamp: {creation_date}")
                        
                # Check chronological consistency
                if creation_date and completion_date:
                    try:
                        created_dt = self._parse_timestamp(creation_date)
                        completed_dt = self._parse_timestamp(completion_date)
                        
                        if created_dt and completed_dt and created_dt > completed_dt:
                            results['timestamp_validation']['chronological_issues'].append(
                                f"Rem {task_id}: Created time ({creation_date}) after completion time ({completion_date})"
                            )
                    except Exception:
                        pass
                        
            # Assess temporal consistency
            total_issues = (
                len(results['timestamp_validation']['invalid_timestamps']) +
                len(results['timestamp_validation']['chronological_issues']) +
                len(results['timestamp_validation']['timezone_inconsistencies'])
            )
            
            if total_issues > 0:
                results['temporal_consistency'] = False
                results['issues_found'].append(f"Found {total_issues} timestamp integrity issues")
                
            self.log(f"Timestamp Validation: {results['timestamp_validation']['valid_timestamps']}/{results['timestamp_validation']['total_tasks_checked']} valid")
            
        except Exception as e:
            self.log(f"Error in timestamp validation: {e}", "ERROR")
            results['temporal_consistency'] = False
            results['issues_found'].append(f"Timestamp validation failed: {e}")
            
        return results
        
    def _validate_timestamp_format(self, timestamp_str: str) -> bool:
        """Validate timestamp string format"""
        if not timestamp_str:
            return False
            
        # Common timestamp formats
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",  # ISO format with microseconds
            "%Y-%m-%dT%H:%M:%SZ",     # ISO format without microseconds
            "%Y-%m-%dT%H:%M:%S.%f%z", # ISO with timezone
            "%Y-%m-%dT%H:%M:%S%z",    # ISO with timezone, no microseconds
            "%Y-%m-%d %H:%M:%S",      # Simple format
        ]
        
        for fmt in formats:
            try:
                datetime.strptime(timestamp_str, fmt)
                return True
            except ValueError:
                continue
                
        return False
        
    def _parse_timestamp(self, timestamp_str: str) -> Optional[datetime]:
        """Parse timestamp string to datetime object"""
        if not timestamp_str:
            return None
            
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S",
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(timestamp_str, fmt)
            except ValueError:
                continue
                
        return None
        
    def validate_referential_integrity(self) -> Dict[str, Any]:
        """Validate referential integrity between linked tasks"""
        self.log("=== Validating Referential Integrity ===")
        
        results = {
            'referential_checks': {
                'total_links': 0,
                'valid_references': 0,
                'broken_references': [],
                'bidirectional_consistency': True,
                'data_consistency_issues': []
            },
            'integrity_score': 1.0,
            'recovery_recommendations': []
        }
        
        try:
            # Load data
            obs_data = json.loads(self.obs_index.read_text()) if self.obs_index.exists() else {}
            rem_data = json.loads(self.rem_index.read_text()) if self.rem_index.exists() else {}
            links_data = json.loads(self.sync_links.read_text()) if self.sync_links.exists() else {}
            
            obs_tasks = obs_data.get('tasks', {})
            rem_tasks = rem_data.get('tasks', {})
            links = links_data.get('links', [])
            
            # Create UUID to task mappings
            obs_uuid_map = {task.get('uuid'): task for task in obs_tasks.values() if task.get('uuid')}
            rem_uuid_map = {task.get('uuid'): task for task in rem_tasks.values() if task.get('uuid')}
            
            self.log(f"Checking referential integrity for {len(links)} links...")
            
            for i, link in enumerate(links):
                results['referential_checks']['total_links'] += 1
                
                obs_uuid = link.get('obs_uuid')
                rem_uuid = link.get('rem_uuid')
                
                # Check if referenced tasks exist
                obs_task = obs_uuid_map.get(obs_uuid) if obs_uuid else None
                rem_task = rem_uuid_map.get(rem_uuid) if rem_uuid else None
                
                if obs_uuid and not obs_task:
                    results['referential_checks']['broken_references'].append(
                        f"Link {i}: Obsidian UUID {obs_uuid} not found"
                    )
                    continue
                    
                if rem_uuid and not rem_task:
                    results['referential_checks']['broken_references'].append(
                        f"Link {i}: Reminders UUID {rem_uuid} not found"
                    )
                    continue
                    
                if obs_task and rem_task:
                    results['referential_checks']['valid_references'] += 1
                    
                    # Check data consistency between linked tasks
                    obs_completed = obs_task.get('completed', False)
                    rem_completed = rem_task.get('completed', False)
                    
                    if obs_completed != rem_completed:
                        results['referential_checks']['data_consistency_issues'].append(
                            f"Link {i}: Completion status mismatch - Obs: {obs_completed}, Rem: {rem_completed}"
                        )
                        results['referential_checks']['bidirectional_consistency'] = False
                        
                    # Check title similarity (basic validation)
                    obs_title = obs_task.get('title', '').strip().lower()
                    rem_title = rem_task.get('title', '').strip().lower()
                    
                    if obs_title and rem_title:
                        # Simple similarity check
                        if len(obs_title) > 10 and len(rem_title) > 10:
                            if obs_title not in rem_title and rem_title not in obs_title:
                                # Only flag if very different
                                similarity = self._simple_similarity(obs_title, rem_title)
                                if similarity < 0.3:
                                    results['referential_checks']['data_consistency_issues'].append(
                                        f"Link {i}: Low title similarity ({similarity:.2f}): '{obs_title[:30]}...' vs '{rem_title[:30]}...'"
                                    )
                                    
            # Calculate integrity score
            total_issues = (
                len(results['referential_checks']['broken_references']) +
                len(results['referential_checks']['data_consistency_issues'])
            )
            
            if results['referential_checks']['total_links'] > 0:
                results['integrity_score'] = max(0, 1 - (total_issues / results['referential_checks']['total_links']))
            else:
                results['integrity_score'] = 1.0
                
            # Generate recovery recommendations
            if results['referential_checks']['broken_references']:
                results['recovery_recommendations'].append("Run link cleanup to remove broken references")
                results['recovery_recommendations'].append("Regenerate sync links to repair missing connections")
                
            if results['referential_checks']['data_consistency_issues']:
                results['recovery_recommendations'].append("Run sync apply to resolve data inconsistencies")
                results['recovery_recommendations'].append("Consider manual review of low-similarity linked tasks")
                
            self.log(f"Referential Integrity: {results['referential_checks']['valid_references']}/{results['referential_checks']['total_links']} valid references")
            self.log(f"Integrity Score: {results['integrity_score']:.3f}")
            
        except Exception as e:
            self.log(f"Error in referential integrity validation: {e}", "ERROR")
            results['integrity_score'] = 0.0
            results['recovery_recommendations'].append(f"Fix validation error: {e}")
            
        return results
        
    def _simple_similarity(self, str1: str, str2: str) -> float:
        """Simple string similarity calculation"""
        if not str1 or not str2:
            return 0.0
            
        # Simple Jaccard similarity on words
        words1 = set(str1.lower().split())
        words2 = set(str2.lower().split())
        
        if not words1 and not words2:
            return 1.0
        if not words1 or not words2:
            return 0.0
            
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union)
        
    def detect_index_corruption(self) -> Dict[str, Any]:
        """Detect potential index corruption and data inconsistencies"""
        self.log("=== Detecting Index Corruption ===")
        
        results = {
            'corruption_checks': {
                'file_integrity': {},
                'schema_validation': {},
                'data_anomalies': [],
                'size_anomalies': []
            },
            'corruption_detected': False,
            'recovery_steps': []
        }
        
        try:
            # Check file integrity
            files_to_check = [
                (self.obs_index, 'obsidian_tasks_index'),
                (self.rem_index, 'reminders_tasks_index'),
                (self.sync_links, 'sync_links'),
                (self.obs_cache, 'obsidian_tasks_cache')
            ]
            
            for filepath, name in files_to_check:
                if not filepath.exists():
                    results['corruption_checks']['file_integrity'][name] = 'missing'
                    continue
                    
                file_check = {
                    'exists': True,
                    'size_bytes': filepath.stat().st_size,
                    'readable': False,
                    'valid_json': False,
                    'schema_valid': False
                }
                
                # Test readability
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read(100)  # Read first 100 chars
                    file_check['readable'] = True
                except Exception as e:
                    file_check['error'] = str(e)
                    results['corruption_detected'] = True
                    
                # Test JSON validity
                if file_check['readable']:
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        file_check['valid_json'] = True
                        
                        # Basic schema validation
                        if name in ['obsidian_tasks_index', 'reminders_tasks_index']:
                            if 'tasks' in data and isinstance(data['tasks'], dict):
                                file_check['schema_valid'] = True
                            else:
                                results['corruption_checks']['data_anomalies'].append(f"{name}: Missing or invalid 'tasks' field")
                                
                        elif name == 'sync_links':
                            if 'links' in data and isinstance(data['links'], list):
                                file_check['schema_valid'] = True
                            else:
                                results['corruption_checks']['data_anomalies'].append(f"{name}: Missing or invalid 'links' field")
                                
                    except json.JSONDecodeError as e:
                        file_check['json_error'] = str(e)
                        results['corruption_detected'] = True
                        results['recovery_steps'].append(f"Repair corrupted JSON in {name}")
                        
                results['corruption_checks']['file_integrity'][name] = file_check
                
                # Check for size anomalies
                if file_check['size_bytes'] < 100:  # Very small files
                    results['corruption_checks']['size_anomalies'].append(f"{name}: Suspiciously small ({file_check['size_bytes']} bytes)")
                elif file_check['size_bytes'] > 50 * 1024 * 1024:  # Very large files (>50MB)
                    results['corruption_checks']['size_anomalies'].append(f"{name}: Very large ({file_check['size_bytes'] / 1024 / 1024:.1f} MB)")
                    
            # Check for data anomalies
            if self.obs_index.exists() and self.rem_index.exists():
                try:
                    obs_data = json.loads(self.obs_index.read_text())
                    rem_data = json.loads(self.rem_index.read_text())
                    
                    obs_count = len(obs_data.get('tasks', {}))
                    rem_count = len(rem_data.get('tasks', {}))
                    
                    # Check for extreme imbalances
                    if obs_count > 0 and rem_count > 0:
                        ratio = max(obs_count, rem_count) / min(obs_count, rem_count)
                        if ratio > 10:  # One system has 10x more tasks
                            results['corruption_checks']['data_anomalies'].append(
                                f"Extreme task count imbalance: Obs({obs_count}) vs Rem({rem_count})"
                            )
                            
                except Exception as e:
                    results['corruption_checks']['data_anomalies'].append(f"Failed to analyze task counts: {e}")
                    
            # Assess overall corruption
            if (results['corruption_detected'] or 
                results['corruption_checks']['data_anomalies'] or 
                results['corruption_checks']['size_anomalies']):
                results['corruption_detected'] = True
                
            if not results['recovery_steps']:
                if results['corruption_checks']['data_anomalies']:
                    results['recovery_steps'].append("Run full sync update to rebuild indices")
                if results['corruption_checks']['size_anomalies']:
                    results['recovery_steps'].append("Investigate unusual file sizes")
                    
        except Exception as e:
            self.log(f"Error in corruption detection: {e}", "ERROR")
            results['corruption_detected'] = True
            results['recovery_steps'].append(f"Fix corruption detection error: {e}")
            
        return results
        
    def run_comprehensive_validation(self) -> Dict[str, Any]:
        """Run complete data integrity validation suite"""
        self.log("🔍 COMPREHENSIVE DATA INTEGRITY VALIDATION")
        self.log("="*80)
        
        validation_results = {}
        start_time = datetime.now()
        
        # UUID Integrity Validation
        self.log(f"\n{'='*60}")
        validation_results['uuid_integrity'] = self.validate_uuid_integrity()
        
        # Timestamp Integrity Validation
        self.log(f"\n{'='*60}")
        validation_results['timestamp_integrity'] = self.validate_timestamp_integrity()
        
        # Referential Integrity Validation
        self.log(f"\n{'='*60}")
        validation_results['referential_integrity'] = self.validate_referential_integrity()
        
        # Index Corruption Detection
        self.log(f"\n{'='*60}")
        validation_results['corruption_detection'] = self.detect_index_corruption()
        
        # Generate comprehensive summary
        duration = datetime.now() - start_time
        
        summary = {
            'validation_duration_sec': duration.total_seconds(),
            'timestamp': datetime.now().isoformat(),
            'detailed_validation': validation_results,
            'critical_issues': [],
            'warnings': [],
            'recovery_plan': [],
            'overall_integrity_score': 0.0,
            'data_health_grade': 'F'
        }
        
        # Collect critical issues
        if not validation_results['uuid_integrity']['overall_integrity']:
            summary['critical_issues'].extend(validation_results['uuid_integrity']['critical_issues'])
            
        if not validation_results['timestamp_integrity']['temporal_consistency']:
            summary['critical_issues'].extend(validation_results['timestamp_integrity']['issues_found'])
            
        if validation_results['referential_integrity']['integrity_score'] < 0.9:
            summary['critical_issues'].append(f"Low referential integrity score: {validation_results['referential_integrity']['integrity_score']:.3f}")
            
        if validation_results['corruption_detection']['corruption_detected']:
            summary['critical_issues'].append("Index corruption detected")
            
        # Collect warnings
        uuid_val = validation_results['uuid_integrity']['uuid_validation']
        if uuid_val['obsidian_uuids']['duplicates'] or uuid_val['reminders_uuids']['duplicates']:
            summary['warnings'].append("Duplicate UUIDs found")
            
        if validation_results['referential_integrity']['referential_checks']['data_consistency_issues']:
            summary['warnings'].append("Data consistency issues between linked tasks")
            
        # Consolidate recovery plan
        for category in validation_results.values():
            if 'recovery_recommendations' in category:
                summary['recovery_plan'].extend(category['recovery_recommendations'])
            if 'recovery_steps' in category:
                summary['recovery_plan'].extend(category['recovery_steps'])
                
        # Calculate overall integrity score
        scores = [
            1.0 if validation_results['uuid_integrity']['overall_integrity'] else 0.0,
            1.0 if validation_results['timestamp_integrity']['temporal_consistency'] else 0.0,
            validation_results['referential_integrity']['integrity_score'],
            0.0 if validation_results['corruption_detection']['corruption_detected'] else 1.0
        ]
        
        summary['overall_integrity_score'] = sum(scores) / len(scores)
        
        # Assign health grade
        score = summary['overall_integrity_score']
        if score >= 0.95:
            summary['data_health_grade'] = 'A'
        elif score >= 0.85:
            summary['data_health_grade'] = 'B'
        elif score >= 0.70:
            summary['data_health_grade'] = 'C'
        elif score >= 0.50:
            summary['data_health_grade'] = 'D'
        else:
            summary['data_health_grade'] = 'F'
            
        # Print comprehensive summary
        self.log(f"\n{'='*80}")
        self.log("📊 DATA INTEGRITY VALIDATION SUMMARY")
        self.log(f"{'='*80}")
        self.log(f"Overall Integrity Score: {summary['overall_integrity_score']:.3f}")
        self.log(f"Data Health Grade: {summary['data_health_grade']}")
        self.log(f"Validation Duration: {duration.total_seconds():.2f} seconds")
        
        self.log(f"\nComponent Scores:")
        self.log(f"  UUID Integrity: {'✓' if validation_results['uuid_integrity']['overall_integrity'] else '✗'}")
        self.log(f"  Timestamp Integrity: {'✓' if validation_results['timestamp_integrity']['temporal_consistency'] else '✗'}")
        self.log(f"  Referential Integrity: {validation_results['referential_integrity']['integrity_score']:.3f}")
        self.log(f"  Corruption Detection: {'✓' if not validation_results['corruption_detection']['corruption_detected'] else '✗'}")
        
        if summary['critical_issues']:
            self.log(f"\n🚨 Critical Issues ({len(summary['critical_issues'])}):")
            for issue in summary['critical_issues']:
                self.log(f"  ⚠️  {issue}")
                
        if summary['warnings']:
            self.log(f"\n⚠️  Warnings ({len(summary['warnings'])}):")
            for warning in summary['warnings']:
                self.log(f"  ⚡ {warning}")
                
        if summary['recovery_plan']:
            self.log(f"\n🔧 Recovery Recommendations:")
            unique_recommendations = list(dict.fromkeys(summary['recovery_plan']))  # Remove duplicates
            for rec in unique_recommendations[:5]:
                self.log(f"  🛠️  {rec}")
                
        # Save results
        results_file = self.config_dir / "obs-tools" / "backups" / f"data_integrity_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        results_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
            self.log(f"\n📁 Detailed results saved: {results_file}")
        except Exception as e:
            self.log(f"Failed to save results: {e}", "ERROR")
            
        return summary


def main():
    """Main entry point"""
    validator = DataIntegrityValidator()
    results = validator.run_comprehensive_validation()
    
    # Return exit code based on health grade
    grade = results.get('data_health_grade', 'F')
    if grade in ['A', 'B']:
        return 0
    elif grade == 'C':
        return 1
    else:
        return 2


if __name__ == "__main__":
    exit(main())