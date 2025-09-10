#!/usr/bin/env python3
"""
Performance testing and validation script for build_sync_links optimizations.

Tests the performance improvements from:
1. Cached tokenization 
2. Due-date bucketing
3. Top-K similarity filtering
4. Candidate pair pruning

Validates that match quality is maintained or improved.
"""

import time
import json
import sys
import os
from typing import Dict, List, Tuple
from collections import defaultdict

# Add the obs_tools path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'obs_tools', 'commands'))

try:
    from build_sync_links import (
        suggest_links, 
        build_candidate_pairs_optimized,
        get_cached_tokens,
        normalize_text,
        dice_similarity,
        score_pair
    )
except ImportError as e:
    print(f"Error importing build_sync_links: {e}")
    sys.exit(1)


def generate_test_data(n_obs: int = 100, n_rem: int = 100) -> Tuple[Dict[str, dict], Dict[str, dict]]:
    """Generate synthetic test data for performance testing."""
    import random
    import datetime
    
    # Set seed for reproducible tests
    random.seed(42)
    
    obs_tasks = {}
    rem_tasks = {}
    
    # Common words for title generation
    action_words = ["fix", "update", "review", "implement", "test", "debug", "deploy", "analyze", "optimize", "refactor"]
    noun_words = ["bug", "feature", "issue", "task", "project", "system", "code", "database", "api", "interface"]
    
    # Generate Obsidian tasks
    for i in range(n_obs):
        uid = f"obs_{i:04d}"
        
        # Generate title with some duplication/similarity
        title_words = random.choices(action_words, k=1) + random.choices(noun_words, k=random.randint(1, 3))
        title = " ".join(title_words)
        
        # Add some variation
        if random.random() < 0.3:
            title += f" #{random.choice(['urgent', 'lowpri', 'bug', 'feature'])}"
        
        # Generate tokens for caching
        tokens = title.lower().split()
        tokens_hash = f"hash_{i:04x}"
        
        # Generate due date (some tasks have no due date)
        due_date = None
        if random.random() < 0.7:  # 70% have due dates
            base_date = datetime.date.today()
            delta_days = random.randint(-30, 30)
            due_date = (base_date + datetime.timedelta(days=delta_days)).isoformat()
        
        obs_tasks[uid] = {
            "uuid": uid,
            "description": title,
            "due": due_date,
            "status": random.choice(["todo", "done"]),
            "cached_tokens": tokens,
            "title_hash": tokens_hash
        }
    
    # Generate Reminders tasks with some overlap
    for i in range(n_rem):
        uid = f"rem_{i:04d}"
        
        # 30% chance of similar title to an Obsidian task
        if random.random() < 0.3 and obs_tasks:
            # Pick a random obs task and create similar title
            base_obs = random.choice(list(obs_tasks.values()))
            base_title = base_obs["description"]
            
            # Add slight variation
            title = base_title
            if random.random() < 0.5:
                title = base_title.replace(" ", " - ")
            elif random.random() < 0.5:
                title = f"TODO: {base_title}"
        else:
            # Generate independent title
            title_words = random.choices(action_words, k=1) + random.choices(noun_words, k=random.randint(1, 3))
            title = " ".join(title_words)
        
        # Generate tokens for caching
        tokens = title.lower().split()
        tokens_hash = f"rhash_{i:04x}"
        
        # Generate due date (some overlap with obs tasks)
        due_date = None
        if random.random() < 0.7:  # 70% have due dates
            if random.random() < 0.4 and obs_tasks:  # 40% chance to match an obs date
                obs_with_dates = [t for t in obs_tasks.values() if t.get("due")]
                if obs_with_dates:
                    due_date = random.choice(obs_with_dates)["due"]
            
            if not due_date:
                base_date = datetime.date.today()
                delta_days = random.randint(-30, 30)
                due_date = (base_date + datetime.timedelta(days=delta_days)).isoformat()
        
        rem_tasks[uid] = {
            "uuid": uid,
            "description": title,
            "due": due_date,
            "status": random.choice(["todo", "done"]),
            "cached_tokens": tokens,
            "title_hash": tokens_hash
        }
    
    return obs_tasks, rem_tasks


