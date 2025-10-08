# obs-sync Testing Overview

This document summarizes the current pytest coverage for the project, explains how to execute the suite, and records the main coverage gaps together with recommended follow‑ups. The analysis is qualitative; no automated coverage report was generated in this environment.

## Running the Test Suite
- Activate a local virtual environment (see `obs_sync/utils/venv.py` helpers) and install development requirements.
- Run all tests with `python -m pytest tests`.
- Target specific areas with `pytest tests/test_multi_vault_summary.py` or `pytest tests/test_tag_sync.py`.
- Optional: collect coverage locally via `pytest --cov obs_sync --cov-report term-missing`; skip coverage in CI if EventKit tooling is unavailable.
- macOS integrations (EventKit, LaunchAgents) rely on native frameworks; when adding tests that touch these paths, guard them with `pytest.mark.skipif(sys.platform != "darwin", ...)`.

## Current Coverage Snapshot

### Sync and Deduplication
- Core sync orchestration (`obs_sync/sync/engine.py`) is exercised through scenario tests such as `tests/test_multi_vault_summary.py`, `tests/test_tag_routing.py`, `tests/test_link_persistence_fix.py`, and `tests/test_uuid_normalization_regression.py`.
- Matching, resolver, and deduplicator helpers are validated by `tests/test_deduplication.py`, `tests/test_dedup_link_cleanup.py`, `tests/test_repeated_creation_fix.py`, and `tests/test_url_matching.py`.
- Performance and scalability testing for large task sets (100-1000+ tasks) in `tests/test_performance.py`.

### Setup, Migration, and Configuration
- Interactive setup flows and state management (`obs_sync/commands/setup.py`, `obs_sync/core/models.py`) are covered by `tests/test_setup_fix.py`, `tests/test_setup_normalization.py`, `tests/test_suggestions.py`, `tests/test_tag_routing_scenarios.py`, and `tests/test_removal_integration.py`.
- Path migration logic (`obs_sync/commands/migrate.py`, `obs_sync/core/paths.py`) is exercised by `tests/test_path_migration.py`.
- Configuration persistence (`obs_sync/core/config.py`) is touched in `tests/test_reconfigure_integration.py`.
- SyncConfig helper methods (tag routing, vault mapping, removal impact) validated in `tests/test_sync_config_helpers.py`.

### Analytics, Insights, and Task Managers
- Streak tracking, hygiene analysis, and insight formatting (`obs_sync/analytics/*.py`, `obs_sync/utils/insights.py`) are covered by `tests/test_insights_and_analytics.py`.
- Tag utilities and round‑trip behaviour across Reminders/Obsidian managers (`obs_sync/utils/tags.py`, `obs_sync/obsidian/tasks.py`, `obs_sync/reminders/tasks.py`) are validated in `tests/test_tag_sync.py`.
- RemindersTaskManager create/delete flows and error handling tested in `tests/test_reminders_manager.py`.
- Update command prompts (`obs_sync/commands/update.py`) have focused coverage in `tests/test_update_command.py`.

### CLI and Commands
- Main CLI entry point, argument parsing, and command dispatch (`obs_sync/main.py`) covered in `tests/test_main.py`.
- CalendarCommand, daily note injection, and tracker persistence (`obs_sync/commands/calendar.py`, `obs_sync/calendar/*`) tested in `tests/test_calendar.py`.
- InsightsCommand hygiene analysis and JSON export (`obs_sync/commands/insights.py`) validated in `tests/test_insights_command.py`.
- InstallDepsCommand flag handling and platform detection (`obs_sync/commands/install_deps.py`) covered in `tests/test_install_deps_command.py`.

### Utilities
- I/O utilities (atomic writes, safe JSON read/write) from `obs_sync/utils/io.py` tested in `tests/test_utils.py`.
- LaunchAgent generation and macOS helpers (`obs_sync/utils/launchd.py`) covered in `tests/test_utils.py`.
- Venv path resolution and environment building (`obs_sync/utils/venv.py`) validated in `tests/test_utils.py`.

### Regression Hardening
- Automation toggle flows (enable/disable LaunchAgent) tested in `tests/test_regression.py`.
- Sync CLI flags (--apply, --to-reminders, --from-reminders) validated in `tests/test_regression.py`.
- Insights configuration toggles (enable_insights, enable_streak_tracking, etc.) covered in `tests/test_regression.py`.
- Deduplication enable/disable behavior tested in `tests/test_regression.py`.

