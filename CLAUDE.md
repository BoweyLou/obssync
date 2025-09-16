# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

ObsSync is a bidirectional task synchronization system between Obsidian and Apple Reminders. It provides enterprise-grade reliability, deterministic operations, and high-performance incremental updates with comprehensive schema validation and backup systems.

## Core Architecture

### Main Entry Points
- **`obs_tools.py`**: Primary launcher with auto-managed virtual environment
- **`./bin/obs-app`**: Interactive TUI dashboard 
- **`./bin/obs-sync-update`**: Main sync orchestration command
- **`./bin/obs-tasks`**: Obsidian task collection
- **`./bin/obs-reminders`**: Apple Reminders task collection

### Package Structure
- **`obs_tools/commands/`**: Core command implementations
- **`lib/`**: Shared library modules (safe_io, backup_system, schemas, etc.)
- **`tui/`**: Terminal user interface components
- **`tests/`**: Comprehensive test suite with performance benchmarks

### Schema Architecture
Uses deterministic schema v2 with:
- UUID-based identity tracking
- Complete lifecycle management (created_at, updated_at, last_seen, missing_since, deleted)
- Rich metadata extraction from both platforms
- Fingerprint-based change detection for incremental updates

## Development Commands

### Core Workflow Commands
```bash
# Interactive TUI dashboard
./bin/obs-app

# Full sync update (collect + link + apply)
./bin/obs-sync-update

# Individual operations
./bin/obs-tasks collect --use-config
./bin/obs-reminders collect --use-config  
./bin/obs-sync suggest
./bin/obs-sync apply

# Create missing counterpart tasks
./bin/obs-sync-create --dry-run                      # Show what would be created
./bin/obs-sync-create --apply --direction obs-to-rem # Create Reminders from Obsidian
./bin/obs-sync-create --apply --since 7              # Create counterparts for recent tasks
```

### Discovery and Setup
```bash
# Discover Obsidian vaults
./bin/obs-vaults discover

# Discover Apple Reminders lists
./bin/obs-reminders discover

# Reset all configurations
./bin/obs-reset
```

### Development and Testing
```bash
# Run comprehensive test suite
python -m pytest tests/ -v

# Run performance benchmarks
python -m pytest tests/test_performance_optimization.py -v

# Run with coverage
python -m pytest --cov=obs_tools --cov=lib tests/

# Type checking
mypy obs_tools/ lib/

# Code formatting
black obs_tools/ lib/ tests/
```

### Debugging and Maintenance
```bash
# Find duplicate tasks
./bin/obs-duplicates find

# Fix Obsidian block IDs
./bin/obs-ids remove --use-config --apply

# Task operations (delete, modify)
./bin/obs-task-ops delete --uuid <uuid>
```

## Key Technical Details

### Virtual Environment Management
- Automatically managed at `~/Library/Application Support/obs-tools/venv` (macOS)
- Dependencies installed on-demand (pyobjc, EventKit framework for macOS)
- Falls back gracefully when optional dependencies unavailable

### Performance Optimizations
- **Incremental collectors**: 16x improvement for Obsidian (192ms → 12ms), 95% for Reminders
- **Global bipartite matching**: Hungarian algorithm for optimal task pairing
- **Cache hit rates**: 99.9% on subsequent runs with minimal changes
- **Memory efficiency**: 70% smaller cache files vs full indices

### Data Safety Features
- **Atomic operations**: All file writes use safe_io with file locking
- **Backup system**: Comprehensive changeset tracking and rollback capability
- **Schema validation**: JSON schema validation with migration support
- **Defensive I/O**: Run ID coordination to prevent concurrent access conflicts

### Configuration Files
- **`~/.config/obsidian_vaults.json`**: Discovered Obsidian vault configurations
- **`~/.config/reminders_lists.json`**: Apple Reminders list configurations
- **`sync_links.json`**: Deterministic task linkage mapping
- **`*_tasks_index.json`**: Schema v2 task indices with lifecycle metadata

## Platform-Specific Notes

### macOS Dependencies
- EventKit framework access for Apple Reminders integration
- pyobjc bindings automatically installed in managed venv
- Graceful degradation on non-macOS platforms

### Testing Framework
- Comprehensive marker system for different test categories
- Platform-specific test isolation (macOS vs other platforms)
- Optional dependency testing (scipy, munkres, jsonschema)
- Performance benchmarking with statistical analysis

## Architecture & Development Guardrails

**IMPORTANT**: Before making any changes to this codebase, review the comprehensive architecture guidelines and guardrails documented in `agents.md`. This file contains critical principles for:

- **Modularity & Boundaries**: Platform API isolation, TUI separation, CLI command design
- **Data Safety**: Atomic operations, schema validation, backup systems, deterministic operations
- **Performance**: Incremental processing, bounded I/O, caching strategies
- **Error Handling**: Typed errors, graceful degradation, platform compatibility
- **Testing**: Focused unit tests, domain-specific validations, backward compatibility

These guardrails ensure all changes maintain the system's enterprise-grade reliability and deterministic behavior patterns.

## Important Conventions

### Code Style
- Black formatting with 120-character line length
- Type hints required (mypy strict mode)
- Comprehensive docstrings for all public APIs

### Error Handling
- Defensive programming with comprehensive error recovery
- Graceful degradation when optional features unavailable
- Detailed logging and observability throughout

### Deterministic Operations
- All operations must be reproducible across runs
- Sort all collections before processing
- Write-only-if-changed pattern for all file operations
- UUID-based stable identity for all entities