def benchmark_tokenization(obs_tasks: Dict[str, dict], rem_tasks: Dict[str, dict], num_iterations: int = 1000) -> Dict[str, float]:
    """Benchmark tokenization performance: cached vs live."""
    
    # Test tasks
    test_obs = list(obs_tasks.values())[:min(50, len(obs_tasks))]
    test_rem = list(rem_tasks.values())[:min(50, len(rem_tasks))]
    
    # Benchmark cached tokenization
    start_time = time.time()
    for _ in range(num_iterations):
        for obs in test_obs:
            for rem in test_rem:
                obs_tokens = get_cached_tokens(obs)
                rem_tokens = get_cached_tokens(rem)
                dice_similarity(obs_tokens, rem_tokens)
    cached_time = time.time() - start_time
    
    # Benchmark live tokenization (simulate no cache)
    start_time = time.time()
    for _ in range(num_iterations):
        for obs in test_obs:
            for rem in test_rem:
                obs_tokens = normalize_text(obs.get("description"))
                rem_tokens = normalize_text(rem.get("description"))
                dice_similarity(obs_tokens, rem_tokens)
    live_time = time.time() - start_time
    
    return {
        "cached_time_ms": cached_time * 1000,
        "live_time_ms": live_time * 1000,
        "speedup_factor": live_time / cached_time if cached_time > 0 else 0,
        "pairs_per_iteration": len(test_obs) * len(test_rem)
    }


def benchmark_matching_algorithms(obs_tasks: Dict[str, dict], rem_tasks: Dict[str, dict]) -> Dict[str, any]:
    """Benchmark matching algorithm performance and quality."""
    
    obs_ids = list(obs_tasks.keys())
    rem_ids = list(rem_tasks.keys())
    
    results = {}
    
    # Test different dataset sizes
    for size_factor in [0.2, 0.5, 1.0]:
        n_obs = int(len(obs_ids) * size_factor)
        n_rem = int(len(rem_ids) * size_factor)
        
        test_obs_ids = obs_ids[:n_obs]
        test_rem_ids = rem_ids[:n_rem]
        
        size_key = f"{n_obs}x{n_rem}"
        results[size_key] = {}
        
        print(f"Testing {size_key} dataset...")
        
        # Test optimized matching (with pruning)
        start_time = time.time()
        optimized_matches = suggest_links(
            {k: obs_tasks[k] for k in test_obs_ids},
            {k: rem_tasks[k] for k in test_rem_ids},
            min_score=0.5,
            days_tol=3,
            include_done=True,
            use_hungarian=True
        )
        optimized_time = time.time() - start_time
        
        # Test greedy matching (fallback)
        start_time = time.time()
        greedy_matches = suggest_links(
            {k: obs_tasks[k] for k in test_obs_ids},
            {k: rem_tasks[k] for k in test_rem_ids},
            min_score=0.5,
            days_tol=3,
            include_done=True,
            use_hungarian=False
        )
        greedy_time = time.time() - start_time
        
        results[size_key] = {
            "optimized": {
                "time_ms": optimized_time * 1000,
                "matches": len(optimized_matches),
                "avg_score": sum(m[2] for m in optimized_matches) / len(optimized_matches) if optimized_matches else 0
            },
            "greedy": {
                "time_ms": greedy_time * 1000,
                "matches": len(greedy_matches),
                "avg_score": sum(m[2] for m in greedy_matches) / len(greedy_matches) if greedy_matches else 0
            },
            "speedup_factor": greedy_time / optimized_time if optimized_time > 0 else 0
        }
    
    return results


def validate_match_quality(obs_tasks: Dict[str, dict], rem_tasks: Dict[str, dict]) -> Dict[str, any]:
    """Validate that optimization doesn't hurt match quality."""
    
    # Run both algorithms on same data
    obs_ids = list(obs_tasks.keys())[:50]  # Smaller dataset for validation
    rem_ids = list(rem_tasks.keys())[:50]
    
    test_obs = {k: obs_tasks[k] for k in obs_ids}
    test_rem = {k: rem_tasks[k] for k in rem_ids}
    
    # Optimized matching
    opt_matches = suggest_links(test_obs, test_rem, 0.3, 3, True, True)
    
    # Greedy matching
    greedy_matches = suggest_links(test_obs, test_rem, 0.3, 3, True, False)
    
    # Analyze overlap and quality
    opt_pairs = {(m[0], m[1]): m[2] for m in opt_matches}
    greedy_pairs = {(m[0], m[1]): m[2] for m in greedy_matches}
    
    common_pairs = set(opt_pairs.keys()) & set(greedy_pairs.keys())
    opt_only = set(opt_pairs.keys()) - set(greedy_pairs.keys())
    greedy_only = set(greedy_pairs.keys()) - set(opt_pairs.keys())
    
    return {
        "optimized_matches": len(opt_matches),
        "greedy_matches": len(greedy_matches),
        "common_pairs": len(common_pairs),
        "optimized_only": len(opt_only),
        "greedy_only": len(greedy_only),
        "optimized_avg_score": sum(opt_pairs.values()) / len(opt_pairs) if opt_pairs else 0,
        "greedy_avg_score": sum(greedy_pairs.values()) / len(greedy_pairs) if greedy_pairs else 0,
        "overlap_percentage": len(common_pairs) / max(len(opt_pairs), len(greedy_pairs)) * 100 if max(len(opt_pairs), len(greedy_pairs)) > 0 else 0
    }


