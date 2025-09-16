#!/usr/bin/env python3
"""
Comprehensive Performance Analysis Tool

This script performs deep performance analysis of the sync system including:
- Memory usage profiling during large-scale operations
- JSON processing optimization analysis
- Algorithm complexity measurement
- Bottleneck identification and recommendations
"""

import json
import os
import time
import psutil
import subprocess
import gc
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import tracemalloc
import memory_profiler
import sys


class PerformanceProfiler:
    """Advanced performance profiler for sync operations"""
    
    def __init__(self, work_dir: str = "/Users/yannickbowe/Library/Mobile Documents/iCloud~md~obsidian/Documents/Work/obssync"):
        self.work_dir = Path(work_dir)
        self.config_dir = Path.home() / ".config"
        
        # File paths
        self.obs_index = self.config_dir / "obsidian_tasks_index.json"
        self.rem_index = self.config_dir / "reminders_tasks_index.json"
        self.sync_links = self.config_dir / "sync_links.json"
        
        # Performance tracking
        self.measurements = {}
        self.process = psutil.Process()
        
    def log(self, message: str, level: str = "INFO"):
        """Log with timestamps"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] {level}: {message}")
        
    def measure_memory_usage(self) -> Dict[str, float]:
        """Get current memory usage metrics"""
        mem_info = self.process.memory_info()
        return {
            'rss_mb': mem_info.rss / 1024 / 1024,  # Resident Set Size
            'vms_mb': mem_info.vms / 1024 / 1024,  # Virtual Memory Size
            'percent': self.process.memory_percent()
        }
        
    def profile_json_loading(self) -> Dict[str, Any]:
        """Profile JSON file loading performance and memory usage"""
        self.log("=== Profiling JSON Loading Performance ===")
        
        results = {
            'files_analyzed': [],
            'total_load_time': 0,
            'peak_memory_mb': 0,
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
                
            self.log(f"Profiling {name} ({filepath.stat().st_size / 1024 / 1024:.1f}MB)")
            
            # Start memory tracking
            tracemalloc.start()
            gc.collect()
            initial_memory = self.measure_memory_usage()
            
            start_time = time.time()
            
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                load_time = time.time() - start_time
                
                # Memory measurement
                peak_memory = self.measure_memory_usage()
                current, peak_trace = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                
                # Analysis
                memory_delta = peak_memory['rss_mb'] - initial_memory['rss_mb']
                file_size_mb = filepath.stat().st_size / 1024 / 1024
                
                file_analysis = {
                    'name': name,
                    'file_size_mb': file_size_mb,
                    'load_time_sec': load_time,
                    'memory_delta_mb': memory_delta,
                    'memory_efficiency_ratio': file_size_mb / memory_delta if memory_delta > 0 else float('inf'),
                    'peak_traced_mb': peak_trace / 1024 / 1024,
                    'data_structure_size': len(str(data))
                }
                
                # Performance assessment
                if load_time > 5.0:  # > 5 seconds
                    file_analysis['slow_loading'] = True
                    results['recommendations'].append(f"{name}: Consider streaming JSON parser for >5s load time")
                    
                if memory_delta > file_size_mb * 3:  # > 3x file size in memory
                    file_analysis['memory_inefficient'] = True
                    results['memory_efficient'] = False
                    results['recommendations'].append(f"{name}: Memory usage {memory_delta:.1f}MB is {memory_delta/file_size_mb:.1f}x file size")
                    
                results['files_analyzed'].append(file_analysis)
                results['total_load_time'] += load_time
                results['peak_memory_mb'] = max(results['peak_memory_mb'], peak_memory['rss_mb'])
                
                self.log(f"  Load time: {load_time:.2f}s, Memory delta: {memory_delta:.1f}MB")
                
            except Exception as e:
                self.log(f"Error profiling {name}: {e}", "ERROR")
                
        return results
        
    def analyze_similarity_algorithm_performance(self) -> Dict[str, Any]:
        """Analyze the performance characteristics of similarity calculations"""
        self.log("=== Analyzing Similarity Algorithm Performance ===")
        
        results = {
            'algorithm_complexity': 'O(n²)',
            'estimated_comparisons': 0,
            'bottlenecks_identified': [],
            'optimization_opportunities': []
        }
        
        # Load current data to estimate complexity
        try:
            obs_data = json.loads(self.obs_index.read_text())
            rem_data = json.loads(self.rem_index.read_text())
            
            obs_tasks = len(obs_data.get('tasks', {}))
            rem_tasks = len(rem_data.get('tasks', {}))
            
            # Estimate algorithmic complexity
            estimated_comparisons = obs_tasks * rem_tasks
            results['estimated_comparisons'] = estimated_comparisons
            
            self.log(f"Dataset size: {obs_tasks:,} Obsidian × {rem_tasks:,} Reminders")
            self.log(f"Estimated comparisons: {estimated_comparisons:,}")
            
            # Performance bottleneck analysis
            if estimated_comparisons > 10_000_000:  # 10M comparisons
                results['bottlenecks_identified'].append('Quadratic complexity with large datasets')
                results['optimization_opportunities'].extend([
                    'Implement indexing by creation date/time windows',
                    'Use approximate string matching algorithms (locality-sensitive hashing)',
                    'Batch processing with early termination for poor matches',
                    'Cache similarity scores for unchanged tasks'
                ])
                
            if estimated_comparisons > 1_000_000:  # 1M comparisons
                results['optimization_opportunities'].extend([
                    'Parallel processing of similarity calculations',
                    'Use more efficient string similarity algorithms (e.g., Jaro-Winkler)',
                    'Pre-filter by task length and basic properties'
                ])
                
        except Exception as e:
            self.log(f"Error analyzing similarity performance: {e}", "ERROR")
            
        return results
        
    def profile_memory_during_sync(self) -> Dict[str, Any]:
        """Profile memory usage during sync operations"""
        self.log("=== Profiling Memory Usage During Sync ===")
        
        results = {
            'baseline_memory_mb': 0,
            'peak_memory_mb': 0,
            'memory_growth_mb': 0,
            'memory_stable': True,
            'sync_phases': [],
            'memory_leaks_detected': False
        }
        
        # Baseline memory
        gc.collect()
        baseline = self.measure_memory_usage()
        results['baseline_memory_mb'] = baseline['rss_mb']
        
        self.log(f"Baseline memory: {baseline['rss_mb']:.1f}MB")
        
        # Profile different sync phases
        phases = [
            ("task_collection", ["tasks", "collect", "--use-config", "--ignore-common"]),
            ("reminders_collection", ["reminders", "collect"]),
            ("link_building", ["sync", "suggest", "--include-done"]),
            ("sync_apply", ["sync", "apply", "--apply"])
        ]
        
        for phase_name, command in phases:
            self.log(f"Profiling {phase_name}...")
            
            phase_start_memory = self.measure_memory_usage()
            phase_start_time = time.time()
            
            # Run the command
            cmd = [
                str(Path.home() / "Library/Application Support/obs-tools/venv/bin/python3"),
                str(self.work_dir / "obs_tools.py")
            ] + command
            
            try:
                process = subprocess.run(cmd, capture_output=True, text=True, cwd=self.work_dir)
                
                phase_end_time = time.time()
                phase_end_memory = self.measure_memory_usage()
                
                phase_results = {
                    'phase': phase_name,
                    'duration_sec': phase_end_time - phase_start_time,
                    'start_memory_mb': phase_start_memory['rss_mb'],
                    'end_memory_mb': phase_end_memory['rss_mb'],
                    'memory_delta_mb': phase_end_memory['rss_mb'] - phase_start_memory['rss_mb'],
                    'success': process.returncode == 0
                }
                
                results['sync_phases'].append(phase_results)
                results['peak_memory_mb'] = max(results['peak_memory_mb'], phase_end_memory['rss_mb'])
                
                self.log(f"  {phase_name}: {phase_results['duration_sec']:.2f}s, Memory Δ: {phase_results['memory_delta_mb']:+.1f}MB")
                
                # Check for memory leaks (memory not returned after operation)
                if phase_results['memory_delta_mb'] > 50:  # >50MB not released
                    results['memory_leaks_detected'] = True
                    
            except Exception as e:
                self.log(f"Error profiling {phase_name}: {e}", "ERROR")
                
        # Final memory check
        gc.collect()
        final_memory = self.measure_memory_usage()
        results['memory_growth_mb'] = final_memory['rss_mb'] - baseline['rss_mb']
        
        # Memory stability assessment
        if results['memory_growth_mb'] > 100:  # >100MB net growth
            results['memory_stable'] = False
            
        return results
        
    def analyze_data_structure_efficiency(self) -> Dict[str, Any]:
        """Analyze the efficiency of data structures used"""
        self.log("=== Analyzing Data Structure Efficiency ===")
        
        results = {
            'structure_analysis': [],
            'recommendations': [],
            'memory_waste_estimated_mb': 0
        }
        
        files_to_analyze = [
            (self.obs_index, 'obsidian_tasks_index'),
            (self.rem_index, 'reminders_tasks_index'),
            (self.sync_links, 'sync_links')
        ]
        
        for filepath, name in files_to_analyze:
            if not filepath.exists():
                continue
                
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                analysis = {
                    'file': name,
                    'total_keys': 0,
                    'redundant_data_detected': False,
                    'structure_issues': []
                }
                
                if name == 'sync_links':
                    links = data.get('links', [])
                    analysis['total_keys'] = len(links)
                    
                    # Check for redundant link data
                    if links:
                        sample_link = links[0]
                        key_count = len(sample_link.keys())
                        
                        # Check for excessive metadata
                        if key_count > 10:
                            analysis['structure_issues'].append(f'Links have {key_count} keys - consider reducing metadata')
                            
                        # Check for score precision
                        scores = [link.get('score', 0) for link in links[:100]]
                        if scores and any(len(str(s).split('.')[-1]) > 6 for s in scores):
                            analysis['structure_issues'].append('Excessive precision in similarity scores')
                            
                else:  # Task indices
                    tasks = data.get('tasks', {})
                    analysis['total_keys'] = len(tasks)
                    
                    if tasks:
                        # Sample task analysis
                        sample_task = list(tasks.values())[0]
                        
                        # Check for redundant fields
                        redundant_fields = []
                        for key, value in sample_task.items():
                            if value == "" or value is None:
                                redundant_fields.append(key)
                                
                        if redundant_fields:
                            analysis['redundant_data_detected'] = True
                            analysis['structure_issues'].append(f'Empty fields: {redundant_fields[:5]}')
                            
                        # Check for excessive string lengths
                        if any(isinstance(v, str) and len(v) > 1000 for v in sample_task.values()):
                            analysis['structure_issues'].append('Very long string values detected')
                            
                results['structure_analysis'].append(analysis)
                
            except Exception as e:
                self.log(f"Error analyzing {name} structure: {e}", "ERROR")
                
        # Generate recommendations
        for analysis in results['structure_analysis']:
            if analysis['structure_issues']:
                results['recommendations'].extend([
                    f"{analysis['file']}: {issue}" for issue in analysis['structure_issues']
                ])
                
        return results
        
    def measure_batch_processing_efficiency(self) -> Dict[str, Any]:
        """Measure efficiency of batch processing operations"""
        self.log("=== Measuring Batch Processing Efficiency ===")
        
        results = {
            'current_batch_size': 'unknown',
            'processing_rate_tasks_per_sec': 0,
            'memory_per_task_kb': 0,
            'optimal_batch_size_estimate': 0,
            'chunking_recommended': False
        }
        
        try:
            # Load current task data
            obs_data = json.loads(self.obs_index.read_text())
            rem_data = json.loads(self.rem_index.read_text())
            
            total_tasks = len(obs_data.get('tasks', {})) + len(rem_data.get('tasks', {}))
            
            # Estimate from recent performance
            latest_validation = list(Path(self.config_dir / "obs-tools" / "backups").glob("final_validation_*.json"))
            if latest_validation:
                latest_file = max(latest_validation, key=lambda p: p.stat().st_mtime)
                validation_data = json.loads(latest_file.read_text())
                
                perf = validation_data.get('detailed_results', {}).get('performance', {})
                pipeline_time = perf.get('pipeline_time', 0)
                
                if pipeline_time > 0:
                    results['processing_rate_tasks_per_sec'] = total_tasks / pipeline_time
                    
            # Memory efficiency estimation
            current_memory = self.measure_memory_usage()
            if total_tasks > 0:
                results['memory_per_task_kb'] = (current_memory['rss_mb'] * 1024) / total_tasks
                
            # Batch size recommendations
            if total_tasks > 5000:
                results['chunking_recommended'] = True
                # Aim for ~1000 tasks per batch to balance memory and processing efficiency
                results['optimal_batch_size_estimate'] = min(1000, total_tasks // 10)
                
        except Exception as e:
            self.log(f"Error measuring batch efficiency: {e}", "ERROR")
            
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
        
        # Similarity Algorithm Analysis
        self.log(f"\n{'='*60}")
        analysis_results['similarity_algorithm'] = self.analyze_similarity_algorithm_performance()
        
        # Memory Usage Profiling
        self.log(f"\n{'='*60}")
        analysis_results['memory_profiling'] = self.profile_memory_during_sync()
        
        # Data Structure Efficiency
        self.log(f"\n{'='*60}")
        analysis_results['data_structures'] = self.analyze_data_structure_efficiency()
        
        # Batch Processing Efficiency
        self.log(f"\n{'='*60}")
        analysis_results['batch_processing'] = self.measure_batch_processing_efficiency()
        
        # Generate summary and recommendations
        duration = datetime.now() - start_time
        
        summary = {
            'analysis_duration_sec': duration.total_seconds(),
            'timestamp': datetime.now().isoformat(),
            'system_info': {
                'python_version': sys.version,
                'platform': os.uname().sysname,
                'cpu_count': os.cpu_count(),
                'total_memory_gb': psutil.virtual_memory().total / 1024**3
            },
            'detailed_analysis': analysis_results,
            'critical_issues': [],
            'optimization_recommendations': [],
            'performance_grade': 'A'  # Will be calculated
        }
        
        # Identify critical issues
        if not analysis_results['json_loading']['memory_efficient']:
            summary['critical_issues'].append('Inefficient JSON memory usage detected')
            
        if analysis_results['memory_profiling']['memory_leaks_detected']:
            summary['critical_issues'].append('Memory leaks detected during sync operations')
            
        if analysis_results['similarity_algorithm']['estimated_comparisons'] > 10_000_000:
            summary['critical_issues'].append('Quadratic complexity will not scale beyond 10M comparisons')
            
        # Consolidate optimization recommendations
        for category in analysis_results.values():
            if 'recommendations' in category:
                summary['optimization_recommendations'].extend(category['recommendations'])
            if 'optimization_opportunities' in category:
                summary['optimization_recommendations'].extend(category['optimization_opportunities'])
                
        # Calculate performance grade
        issues_count = len(summary['critical_issues'])
        if issues_count == 0:
            summary['performance_grade'] = 'A'
        elif issues_count <= 2:
            summary['performance_grade'] = 'B'
        elif issues_count <= 4:
            summary['performance_grade'] = 'C'
        else:
            summary['performance_grade'] = 'D'
            
        # Print summary
        self.log(f"\n{'='*80}")
        self.log("📊 PERFORMANCE ANALYSIS SUMMARY")
        self.log(f"{'='*80}")
        self.log(f"Performance Grade: {summary['performance_grade']}")
        self.log(f"Analysis Duration: {duration.total_seconds():.2f} seconds")
        self.log(f"Critical Issues: {len(summary['critical_issues'])}")
        self.log(f"Optimization Opportunities: {len(summary['optimization_recommendations'])}")
        
        if summary['critical_issues']:
            self.log(f"\n🚨 Critical Issues:")
            for issue in summary['critical_issues']:
                self.log(f"  - {issue}")
                
        if summary['optimization_recommendations']:
            self.log(f"\n💡 Top Optimization Recommendations:")
            for rec in summary['optimization_recommendations'][:5]:
                self.log(f"  - {rec}")
                
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
    grade = results.get('performance_grade', 'D')
    if grade in ['A', 'B']:
        return 0
    elif grade == 'C':
        return 1
    else:
        return 2


if __name__ == "__main__":
    exit(main())