#!/usr/bin/env python3
"""
Simplified Performance Analysis Tool

This script performs deep performance analysis without external dependencies.
"""

import json
import os
import time
import subprocess
import gc
import resource
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import sys


class PerformanceProfiler:
    """Performance profiler using only stdlib"""
    
    def __init__(self, work_dir: str = "/Users/yannickbowe/Library/Mobile Documents/iCloud~md~obsidian/Documents/Work/obssync"):
        self.work_dir = Path(work_dir)
        self.config_dir = Path.home() / ".config"
        
        # File paths
        self.obs_index = self.config_dir / "obsidian_tasks_index.json"
        self.rem_index = self.config_dir / "reminders_tasks_index.json"
        self.sync_links = self.config_dir / "sync_links.json"
        
        # Performance tracking
        self.measurements = {}
        
    def log(self, message: str, level: str = "INFO"):
        """Log with timestamps"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] {level}: {message}")
        
    def get_memory_usage(self) -> Dict[str, float]:
        """Get memory usage using resource module"""
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return {
            'max_rss_mb': usage.ru_maxrss / 1024 / 1024,  # macOS reports in bytes
            'user_time': usage.ru_utime,
            'system_time': usage.ru_stime
        }
        
    def profile_json_loading(self) -> Dict[str, Any]:
        """Profile JSON file loading performance"""
        self.log("=== Profiling JSON Loading Performance ===")
        
        results = {
            'files_analyzed': [],
            'total_load_time': 0,
            'memory_efficient': True,
            'recommendations': []
        }
        
        files_to_test = [
            (self.obs_index, 'obsidian_tasks_index'),
            (self.rem_index, 'reminders_tasks_index'),
            (self.sync_links, 'sync_links')
        ]
        
        for filepath, name in files_to_test:
            if not filepath.exists():
                continue
                
            file_size_mb = filepath.stat().st_size / 1024 / 1024
            self.log(f"Profiling {name} ({file_size_mb:.1f}MB)")
            
            # Memory before loading
            gc.collect()
            mem_before = self.get_memory_usage()
            
            start_time = time.time()
            
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                load_time = time.time() - start_time
                
                # Memory after loading
                mem_after = self.get_memory_usage()
                memory_delta_mb = mem_after['max_rss_mb'] - mem_before['max_rss_mb']
                
                file_analysis = {
                    'name': name,
                    'file_size_mb': file_size_mb,
                    'load_time_sec': load_time,
                    'memory_delta_mb': memory_delta_mb,
                    'efficiency_ratio': file_size_mb / memory_delta_mb if memory_delta_mb > 0 else float('inf'),
                    'data_points': len(str(data)),
                    'parse_rate_mb_per_sec': file_size_mb / load_time if load_time > 0 else 0
                }
                
                # Performance assessment
                if load_time > 5.0:
                    file_analysis['slow_loading'] = True
                    results['recommendations'].append(f"{name}: Load time {load_time:.1f}s exceeds 5s threshold")
                    
                if file_size_mb > 5 and file_analysis['parse_rate_mb_per_sec'] < 1.0:
                    results['recommendations'].append(f"{name}: Slow parse rate {file_analysis['parse_rate_mb_per_sec']:.2f} MB/s")
                    
                results['files_analyzed'].append(file_analysis)
                results['total_load_time'] += load_time
                
                self.log(f"  Load: {load_time:.2f}s, Rate: {file_analysis['parse_rate_mb_per_sec']:.1f} MB/s")
                
            except Exception as e:
                self.log(f"Error profiling {name}: {e}", "ERROR")
                
        return results
        
    def analyze_data_complexity(self) -> Dict[str, Any]:
        """Analyze data complexity and processing characteristics"""
        self.log("=== Analyzing Data Complexity ===")
        
        results = {
            'dataset_metrics': {},
            'complexity_analysis': {},
            'scaling_projections': {},
            'bottleneck_predictions': []
        }
        
        try:
            # Load data for analysis
            start_time = time.time()
            
            obs_data = json.loads(self.obs_index.read_text()) if self.obs_index.exists() else {}
            rem_data = json.loads(self.rem_index.read_text()) if self.rem_index.exists() else {}
            links_data = json.loads(self.sync_links.read_text()) if self.sync_links.exists() else {}
            
            load_time = time.time() - start_time
            
            obs_tasks = obs_data.get('tasks', {})
            rem_tasks = rem_data.get('tasks', {})
            links = links_data.get('links', [])
            
            # Dataset metrics
            results['dataset_metrics'] = {
                'obsidian_tasks': len(obs_tasks),
                'reminders_tasks': len(rem_tasks),
                'total_tasks': len(obs_tasks) + len(rem_tasks),
                'sync_links': len(links),
                'link_coverage': len(links) / max(len(obs_tasks), len(rem_tasks)) if obs_tasks or rem_tasks else 0,
                'data_load_time_sec': load_time
            }
            
            # Complexity analysis
            total_tasks = results['dataset_metrics']['total_tasks']
            estimated_comparisons = len(obs_tasks) * len(rem_tasks)
            
            results['complexity_analysis'] = {
                'similarity_comparisons': estimated_comparisons,
                'algorithmic_complexity': 'O(n²)',
                'current_scale_assessment': self._assess_scale(estimated_comparisons),
                'memory_footprint_estimate_mb': (total_tasks * 2) / 1000  # Rough estimate
            }
            
            # Scaling projections
            scale_factors = [2, 5, 10]
            for factor in scale_factors:
                scaled_tasks = total_tasks * factor
                scaled_comparisons = (len(obs_tasks) * factor) * (len(rem_tasks) * factor)
                projected_time = (load_time * factor) + (estimated_comparisons / 1000000 * factor * factor)
                
                results['scaling_projections'][f'{factor}x_scale'] = {
                    'total_tasks': scaled_tasks,
                    'comparisons': scaled_comparisons,
                    'projected_time_sec': projected_time,
                    'feasible': projected_time < 600  # 10 minutes
                }
                
            # Bottleneck predictions
            if estimated_comparisons > 25_000_000:  # 25M
                results['bottleneck_predictions'].append('Similarity calculations will become primary bottleneck')
                
            if total_tasks > 20_000:
                results['bottleneck_predictions'].append('JSON serialization/deserialization overhead')
                
            if len(links) > 10_000:
                results['bottleneck_predictions'].append('Link validation and consistency checking')
                
        except Exception as e:
            self.log(f"Error in complexity analysis: {e}", "ERROR")
            
        return results
        
    def _assess_scale(self, comparisons: int) -> str:
        """Assess the current scale of operations"""
        if comparisons < 100_000:
            return "Small scale - good performance expected"
        elif comparisons < 1_000_000:
            return "Medium scale - acceptable performance"
        elif comparisons < 10_000_000:
            return "Large scale - performance optimizations recommended"
        else:
            return "Very large scale - major optimizations required"
            
    def profile_sync_operations(self) -> Dict[str, Any]:
        """Profile actual sync operations with timing"""
        self.log("=== Profiling Sync Operations ===")
        
        results = {
            'operations_profiled': [],
            'total_pipeline_time': 0,
            'performance_breakdown': {},
            'efficiency_metrics': {}
        }
        
        # Operations to profile
        operations = [
            ("collection", ["tasks", "collect", "--use-config", "--ignore-common"]),
            ("reminders", ["reminders", "collect"]),
            ("linking", ["sync", "suggest", "--include-done", "--min-score", "0.7"]),
            ("validation", ["sync", "apply", "--verbose"])  # Dry run
        ]
        
        venv_python = Path.home() / "Library/Application Support/obs-tools/venv/bin/python3"
        
        for op_name, command in operations:
            self.log(f"Profiling {op_name} operation...")
            
            # Pre-operation state
            mem_before = self.get_memory_usage()
            start_time = time.time()
            
            # Execute operation
            cmd = [str(venv_python), str(self.work_dir / "obs_tools.py")] + command
            
            try:
                process = subprocess.run(cmd, capture_output=True, text=True, cwd=self.work_dir)
                
                end_time = time.time()
                mem_after = self.get_memory_usage()
                
                duration = end_time - start_time
                memory_delta = mem_after['max_rss_mb'] - mem_before['max_rss_mb']
                
                op_results = {
                    'operation': op_name,
                    'duration_sec': duration,
                    'memory_delta_mb': memory_delta,
                    'success': process.returncode == 0,
                    'output_size': len(process.stdout) + len(process.stderr),
                    'cpu_efficiency': duration / (mem_after['user_time'] - mem_before['user_time']) if mem_after['user_time'] > mem_before['user_time'] else 0
                }
                
                if not op_results['success']:
                    op_results['error'] = process.stderr[:200]
                    
                results['operations_profiled'].append(op_results)
                results['total_pipeline_time'] += duration
                
                self.log(f"  {op_name}: {duration:.2f}s, Memory Δ: {memory_delta:+.1f}MB")
                
            except Exception as e:
                self.log(f"Error profiling {op_name}: {e}", "ERROR")
                
        # Calculate efficiency metrics
        if results['operations_profiled']:
            successful_ops = [op for op in results['operations_profiled'] if op['success']]
            if successful_ops:
                avg_duration = sum(op['duration_sec'] for op in successful_ops) / len(successful_ops)
                total_memory_delta = sum(op['memory_delta_mb'] for op in successful_ops)
                
                results['efficiency_metrics'] = {
                    'avg_operation_time_sec': avg_duration,
                    'total_memory_overhead_mb': total_memory_delta,
                    'pipeline_efficiency_score': 1.0 / (results['total_pipeline_time'] / 60) if results['total_pipeline_time'] > 0 else 0,
                    'memory_efficiency_score': 1.0 / (total_memory_delta / 100) if total_memory_delta > 0 else 1.0
                }
                
        return results
        
    def analyze_link_quality_and_coverage(self) -> Dict[str, Any]:
        """Analyze sync link quality and coverage metrics"""
        self.log("=== Analyzing Link Quality and Coverage ===")
        
        results = {
            'coverage_metrics': {},
            'quality_distribution': {},
            'data_integrity_issues': [],
            'optimization_opportunities': []
        }
        
        try:
            # Load current data
            obs_data = json.loads(self.obs_index.read_text()) if self.obs_index.exists() else {}
            rem_data = json.loads(self.rem_index.read_text()) if self.rem_index.exists() else {}
            links_data = json.loads(self.sync_links.read_text()) if self.sync_links.exists() else {}
            
            obs_tasks = obs_data.get('tasks', {})
            rem_tasks = rem_data.get('tasks', {})
            links = links_data.get('links', [])
            
            # Coverage analysis
            obs_uuids_in_links = set(link.get('obs_uuid') for link in links if link.get('obs_uuid'))
            rem_uuids_in_links = set(link.get('rem_uuid') for link in links if link.get('rem_uuid'))
            
            obs_uuids_total = set(task.get('uuid') for task in obs_tasks.values() if task.get('uuid'))
            rem_uuids_total = set(task.get('uuid') for task in rem_tasks.values() if task.get('uuid'))
            
            results['coverage_metrics'] = {
                'total_links': len(links),
                'obsidian_coverage': len(obs_uuids_in_links) / len(obs_uuids_total) if obs_uuids_total else 0,
                'reminders_coverage': len(rem_uuids_in_links) / len(rem_uuids_total) if rem_uuids_total else 0,
                'bidirectional_links': len([l for l in links if l.get('obs_uuid') and l.get('rem_uuid')]),
                'orphaned_obs_tasks': len(obs_uuids_total - obs_uuids_in_links),
                'orphaned_rem_tasks': len(rem_uuids_total - rem_uuids_in_links)
            }
            
            # Quality distribution
            scores = [link.get('score', 0) for link in links if 'score' in link]
            if scores:
                results['quality_distribution'] = {
                    'total_scored_links': len(scores),
                    'average_score': sum(scores) / len(scores),
                    'high_quality_links': len([s for s in scores if s >= 0.9]),
                    'medium_quality_links': len([s for s in scores if 0.7 <= s < 0.9]),
                    'low_quality_links': len([s for s in scores if s < 0.7]),
                    'perfect_matches': len([s for s in scores if s == 1.0])
                }
                
                # Quality thresholds
                high_quality_ratio = results['quality_distribution']['high_quality_links'] / len(scores)
                if high_quality_ratio < 0.5:
                    results['data_integrity_issues'].append(f"Only {high_quality_ratio:.1%} of links are high quality (>=0.9)")
                    
            # Data integrity checks
            duplicate_obs_uuids = len(obs_uuids_in_links) - len(set(obs_uuids_in_links))
            duplicate_rem_uuids = len(rem_uuids_in_links) - len(set(rem_uuids_in_links))
            
            if duplicate_obs_uuids > 0:
                results['data_integrity_issues'].append(f"{duplicate_obs_uuids} duplicate Obsidian UUIDs in links")
                
            if duplicate_rem_uuids > 0:
                results['data_integrity_issues'].append(f"{duplicate_rem_uuids} duplicate Reminders UUIDs in links")
                
            # Optimization opportunities
            if results['coverage_metrics']['orphaned_obs_tasks'] > 100:
                results['optimization_opportunities'].append("High number of unlinked Obsidian tasks - consider lowering similarity threshold")
                
            if results['coverage_metrics']['orphaned_rem_tasks'] > 100:
                results['optimization_opportunities'].append("High number of unlinked Reminders tasks - consider creating counterparts")
                
            if len(links) > 0 and results['quality_distribution']['low_quality_links'] > len(links) * 0.2:
                results['optimization_opportunities'].append("Many low-quality links detected - consider raising similarity threshold")
                
        except Exception as e:
            self.log(f"Error in link analysis: {e}", "ERROR")
            
        return results
        
    def run_comprehensive_analysis(self) -> Dict[str, Any]:
        """Run the complete performance analysis suite"""
        self.log("🔍 COMPREHENSIVE PERFORMANCE ANALYSIS")
        self.log("="*80)
        
        analysis_results = {}
        start_time = datetime.now()
        
        # JSON Loading Performance
        self.log(f"\n{'='*60}")
        analysis_results['json_loading'] = self.profile_json_loading()
        
        # Data Complexity Analysis
        self.log(f"\n{'='*60}")
        analysis_results['data_complexity'] = self.analyze_data_complexity()
        
        # Sync Operations Profiling
        self.log(f"\n{'='*60}")
        analysis_results['sync_operations'] = self.profile_sync_operations()
        
        # Link Quality Analysis
        self.log(f"\n{'='*60}")
        analysis_results['link_analysis'] = self.analyze_link_quality_and_coverage()
        
        # Generate comprehensive summary
        duration = datetime.now() - start_time
        
        summary = {
            'analysis_duration_sec': duration.total_seconds(),
            'timestamp': datetime.now().isoformat(),
            'system_info': {
                'python_version': sys.version,
                'platform': os.uname().sysname if hasattr(os, 'uname') else 'unknown'
            },
            'detailed_analysis': analysis_results,
            'critical_findings': [],
            'performance_recommendations': [],
            'overall_assessment': {}
        }
        
        # Extract critical findings
        complexity = analysis_results['data_complexity']
        if complexity['complexity_analysis']['similarity_comparisons'] > 25_000_000:
            summary['critical_findings'].append("Algorithmic complexity approaching unmanageable levels")
            
        link_analysis = analysis_results['link_analysis']
        if link_analysis['coverage_metrics']['obsidian_coverage'] < 0.5:
            summary['critical_findings'].append("Poor Obsidian task coverage in sync links")
            
        ops = analysis_results['sync_operations']
        if ops['total_pipeline_time'] > 180:  # 3 minutes
            summary['critical_findings'].append("Sync pipeline exceeds acceptable time threshold")
            
        # Consolidate recommendations
        for category in analysis_results.values():
            if 'recommendations' in category:
                summary['performance_recommendations'].extend(category['recommendations'])
            if 'optimization_opportunities' in category:
                summary['performance_recommendations'].extend(category['optimization_opportunities'])
            if 'bottleneck_predictions' in category:
                summary['performance_recommendations'].extend(category['bottleneck_predictions'])
                
        # Overall assessment
        critical_count = len(summary['critical_findings'])
        total_tasks = complexity['dataset_metrics']['total_tasks']
        pipeline_time = ops['total_pipeline_time']
        
        if critical_count == 0 and pipeline_time < 60:
            grade = 'A'
            status = 'EXCELLENT'
        elif critical_count <= 1 and pipeline_time < 120:
            grade = 'B'
            status = 'GOOD'
        elif critical_count <= 2 and pipeline_time < 180:
            grade = 'C'
            status = 'ACCEPTABLE'
        else:
            grade = 'D'
            status = 'NEEDS_OPTIMIZATION'
            
        summary['overall_assessment'] = {
            'grade': grade,
            'status': status,
            'scale_level': complexity['complexity_analysis']['current_scale_assessment'],
            'performance_score': max(0, 100 - (critical_count * 20) - max(0, (pipeline_time - 60) / 2))
        }
        
        # Print comprehensive summary
        self.log(f"\n{'='*80}")
        self.log("📊 PERFORMANCE ANALYSIS SUMMARY")
        self.log(f"{'='*80}")
        self.log(f"Overall Grade: {grade} ({status})")
        self.log(f"Performance Score: {summary['overall_assessment']['performance_score']:.1f}/100")
        self.log(f"Analysis Duration: {duration.total_seconds():.2f} seconds")
        
        self.log(f"\nDataset Scale:")
        metrics = complexity['dataset_metrics']
        self.log(f"  Total Tasks: {metrics['total_tasks']:,}")
        self.log(f"  Sync Links: {metrics['sync_links']:,}")
        self.log(f"  Link Coverage: {link_analysis['coverage_metrics']['obsidian_coverage']:.1%}")
        
        self.log(f"\nPerformance Metrics:")
        self.log(f"  Pipeline Time: {pipeline_time:.2f}s")
        self.log(f"  JSON Load Time: {analysis_results['json_loading']['total_load_time']:.2f}s")
        self.log(f"  Estimated Comparisons: {complexity['complexity_analysis']['similarity_comparisons']:,}")
        
        if summary['critical_findings']:
            self.log(f"\n🚨 Critical Findings ({len(summary['critical_findings'])}):")
            for finding in summary['critical_findings']:
                self.log(f"  ⚠️  {finding}")
                
        if summary['performance_recommendations']:
            self.log(f"\n💡 Top Recommendations:")
            for rec in summary['performance_recommendations'][:5]:
                self.log(f"  📈 {rec}")
                
        # Save results
        results_file = self.config_dir / "obs-tools" / "backups" / f"performance_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
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
    profiler = PerformanceProfiler()
    results = profiler.run_comprehensive_analysis()
    
    # Return exit code based on performance grade
    grade = results.get('overall_assessment', {}).get('grade', 'D')
    if grade in ['A', 'B']:
        return 0
    elif grade == 'C':
        return 1
    else:
        return 2


if __name__ == "__main__":
    exit(main())