## Coverage Gaps and Recommendations

### Remaining Functional Gaps
Most major functional gaps have been addressed. Remaining areas:
- **End-to-end integration with real EventKit** – Current calendar tests use mocks; consider opt-in E2E tests on macOS with real EventKit access (marked with `@pytest.mark.integration`).
- **Multi-root workspace scenarios** – Add tests validating behavior when multiple Obsidian vaults in different root directories are configured.
- **Network/sync conflicts** – Test edge cases where tasks are modified simultaneously in both Obsidian and Reminders.

### Additional Regression Hardening
- **StreakTracker cleanup** – Add explicit test for `cleanup_old_data` with synthetic 2-year dataset (already covered in `test_performance.py`).
- **Tag route conflict detection** – Validate warnings when multiple vaults route the same tag to different calendars.
- **Vault removal cascading** – Ensure removing a vault properly cleans up tag routes, mappings, and sync links.

### Performance and Scalability
- **Stress testing implemented** – `tests/test_performance.py` includes:
  - Deduplication with 100, 500, and 1000 tasks
  - Hungarian vs greedy matching performance
  - Full sync engine dry-run benchmarks
  - Memory usage validation for large task sets
  - Streak tracker cleanup performance
- Run performance tests with: `pytest -v -m slow`
- Skip slow tests by default: `pytest -v -m "not slow"`

### Developer Workflow and Tooling
- **Pytest configuration** – `pytest.ini` now registers custom markers:
  - `@pytest.mark.slow` – Performance/stress tests (skip with `-m "not slow"`)
  - `@pytest.mark.macos` – macOS-specific tests (EventKit, LaunchAgents)
  - `@pytest.mark.integration` – Integration tests requiring real services
- **Common test commands**:
  - `pytest -v` – Run all fast tests
  - `pytest -v -m slow` – Run performance tests only
  - `pytest -v -m "not slow"` – Skip performance tests
  - `pytest -k "tag_routing"` – Run tests matching pattern
  - `pytest tests/test_main.py -v` – Run specific test file
- **CI Recommendations**:
  - Separate jobs for fast tests vs slow tests
  - macOS-specific job for EventKit integration tests
  - Optional coverage reporting with `pytest-cov` plugin

## Test File Reference

### New Test Files (Added in This Session)
- `tests/test_main.py` – CLI entry point, argument parsing, command dispatch
- `tests/test_calendar.py` – Calendar pipeline, daily notes, EventKit mocking
- `tests/test_insights_command.py` – InsightsCommand, hygiene analysis, JSON export
- `tests/test_install_deps_command.py` – Dependency installation, platform detection
- `tests/test_reminders_manager.py` – RemindersTaskManager create/delete/error handling
- `tests/test_sync_config_helpers.py` – SyncConfig tag routing, vault mapping, removal
- `tests/test_utils.py` – I/O utilities, LaunchAgent generation, venv path resolution
- `tests/test_regression.py` – Automation toggles, sync flags, insights configuration
- `tests/test_performance.py` – Performance benchmarks, scalability tests (marked `@pytest.mark.slow`)
- `pytest.ini` – Pytest configuration with custom markers

### Existing Test Files (Already Present)
- `tests/test_deduplication.py` – Deduplication analysis and prompts
- `tests/test_sync_*.py` – Various sync scenarios and edge cases
- `tests/test_tag_*.py` – Tag routing and tag sync behavior
- `tests/test_setup_*.py` – Setup command flows and normalization
- `tests/test_insights_and_analytics.py` – Streak tracking and hygiene analysis
- `tests/test_path_migration.py` – Path manager and migration logic
- `tests/test_uuid_*.py` – UUID stability and normalization
- And many more scenario-specific tests...

## Next Steps
1. ✅ **Completed**: Functional coverage for CLI, Calendar, Insights, InstallDeps, RemindersTaskManager, SyncConfig, and utilities.
2. ✅ **Completed**: Regression coverage for automation toggles, sync flags, and insights configuration.
3. ✅ **Completed**: Performance test framework with `pytest.mark.slow` marker.
4. **Recommended**: Add opt-in integration tests with real EventKit (marked `@pytest.mark.integration`).
5. **Recommended**: Wire pytest suite into CI with separate fast/slow/macos jobs.
6. **Ongoing**: Update this document as new tests are added or coverage areas evolve.