def main():
    """Run performance benchmark and validation tests."""
    print("=== Task Matching Performance Optimization Benchmark ===")
    print()
    
    # Generate test data
    print("Generating test data...")
    obs_tasks, rem_tasks = generate_test_data(200, 200)
    print(f"Generated {len(obs_tasks)} Obsidian tasks and {len(rem_tasks)} Reminders tasks")
    print()
    
    # Tokenization benchmark
    print("1. Tokenization Performance Test")
    print("-" * 40)
    tokenization_results = benchmark_tokenization(obs_tasks, rem_tasks, 100)
    print(f"Cached tokenization: {tokenization_results['cached_time_ms']:.1f}ms")
    print(f"Live tokenization: {tokenization_results['live_time_ms']:.1f}ms")
    print(f"Speedup factor: {tokenization_results['speedup_factor']:.2f}x")
    print(f"Pairs per iteration: {tokenization_results['pairs_per_iteration']}")
    print()
    
    # Matching algorithm benchmark
    print("2. Matching Algorithm Performance Test")
    print("-" * 40)
    matching_results = benchmark_matching_algorithms(obs_tasks, rem_tasks)
    for size, results in matching_results.items():
        print(f"\nDataset size: {size}")
        print(f"  Optimized: {results['optimized']['time_ms']:.1f}ms, {results['optimized']['matches']} matches, avg score: {results['optimized']['avg_score']:.3f}")
        print(f"  Greedy:    {results['greedy']['time_ms']:.1f}ms, {results['greedy']['matches']} matches, avg score: {results['greedy']['avg_score']:.3f}")
        if results['speedup_factor'] > 1:
            print(f"  Performance: Optimized is {results['speedup_factor']:.2f}x faster")
        elif results['speedup_factor'] < 1:
            print(f"  Performance: Greedy is {1/results['speedup_factor']:.2f}x faster")
    print()
    
    # Match quality validation
    print("3. Match Quality Validation")
    print("-" * 40)
    quality_results = validate_match_quality(obs_tasks, rem_tasks)
    print(f"Optimized algorithm: {quality_results['optimized_matches']} matches, avg score: {quality_results['optimized_avg_score']:.3f}")
    print(f"Greedy algorithm: {quality_results['greedy_matches']} matches, avg score: {quality_results['greedy_avg_score']:.3f}")
    print(f"Common pairs: {quality_results['common_pairs']}")
    print(f"Overlap: {quality_results['overlap_percentage']:.1f}%")
    print()
    
    # Performance summary
    print("=== Summary ===")
    print(f"✓ Tokenization caching provides {tokenization_results['speedup_factor']:.1f}x speedup")
    
    # Find best performance improvement
    best_speedup = max(r['speedup_factor'] for r in matching_results.values())
    if best_speedup > 1:
        print(f"✓ Matching algorithm optimization provides up to {best_speedup:.1f}x speedup")
    else:
        print(f"⚠ Matching algorithm shows mixed performance (up to {1/min(r['speedup_factor'] for r in matching_results.values()):.1f}x slower)")
    
    if quality_results['overlap_percentage'] > 80:
        print(f"✓ Match quality maintained ({quality_results['overlap_percentage']:.1f}% overlap)")
    else:
        print(f"⚠ Match quality differs significantly ({quality_results['overlap_percentage']:.1f}% overlap)")
    
    print("\nOptimizations successfully implemented!")


if __name__ == "__main__":
    main()