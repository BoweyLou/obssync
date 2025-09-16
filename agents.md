# Repository Guidelines

## Project Structure & Module Organization
Core orchestration lives in `obs_tools/` with commands under `obs_tools/commands/`. Shared, side-effect-aware helpers sit in `lib/` (safe I/O, schema validation, backups). The curses TUI is in `tui/` with clear view/controller/service separation. Resource schemas and gateway assets reside in `Resources/`, while executable shims live in `bin/`. Deterministic JSON indices (`*_tasks_index.json`) and link maps (`sync_links*.json`) are persisted via the configured path module—do not hardcode paths elsewhere. Tests are under `tests/` (unit/integration) with targeted scenario files beside related modules.

## Build, Test, and Development Commands
Use `./bin/obs-app` for the interactive dashboard and `./bin/obs-sync-update --dry-run` for the end-to-end pipeline; follow with `--apply` only after reviewing backups. Collectors can be run individually via `./bin/obs-tasks collect --use-config` and `./bin/obs-reminders collect --use-config`. For local verification run `python -m pytest tests/ -v`, `mypy obs_tools/ lib/`, and `black obs_tools/ lib/ tests/` (line length 120) before opening a PR.

## Coding Style & Naming Conventions
Python 3.8+ with four-space indentation. Keep modules cohesive and side-effect-light, preferring pure functions in `lib/` and thin orchestrators elsewhere. Follow snake_case for modules/functions, PascalCase for classes, and MAJOR_CAPS for constants. Ensure deterministic ordering when serializing JSON and log via the shared structured logger. Run `black` and strict `mypy`; include type hints on public APIs.

## Testing Guidelines
Primary tests use `pytest` (`tests/` + `test_*.py` alongside modules). Name tests after the behavior under validation (`test_should_record_missing_since`). Mark long-running or macOS-specific cases with existing markers (`slow`, `macos`, `eventkit`). Aim to cover new schema or sync decisions with focused unit tests; capture regression cases near the relevant module. Use `python -m pytest --cov=obs_tools --cov=lib tests/` when touching core flows.

## Commit & Pull Request Guidelines
Commits follow the short, imperative style seen in history (`Add …`, `Fix …`). Each PR should summarize the change, reference associated issues, and state whether dry-run outputs, backups, and schema versions were touched. Include testing evidence (commands + results) and note any macOS-only behaviors or new configuration files. Keep diffs minimal, deterministic, and accompanied by updated docs when contracts change.

## Architecture & Safety Guardrails
Respect the gateway boundaries: interact with Apple Reminders only through `calendar_gateway.py` and related abstractions. All new persistent artifacts must route through the centralized path configuration to preserve determinism and backups. Default mutating flows to dry-run, write structured backups before applying, and surface human-readable summaries. Treat JSON indices as public contracts—bump schema versions and supply migrations for breaking changes.
