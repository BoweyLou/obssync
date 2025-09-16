#!/usr/bin/env python3
"""
Build cross-system link suggestions between Obsidian and Reminders tasks.

Inputs (schema v2 JSONs):
  - Obsidian index: ~/.config/obsidian_tasks_index.json (or --obs)
  - Reminders index: ~/.config/reminders_tasks_index.json (or --rem)

Output:
  - sync_links.json with suggested links (one-to-one mapping):
    {
      "meta": {"schema": 1, "generated_at": <iso>},
      "links": [
        {
          "obs_uuid": "...",
          "rem_uuid": "...",
          "score": 0.87,
          "title_similarity": 0.90,
          "date_distance_days": 0,
          "due_equal": true,
          "created_at": <first time we created this link>,
          "last_scored": <this run>,
          "last_synced": null,
          "fields": {
            "obs_title": "...",
            "rem_title": "...",
            "obs_due": "YYYY-MM-DD...",
            "rem_due": "YYYY-MM-DD..."
          }
        }
      ]
    }

Heuristics:
  - Token-based title similarity (Dice coefficient on word sets).
  - Due-date equality (date-only) or within N days (tolerance).
  - Optional small boost for matching priority.
  - Global bipartite matching (Hungarian algorithm) for optimal one-to-one assignment.
  - Falls back to greedy matching for very large datasets or when scipy unavailable.

Notes:
  - Existing links are preserved (updated last_scored and fields).
  - New suggestions do not overwrite existing conflicting links.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import sys
import logging

# Import safe I/O utilities and configuration
try:
    # When run as a module from obs_tools
    from lib.safe_io import (
        file_lock,
        safe_write_json_with_lock,
        generate_run_id,
        ensure_run_id_in_meta,
        check_concurrent_access
    )
    from lib.observability import get_logger
    from app_config import get_path
except ImportError:
    # Fallback for direct script execution (though this should be avoided)
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from lib.safe_io import (
        file_lock,
        safe_write_json_with_lock,
        generate_run_id,
        ensure_run_id_in_meta,
        check_concurrent_access
    )
    from lib.observability import get_logger
    from app_config import get_path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
std_logger = logging.getLogger(__name__)

# Try to import optimization libraries in order of preference
try:
    from scipy.optimize import linear_sum_assignment
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    
try:
    from munkres import Munkres
    HAS_MUNKRES = True
except ImportError:
    HAS_MUNKRES = False


def munkres_hungarian(cost_matrix: List[List[float]]) -> Tuple[List[int], List[int]]:
    """
    Use the munkres library for Hungarian algorithm implementation.
    
    Args:
        cost_matrix: 2D list where cost_matrix[i][j] is the cost of assigning row i to column j
        
    Returns:
        (row_indices, col_indices): Lists of matched row and column indices
    """
    if not cost_matrix or not cost_matrix[0]:
        return [], []
    
    n_rows = len(cost_matrix)
    n_cols = len(cost_matrix[0]) if cost_matrix else 0
    
    if n_rows == 0 or n_cols == 0:
        return [], []
    
    # Create munkres instance
    m = Munkres()
    
    # Make a copy to avoid modifying the original
    matrix = [row[:] for row in cost_matrix]
    
    # munkres expects a square matrix, so pad if necessary
    max_size = max(n_rows, n_cols)
    
    # Pad rows
    for i in range(n_rows):
        while len(matrix[i]) < max_size:
            matrix[i].append(float('inf'))
    
    # Pad columns (add new rows)
    while len(matrix) < max_size:
        matrix.append([float('inf')] * max_size)
    
    try:
        # Convert inf to a large finite number for munkres
        MAX_COST = 1e6
        for i in range(max_size):
            for j in range(max_size):
                if matrix[i][j] == float('inf'):
                    matrix[i][j] = MAX_COST
        
        # Compute optimal assignment
        indices = m.compute(matrix)
        
        # Extract valid assignments within original matrix bounds
        row_ind = []
        col_ind = []
        for i, j in indices:
            if i < n_rows and j < n_cols and cost_matrix[i][j] != float('inf'):
                row_ind.append(i)
                col_ind.append(j)
        
        return row_ind, col_ind
        
    except Exception as e:
        std_logger.warning(f"Munkres algorithm failed: {e}. Falling back to greedy.")
        return [], []  # Signal failure to caller




def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: str) -> dict:
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def date_only(iso: Optional[str]) -> Optional[str]:
    if not iso:
        return None
    try:
        return iso[:10]
    except Exception:
        return None


def date_distance_days(a: Optional[str], b: Optional[str]) -> Optional[int]:
    if not a or not b:
        return None
    try:
        da = datetime.fromisoformat(a.replace("Z", "+00:00"))
        db = datetime.fromisoformat(b.replace("Z", "+00:00"))
        return abs((da.date() - db.date()).days)
    except Exception:
        # Fall back to string compare on date-only
        try:
            if a[:10] == b[:10]:
                return 0
        except Exception:
            pass
        return None


def normalize_text(s: Optional[str]) -> List[str]:
    """Legacy function - use cached tokens when available."""
    if not s:
        return []
    import re

    s = s.lower()
    s = re.sub(r"https?://\S+", " ", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    words = [w for w in s.split(" ") if w]
    return words


def get_cached_tokens(task: dict) -> List[str]:
    """Get pre-computed tokens from task record, fallback to live tokenization."""
    cached = task.get("cached_tokens")
    if cached and isinstance(cached, list):
        return cached
    # Fallback to live tokenization for backward compatibility
    return normalize_text(task.get("description"))


def dice_similarity(a_words: List[str], b_words: List[str]) -> float:
    if not a_words or not b_words:
        return 0.0
    a, b = set(a_words), set(b_words)
    inter = len(a & b)
    return (2.0 * inter) / (len(a) + len(b)) if (len(a) + len(b)) else 0.0


def build_indices(rem_tasks: Dict[str, dict]) -> Dict[str, List[str]]:
    by_due: Dict[str, List[str]] = {}
    for rid, r in rem_tasks.items():
        dd = date_only(r.get("due")) or ""
        by_due.setdefault(dd, []).append(rid)
    return by_due


def build_candidate_pairs_optimized(
    obs_ids: List[str], 
    rem_ids: List[str], 
    obs_tasks: Dict[str, dict],
    rem_tasks: Dict[str, dict], 
    days_tol: int,
    top_k_similarity: int = 50
) -> List[Tuple[str, str]]:
    """
    Build pruned candidate pairs using due-date bucketing + top-K title similarity.
    
    Strategy:
    1. Group by due-date buckets (±days_tol)
    2. For each Obsidian task, find top-K most similar Reminders by title
    3. Return only high-potential pairs for cost matrix
    
    Args:
        obs_ids, rem_ids: Task IDs to consider
        obs_tasks, rem_tasks: Task data dictionaries
        days_tol: Due date tolerance in days
        top_k_similarity: Maximum candidates per Obsidian task (default 50)
        
    Returns:
        List of (obs_id, rem_id) candidate pairs
    """
    # Build due-date index for reminders
    rem_by_due = build_indices({rid: rem_tasks[rid] for rid in rem_ids})
    
    # Build expanded due date keys for tolerance
    def get_due_date_candidates(obs_due: Optional[str]) -> List[str]:
        """Get all due date keys within tolerance."""
        candidates = [""]
        if not obs_due:
            return candidates
        
        try:
            from datetime import datetime, timedelta
            base_date = datetime.fromisoformat(obs_due.replace("Z", "+00:00")).date()
            
            for delta_days in range(-days_tol, days_tol + 1):
                candidate_date = base_date + timedelta(days=delta_days)
                candidates.append(candidate_date.isoformat())
        except Exception:
            # Fallback: just exact match and empty
            candidates.append(obs_due[:10] if len(obs_due) >= 10 else obs_due)
        
        return candidates
    
    candidate_pairs = []
    
    for oid in obs_ids:
        o = obs_tasks[oid]
        obs_due = o.get("due")
        
        # Get candidate reminders by due date bucketing
        due_candidates = set()
        for due_key in get_due_date_candidates(obs_due):
            due_candidates.update(rem_by_due.get(due_key, []))
        
        # If no due date matches, include a sample of all reminders
        if not due_candidates:
            due_candidates = set(rem_ids[:min(200, len(rem_ids))]) # Limit fallback
        
        # Calculate title similarity for due-date candidates
        obs_tokens = get_cached_tokens(o)
        similarities = []
        
        for rid in due_candidates:
            if rid not in rem_tasks:  # Safety check
                continue
            r = rem_tasks[rid]
            rem_tokens = get_cached_tokens(r)
            sim = dice_similarity(obs_tokens, rem_tokens)
            similarities.append((sim, rid))
        
        # Sort by similarity (desc) and take top-K
        similarities.sort(key=lambda x: -x[0])
        top_k_rids = [rid for _, rid in similarities[:top_k_similarity]]
        
        # Add to candidate pairs
        for rid in top_k_rids:
            candidate_pairs.append((oid, rid))
    
    std_logger.info(f"Pruned to {len(candidate_pairs)} candidate pairs from {len(obs_ids)}×{len(rem_ids)} = {len(obs_ids)*len(rem_ids)} total pairs")
    return candidate_pairs


def score_pair(o: dict, r: dict, days_tol: int) -> Tuple[float, Dict[str, object]]:
    # Title similarity using cached tokens when available
    t_obs = get_cached_tokens(o)
    t_rem = get_cached_tokens(r)
    title_sim = dice_similarity(t_obs, t_rem)

    # Date score
    o_due = o.get("due")
    r_due = r.get("due")
    ddist = date_distance_days(o_due, r_due)
    if ddist is None:
        # If both have no due date, treat as neutral (don't penalize)
        if not o_due and not r_due:
            date_score = 0.5  # Neutral score for both missing dates
            due_equal = True  # Consider both missing dates as "equal"
        else:
            date_score = 0.0  # One has date, other doesn't - penalize
            due_equal = False
    else:
        due_equal = ddist == 0
        date_score = 1.0 if ddist == 0 else (0.6 if ddist <= days_tol else 0.0)

    # Priority boost
    boost = 0.0
    if o.get("priority") and o.get("priority") == r.get("priority"):
        boost = 0.05

    score = 0.75 * title_sim + 0.25 * date_score + boost
    score = min(score, 1.0)

    fields = {
        "title_similarity": round(title_sim, 4),
        "date_distance_days": ddist,
        "due_equal": due_equal,
        "obs_title": o.get("description"),
        "rem_title": r.get("description"),
        "obs_due": o_due,
        "rem_due": r_due,
    }
    return score, fields


def optimal_matching(
    obs_ids: List[str], 
    rem_ids: List[str], 
    obs_tasks: Dict[str, dict],
    rem_tasks: Dict[str, dict], 
    days_tol: int,
    min_score: float,
    use_pruning: bool = True
) -> Tuple[List[Tuple[str, str, float, Dict[str, object]]], str]:
    """
    Use optimal Hungarian algorithm for globally optimal bipartite matching.
    Returns matches that meet the min_score threshold and the algorithm used.
    
    Args:
        use_pruning: If True, use candidate pair pruning for performance
    
    Returns:
        (matches, algorithm_name): Tuple of matches and algorithm name used
    """
    if not obs_ids or not rem_ids:
        return [], "none"
    
    # Performance optimization: use candidate pruning for large datasets
    if use_pruning and len(obs_ids) * len(rem_ids) > 10000:  # 100x100 threshold
        candidate_pairs = build_candidate_pairs_optimized(
            obs_ids, rem_ids, obs_tasks, rem_tasks, days_tol, top_k_similarity=50
        )
        
        # Create sparse cost matrix using only candidate pairs
        n_obs = len(obs_ids)
        n_rem = len(rem_ids)
        
        # Build lookup maps
        obs_idx_map = {oid: i for i, oid in enumerate(obs_ids)}
        rem_idx_map = {rid: j for j, rid in enumerate(rem_ids)}
        
        # Initialize with high cost
        INF_COST = 1000.0
        cost_matrix = [[INF_COST for _ in range(n_rem)] for _ in range(n_obs)]
        pair_data = {}
        
        # Populate only candidate pairs
        for oid, rid in candidate_pairs:
            if oid in obs_tasks and rid in rem_tasks:
                i, j = obs_idx_map[oid], rem_idx_map[rid]
                o, r = obs_tasks[oid], rem_tasks[rid]
                score, fields = score_pair(o, r, days_tol)
                
                if score >= min_score:
                    cost_matrix[i][j] = -score  # Negative for minimization
                    pair_data[(i, j)] = (score, fields)
    
    else:
        # Original dense matrix approach for smaller datasets
        n_obs = len(obs_ids)
        n_rem = len(rem_ids)
        
        # Create cost matrix (negative scores since Hungarian minimizes cost)
        INF_COST = 1000.0  # Large cost for forbidden pairs
        
        cost_matrix = []
        pair_data = {}  # Store score and fields for each valid pair
        
        for i, oid in enumerate(obs_ids):
            row = []
            o = obs_tasks[oid]
            for j, rid in enumerate(rem_ids):
                r = rem_tasks[rid]
                score, fields = score_pair(o, r, days_tol)
                
                if score >= min_score:
                    cost = -score  # Negative because Hungarian minimizes
                    pair_data[(i, j)] = (score, fields)
                else:
                    cost = INF_COST  # High cost for pairs below threshold
                
                row.append(cost)
            cost_matrix.append(row)
    
    # Try optimal algorithms in order of preference
    row_ind, col_ind, algorithm = None, None, None
    
    if HAS_SCIPY:
        try:
            row_ind, col_ind = linear_sum_assignment(cost_matrix)
            algorithm = "scipy_hungarian"
        except Exception as e:
            std_logger.warning(f"SciPy Hungarian algorithm failed: {e}")
            row_ind, col_ind = None, None
    
    if (row_ind is None or col_ind is None) and HAS_MUNKRES:
        try:
            row_ind, col_ind = munkres_hungarian(cost_matrix)
            if row_ind and col_ind:  # Check if it succeeded
                algorithm = "munkres_hungarian"
            else:
                row_ind, col_ind = None, None
        except Exception as e:
            std_logger.warning(f"Munkres Hungarian algorithm failed: {e}")
            row_ind, col_ind = None, None
    
    if row_ind is None or col_ind is None:
        # Both optimal algorithms failed, signal to caller
        return [], "failed"
    
    # Extract valid matches (those that meet min_score threshold)
    chosen = []
    for i, j in zip(row_ind, col_ind):
        if (i, j) in pair_data:
            oid = obs_ids[i]
            rid = rem_ids[j]
            score, fields = pair_data[(i, j)]
            chosen.append((oid, rid, score, fields))
    
    # Sort for deterministic output
    chosen.sort(key=lambda x: (-x[2], x[0], x[1]))
    return chosen, algorithm


def greedy_matching(
    obs_ids: List[str], 
    rem_ids: List[str], 
    obs_tasks: Dict[str, dict],
    rem_tasks: Dict[str, dict], 
    days_tol: int,
    min_score: float
) -> List[Tuple[str, str, float, Dict[str, object]]]:
    """
    Optimized greedy matching with candidate pruning.
    """
    # Use candidate pruning for better performance
    if len(obs_ids) * len(rem_ids) > 5000:  # 50x100 threshold
        candidate_pairs = build_candidate_pairs_optimized(
            obs_ids, rem_ids, obs_tasks, rem_tasks, days_tol, top_k_similarity=50
        )
        
        candidates: List[Tuple[str, str, float, Dict[str, object]]] = []
        for oid, rid in candidate_pairs:
            if oid in obs_tasks and rid in rem_tasks:
                o, r = obs_tasks[oid], rem_tasks[rid]
                score, fields = score_pair(o, r, days_tol)
                if score >= min_score:
                    candidates.append((oid, rid, score, fields))
    else:
        # Original approach for smaller datasets
        rem_by_due = build_indices({rid: rem_tasks[rid] for rid in rem_ids})
        # Sort the due buckets for determinism
        for k in list(rem_by_due.keys()):
            rem_by_due[k] = sorted(rem_by_due[k])

        candidates: List[Tuple[str, str, float, Dict[str, object]]] = []
        for oid in obs_ids:
            o = obs_tasks[oid]
            dd = date_only(o.get("due")) or ""
            pool = rem_by_due.get(dd, [])
            # If no due date match, consider all reminders (fallback)
            pool = pool if pool else rem_ids
            for rid in pool:
                r = rem_tasks[rid]
                score, fields = score_pair(o, r, days_tol)
                if score >= min_score:
                    candidates.append((oid, rid, score, fields))

    # Greedy one-to-one assignment
    candidates.sort(key=lambda x: (-x[2], x[0], x[1]))
    used_o: set[str] = set()
    used_r: set[str] = set()
    chosen: List[Tuple[str, str, float, Dict[str, object]]] = []
    for oid, rid, s, f in candidates:
        if oid in used_o or rid in used_r:
            continue
        used_o.add(oid)
        used_r.add(rid)
        chosen.append((oid, rid, s, f))

    return chosen


def suggest_links(
    obs_tasks: Dict[str, dict],
    rem_tasks: Dict[str, dict],
    min_score: float,
    days_tol: int,
    include_done: bool,
    use_hungarian: bool = True,
) -> List[Tuple[str, str, float, Dict[str, object]]]:
    # Filter tasks
    def keep(t: dict) -> bool:
        if t.get("deleted"):
            return False
        return include_done or (t.get("status") != "done")

    obs_ids = sorted([oid for oid, o in obs_tasks.items() if keep(o)])
    rem_ids = sorted([rid for rid, r in rem_tasks.items() if keep(r)])

    if not obs_ids or not rem_ids:
        return []

    std_logger.info(f"Matching {len(obs_ids)} Obsidian tasks with {len(rem_ids)} Reminders tasks")
    
    # Choose matching algorithm with improved logic
    if use_hungarian:
        # Performance threshold: use Hungarian for reasonable matrix sizes
        # Optimized thresholds with candidate pruning
        matrix_size = len(obs_ids) * len(rem_ids)
        if matrix_size > 250000:  # 500x500 threshold (reduced from 1M with pruning)
            std_logger.info(f"Large dataset ({len(obs_ids)}x{len(rem_ids)}), forcing greedy matching for performance")
            return greedy_matching(obs_ids, rem_ids, obs_tasks, rem_tasks, days_tol, min_score)
        
        # Try optimal matching first
        optimal_matches, algorithm = optimal_matching(obs_ids, rem_ids, obs_tasks, rem_tasks, days_tol, min_score, use_pruning=True)
        
        if algorithm == "failed":
            # Optimal algorithms failed, fall back to greedy
            std_logger.warning("Optimal Hungarian algorithms failed, falling back to greedy matching")
            return greedy_matching(obs_ids, rem_ids, obs_tasks, rem_tasks, days_tol, min_score)
        
        # Guard: Ensure fallback doesn't produce fewer matches than greedy
        # Run greedy as a comparison
        greedy_matches = greedy_matching(obs_ids, rem_ids, obs_tasks, rem_tasks, days_tol, min_score)
        
        if len(optimal_matches) < len(greedy_matches):
            std_logger.warning(f"{algorithm} produced {len(optimal_matches)} matches vs greedy's {len(greedy_matches)}, falling back to greedy")
            return greedy_matches
        
        # Log successful optimal matching
        if algorithm == "scipy_hungarian":
            std_logger.info(f"Using SciPy Hungarian algorithm, found {len(optimal_matches)} matches")
        elif algorithm == "munkres_hungarian":
            std_logger.info(f"Using Munkres Hungarian algorithm, found {len(optimal_matches)} matches")
        
        return optimal_matches
    
    else:
        # Explicitly requested greedy matching
        std_logger.info("Using greedy matching (explicitly requested)")
        return greedy_matching(obs_ids, rem_ids, obs_tasks, rem_tasks, days_tol, min_score)


def load_existing_links(path: str) -> List[dict]:
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("links", []) or []
    except Exception:
        return []


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Suggest links between Obsidian and Reminders tasks.")
    ap.add_argument("--obs", default=get_path("obsidian_index"), help="Path to obsidian_tasks_index.json")
    ap.add_argument("--rem", default=get_path("reminders_index"), help="Path to reminders_tasks_index.json")
    ap.add_argument("--output", default=get_path("links"), help="Path to sync_links.json to write")
    ap.add_argument("--min-score", type=float, default=0.75, help="Minimum match score to accept (0-1)")
    ap.add_argument("--days-tol", type=int, default=1, help="Due date tolerance in days")
    ap.add_argument("--include-done", action="store_true", help="Include completed tasks in matching")
    ap.add_argument("--greedy", action="store_true", help="Force use of greedy matching instead of Hungarian algorithm")
    args = ap.parse_args(argv)
    
    # Initialize logger and start run tracking
    logger = get_logger("build_sync_links")
    run_id = logger.start_run("build_sync_links", {
        "obs_path": args.obs,
        "rem_path": args.rem,
        "output_path": args.output,
        "min_score": args.min_score,
        "days_tol": args.days_tol,
        "include_done": args.include_done,
        "force_greedy": args.greedy
    })

    try:
        obs = load_json(os.path.abspath(os.path.expanduser(args.obs)))
        rem = load_json(os.path.abspath(os.path.expanduser(args.rem)))
        obs_tasks: Dict[str, dict] = obs.get("tasks", {}) or {}
        rem_tasks: Dict[str, dict] = rem.get("tasks", {}) or {}
        
        logger.info("Loaded task indices", 
                   obs_tasks_count=len(obs_tasks),
                   rem_tasks_count=len(rem_tasks))
    except FileNotFoundError as e:
        logger.error("Input file not found", error=str(e))
        logger.end_run(False, str(e))
        print(f"Error: {e}")
        return 1
    except Exception as e:
        logger.error("Failed to load input files", error=str(e))
        logger.end_run(False, str(e))
        print(f"Error loading input files: {e}")
        return 1

    use_hungarian = not args.greedy
    algorithm_name = "greedy" if args.greedy else "hungarian"
    
    logger.info("Starting link matching", 
               algorithm=algorithm_name,
               min_score=args.min_score,
               days_tolerance=args.days_tol,
               include_done=args.include_done)
    
    suggestions = suggest_links(obs_tasks, rem_tasks, args.min_score, args.days_tol, args.include_done, use_hungarian)
    
    logger.info("Link suggestion completed", candidates_found=len(suggestions))

    # Merge with existing links with one-to-one enforcement
    out_path = os.path.abspath(os.path.expanduser(args.output))
    existing = load_existing_links(out_path)
    now = now_iso()
    
    logger.info("Processing existing links", existing_links_count=len(existing))

    # Build current maps
    links: List[dict] = []
    by_obs: Dict[str, dict] = {}
    by_rem: Dict[str, dict] = {}
    by_pair: Dict[Tuple[str, str], dict] = {}

    for rec in existing:
        ou = rec.get("obs_uuid"); ru = rec.get("rem_uuid")
        if not ou or not ru:
            continue
        rec = dict(rec)
        rec.setdefault("created_at", now)
        rec["last_scored"] = now
        links.append(rec)
        by_pair[(ou, ru)] = rec
        # Prefer first occurrence per side
        by_obs.setdefault(ou, rec)
        by_rem.setdefault(ru, rec)

    # Process new suggestions deterministically (already sorted)
    new_links = 0
    updated_links = 0
    replaced_links = 0
    rejected_candidates = 0
    
    for ou, ru, score, fields in suggestions:
        pair = (ou, ru)
        if pair in by_pair:
            # Update existing pair's score/fields if improved
            rec = by_pair[pair]
            old_score = rec.get("score", 0)
            rec["score"] = max(round(score, 4), old_score)
            rec.setdefault("fields", {}).update(fields)
            if round(score, 4) > old_score:
                updated_links += 1
            continue

        existing_o = by_obs.get(ou)
        existing_r = by_rem.get(ru)
        if existing_o is None and existing_r is None:
            # Free on both sides: accept
            newrec = {
                "obs_uuid": ou,
                "rem_uuid": ru,
                "score": round(score, 4),
                "title_similarity": fields.get("title_similarity"),
                "date_distance_days": fields.get("date_distance_days"),
                "due_equal": fields.get("due_equal"),
                "created_at": now,
                "last_scored": now,
                "last_synced": None,
                "fields": fields,
            }
            links.append(newrec)
            by_pair[pair] = newrec
            by_obs[ou] = newrec
            by_rem[ru] = newrec
            new_links += 1
            continue

        # If one (or both) sides already linked, only replace if strictly higher score
        def score_of(rec: Optional[dict]) -> float:
            return float(rec.get("score", 0)) if rec else 0.0

        replace = False
        # If both sides are linked, require new score > both existing
        if existing_o is not None and existing_r is not None:
            replace = (score > max(score_of(existing_o), score_of(existing_r)))
        elif existing_o is not None:
            replace = (score > score_of(existing_o))
        elif existing_r is not None:
            replace = (score > score_of(existing_r))

        if replace:
            # Remove old links for the occupied sides
            to_remove: List[dict] = []
            if existing_o is not None:
                to_remove.append(existing_o)
            if existing_r is not None and existing_r is not existing_o:
                to_remove.append(existing_r)
            for rec in to_remove:
                old_ou, old_ru = rec.get("obs_uuid"), rec.get("rem_uuid")
                try:
                    links.remove(rec)
                except ValueError:
                    pass
                by_pair.pop((old_ou, old_ru), None)
                if by_obs.get(old_ou) is rec:
                    by_obs.pop(old_ou, None)
                if by_rem.get(old_ru) is rec:
                    by_rem.pop(old_ru, None)

            newrec = {
                "obs_uuid": ou,
                "rem_uuid": ru,
                "score": round(score, 4),
                "title_similarity": fields.get("title_similarity"),
                "date_distance_days": fields.get("date_distance_days"),
                "due_equal": fields.get("due_equal"),
                "created_at": now,
                "last_scored": now,
                "last_synced": None,
                "fields": fields,
            }
            links.append(newrec)
            by_pair[pair] = newrec
            by_obs[ou] = newrec
            by_rem[ru] = newrec
            replaced_links += 1
        else:
            # Keep existing link(s), ignore this candidate
            rejected_candidates += 1

    # Sort links deterministically by (obs_uuid, rem_uuid)
    links.sort(key=lambda d: (d.get("obs_uuid"), d.get("rem_uuid")))
    
    # Calculate acceptance rate
    total_candidates = len(suggestions)
    accepted = new_links + replaced_links
    acceptance_rate = accepted / total_candidates if total_candidates > 0 else 0.0
    
    # Log link processing metrics
    logger.update_counts(
        input_counts={
            "obs_tasks": len(obs_tasks),
            "rem_tasks": len(rem_tasks),
            "candidate_links": total_candidates,
            "existing_links": len(existing)
        },
        output_counts={
            "final_links": len(links),
            "new_links": new_links,
            "updated_links": updated_links,
            "replaced_links": replaced_links,
            "rejected_candidates": rejected_candidates
        }
    )
    
    logger.update_metrics({
        "acceptance_rate": acceptance_rate,
        "algorithm_used": algorithm_name if suggestions else "none"
    })
    
    logger.info("Link processing completed",
               total_links=len(links),
               new_links=new_links,
               updated_links=updated_links,
               replaced_links=replaced_links,
               rejected_candidates=rejected_candidates,
               acceptance_rate=round(acceptance_rate, 3))

    out = {
        "meta": {"schema": 1, "generated_at": now, "obs_total": len(obs_tasks), "rem_total": len(rem_tasks)},
        "links": links,
    }
    
    # Add run_id to meta for concurrent write detection
    out = ensure_run_id_in_meta(out, run_id)

    # Check for concurrent access before writing
    if check_concurrent_access(out_path, run_id):
        print(f"Warning: Concurrent access detected to {out_path}, proceeding with caution")

    # Write with locking and atomic operations
    try:
        # Create deterministic JSON for comparison
        new_json = json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True)
        
        # Check if file exists and content has changed
        changed = True
        if os.path.isfile(out_path):
            try:
                with open(out_path, "r", encoding="utf-8") as f:
                    old_json = f.read()
                # Compare content ignoring generated_at timestamp for change detection
                try:
                    import copy
                    old_obj = json.loads(old_json)
                    new_obj = copy.deepcopy(out)
                    # Remove generated_at for comparison
                    old_obj.get("meta", {}).pop("generated_at", None)
                    new_obj.get("meta", {}).pop("generated_at", None)
                    if json.dumps(old_obj, sort_keys=True) == json.dumps(new_obj, sort_keys=True):
                        changed = False
                except Exception:
                    # Fall back to simple string comparison
                    if old_json == new_json:
                        changed = False
            except Exception:
                pass  # Assume changed if we can't read the old file
        
        if not changed:
            logger.info("No changes detected, skipping write", 
                       output_path=out_path, 
                       link_count=len(links))
            summary_path = logger.end_run(True)
            print(f"No changes for {out_path} (links={len(links)})")
            return 0
        
        # Write safely with file locking
        safe_write_json_with_lock(
            out_path, 
            out, 
            run_id=run_id,
            indent=2,
            timeout=30.0
        )
        
        logger.info("Successfully wrote link suggestions", 
                   output_path=out_path, 
                   link_count=len(links),
                   suggestions_processed=len(suggestions))
        summary_path = logger.end_run(True)
        print(f"Wrote {len(links)} link(s) to {out_path} (from {len(suggestions)} suggestions)")
        return 0
        
    except Exception as e:
        logger.error("Failed to write link suggestions", 
                    output_path=out_path, 
                    error=str(e))
        logger.end_run(False, str(e))
        print(f"Error writing to {out_path}: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
