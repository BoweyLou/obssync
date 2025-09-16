#!/usr/bin/env python3
"""
System Optimization Analyzer

This script identifies specific optimization opportunities and provides
actionable recommendations for improving sync system performance,
memory efficiency, and data integrity.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import sys


class OptimizationAnalyzer:
    """Analyzes system for optimization opportunities"""
    
    def __init__(self, work_dir: str = "/Users/yannickbowe/Library/Mobile Documents/iCloud~md~obsidian/Documents/Work/obssync"):
        self.work_dir = Path(work_dir)
        self.config_dir = Path.home() / ".config"
        
        # File paths
        self.obs_index = self.config_dir / "obsidian_tasks_index.json"
        self.rem_index = self.config_dir / "reminders_tasks_index.json"
        self.sync_links = self.config_dir / "sync_links.json"
        
        # Load recent analysis results
        self.recent_results = self._load_recent_analysis_results()
        
    def log(self, message: str, level: str = "INFO"):
        """Log with timestamps"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] {level}: {message}")
        
    def _load_recent_analysis_results(self) -> Dict[str, Any]:
        """Load the most recent analysis results"""
        results = {}
        backup_dir = self.config_dir / "obs-tools" / "backups"
        
        if backup_dir.exists():
            # Find most recent validation results
            validation_files = list(backup_dir.glob("final_validation_*.json"))
            if validation_files:
                latest_validation = max(validation_files, key=lambda p: p.stat().st_mtime)
                try:
                    with open(latest_validation, 'r') as f:
                        results['validation'] = json.load(f)
                except Exception as e:
                    self.log(f"Could not load validation results: {e}", "WARN")
                    
            # Find most recent performance analysis
            perf_files = list(backup_dir.glob("performance_analysis_*.json"))
            if perf_files:
                latest_perf = max(perf_files, key=lambda p: p.stat().st_mtime)
                try:
                    with open(latest_perf, 'r') as f:
                        results['performance'] = json.load(f)
                except Exception as e:
                    self.log(f"Could not load performance results: {e}", "WARN")
                    
            # Find most recent integrity analysis
            integrity_files = list(backup_dir.glob("data_integrity_*.json"))
            if integrity_files:
                latest_integrity = max(integrity_files, key=lambda p: p.stat().st_mtime)
                try:
                    with open(latest_integrity, 'r') as f:
                        results['integrity'] = json.load(f)
                except Exception as e:
                    self.log(f"Could not load integrity results: {e}", "WARN")
                    
        return results
        
    def analyze_algorithmic_optimizations(self) -> Dict[str, Any]:
        """Identify algorithmic optimization opportunities"""
        self.log("=== Analyzing Algorithmic Optimizations ===")
        
        optimizations = {
            'similarity_algorithm': [],
            'data_processing': [],
            'indexing_strategies': [],
            'caching_opportunities': [],
            'priority': 'HIGH'
        }
        
        try:
            # Load current dataset metrics
            obs_data = json.loads(self.obs_index.read_text()) if self.obs_index.exists() else {}
            rem_data = json.loads(self.rem_index.read_text()) if self.rem_index.exists() else {}
            
            obs_count = len(obs_data.get('tasks', {}))
            rem_count = len(rem_data.get('tasks', {}))
            estimated_comparisons = obs_count * rem_count
            
            # Similarity algorithm optimizations
            if estimated_comparisons > 10_000_000:  # 10M+ comparisons
                optimizations['similarity_algorithm'].extend([
                    {
                        'optimization': 'Implement locality-sensitive hashing (LSH)',
                        'impact': 'HIGH',
                        'complexity': 'MEDIUM',
                        'description': 'Use LSH to reduce similarity calculations from O(n²) to approximately O(n)',
                        'estimated_speedup': '10-100x for large datasets',
                        'implementation': 'Use MinHash or SimHash algorithms for text similarity'
                    },
                    {
                        'optimization': 'Time-window-based pre-filtering',
                        'impact': 'HIGH', 
                        'complexity': 'LOW',
                        'description': 'Only compare tasks created within similar time windows',
                        'estimated_speedup': '5-20x depending on temporal distribution',
                        'implementation': 'Group tasks by creation date ranges before similarity comparison'
                    },
                    {
                        'optimization': 'Parallel similarity processing',
                        'impact': 'MEDIUM',
                        'complexity': 'MEDIUM',
                        'description': 'Process similarity calculations in parallel batches',
                        'estimated_speedup': '2-4x on multi-core systems',
                        'implementation': 'Use multiprocessing or asyncio for batch processing'
                    }
                ])
            elif estimated_comparisons > 1_000_000:  # 1M+ comparisons
                optimizations['similarity_algorithm'].extend([
                    {
                        'optimization': 'Early termination with score thresholds',
                        'impact': 'MEDIUM',
                        'complexity': 'LOW',
                        'description': 'Stop similarity calculation early for obviously poor matches',
                        'estimated_speedup': '2-5x for mixed quality datasets',
                        'implementation': 'Use progressive similarity metrics with early exit'
                    },
                    {
                        'optimization': 'Optimized string similarity algorithms',
                        'impact': 'MEDIUM',
                        'complexity': 'LOW',
                        'description': 'Use faster similarity algorithms like Jaro-Winkler',
                        'estimated_speedup': '2-3x over current implementation',
                        'implementation': 'Replace current similarity metric with optimized version'
                    }
                ])
                
            # Data processing optimizations
            optimizations['data_processing'].extend([
                {
                    'optimization': 'Streaming JSON processing',
                    'impact': 'MEDIUM',
                    'complexity': 'MEDIUM',
                    'description': 'Process large JSON files incrementally to reduce memory usage',
                    'estimated_memory_savings': '50-80% for large files',
                    'implementation': 'Use ijson or similar streaming JSON library'
                },
                {
                    'optimization': 'Compressed storage for indices',
                    'impact': 'LOW',
                    'complexity': 'LOW',
                    'description': 'Use gzip compression for large index files',
                    'estimated_space_savings': '60-80% file size reduction',
                    'implementation': 'Store indices as compressed JSON'
                },
                {
                    'optimization': 'Incremental updates',
                    'impact': 'HIGH',
                    'complexity': 'HIGH',
                    'description': 'Only process changed tasks instead of full rebuilds',
                    'estimated_speedup': '5-50x for incremental updates',
                    'implementation': 'Track modification timestamps and process deltas'
                }
            ])
            
            # Indexing strategies
            if obs_count > 1000 or rem_count > 1000:
                optimizations['indexing_strategies'].extend([
                    {
                        'optimization': 'Task title indexing',
                        'impact': 'HIGH',
                        'complexity': 'MEDIUM',
                        'description': 'Create inverted index of task titles for faster similarity lookups',
                        'estimated_speedup': '10-100x for title-based matching',
                        'implementation': 'Use word-level indexing with TF-IDF scoring'
                    },
                    {
                        'optimization': 'UUID-based lookup tables',
                        'impact': 'MEDIUM',
                        'complexity': 'LOW',
                        'description': 'Create fast UUID to task mappings',
                        'estimated_speedup': '100-1000x for UUID lookups',
                        'implementation': 'Maintain hash tables for UUID resolution'
                    },
                    {
                        'optimization': 'Date-based partitioning',
                        'impact': 'MEDIUM',
                        'complexity': 'MEDIUM',
                        'description': 'Partition tasks by date ranges for faster filtering',
                        'estimated_speedup': '2-10x for date-based queries',
                        'implementation': 'Create date-indexed task buckets'
                    }
                ])
                
            # Caching opportunities
            optimizations['caching_opportunities'].extend([
                {
                    'optimization': 'Similarity score caching',
                    'impact': 'HIGH',
                    'complexity': 'MEDIUM',
                    'description': 'Cache similarity scores for task pairs to avoid recalculation',
                    'estimated_speedup': '2-10x for repeated operations',
                    'implementation': 'Use content-based cache keys (task hashes)'
                },
                {
                    'optimization': 'Task content hashing',
                    'impact': 'MEDIUM',
                    'complexity': 'LOW',
                    'description': 'Use content hashes to detect unchanged tasks',
                    'estimated_speedup': '5-20x for unchanged content',
                    'implementation': 'SHA-256 hash of normalized task content'
                },
                {
                    'optimization': 'Link validation caching',
                    'impact': 'LOW',
                    'complexity': 'LOW',
                    'description': 'Cache link validation results',
                    'estimated_speedup': '2-5x for validation operations',
                    'implementation': 'Cache validation results with timestamp checks'
                }
            ])
            
        except Exception as e:
            self.log(f"Error in algorithmic analysis: {e}", "ERROR")
            
        return optimizations
        
    def analyze_memory_optimizations(self) -> Dict[str, Any]:
        """Identify memory usage optimization opportunities"""
        self.log("=== Analyzing Memory Optimizations ===")
        
        optimizations = {
            'memory_management': [],
            'data_structures': [],
            'loading_strategies': [],
            'priority': 'MEDIUM'
        }
        
        try:
            # Check file sizes for memory optimization opportunities
            files_to_check = [
                (self.obs_index, 'obsidian_tasks_index'),
                (self.rem_index, 'reminders_tasks_index'),
                (self.sync_links, 'sync_links')
            ]
            
            large_files = []
            for filepath, name in files_to_check:
                if filepath.exists():
                    size_mb = filepath.stat().st_size / 1024 / 1024
                    if size_mb > 5:  # Files larger than 5MB
                        large_files.append((name, size_mb))
                        
            if large_files:
                optimizations['loading_strategies'].extend([
                    {
                        'optimization': 'Lazy loading for large files',
                        'impact': 'HIGH',
                        'complexity': 'MEDIUM',
                        'description': f'Implement lazy loading for files: {", ".join(f[0] for f in large_files)}',
                        'affected_files': large_files,
                        'estimated_memory_savings': '70-90% initial memory usage',
                        'implementation': 'Load data on-demand rather than all at once'
                    },
                    {
                        'optimization': 'Paginated data access',
                        'impact': 'MEDIUM',
                        'complexity': 'HIGH',
                        'description': 'Process large datasets in smaller chunks',
                        'estimated_memory_savings': '50-80% peak memory usage',
                        'implementation': 'Implement cursor-based pagination for task processing'
                    }
                ])
                
            # Memory management optimizations
            optimizations['memory_management'].extend([
                {
                    'optimization': 'Explicit garbage collection',
                    'impact': 'LOW',
                    'complexity': 'LOW',
                    'description': 'Force garbage collection after large operations',
                    'estimated_memory_savings': '10-30% after operations',
                    'implementation': 'Call gc.collect() after similarity calculations'
                },
                {
                    'optimization': 'Object pooling for frequent allocations',
                    'impact': 'MEDIUM',
                    'complexity': 'MEDIUM',
                    'description': 'Reuse objects for similarity calculations',
                    'estimated_memory_savings': '20-50% allocation overhead',
                    'implementation': 'Pool similarity calculation objects'
                },
                {
                    'optimization': 'Memory-mapped file access',
                    'impact': 'MEDIUM',
                    'complexity': 'HIGH',
                    'description': 'Use memory mapping for very large files',
                    'estimated_memory_savings': '80-95% for read-only access',
                    'implementation': 'Use mmap for large index files'
                }
            ])
            
            # Data structure optimizations
            optimizations['data_structures'].extend([
                {
                    'optimization': 'Use generators for large iterations',
                    'impact': 'MEDIUM',
                    'complexity': 'LOW',
                    'description': 'Replace lists with generators for task iteration',
                    'estimated_memory_savings': '50-90% for iteration memory',
                    'implementation': 'Convert list comprehensions to generator expressions'
                },
                {
                    'optimization': 'Optimize dictionary structures',
                    'impact': 'LOW',
                    'complexity': 'LOW',
                    'description': 'Use slots and other memory-efficient patterns',
                    'estimated_memory_savings': '10-30% object overhead',
                    'implementation': 'Use __slots__ for frequent objects'
                },
                {
                    'optimization': 'String interning for repeated values',
                    'impact': 'LOW',
                    'complexity': 'LOW',
                    'description': 'Intern frequently repeated strings',
                    'estimated_memory_savings': '20-50% for duplicate strings',
                    'implementation': 'Use sys.intern() for common field values'
                }
            ])
            
        except Exception as e:
            self.log(f"Error in memory optimization analysis: {e}", "ERROR")
            
        return optimizations
        
    def analyze_data_integrity_optimizations(self) -> Dict[str, Any]:
        """Identify data integrity and consistency optimization opportunities"""
        self.log("=== Analyzing Data Integrity Optimizations ===")
        
        optimizations = {
            'integrity_improvements': [],
            'consistency_mechanisms': [],
            'recovery_strategies': [],
            'priority': 'HIGH'
        }
        
        try:
            # Use integrity analysis results if available
            integrity_results = self.recent_results.get('integrity', {})
            
            if integrity_results:
                integrity_score = integrity_results.get('overall_integrity_score', 0)
                
                if integrity_score < 0.9:
                    optimizations['integrity_improvements'].extend([
                        {
                            'optimization': 'Automated link cleanup',
                            'impact': 'HIGH',
                            'complexity': 'MEDIUM',
                            'description': 'Automatically remove broken links and orphaned references',
                            'current_issue': f'Integrity score: {integrity_score:.3f}',
                            'implementation': 'Create periodic cleanup job for broken references'
                        },
                        {
                            'optimization': 'Enhanced UUID validation',
                            'impact': 'MEDIUM',
                            'complexity': 'LOW',
                            'description': 'Add stricter UUID validation and duplicate detection',
                            'implementation': 'Validate UUIDs at ingestion time with duplicate checking'
                        }
                    ])
                    
                # Check for specific integrity issues
                detailed = integrity_results.get('detailed_validation', {})
                ref_integrity = detailed.get('referential_integrity', {})
                
                if ref_integrity.get('integrity_score', 1.0) < 0.7:
                    optimizations['integrity_improvements'].append({
                        'optimization': 'Referential integrity enforcement',
                        'impact': 'HIGH',
                        'complexity': 'MEDIUM',
                        'description': 'Implement foreign key-like constraints for task links',
                        'current_issue': f'Referential integrity: {ref_integrity.get("integrity_score", 0):.3f}',
                        'implementation': 'Add validation rules and automatic repair mechanisms'
                    })
                    
            # Consistency mechanisms
            optimizations['consistency_mechanisms'].extend([
                {
                    'optimization': 'Atomic operations for sync updates',
                    'impact': 'HIGH',
                    'complexity': 'MEDIUM',
                    'description': 'Ensure sync operations are atomic to prevent partial updates',
                    'implementation': 'Use transaction-like patterns for multi-step sync operations'
                },
                {
                    'optimization': 'Checksum validation for data files',
                    'impact': 'MEDIUM',
                    'complexity': 'LOW',
                    'description': 'Add checksums to detect file corruption',
                    'implementation': 'Store and verify SHA-256 checksums for index files'
                },
                {
                    'optimization': 'Backup and versioning system',
                    'impact': 'MEDIUM',
                    'complexity': 'MEDIUM',
                    'description': 'Implement automatic backups with versioning',
                    'implementation': 'Create timestamped backups before major operations'
                }
            ])
            
            # Recovery strategies
            optimizations['recovery_strategies'].extend([
                {
                    'optimization': 'Self-healing link repair',
                    'impact': 'HIGH',
                    'complexity': 'HIGH',
                    'description': 'Automatically detect and repair broken links',
                    'implementation': 'Use fuzzy matching to reconnect orphaned tasks'
                },
                {
                    'optimization': 'Incremental rebuild capability',
                    'impact': 'MEDIUM',
                    'complexity': 'MEDIUM',
                    'description': 'Rebuild only corrupted portions of indices',
                    'implementation': 'Track which parts of indices need rebuilding'
                },
                {
                    'optimization': 'Data validation hooks',
                    'impact': 'MEDIUM',
                    'complexity': 'LOW',
                    'description': 'Add validation at key operation points',
                    'implementation': 'Validate data before and after major operations'
                }
            ])
            
        except Exception as e:
            self.log(f"Error in integrity optimization analysis: {e}", "ERROR")
            
        return optimizations
        
    def analyze_performance_bottlenecks(self) -> Dict[str, Any]:
        """Identify specific performance bottlenecks"""
        self.log("=== Analyzing Performance Bottlenecks ===")
        
        bottlenecks = {
            'identified_bottlenecks': [],
            'performance_improvements': [],
            'scalability_concerns': [],
            'priority': 'HIGH'
        }
        
        try:
            # Use performance analysis results if available
            perf_results = self.recent_results.get('performance', {})
            
            if perf_results:
                detailed = perf_results.get('detailed_analysis', {})
                
                # Check data complexity
                complexity = detailed.get('data_complexity', {})
                if complexity:
                    comparisons = complexity.get('complexity_analysis', {}).get('similarity_comparisons', 0)
                    if comparisons > 25_000_000:
                        bottlenecks['identified_bottlenecks'].append({
                            'bottleneck': 'Similarity calculation complexity',
                            'severity': 'CRITICAL',
                            'impact': f'{comparisons:,} comparisons (O(n²) algorithm)',
                            'current_time': 'Estimated >5 minutes for full rebuild',
                            'recommendation': 'Implement LSH or other sub-quadratic algorithm'
                        })
                        
                # Check sync operation times
                sync_ops = detailed.get('sync_operations', {})
                if sync_ops:
                    total_time = sync_ops.get('total_pipeline_time', 0)
                    if total_time > 120:  # 2 minutes
                        bottlenecks['identified_bottlenecks'].append({
                            'bottleneck': 'Long sync pipeline duration',
                            'severity': 'HIGH',
                            'impact': f'{total_time:.1f} seconds total pipeline time',
                            'recommendation': 'Optimize individual sync operations and add parallelization'
                        })
                        
                    # Check individual operations
                    for phase in sync_ops.get('operations_profiled', []):
                        if phase.get('duration_sec', 0) > 30:
                            bottlenecks['identified_bottlenecks'].append({
                                'bottleneck': f'Slow {phase["operation"]} operation',
                                'severity': 'MEDIUM',
                                'impact': f'{phase["duration_sec"]:.1f} seconds',
                                'recommendation': f'Optimize {phase["operation"]} algorithm or implementation'
                            })
                            
                # Check JSON loading performance
                json_loading = detailed.get('json_loading', {})
                if json_loading:
                    total_load_time = json_loading.get('total_load_time', 0)
                    if total_load_time > 5:
                        bottlenecks['identified_bottlenecks'].append({
                            'bottleneck': 'Slow JSON loading',
                            'severity': 'MEDIUM',
                            'impact': f'{total_load_time:.1f} seconds to load all files',
                            'recommendation': 'Implement streaming JSON parsing or lazy loading'
                        })
                        
            # Performance improvements based on current system
            bottlenecks['performance_improvements'].extend([
                {
                    'improvement': 'Implement result caching',
                    'impact': 'HIGH',
                    'complexity': 'MEDIUM',
                    'description': 'Cache expensive operations like similarity calculations',
                    'estimated_speedup': '5-50x for repeated operations'
                },
                {
                    'improvement': 'Add progress indicators',
                    'impact': 'LOW',
                    'complexity': 'LOW',
                    'description': 'Show progress for long-running operations',
                    'user_benefit': 'Better user experience during long operations'
                },
                {
                    'improvement': 'Optimize file I/O',
                    'impact': 'MEDIUM',
                    'complexity': 'LOW',
                    'description': 'Use buffered I/O and async file operations',
                    'estimated_speedup': '20-50% for file operations'
                }
            ])
            
            # Scalability concerns
            if perf_results:
                scaling = detailed.get('data_complexity', {}).get('scaling_projections', {})
                for scale, projection in scaling.items():
                    if not projection.get('feasible', True):
                        bottlenecks['scalability_concerns'].append({
                            'concern': f'Performance at {scale}',
                            'issue': f'Projected time: {projection.get("projected_time_sec", 0):.1f}s',
                            'recommendation': 'Implement algorithmic optimizations before scaling further'
                        })
                        
        except Exception as e:
            self.log(f"Error in bottleneck analysis: {e}", "ERROR")
            
        return bottlenecks
        
    def generate_implementation_plan(self, optimizations: Dict[str, Any]) -> Dict[str, Any]:
        """Generate prioritized implementation plan"""
        self.log("=== Generating Implementation Plan ===")
        
        plan = {
            'immediate_actions': [],
            'short_term_optimizations': [],
            'long_term_improvements': [],
            'estimated_impact': {},
            'implementation_order': []
        }
        
        try:
            # Collect all optimizations
            all_optimizations = []
            
            for category, opts in optimizations.items():
                if isinstance(opts, dict) and 'priority' in opts:
                    category_priority = opts['priority']
                    for opt_type, opt_list in opts.items():
                        if opt_type != 'priority' and isinstance(opt_list, list):
                            for opt in opt_list:
                                opt['category'] = category
                                opt['opt_type'] = opt_type
                                opt['category_priority'] = category_priority
                                all_optimizations.append(opt)
                                
            # Sort by impact and complexity
            def optimization_score(opt):
                impact_score = {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}.get(opt.get('impact', 'LOW'), 1)
                complexity_penalty = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2}.get(opt.get('complexity', 'MEDIUM'), 1)
                priority_bonus = {'HIGH': 2, 'MEDIUM': 1, 'LOW': 0}.get(opt.get('category_priority', 'MEDIUM'), 1)
                return impact_score + priority_bonus - complexity_penalty
                
            sorted_optimizations = sorted(all_optimizations, key=optimization_score, reverse=True)
            
            # Categorize by implementation timeline
            for opt in sorted_optimizations:
                complexity = opt.get('complexity', 'MEDIUM')
                impact = opt.get('impact', 'MEDIUM')
                
                if complexity == 'LOW' and impact in ['HIGH', 'MEDIUM']:
                    plan['immediate_actions'].append(opt)
                elif complexity == 'MEDIUM':
                    plan['short_term_optimizations'].append(opt)
                else:  # HIGH complexity
                    plan['long_term_improvements'].append(opt)
                    
            # Limit each category to reasonable sizes
            plan['immediate_actions'] = plan['immediate_actions'][:5]
            plan['short_term_optimizations'] = plan['short_term_optimizations'][:8]
            plan['long_term_improvements'] = plan['long_term_improvements'][:5]
            
            # Create implementation order
            plan['implementation_order'] = (
                plan['immediate_actions'][:3] +
                plan['short_term_optimizations'][:3] +
                plan['immediate_actions'][3:] +
                plan['short_term_optimizations'][3:] +
                plan['long_term_improvements']
            )
            
            # Estimate overall impact
            plan['estimated_impact'] = {
                'performance_improvement': '2-10x speedup for most operations',
                'memory_reduction': '50-80% memory usage reduction',
                'reliability_improvement': '90%+ data integrity score',
                'scalability_enhancement': 'Support for 100K+ tasks efficiently'
            }
            
        except Exception as e:
            self.log(f"Error generating implementation plan: {e}", "ERROR")
            
        return plan
        
    def run_comprehensive_optimization_analysis(self) -> Dict[str, Any]:
        """Run complete optimization analysis"""
        self.log("🚀 COMPREHENSIVE OPTIMIZATION ANALYSIS")
        self.log("="*80)
        
        start_time = datetime.now()
        
        # Run all optimization analyses
        self.log(f"\n{'='*60}")
        algorithmic_opts = self.analyze_algorithmic_optimizations()
        
        self.log(f"\n{'='*60}")
        memory_opts = self.analyze_memory_optimizations()
        
        self.log(f"\n{'='*60}")
        integrity_opts = self.analyze_data_integrity_optimizations()
        
        self.log(f"\n{'='*60}")
        bottlenecks = self.analyze_performance_bottlenecks()
        
        # Combine all optimizations
        all_optimizations = {
            'algorithmic': algorithmic_opts,
            'memory': memory_opts,
            'data_integrity': integrity_opts,
            'bottlenecks': bottlenecks
        }
        
        # Generate implementation plan
        self.log(f"\n{'='*60}")
        implementation_plan = self.generate_implementation_plan(all_optimizations)
        
        # Generate comprehensive summary
        duration = datetime.now() - start_time
        
        summary = {
            'analysis_duration_sec': duration.total_seconds(),
            'timestamp': datetime.now().isoformat(),
            'optimization_categories': all_optimizations,
            'implementation_plan': implementation_plan,
            'summary_metrics': {
                'total_optimizations_identified': sum(
                    len(opt_dict.get(key, [])) 
                    for opt_dict in all_optimizations.values() 
                    for key in opt_dict.keys() 
                    if isinstance(opt_dict.get(key), list)
                ),
                'high_impact_optimizations': len([
                    opt for opts in all_optimizations.values()
                    for opt_list in opts.values()
                    if isinstance(opt_list, list)
                    for opt in opt_list
                    if opt.get('impact') == 'HIGH'
                ]),
                'immediate_actions_count': len(implementation_plan['immediate_actions']),
                'critical_bottlenecks': len([
                    b for b in bottlenecks.get('identified_bottlenecks', [])
                    if b.get('severity') == 'CRITICAL'
                ])
            },
            'recommendations_summary': []
        }
        
        # Generate top recommendations
        if implementation_plan['immediate_actions']:
            summary['recommendations_summary'].append(
                f"Implement {len(implementation_plan['immediate_actions'])} immediate actions for quick wins"
            )
            
        if summary['summary_metrics']['critical_bottlenecks'] > 0:
            summary['recommendations_summary'].append(
                f"Address {summary['summary_metrics']['critical_bottlenecks']} critical performance bottlenecks immediately"
            )
            
        if algorithmic_opts.get('priority') == 'HIGH':
            summary['recommendations_summary'].append(
                "Focus on algorithmic optimizations for maximum impact"
            )
            
        # Print comprehensive summary
        self.log(f"\n{'='*80}")
        self.log("🎯 OPTIMIZATION ANALYSIS SUMMARY")
        self.log(f"{'='*80}")
        self.log(f"Analysis Duration: {duration.total_seconds():.2f} seconds")
        self.log(f"Total Optimizations: {summary['summary_metrics']['total_optimizations_identified']}")
        self.log(f"High Impact: {summary['summary_metrics']['high_impact_optimizations']}")
        self.log(f"Immediate Actions: {summary['summary_metrics']['immediate_actions_count']}")
        self.log(f"Critical Bottlenecks: {summary['summary_metrics']['critical_bottlenecks']}")
        
        self.log(f"\n📋 TOP IMMEDIATE ACTIONS:")
        for i, action in enumerate(implementation_plan['immediate_actions'][:3], 1):
            self.log(f"  {i}. {action.get('optimization', 'Unknown')}")
            self.log(f"     Impact: {action.get('impact', 'Unknown')}, Complexity: {action.get('complexity', 'Unknown')}")
            
        self.log(f"\n🚨 CRITICAL BOTTLENECKS:")
        critical_bottlenecks = [b for b in bottlenecks.get('identified_bottlenecks', []) if b.get('severity') == 'CRITICAL']
        for bottleneck in critical_bottlenecks:
            self.log(f"  ⚠️  {bottleneck.get('bottleneck', 'Unknown')}: {bottleneck.get('impact', 'Unknown')}")
            
        self.log(f"\n💡 KEY RECOMMENDATIONS:")
        for rec in summary['recommendations_summary']:
            self.log(f"  📈 {rec}")
            
        self.log(f"\n🎯 ESTIMATED IMPROVEMENTS:")
        for metric, improvement in implementation_plan['estimated_impact'].items():
            self.log(f"  📊 {metric.replace('_', ' ').title()}: {improvement}")
            
        # Save results
        results_file = self.config_dir / "obs-tools" / "backups" / f"optimization_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
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
    analyzer = OptimizationAnalyzer()
    results = analyzer.run_comprehensive_optimization_analysis()
    
    # Return exit code based on optimization urgency
    critical_bottlenecks = results.get('summary_metrics', {}).get('critical_bottlenecks', 0)
    if critical_bottlenecks > 0:
        return 2  # Critical issues need immediate attention
    elif results.get('summary_metrics', {}).get('high_impact_optimizations', 0) > 5:
        return 1  # Many high-impact optimizations available
    else:
        return 0  # System is reasonably optimized


if __name__ == "__main__":
    exit(main())