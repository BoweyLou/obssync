#!/usr/bin/env python3
"""
Comprehensive Sync System Analysis

This script provides a complete analysis of the sync system's state and functionality
without requiring live EventKit operations. It analyzes existing data to validate:

1. Data integrity across all indices and links
2. UUID-based identity consistency
3. Link quality and matching accuracy
4. System performance metrics
5. Sync history and patterns
6. Edge cases and potential issues

This gives us a complete picture of how well the sync system is working
with real production data.

Environment Variables:
    OBSSYNC_WORK_DIR: Override the default ObsSync working directory path
                     (defaults to ~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Work/obssync)

Usage:
    # Use default path detection
    python comprehensive_analysis.py

    # Override working directory
    OBSSYNC_WORK_DIR=/path/to/custom/obsync python comprehensive_analysis.py
"""

import json
import os
import time
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import re
import hashlib


class ComprehensiveSyncAnalyzer:
    """Comprehensive analyzer for sync system state and performance

    Args:
        work_dir: Path to the ObsSync working directory. If None, uses:
                 1. OBSSYNC_WORK_DIR environment variable if set
                 2. Otherwise defaults to ~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Work/obssync

    Environment Variables:
        OBSSYNC_WORK_DIR: Override the default working directory path
    """
    
    def __init__(self, work_dir: Optional[str] = None):
        # Use environment variable if set, otherwise construct portable default
        if work_dir is None:
            work_dir = os.environ.get('OBSSYNC_WORK_DIR')
            if work_dir is None:
                # Fallback to portable default under user's home directory
                work_dir = Path.home() / "Library" / "Mobile Documents" / "iCloud~md~obsidian" / "Documents" / "Work" / "obssync"

        self.work_dir = Path(work_dir)
        self.config_dir = Path.home() / ".config"
        
        # File paths
        self.obs_index = self.config_dir / "obsidian_tasks_index.json"
        self.rem_index = self.config_dir / "reminders_tasks_index.json" 
        self.sync_links = self.config_dir / "sync_links.json"
        self.obs_cache = self.config_dir / "obsidian_tasks_cache.json"
        self.rem_cache = self.config_dir / "reminders_snapshot_cache.json"
        
        # Analysis results
        self.analysis = {
            'metadata': {
                'analysis_time': datetime.now().isoformat(),
                'files_analyzed': [],
                'data_sources': {}
            },
            'data_integrity': {},
            'link_analysis': {},
            'performance_metrics': {},
            'sync_patterns': {},
            'quality_assessment': {},
            'recommendations': []
        }
        
    def log(self, message: str, level: str = "INFO"):
        """Log with timestamps"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")
        
    def load_json_file(self, filepath: Path) -> Dict[str, Any]:
        """Load JSON file with metadata collection"""
        if not filepath.exists():
            self.log(f"File not found: {filepath}", "WARNING")
            return {}
            
        try:
            stat = filepath.stat()
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Record metadata
            self.analysis['metadata']['files_analyzed'].append(str(filepath))
            self.analysis['metadata']['data_sources'][filepath.name] = {
                'size_mb': stat.st_size / 1024 / 1024,
                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'records': len(data.get('tasks', data.get('links', [])))
            }
            
            return data
        except Exception as e:
            self.log(f"Error loading {filepath}: {e}", "ERROR")
            return {}
            
    def analyze_data_integrity(self) -> Dict[str, Any]:
        """Analyze data integrity across all sources"""
        self.log("=== Analyzing Data Integrity ===")
        
        # Load all data sources
        obs_data = self.load_json_file(self.obs_index)
        rem_data = self.load_json_file(self.rem_index)
        links_data = self.load_json_file(self.sync_links)
        obs_cache = self.load_json_file(self.obs_cache)
        rem_cache = self.load_json_file(self.rem_cache)
        
        obs_tasks = obs_data.get('tasks', {})
        rem_tasks = rem_data.get('tasks', {})
        links = links_data.get('links', [])
        
        integrity = {
            'file_status': {
                'obs_index_exists': self.obs_index.exists(),
                'rem_index_exists': self.rem_index.exists(),
                'sync_links_exists': self.sync_links.exists(),
                'obs_cache_exists': self.obs_cache.exists(),
                'rem_cache_exists': self.rem_cache.exists()
            },
            'data_counts': {
                'obsidian_tasks': len(obs_tasks),
                'reminders_tasks': len(rem_tasks),
                'sync_links': len(links),
                'obs_cache_tasks': len(obs_cache.get('tasks', {})),
                'rem_cache_reminders': len(rem_cache.get('reminders', {}))
            },
            'uuid_analysis': {},
            'schema_validation': {},
            'data_quality': {}
        }
        
        # Analyze UUIDs
        obs_uuids = set()
        rem_uuids = set()
        link_obs_uuids = set()
        link_rem_uuids = set()
        
        uuid_issues = []
        
        # Collect Obsidian UUIDs
        for task_id, task in obs_tasks.items():
            uuid_val = task.get('uuid')
            if not uuid_val:
                uuid_issues.append(f"Obsidian task {task_id} missing UUID")
            else:
                if uuid_val in obs_uuids:
                    uuid_issues.append(f"Duplicate Obsidian UUID: {uuid_val}")
                obs_uuids.add(uuid_val)
                
        # Collect Reminders UUIDs
        for task_id, task in rem_tasks.items():
            uuid_val = task.get('uuid')
            if not uuid_val:
                uuid_issues.append(f"Reminders task {task_id} missing UUID")
            else:
                if uuid_val in rem_uuids:
                    uuid_issues.append(f"Duplicate Reminders UUID: {uuid_val}")
                rem_uuids.add(uuid_val)
                
        # Collect Link UUIDs
        for i, link in enumerate(links):
            obs_uuid = link.get('obs_uuid')
            rem_uuid = link.get('rem_uuid')
            
            if obs_uuid:
                link_obs_uuids.add(obs_uuid)
            if rem_uuid:
                link_rem_uuids.add(rem_uuid)
                
        integrity['uuid_analysis'] = {
            'unique_obs_uuids': len(obs_uuids),
            'unique_rem_uuids': len(rem_uuids),
            'linked_obs_uuids': len(link_obs_uuids),
            'linked_rem_uuids': len(link_rem_uuids),
            'orphaned_obs_links': len(link_obs_uuids - obs_uuids),
            'orphaned_rem_links': len(link_rem_uuids - rem_uuids),
            'unlinked_obs_tasks': len(obs_uuids - link_obs_uuids),
            'unlinked_rem_tasks': len(rem_uuids - link_rem_uuids),
            'uuid_issues': len(uuid_issues),
            'sample_issues': uuid_issues[:10]
        }
        
        # Schema validation
        schema_issues = []
        
        # Check required fields in Obsidian tasks
        for task_id, task in list(obs_tasks.items())[:100]:  # Sample first 100
            if not isinstance(task, dict):
                schema_issues.append(f"Obsidian task {task_id} is not a dict")
                continue
            required_fields = ['title', 'completed', 'uuid']
            for field in required_fields:
                if field not in task:
                    schema_issues.append(f"Obsidian task {task_id} missing {field}")
                    
        # Check required fields in Reminders tasks
        for task_id, task in list(rem_tasks.items())[:100]:  # Sample first 100
            if not isinstance(task, dict):
                schema_issues.append(f"Reminders task {task_id} is not a dict")
                continue
            required_fields = ['title', 'completed', 'uuid']
            for field in required_fields:
                if field not in task:
                    schema_issues.append(f"Reminders task {task_id} missing {field}")
                    
        # Check link structure
        for i, link in enumerate(links[:100]):  # Sample first 100
            if not isinstance(link, dict):
                schema_issues.append(f"Link {i} is not a dict")
                continue
            required_fields = ['obs_uuid', 'rem_uuid', 'score']
            for field in required_fields:
                if field not in link:
                    schema_issues.append(f"Link {i} missing {field}")
                    
        integrity['schema_validation'] = {
            'issues_found': len(schema_issues),
            'sample_issues': schema_issues[:10]
        }
        
        self.log(f"Data integrity analysis complete:")
        self.log(f"  - {integrity['data_counts']['obsidian_tasks']} Obsidian tasks")
        self.log(f"  - {integrity['data_counts']['reminders_tasks']} Reminders tasks") 
        self.log(f"  - {integrity['data_counts']['sync_links']} sync links")
        self.log(f"  - {integrity['uuid_analysis']['uuid_issues']} UUID issues")
        self.log(f"  - {integrity['schema_validation']['issues_found']} schema issues")
        
        return integrity
        
    def analyze_link_quality(self) -> Dict[str, Any]:
        """Analyze sync link quality and matching accuracy"""
        self.log("=== Analyzing Link Quality ===")
        
        links_data = self.load_json_file(self.sync_links)
        obs_data = self.load_json_file(self.obs_index)
        rem_data = self.load_json_file(self.rem_index)
        
        links = links_data.get('links', [])
        obs_tasks = obs_data.get('tasks', {})
        rem_tasks = rem_data.get('tasks', {})
        
        quality = {
            'score_distribution': {},
            'confidence_levels': {},
            'field_analysis': {},
            'matching_accuracy': {},
            'sync_status': {}
        }
        
        if not links:
            self.log("No links found for quality analysis")
            return quality
            
        # Analyze score distribution
        scores = [link.get('score', 0) for link in links]
        score_ranges = {
            'perfect_1.0': sum(1 for s in scores if s == 1.0),
            'high_0.9+': sum(1 for s in scores if 0.9 <= s < 1.0),
            'good_0.8+': sum(1 for s in scores if 0.8 <= s < 0.9),
            'medium_0.7+': sum(1 for s in scores if 0.7 <= s < 0.8),
            'low_<0.7': sum(1 for s in scores if s < 0.7)
        }
        
        quality['score_distribution'] = {
            'total_links': len(links),
            'average_score': sum(scores) / len(scores) if scores else 0,
            'min_score': min(scores) if scores else 0,
            'max_score': max(scores) if scores else 0,
            'ranges': score_ranges,
            'high_quality_percentage': (score_ranges['perfect_1.0'] + score_ranges['high_0.9+']) / len(links) * 100 if links else 0
        }
        
        # Analyze field-level matching
        title_similarities = []
        date_matches = []
        completion_matches = []
        
        valid_links = 0
        
        for link in links[:1000]:  # Sample first 1000 for performance
            obs_uuid = link.get('obs_uuid')
            rem_uuid = link.get('rem_uuid')
            
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
                continue
                
            valid_links += 1
            
            # Title similarity
            obs_title = obs_task.get('title', '').strip().lower()
            rem_title = rem_task.get('title', '').strip().lower()
            
            if obs_title and rem_title:
                title_sim = 1.0 if obs_title == rem_title else (
                    len(set(obs_title.split()) & set(rem_title.split())) / 
                    len(set(obs_title.split()) | set(rem_title.split()))
                    if set(obs_title.split()) | set(rem_title.split()) else 0
                )
                title_similarities.append(title_sim)
                
            # Completion status match
            obs_completed = obs_task.get('completed', False)
            rem_completed = rem_task.get('completed', False)
            completion_matches.append(obs_completed == rem_completed)
            
            # Due date analysis
            obs_due = obs_task.get('due_date')
            rem_due = rem_task.get('due_date')
            
            if obs_due and rem_due:
                # Simple date comparison (both have dates)
                date_matches.append(True)
            elif not obs_due and not rem_due:
                # Both have no dates
                date_matches.append(True)
            else:
                # One has date, other doesn't
                date_matches.append(False)
                
        quality['field_analysis'] = {
            'valid_links_analyzed': valid_links,
            'title_similarity': {
                'average': sum(title_similarities) / len(title_similarities) if title_similarities else 0,
                'perfect_matches': sum(1 for s in title_similarities if s == 1.0),
                'high_similarity': sum(1 for s in title_similarities if s >= 0.8)
            },
            'completion_consistency': {
                'matching_percentage': sum(completion_matches) / len(completion_matches) * 100 if completion_matches else 0,
                'total_compared': len(completion_matches)
            },
            'date_consistency': {
                'matching_percentage': sum(date_matches) / len(date_matches) * 100 if date_matches else 0,
                'total_compared': len(date_matches)
            }
        }
        
        # Analyze sync history
        recent_syncs = 0
        never_synced = 0
        sync_ages = []
        
        now = datetime.now()
        
        for link in links:
            last_synced = link.get('last_synced')
            if last_synced:
                try:
                    sync_time = datetime.fromisoformat(last_synced.replace('Z', '+00:00'))
                    age_hours = (now - sync_time).total_seconds() / 3600
                    sync_ages.append(age_hours)
                    
                    if age_hours < 24:  # Within last 24 hours
                        recent_syncs += 1
                except:
                    pass
            else:
                never_synced += 1
                
        quality['sync_status'] = {
            'recently_synced_24h': recent_syncs,
            'never_synced': never_synced,
            'average_sync_age_hours': sum(sync_ages) / len(sync_ages) if sync_ages else 0,
            'oldest_sync_hours': max(sync_ages) if sync_ages else 0,
            'newest_sync_hours': min(sync_ages) if sync_ages else 0
        }
        
        self.log(f"Link quality analysis complete:")
        self.log(f"  - {quality['score_distribution']['high_quality_percentage']:.1f}% high quality links")
        self.log(f"  - {quality['field_analysis']['title_similarity']['average']:.3f} average title similarity")
        self.log(f"  - {quality['field_analysis']['completion_consistency']['matching_percentage']:.1f}% completion consistency")
        self.log(f"  - {quality['sync_status']['recently_synced_24h']} recently synced links")
        
        return quality
        
    def analyze_performance_patterns(self) -> Dict[str, Any]:
        """Analyze performance and usage patterns"""
        self.log("=== Analyzing Performance Patterns ===")
        
        performance = {
            'file_sizes': {},
            'processing_efficiency': {},
            'growth_patterns': {},
            'bottlenecks': {}
        }
        
        # File size analysis
        files_to_analyze = [
            self.obs_index, self.rem_index, self.sync_links,
            self.obs_cache, self.rem_cache
        ]
        
        total_size = 0
        for file_path in files_to_analyze:
            if file_path.exists():
                size_mb = file_path.stat().st_size / 1024 / 1024
                performance['file_sizes'][file_path.name] = size_mb
                total_size += size_mb
                
        performance['file_sizes']['total_mb'] = total_size
        
        # Load metadata from files
        obs_data = self.load_json_file(self.obs_index)
        rem_data = self.load_json_file(self.rem_index)
        links_data = self.load_json_file(self.sync_links)
        
        # Calculate processing efficiency metrics
        obs_count = len(obs_data.get('tasks', {}))
        rem_count = len(rem_data.get('tasks', {}))
        link_count = len(links_data.get('links', []))
        
        performance['processing_efficiency'] = {
            'tasks_per_mb': (obs_count + rem_count) / total_size if total_size > 0 else 0,
            'links_per_task': link_count / (obs_count + rem_count) if (obs_count + rem_count) > 0 else 0,
            'avg_task_size_kb': (total_size * 1024) / (obs_count + rem_count) if (obs_count + rem_count) > 0 else 0
        }
        
        # Analyze metadata timestamps
        timestamps = []
        for data_source in [obs_data, rem_data, links_data]:
            metadata = data_source.get('metadata', {})
            if 'last_updated' in metadata:
                timestamps.append(metadata['last_updated'])
            elif 'generated_at' in data_source.get('meta', {}):
                timestamps.append(data_source['meta']['generated_at'])
                
        performance['growth_patterns'] = {
            'last_update_times': timestamps,
            'data_freshness_hours': [],
            'update_frequency': 'unknown'
        }
        
        # Calculate data freshness
        now = datetime.now()
        for ts in timestamps:
            try:
                update_time = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                age_hours = (now - update_time).total_seconds() / 3600
                performance['growth_patterns']['data_freshness_hours'].append(age_hours)
            except:
                pass
                
        self.log(f"Performance analysis complete:")
        self.log(f"  - {performance['file_sizes']['total_mb']:.1f} MB total data")
        self.log(f"  - {performance['processing_efficiency']['tasks_per_mb']:.0f} tasks per MB")
        self.log(f"  - {performance['processing_efficiency']['links_per_task']:.2f} links per task")
        
        return performance
        
    def generate_recommendations(self) -> List[str]:
        """Generate actionable recommendations based on analysis"""
        recommendations = []
        
        integrity = self.analysis.get('data_integrity', {})
        quality = self.analysis.get('link_analysis', {})
        performance = self.analysis.get('performance_metrics', {})
        
        # UUID issues
        uuid_issues = integrity.get('uuid_analysis', {}).get('uuid_issues', 0)
        if uuid_issues > 0:
            recommendations.append(f"Fix {uuid_issues} UUID consistency issues to improve data integrity")
            
        # Orphaned links
        orphaned_obs = integrity.get('uuid_analysis', {}).get('orphaned_obs_links', 0)
        orphaned_rem = integrity.get('uuid_analysis', {}).get('orphaned_rem_links', 0)
        if orphaned_obs > 0 or orphaned_rem > 0:
            recommendations.append(f"Clean up {orphaned_obs + orphaned_rem} orphaned sync links")
            
        # Link quality
        high_quality_pct = quality.get('score_distribution', {}).get('high_quality_percentage', 0)
        if high_quality_pct < 80:
            recommendations.append(f"Improve link quality (currently {high_quality_pct:.1f}% high quality)")
            
        # Completion consistency
        completion_pct = quality.get('field_analysis', {}).get('completion_consistency', {}).get('matching_percentage', 0)
        if completion_pct < 90:
            recommendations.append(f"Improve completion status sync (currently {completion_pct:.1f}% consistent)")
            
        # Never synced tasks
        never_synced = quality.get('sync_status', {}).get('never_synced', 0)
        if never_synced > 100:
            recommendations.append(f"Sync {never_synced} tasks that have never been synchronized")
            
        # File size optimization
        total_size = performance.get('file_sizes', {}).get('total_mb', 0)
        if total_size > 50:  # Arbitrary threshold
            recommendations.append(f"Consider optimizing data storage ({total_size:.1f} MB total)")
            
        # Data freshness
        freshness_hours = performance.get('growth_patterns', {}).get('data_freshness_hours', [])
        if freshness_hours and max(freshness_hours) > 168:  # 1 week
            recommendations.append("Some data sources are over 1 week old - consider more frequent updates")
            
        # Unlinked tasks
        unlinked_obs = integrity.get('uuid_analysis', {}).get('unlinked_obs_tasks', 0)
        unlinked_rem = integrity.get('uuid_analysis', {}).get('unlinked_rem_tasks', 0)
        total_unlinked = unlinked_obs + unlinked_rem
        if total_unlinked > 1000:
            recommendations.append(f"Consider creating counterparts for {total_unlinked} unlinked tasks")
            
        return recommendations
        
    def run_comprehensive_analysis(self) -> Dict[str, Any]:
        """Run complete analysis and generate report"""
        self.log("🔍 Starting Comprehensive Sync System Analysis")
        
        start_time = time.time()
        
        # Run all analyses
        self.analysis['data_integrity'] = self.analyze_data_integrity()
        self.analysis['link_analysis'] = self.analyze_link_quality()
        self.analysis['performance_metrics'] = self.analyze_performance_patterns()
        
        # Generate recommendations
        self.analysis['recommendations'] = self.generate_recommendations()
        
        # Calculate overall health score
        health_score = self.calculate_health_score()
        
        # Analysis summary
        duration = time.time() - start_time
        
        summary = {
            'analysis_duration': duration,
            'health_score': health_score,
            'data_sources': len(self.analysis['metadata']['files_analyzed']),
            'total_tasks': (
                self.analysis['data_integrity']['data_counts']['obsidian_tasks'] +
                self.analysis['data_integrity']['data_counts']['reminders_tasks']
            ),
            'total_links': self.analysis['data_integrity']['data_counts']['sync_links'],
            'recommendations_count': len(self.analysis['recommendations'])
        }
        
        self.analysis['summary'] = summary
        
        # Print comprehensive summary
        self.log(f"\n{'='*80}")
        self.log("📊 COMPREHENSIVE SYNC ANALYSIS SUMMARY")
        self.log(f"{'='*80}")
        
        self.log(f"Overall Health Score: {health_score:.1f}/100")
        self.log(f"Analysis Duration: {duration:.2f} seconds")
        self.log(f"Total Tasks: {summary['total_tasks']:,}")
        self.log(f"Total Links: {summary['total_links']:,}")
        
        # Data integrity summary
        integrity = self.analysis['data_integrity']
        uuid_analysis = integrity.get('uuid_analysis', {})
        self.log(f"\nData Integrity:")
        self.log(f"  ✓ UUID Issues: {uuid_analysis.get('uuid_issues', 0)}")
        self.log(f"  ✓ Orphaned Links: {uuid_analysis.get('orphaned_obs_links', 0) + uuid_analysis.get('orphaned_rem_links', 0)}")
        self.log(f"  ✓ Unlinked Tasks: {uuid_analysis.get('unlinked_obs_tasks', 0) + uuid_analysis.get('unlinked_rem_tasks', 0)}")
        
        # Link quality summary  
        quality = self.analysis['link_analysis']
        score_dist = quality.get('score_distribution', {})
        field_analysis = quality.get('field_analysis', {})
        self.log(f"\nLink Quality:")
        self.log(f"  ✓ High Quality Links: {score_dist.get('high_quality_percentage', 0):.1f}%")
        self.log(f"  ✓ Average Score: {score_dist.get('average_score', 0):.3f}")
        self.log(f"  ✓ Title Similarity: {field_analysis.get('title_similarity', {}).get('average', 0):.3f}")
        self.log(f"  ✓ Completion Consistency: {field_analysis.get('completion_consistency', {}).get('matching_percentage', 0):.1f}%")
        
        # Performance summary
        performance = self.analysis['performance_metrics']
        file_sizes = performance.get('file_sizes', {})
        efficiency = performance.get('processing_efficiency', {})
        self.log(f"\nPerformance:")
        self.log(f"  ✓ Total Data Size: {file_sizes.get('total_mb', 0):.1f} MB")
        self.log(f"  ✓ Tasks per MB: {efficiency.get('tasks_per_mb', 0):.0f}")
        self.log(f"  ✓ Links per Task: {efficiency.get('links_per_task', 0):.2f}")
        
        # Recommendations
        if self.analysis['recommendations']:
            self.log(f"\nRecommendations ({len(self.analysis['recommendations'])}):")
            for i, rec in enumerate(self.analysis['recommendations'][:5], 1):
                self.log(f"  {i}. {rec}")
            if len(self.analysis['recommendations']) > 5:
                self.log(f"     ... and {len(self.analysis['recommendations']) - 5} more")
        else:
            self.log(f"\n✅ No immediate recommendations - system is performing well!")
            
        # Save detailed analysis
        analysis_file = self.config_dir / "obs-tools" / "backups" / f"comprehensive_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        analysis_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(analysis_file, 'w', encoding='utf-8') as f:
                json.dump(self.analysis, f, indent=2, ensure_ascii=False, default=str)
            self.log(f"\nDetailed analysis saved: {analysis_file}")
        except Exception as e:
            self.log(f"Failed to save analysis: {e}", "ERROR")
            
        return self.analysis
        
    def calculate_health_score(self) -> float:
        """Calculate overall system health score (0-100)"""
        score = 100.0
        
        # Data integrity penalties
        integrity = self.analysis.get('data_integrity', {})
        uuid_analysis = integrity.get('uuid_analysis', {})
        
        uuid_issues = uuid_analysis.get('uuid_issues', 0)
        if uuid_issues > 0:
            score -= min(20, uuid_issues * 0.1)  # Max 20 point penalty
            
        orphaned_links = uuid_analysis.get('orphaned_obs_links', 0) + uuid_analysis.get('orphaned_rem_links', 0)
        if orphaned_links > 0:
            score -= min(15, orphaned_links * 0.01)  # Max 15 point penalty
            
        # Link quality penalties
        quality = self.analysis.get('link_analysis', {})
        high_quality_pct = quality.get('score_distribution', {}).get('high_quality_percentage', 100)
        if high_quality_pct < 90:
            score -= (90 - high_quality_pct) * 0.5  # 0.5 points per percent below 90%
            
        completion_pct = quality.get('field_analysis', {}).get('completion_consistency', {}).get('matching_percentage', 100)
        if completion_pct < 95:
            score -= (95 - completion_pct) * 0.3  # 0.3 points per percent below 95%
            
        # Performance penalties
        performance = self.analysis.get('performance_metrics', {})
        total_size = performance.get('file_sizes', {}).get('total_mb', 0)
        if total_size > 100:  # Large dataset penalty
            score -= min(10, (total_size - 100) * 0.1)
            
        return max(0, min(100, score))


def main():
    """Main entry point"""
    analyzer = ComprehensiveSyncAnalyzer()
    analysis = analyzer.run_comprehensive_analysis()
    
    health_score = analysis.get('summary', {}).get('health_score', 0)
    
    # Return exit code based on health score
    if health_score >= 90:
        return 0  # Excellent
    elif health_score >= 70:
        return 1  # Good with minor issues
    else:
        return 2  # Needs attention


if __name__ == "__main__":
    exit(main())