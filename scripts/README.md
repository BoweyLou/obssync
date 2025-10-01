# Developer Scripts

This directory contains utility scripts for development, testing, and one-time maintenance tasks.

## Directory Structure

### `demos/`
Interactive demonstration scripts showcasing specific features:

- `demo_deduplication.py` - Interactive demonstration of task deduplication functionality
- `demo_reconfigure.py` - Configuration reconfiguration and amendment workflow demo
- `demo_removal_features.py` - Vault and Reminders list removal features demo

**Usage**: These scripts are educational/testing tools. Run directly with `python3 scripts/demos/<script>.py`

### `cleanup/`
Maintenance utilities for data cleanup:

- `cleanup_sync_links.py` - Clean orphaned or invalid sync links from the database
- `clean_reminders_simple.py` - Simple utility to bulk-clean Reminders items
- `clean_reminders.py` - Advanced Reminders cleanup with filtering options

**Warning**: Cleanup scripts modify data. Always backup before running.

### `testing/`
Testing utilities and test runners:

- `quick_test.py` - Quick smoke test for core functionality
- `run_edge_case_tests.py` - Runner for edge case test scenarios

**Note**: For comprehensive testing, use `pytest tests/` instead.

## When to Use These Scripts

- **Regular users**: You typically won't need these scripts. Use `obs-sync` commands instead.
- **Developers**: Use for testing features, debugging issues, or performing one-time migrations.
- **Troubleshooting**: Some cleanup scripts may help recover from sync issues.

## Running Scripts

All scripts should be run from the repository root:

```bash
# From repo root
python3 scripts/demos/demo_deduplication.py
python3 scripts/cleanup/cleanup_sync_links.py --dry-run
python3 scripts/testing/quick_test.py
```

Scripts will automatically use the managed virtual environment if available, or fall back to system Python with appropriate error messages if dependencies are missing.