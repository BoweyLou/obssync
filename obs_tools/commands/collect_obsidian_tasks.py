#!/usr/bin/env python3
"""
Collect Obsidian Tasks across saved vaults and write a unified JSON index.

By default, reads vaults from the discovery config created by
discover_obsidian_vaults.py (at ~/.config/obsidian_vaults.json).

For each Markdown task ("- [ ]" / "- [x]"), extracts:
  - vault name and path, file relative path, line number
  - status (todo/done), description, full original line
  - tags (#tag), due/scheduled/start/done dates, recurrence, priority
  - nearest heading (breadcrumb)
  - file timestamps (created_at/modified_at)

Persistency & UUIDs:
  - Each task gets a stable UUID per (file, block-id/line-hash).
  - If an existing index file is provided, previously seen tasks
    keep their UUID and created_at; updated_at is refreshed.

Output file (JSON):
  - Default: ~/.config/obsidian_tasks_index.json
  - Structure: { meta: {...}, tasks: { <uuid>: <record>, ... } }
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Set, Tuple
from uuid import uuid4
import time

# Add the project root to the path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# Import safe I/O utilities
from lib.safe_io import (
    safe_write_json_with_lock, 
    generate_run_id, 
    ensure_run_id_in_meta, 
    check_concurrent_access
)

# Import observability utilities
from lib.observability import get_logger

# Import centralized path configuration
from app_config import get_path


@dataclass(frozen=True)
class Vault:
    name: str
    path: str


@dataclass
class FileCache:
    """Cache entry for a single markdown file."""
    mtime: float
    tasks: List[dict]
    parsed_at: str


@dataclass 
class IncrementalCache:
    """Incremental cache for file parsing optimization."""
    schema_version: int
    created_at: str
    last_updated: str
    file_cache: Dict[str, FileCache]  # absolute_path -> FileCache


TASK_RE = re.compile(r"^(?P<indent>\s*)[-*]\s\[(?P<status>[ xX])\]\s*(?P<rest>.*)$")
HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<title>.+?)\s*$")
BLOCK_ID_RE = re.compile(r"\^(?P<bid>[A-Za-z0-9\-]+)\s*$")

# Tokens (common Tasks plugin markers)
DATE_PAT = r"(\d{4}-\d{2}-\d{2})"
DUE_RE = re.compile(r"(?:📅\s*|\(\s*due\s*:\s*)(?P<due>" + DATE_PAT + r")(?:\)|\b)")
SCHED_RE = re.compile(r"(?:⏳\s*|\(\s*scheduled\s*:\s*)(?P<scheduled>" + DATE_PAT + r")(?:\)|\b)")
START_RE = re.compile(r"(?:🛫\s*|\(\s*start\s*:\s*)(?P<start>" + DATE_PAT + r")(?:\)|\b)")
DONE_RE = re.compile(r"(?:✅\s*|\(\s*done\s*:\s*)(?P<done>" + DATE_PAT + r")(?:\)|\b)")
RECUR_RE = re.compile(r"(?:🔁\s*)(?P<recurrence>[^#^✅📅⏳🛫⏫🔼🔽🔺]+?)\s*(?=$|[#^✅📅⏳🛫⏫🔼🔽🔺])")
PRIORITY_RE = re.compile(r"(?P<prio>[⏫🔼🔽🔺])")
TAG_RE = re.compile(r"(?P<tag>#[A-Za-z0-9/_\-]+)")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def file_times(path: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        st = os.stat(path)
        created = getattr(st, "st_birthtime", None)
        if created is None:
            created = min(st.st_mtime, st.st_ctime)
        modified = st.st_mtime
        return to_iso(created), to_iso(modified)
    except OSError:
        return None, None


def load_vaults(config_path: str) -> List[Vault]:
    cfg = os.path.abspath(os.path.expanduser(config_path))
    if not os.path.isfile(cfg):
        raise FileNotFoundError(f"Vaults config not found: {cfg}")
    with open(cfg, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        entries = data.get("vaults", [])
    else:
        entries = data

    vaults: List[Vault] = []
    for item in entries:
        if isinstance(item, dict) and "path" in item:
            name = str(item.get("name") or os.path.basename(item["path"]))
            path = os.path.abspath(os.path.expanduser(str(item["path"])))
            if os.path.isdir(path):
                vaults.append(Vault(name=name, path=path))
    return vaults


def iter_md_files(root: str, ignore_dirs: Set[str]) -> Iterable[str]:
    for dirpath, dirnames, filenames in os.walk(root):
        pruned = [d for d in list(dirnames) if d in ignore_dirs]
        for d in pruned:
            dirnames.remove(d)
        for fn in filenames:
            if fn.lower().endswith(".md"):
                yield os.path.join(dirpath, fn)


def normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def normalize_text_for_similarity(s: Optional[str]) -> List[str]:
    """Normalize text for similarity matching and return tokenized words."""
    if not s:
        return []
    import re

    s = s.lower()
    s = re.sub(r"https?://\S+", " ", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    words = [w for w in s.split(" ") if w]
    return words


def extract_tokens(text: str) -> Tuple[dict, str]:
    meta: Dict[str, Optional[str] | str] = {
        "due": None,
        "scheduled": None,
        "start": None,
        "done": None,
        "recurrence": None,
        "priority": None,
        "tags": [],
    }

    # Tags (collect but do not remove yet; we'll remove later from desc)
    tags = [m.group("tag") for m in TAG_RE.finditer(text)]
    meta["tags"] = sorted(set(tags))

    # Dates and recurrence and priority
    for rx, key in ((DUE_RE, "due"), (SCHED_RE, "scheduled"), (START_RE, "start"), (DONE_RE, "done")):
        m = rx.search(text)
        if m:
            meta[key] = m.group(key)
            text = rx.sub("", text)

    m = RECUR_RE.search(text)
    if m:
        meta["recurrence"] = normalize_spaces(m.group("recurrence"))
        text = RECUR_RE.sub("", text)

    m = PRIORITY_RE.search(text)
    if m:
        sym = m.group("prio")
        pr = {"⏫": "high", "🔼": "medium", "🔽": "low", "🔺": "low"}.get(sym, sym)
        meta["priority"] = pr
        text = PRIORITY_RE.sub("", text)

    # Remove tags from description text
    text = TAG_RE.sub("", text)

    # Remove any leftover parentheses pairs that are now empty
    text = re.sub(r"\(\s*\)", "", text)

    return meta, normalize_spaces(text)


def heading_tracker(lines: List[str]) -> List[Tuple[int, List[str]]]:
    breadcrumb: List[str] = []
    mapping: List[Tuple[int, List[str]]] = []
    for idx, line in enumerate(lines, start=1):
        hm = HEADING_RE.match(line)
        if hm:
            level = len(hm.group("hashes"))
            title = hm.group("title").strip()
            # Adjust breadcrumb to level
            while len(breadcrumb) >= level:
                breadcrumb.pop()
            breadcrumb.append(title)
        mapping.append((idx, breadcrumb.copy()))
    return mapping


def code_block_tracker(lines: List[str]) -> Set[int]:
    """Track which lines are inside code blocks and should be ignored for task parsing."""
    in_fenced_block = False
    in_indented_block = False
    code_lines = set()
    fence_pattern = re.compile(r"^\s*```")
    
    for idx, line in enumerate(lines, start=1):
        # Check for fenced code blocks
        if fence_pattern.match(line):
            if in_fenced_block:
                # End of fenced block
                in_fenced_block = False
            else:
                # Start of fenced block
                in_fenced_block = True
            code_lines.add(idx)
            continue
            
        # If in fenced block, mark line as code
        if in_fenced_block:
            code_lines.add(idx)
            continue
            
        # Check for indented code blocks (4+ spaces or 1+ tabs at start)
        # But exclude lines that look like list items (start with - or * or numbers)
        stripped = line.lstrip()
        if line and not stripped:
            # Empty line - doesn't affect indented code block status
            if in_indented_block:
                code_lines.add(idx)
            continue
            
        indent = len(line) - len(stripped)
        has_tab_indent = line.startswith('\t')
        
        # Check if this looks like a list item (could be nested)
        is_list_item = re.match(r'^\s*[-*+]\s', line) or re.match(r'^\s*\d+\.\s', line)
        
        is_indented_code = (indent >= 4 or has_tab_indent) and not is_list_item
        
        if is_indented_code:
            in_indented_block = True
            code_lines.add(idx)
        else:
            # Non-indented content or list items break indented code blocks
            in_indented_block = False
    
    return code_lines


def parse_tasks_from_file(path: str) -> List[dict]:
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    headings = heading_tracker(lines)
    code_lines = code_block_tracker(lines)
    tasks: List[dict] = []

    for idx, raw in enumerate(lines, start=1):
        # Skip lines that are inside code blocks
        if idx in code_lines:
            continue
            
        m = TASK_RE.match(raw)
        if not m:
            continue
        status = m.group("status").lower() == "x"
        rest = m.group("rest").strip()

        # Capture possible trailing block ID
        block_id = None
        bid = BLOCK_ID_RE.search(rest)
        if bid:
            block_id = bid.group("bid")
            # remove block id from rest for description parsing
            rest = BLOCK_ID_RE.sub("", rest)

        meta, desc = extract_tokens(rest)

        tasks.append(
            {
                "line_number": idx,
                "status": "done" if status else "todo",
                "description": desc,
                "raw": raw.strip(),
                "block_id": block_id,
                **meta,
                "heading": " > ".join(headings[idx - 1][1]) if headings[idx - 1][1] else None,
            }
        )

    return tasks


def make_source_key(vault_name: str, rel_path: str, task: dict) -> str:
    if task.get("block_id"):
        return f"block:{vault_name}:{rel_path}:{task['block_id']}"
    # Fallback to hash of original line; stable until text changes
    h = hashlib.sha1(task.get("raw", "").encode("utf-8")).hexdigest()[:16]
    return f"hash:{vault_name}:{rel_path}:{h}"


def normalize_content_key(vault_name: str, rel_path: str, raw_line: str) -> str:
    line = raw_line.rstrip()
    # Extract block-id if present before normalizing
    block_id = ""
    m = re.search(r"\s+\^([A-Za-z0-9\-]+)\s*$", line)
    if m:
        block_id = m.group(1)
        line = line[: m.start()]
    
    # Normalize whitespace and case
    line = re.sub(r"\s+", " ", line).strip().lower()
    
    # Check if line has meaningful content beyond task markers and common symbols
    content_part = line.replace("- [ ]", "").replace("- [x]", "").strip()
    # Remove common task markers and symbols
    content_part = re.sub(r'[⏫🔼🔽🔺⏳📅🛫✅🔁]', '', content_part).strip()
    content_part = re.sub(r'#\w+', '', content_part).strip()  # Remove hashtags
    
    # If the actual content is very minimal, include block_id to avoid collisions
    if len(content_part) < 3 or not content_part:
        if block_id:
            return f"{vault_name}:{rel_path}:{line}:^{block_id}"
    
    return f"{vault_name}:{rel_path}:{line}"


def load_existing(output_path: str) -> Tuple[Dict[str, dict], Dict[str, str]]:
    if not os.path.isfile(output_path):
        return {}, {}
    try:
        with open(output_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        tasks = data.get("tasks", {}) or {}
        by_source: Dict[str, str] = {}
        for uid, rec in tasks.items():
            sk = rec.get("source_key")
            if sk:
                by_source[sk] = uid
            for alias in rec.get("aliases", []) or []:
                if alias and alias not in by_source:
                    by_source[alias] = uid
        return tasks, by_source
    except Exception:
        return {}, {}


def load_incremental_cache(cache_path: str) -> Optional[IncrementalCache]:
    """Load incremental cache from disk, return None if invalid or missing."""
    if not os.path.isfile(cache_path):
        return None
    
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Validate cache structure and schema version
        if not isinstance(data, dict):
            print(f"Warning: Cache file corrupted (not a dict): {cache_path}")
            return None
            
        if data.get("schema_version") != 2:
            print(f"Warning: Cache schema version mismatch, expected 2, got {data.get('schema_version')}")
            return None
        
        # Validate and recover file cache entries
        file_cache = {}
        corrupted_entries = 0
        for path, entry in (data.get("file_cache") or {}).items():
            try:
                if not isinstance(entry, dict):
                    corrupted_entries += 1
                    continue
                    
                # Validate required fields
                mtime = entry.get("mtime")
                if not isinstance(mtime, (int, float)):
                    corrupted_entries += 1
                    continue
                    
                tasks = entry.get("tasks", [])
                if not isinstance(tasks, list):
                    corrupted_entries += 1
                    continue
                
                # Validate file still exists and mtime makes sense
                if os.path.exists(path):
                    try:
                        current_mtime = os.path.getmtime(path)
                        # If cached mtime is in the future, it's likely corrupted
                        if mtime > current_mtime + 60:  # 60 second tolerance for clock drift
                            corrupted_entries += 1
                            continue
                    except OSError:
                        pass  # File might be temporarily inaccessible
                
                file_cache[path] = FileCache(
                    mtime=float(mtime),
                    tasks=tasks,
                    parsed_at=entry.get("parsed_at", "")
                )
            except Exception:
                corrupted_entries += 1
                continue
        
        if corrupted_entries > 0:
            print(f"Warning: Recovered cache with {corrupted_entries} corrupted entries removed")
        
        return IncrementalCache(
            schema_version=data.get("schema_version", 2),
            created_at=data.get("created_at", now_iso()),
            last_updated=data.get("last_updated", now_iso()),
            file_cache=file_cache
        )
    except json.JSONDecodeError as e:
        print(f"Warning: Cache file corrupted (JSON decode error): {cache_path}: {e}")
        return None
    except Exception as e:
        print(f"Warning: Failed to load cache from {cache_path}: {e}")
        return None


def save_incremental_cache(cache: IncrementalCache, cache_path: str) -> bool:
    """Save incremental cache to disk with atomic write and validation."""
    import tempfile
    
    try:
        # Convert to JSON-serializable format
        file_cache_data = {}
        for path, entry in cache.file_cache.items():
            # Validate entry before saving
            if not isinstance(entry.mtime, (int, float)) or entry.mtime < 0:
                continue
            if not isinstance(entry.tasks, list):
                continue
                
            file_cache_data[path] = {
                "mtime": entry.mtime,
                "tasks": entry.tasks,
                "parsed_at": entry.parsed_at
            }
        
        data = {
            "schema_version": cache.schema_version,
            "created_at": cache.created_at,
            "last_updated": cache.last_updated,
            "file_cache": file_cache_data
        }
        
        # Ensure directory exists
        cache_dir = os.path.dirname(os.path.abspath(cache_path))
        os.makedirs(cache_dir, exist_ok=True)
        
        # Atomic write: write to temp file, then rename
        with tempfile.NamedTemporaryFile(
            mode="w", 
            dir=cache_dir,
            prefix=".tmp_cache_",
            suffix=".json",
            delete=False,
            encoding="utf-8"
        ) as f:
            temp_path = f.name
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        
        # Verify written file is valid
        try:
            with open(temp_path, "r", encoding="utf-8") as f:
                json.load(f)  # Just validate it's parseable
        except Exception as e:
            os.unlink(temp_path)
            raise Exception(f"Cache validation failed after write: {e}")
        
        # Atomic rename
        if os.name == 'nt':  # Windows
            if os.path.exists(cache_path):
                os.unlink(cache_path)
        os.rename(temp_path, cache_path)
        
        return True
        
    except Exception as e:
        print(f"Warning: Failed to save cache to {cache_path}: {e}")
        # Clean up temp file if it exists
        try:
            if 'temp_path' in locals() and os.path.exists(temp_path):
                os.unlink(temp_path)
        except Exception:
            pass
        return False


def should_reparse_file(path: str, cache_entry: Optional[FileCache]) -> bool:
    """Check if file needs reparsing based on mtime comparison."""
    try:
        current_mtime = os.path.getmtime(path)
        if cache_entry is None:
            return True
        return current_mtime > cache_entry.mtime
    except OSError:
        # File doesn't exist or can't be accessed
        return False


def collect_tasks_incremental(vaults: List[Vault], ignore: Set[str], cache: Optional[IncrementalCache]) -> Tuple[List[Tuple[str, str, List[dict]]], IncrementalCache, Dict[str, int]]:
    """
    Collect tasks using incremental parsing with mtime-based caching.
    
    Returns:
        - List of (vault_name, rel_path, tasks) tuples
        - Updated cache
        - Performance metrics dict
    """
    start_time = time.time()
    
    # Initialize new cache if none provided
    if cache is None:
        cache = IncrementalCache(
            schema_version=2,
            created_at=now_iso(),
            last_updated=now_iso(),
            file_cache={}
        )
    
    result_tasks = []
    files_checked = 0
    files_parsed = 0
    files_cached = 0
    
    for vault in vaults:
        for path in iter_md_files(vault.path, ignore_dirs=ignore):
            files_checked += 1
            rel_path = os.path.relpath(path, vault.path)
            
            # Check if file needs reparsing
            cache_entry = cache.file_cache.get(path)
            if should_reparse_file(path, cache_entry):
                # Parse file
                files_parsed += 1
                try:
                    tasks = parse_tasks_from_file(path)
                    current_mtime = os.path.getmtime(path)
                    
                    # Update cache
                    cache.file_cache[path] = FileCache(
                        mtime=current_mtime,
                        tasks=tasks,
                        parsed_at=now_iso()
                    )
                    
                    result_tasks.append((vault.name, rel_path, tasks))
                    
                except Exception as e:
                    print(f"Warning: failed to parse {path}: {e}")
                    continue
            else:
                # Use cached tasks
                files_cached += 1
                if cache_entry and cache_entry.tasks:
                    result_tasks.append((vault.name, rel_path, cache_entry.tasks))
    
    # Update cache metadata  
    cache.last_updated = now_iso()
    
    metrics = {
        "total_time_ms": int((time.time() - start_time) * 1000),
        "files_checked": files_checked,
        "files_parsed": files_parsed,
        "files_cached": files_cached,
        "cache_hit_rate": files_cached / files_checked if files_checked > 0 else 0.0
    }
    
    return result_tasks, cache, metrics


def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(description="Collect Obsidian Tasks into a single JSON index (schema v2).")
    p.add_argument("--use-config", action="store_true", help="Use saved vaults from discover_obsidian_vaults.py")
    p.add_argument("--config", default=get_path("obsidian_vaults"), help="Vaults config JSON path")
    p.add_argument("--root", action="append", help="Additional vault root(s) to include")
    p.add_argument("--output", default=get_path("obsidian_index"), help="Output JSON index path")
    p.add_argument("--cache", default=get_path("obsidian_cache"), help="Incremental cache JSON path")
    p.add_argument("--ignore-common", action="store_true", help="Ignore .obsidian, .recovery_backups, .trash (and VCS)")
    p.add_argument("--no-cache", action="store_true", help="Disable incremental caching (full rescan)")
    p.add_argument("--clear-cache", action="store_true", help="Clear cache before running")
    args = p.parse_args(argv)
    
    # Initialize logger and start run tracking
    logger = get_logger("collect_obsidian")
    run_id = logger.start_run("collect_obsidian", {
        "use_config": args.use_config,
        "no_cache": args.no_cache,
        "clear_cache": args.clear_cache,
        "config": args.config,
        "output": args.output,
        "cache": args.cache
    })

    # Load vaults
    vaults: List[Vault] = []
    if args.use_config:
        try:
            vaults.extend(load_vaults(args.config))
            logger.info(f"Loaded {len(vaults)} vaults from config", config_path=args.config)
        except FileNotFoundError as e:
            logger.error(f"Vaults config not found: {args.config}", error=str(e))
            logger.end_run(False, str(e))
            print(str(e))
            return 1
    if args.root:
        for r in args.root:
            ap = os.path.abspath(os.path.expanduser(r))
            if os.path.isdir(ap):
                vaults.append(Vault(name=os.path.basename(ap) or ap, path=ap))
                logger.debug(f"Added vault from root", vault_path=ap)
            else:
                logger.warning(f"Skipping non-directory root", invalid_path=ap)
                print(f"Warning: skipping non-directory root: {ap}")

    # Deduplicate vaults by path
    uniq: Dict[str, Vault] = {}
    for v in vaults:
        uniq[v.path] = v
    vaults = list(uniq.values())
    if not vaults:
        logger.error("No vaults to scan")
        logger.end_run(False, "No vaults to scan. Use --use-config or --root.")
        print("No vaults to scan. Use --use-config or --root.")
        return 1

    ignore: Set[str] = {".git", ".hg", ".svn"}
    if args.ignore_common:
        ignore.update({".obsidian", ".recovery_backups", ".trash"})

    logger.info(f"Scanning {len(vaults)} vaults", 
                vault_count=len(vaults),
                ignore_patterns=sorted(ignore))
    print(f"Scanning {len(vaults)} vault(s)…")
    for v in vaults:
        print(f" - {v.name}: {v.path}")
        logger.debug(f"Vault: {v.name}", vault_path=v.path)

    # Load or initialize incremental cache
    incremental_cache = None
    if not args.no_cache:
        if args.clear_cache and os.path.exists(args.cache):
            logger.info("Clearing cache", cache_path=args.cache)
            print(f"Clearing cache: {args.cache}")
            os.remove(args.cache)
        incremental_cache = load_incremental_cache(args.cache)
        if incremental_cache:
            cached_files = len(incremental_cache.file_cache)
            logger.info("Loaded incremental cache", 
                       cached_files=cached_files,
                       cache_path=args.cache)
            print(f"Loaded incremental cache with {cached_files} files")
        else:
            logger.info("No valid cache found, performing full scan")
            print("No valid cache found, performing full scan")

    existing_tasks, source_to_uuid = load_existing(args.output)
    # Build content-key -> set(UUIDs) map from prior index for reconciliation and cleanup
    content_to_uids: Dict[str, Set[str]] = {}
    for puid, prec in existing_tasks.items():
        try:
            if prec.get("deleted"):
                continue
            vname = (prec.get("vault") or {}).get("name") or ""
            relp = (prec.get("file") or {}).get("relative_path") or ""
            raw_prev = prec.get("raw", "")
            ckey = normalize_content_key(vname, relp, raw_prev)
            content_to_uids.setdefault(ckey, set()).add(puid)
        except Exception:
            continue
    out_tasks: Dict[str, dict] = {}
    # Track prior duplicate UIDs to be skipped from carry-forward
    skip_uids: Set[str] = set()
    now = now_iso()

    # Use incremental collection
    if args.no_cache:
        logger.info("Cache disabled, performing full scan")
        print("Cache disabled, performing full scan...")
        collected_data = []
        files_parsed = 0
        for v in vaults:
            for path in iter_md_files(v.path, ignore_dirs=ignore):
                rel = os.path.relpath(path, v.path)
                try:
                    tasks = parse_tasks_from_file(path)
                    collected_data.append((v.name, rel, tasks))
                    files_parsed += 1
                except Exception as e:
                    logger.warning(f"Failed to parse file", file_path=path, error=str(e))
                    print(f"Warning: failed to parse {path}: {e}")
                    continue
        metrics = {"total_time_ms": 0, "files_checked": files_parsed, "files_parsed": files_parsed, "files_cached": 0, "cache_hit_rate": 0.0}
    else:
        logger.info("Using incremental collection")
        print("Using incremental collection...")
        collected_data, incremental_cache, metrics = collect_tasks_incremental(vaults, ignore, incremental_cache)
        
        # Log cache performance metrics
        logger.update_metrics({
            "cache_hit_rate": metrics["cache_hit_rate"],
            "processing_rate_files_per_sec": metrics["files_checked"] / (metrics["total_time_ms"] / 1000) if metrics["total_time_ms"] > 0 else 0
        })
        
        # Save updated cache
        if save_incremental_cache(incremental_cache, args.cache):
            logger.info("Cache saved successfully", cache_path=args.cache)
            print(f"Cache saved to {args.cache}")
        else:
            logger.warning("Failed to save cache", cache_path=args.cache)
        
        # Print performance metrics
        logger.info("Collection performance", **metrics)
        print(f"Performance: {metrics['total_time_ms']}ms, "
              f"files checked: {metrics['files_checked']}, "
              f"parsed: {metrics['files_parsed']}, "
              f"cached: {metrics['files_cached']}, "
              f"cache hit rate: {metrics['cache_hit_rate']:.1%}")

    # Process collected tasks
    total_raw_tasks = sum(len(tasks) for _, _, tasks in collected_data)
    logger.info("Processing collected tasks", 
                total_files=len(collected_data), 
                total_raw_tasks=total_raw_tasks)
    
    for vault_name, rel, tasks in collected_data:
        # Construct full path for file timestamp lookup
        vault_path = next((v.path for v in vaults if v.name == vault_name), "")
        if vault_path:
            path = os.path.join(vault_path, rel)
            f_created, f_modified = file_times(path)
        else:
            f_created, f_modified = None, None
            
        for t in tasks:
            source_key = make_source_key(vault_name, rel, t)
            # Resolve UUID via source key or aliases
            if source_key in source_to_uuid:
                uid = source_to_uuid[source_key]
                prev = existing_tasks.get(uid, {})
                created_at = prev.get("created_at", now)
                prev_aliases = set(prev.get("aliases", []) or [])
            else:
                # Try reconciliation by content (handles migration hash->block)
                ckey = normalize_content_key(vault_name, rel, t.get("raw", ""))
                uids_for_key = content_to_uids.get(ckey) or set()
                # Filter out UIDs that have already been processed in this run
                available_uids = uids_for_key - skip_uids - set(out_tasks.keys())
                
                if available_uids:
                    # Prefer the earliest created_at if available (stable)
                    chosen_uid = None
                    chosen_created = None
                    for cand in available_uids:
                        cr = existing_tasks.get(cand, {})
                        ca = cr.get("created_at")
                        if chosen_uid is None:
                            chosen_uid = cand
                            chosen_created = ca
                        else:
                            # Keep the earliest created_at if comparable
                            if ca and chosen_created and ca < chosen_created:
                                chosen_uid = cand
                                chosen_created = ca
                    uid = chosen_uid or next(iter(available_uids))
                    prev = existing_tasks.get(uid, {})
                    created_at = prev.get("created_at", now)
                    prev_aliases = set(prev.get("aliases", []) or [])
                    # Mark other prior UIDs for same content to be skipped from carry-forward
                    for other in uids_for_key:
                        if other != uid:
                            skip_uids.add(other)
                else:
                    uid = str(uuid4())
                    created_at = now
                    prev_aliases = set()

            # Build aliases set (include prior source_key if differed)
            aliases = set(prev_aliases)
            # Include previous recorded source_key to preserve history
            prev_source = existing_tasks.get(uid, {}).get("source_key") if uid in existing_tasks else None
            if prev_source:
                aliases.add(prev_source)
            aliases.add(source_key)

            # Fingerprint for reconciliation/reporting (normalized desc + heading + file + raw hash)
            desc_norm = t.get("description", "").strip().lower()
            heading = (t.get("heading") or "").strip().lower()
            base = os.path.basename(rel).lower()
            raw_hash = hashlib.sha1((t.get("raw", "")).encode("utf-8")).hexdigest()[:16]
            fingerprint = hashlib.sha1(f"{desc_norm}|{heading}|{base}|{raw_hash}".encode("utf-8")).hexdigest()

            # Cache tokenized title for performance optimization
            title_tokens = normalize_text_for_similarity(t["description"])
            title_tokens_hash = hashlib.sha1("|".join(title_tokens).encode("utf-8")).hexdigest()[:8] if title_tokens else ""
            
            rec = {
                "uuid": uid,
                "source_key": source_key,
                "aliases": sorted(aliases),
                "vault": {"name": vault_name, "path": vault_path},
                "file": {
                    "relative_path": rel,
                    "absolute_path": path,
                    "line": t["line_number"],
                    "heading": t.get("heading"),
                    "created_at": f_created,
                    "modified_at": f_modified,
                },
                "status": t["status"],
                "description": t["description"],
                "raw": t["raw"],
                "tags": t.get("tags", []),
                "due": t.get("due"),
                "scheduled": t.get("scheduled"),
                "start": t.get("start"),
                "done": t.get("done"),
                "recurrence": t.get("recurrence"),
                "priority": t.get("priority"),
                "block_id": t.get("block_id"),
                "external_ids": {"block_id": t.get("block_id")},
                "fingerprint": fingerprint,
                "created_at": created_at,
                "updated_at": now,
                "last_seen": now,
                # Performance optimization fields
                "cached_tokens": title_tokens,
                "title_hash": title_tokens_hash,
            }
            out_tasks[uid] = rec

    # Note: Instead of carrying forward all missing tasks (which preserves deleted tasks),
    # we now treat tasks not found in the current scan as permanently deleted.
    # This fixes the issue where deleted tasks were being preserved indefinitely
    # in the index because the carry-forward logic assumed missing = temporarily unavailable.
    # 
    # The previous logic was:
    # - Carry forward tasks not seen this run
    # - for uid, prev in existing_tasks.items():
    #     if uid in out_tasks:
    #         continue
    #     if uid in skip_uids:
    #         # Drop prior duplicates for reconciled content
    #         continue
    #     out_tasks[uid] = prev
    #
    # Now we only include tasks actually found in the current scan, treating missing ones as deleted.
    # Tasks from deleted files or removed from existing files are properly excluded.

    # Sort tasks by UUID for deterministic output
    tasks_sorted = {uid: out_tasks[uid] for uid in sorted(out_tasks)}
    new_tasks = len([t for t in tasks_sorted.values() if t.get("created_at") == now])
    carried_forward = 0  # No longer carrying forward, so this is always 0
    deleted_tasks = len(existing_tasks) - len(tasks_sorted) + new_tasks
    
    logger.update_counts(
        input_counts={
            "vaults": len(vaults),
            "files_checked": metrics.get("files_checked", 0),
            "raw_tasks": total_raw_tasks
        },
        output_counts={
            "tasks_indexed": len(tasks_sorted),
            "new_tasks": new_tasks,
            "carried_forward": max(0, carried_forward),
            "deleted_tasks": max(0, deleted_tasks)
        }
    )

    out = {
        "meta": {
            "schema": 2,
            "generated_at": now,
            "vault_count": len(vaults),
            "ignore": sorted(ignore),
        },
        "tasks": tasks_sorted,
    }
    
    # Add run_id to meta for concurrent write detection
    out = ensure_run_id_in_meta(out, run_id)
    
    # Check for concurrent access before writing
    if check_concurrent_access(args.output, run_id):
        print(f"Warning: Concurrent access detected to {args.output}, proceeding with caution")
    
    # Write with locking and atomic operations
    try:
        # Create deterministic JSON for comparison
        new_json = json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True)
        
        # Check if file exists and content has changed
        changed = True
        if os.path.isfile(args.output):
            try:
                with open(args.output, "r", encoding="utf-8") as f:
                    old_json = f.read()
                # Compare content ignoring generated_at and run_id for change detection
                try:
                    import copy
                    old_obj = json.loads(old_json)
                    new_obj = copy.deepcopy(out)
                    old_obj.get("meta", {}).pop("generated_at", None)
                    new_obj.get("meta", {}).pop("generated_at", None)
                    old_obj.get("meta", {}).pop("run_id", None)
                    new_obj.get("meta", {}).pop("run_id", None)
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
                       output_path=args.output, 
                       task_count=len(tasks_sorted))
            summary_path = logger.end_run(True)
            print(f"No changes for {args.output} (tasks={len(tasks_sorted)})")
            return 0
        
        # Write safely with file locking
        safe_write_json_with_lock(
            args.output, 
            out, 
            run_id=run_id,
            indent=2,
            timeout=30.0
        )
        
        logger.info("Successfully wrote task index", 
                   output_path=args.output, 
                   task_count=len(tasks_sorted))
        summary_path = logger.end_run(True)
        if deleted_tasks > 0:
            print(f"Wrote {len(tasks_sorted)} task(s) to {args.output} (deleted {deleted_tasks} from index)")
        else:
            print(f"Wrote {len(tasks_sorted)} task(s) to {args.output}")
        return 0
        
    except Exception as e:
        logger.error("Failed to write task index", 
                    output_path=args.output, 
                    error=str(e))
        logger.end_run(False, str(e))
        print(f"Error writing to {args.output}: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
