# Obsidian ↔ Reminders Task Sync — Overview

## Core Capabilities
- Obsidian tasks: Parse Markdown tasks across saved vaults, extract rich metadata, assign stable UUIDs, and write a deterministic schema v2 index.
- Reminders tasks: Use EventKit (via a managed venv) to enumerate reminders across saved lists, extract rich metadata, assign stable UUIDs, and write a deterministic schema v2 index.
- Link suggestions: Cross-reference Obsidian and Reminders tasks using title similarity, due dates, and priority; enforce one-to-one matches deterministically; write only when changed.

## Schema v2 (Per Task)
- Identity: `uuid` (dict key + field), `source_key`, `aliases[]`, `fingerprint`.
- Lifecycle: `created_at`, `updated_at`, `last_seen`, `missing_since` (when not seen this run), `deleted` (after N days missing), `deleted_at`.
- Obsidian: `vault{name,path}`, `file{relative_path,absolute_path,line,heading,created_at,modified_at}`, `raw`, `tags[]`, `scheduled`, `recurrence`, `priority`, `block_id`, `external_ids{block_id}`.
- Reminders: `list{name,identifier,source{name,type},color}`, `notes`, `url`, `alarms[]`, `item_created_at`, `item_modified_at`, `recurrence`, `priority`, `external_ids{external,item,calendar}`.
- Meta: `schema: 2`, `generated_at`, counts.

## Determinism & Idempotence
- Collectors: sort tasks by UUID, output JSON with sorted keys; skip writing if no changes.
- Linker: sorts inputs, candidates, and final links; enforces 1:1 mapping; replaces only if new score is strictly higher; writes only when changed.

## Lifecycle & Pruning
- After each collect, lifecycle marks `missing_since` for tasks not seen this run, and sets `deleted=true` after N prune days (adds `deleted_at`).
- Linker ignores `deleted=true` tasks when suggesting links.
- Prune setting adjustable in TUI and CLI.

## Tools (Scripts)
- `discover_obsidian_vaults.py`: Finds vaults; confirms; saves `~/.config/obsidian_vaults.json`.
- `collect_obsidian_tasks.py`: Builds Obsidian index (schema v2, deterministic).
- `discover_reminders_lists.py`: Finds Apple Reminders lists via EventKit; saves `~/.config/reminders_lists.json`.
- `collect_reminders_tasks.py`: Builds Reminders index (schema v2, deterministic).
- `build_sync_links.py`: Suggests links; deterministic 1:1 merge; write-only-if-changed.
- `update_indices_and_links.py`: Orchestrates collect → lifecycle → links; supports `--prune-days`.

## Unified Launcher & Wrappers
- `obs_tools.py`: Single entrypoint with auto-managed venv; commands: `reminders discover|collect`, `vaults discover`, `tasks collect`, `sync suggest|update`, `app tui`.
- Wrappers: `bin/obs-vaults`, `bin/obs-reminders`, `bin/obs-tasks`, `bin/obs-reminders-tasks`, `bin/obs-sync-suggest`, `bin/obs-sync-update`, `bin/obs-app`.

## TUI (Curses)
- `app_tui.py` via `./bin/obs-app`.
- Actions: Update All, Discover Vaults, Collect Obsidian, Discover Reminders, Collect Reminders, Build Links, Settings.
- Dashboard: totals and active counts; last-run summary (+new ~updated ?missing -deleted); links Δ; log pane.
- Settings: min score, days tolerance, include done, ignore common, prune days.
- Discovery runs interactively; collect shows “Wrote …/No changes …”; lifecycle applied automatically.

## Defaults & Paths
- Vaults: `~/.config/obsidian_vaults.json`
- Reminders lists: `~/.config/reminders_lists.json`
- Indices: `~/.config/obsidian_tasks_index.json`, `~/.config/reminders_tasks_index.json`
- Links: `~/.config/sync_links.json`
- App prefs: `~/.config/obs-tools/app.json`
- Managed venv: `~/Library/Application Support/obs-tools/venv` (macOS)

## Typical Usage
- First run: `./bin/obs-app` → Discover Vaults/Reminders → Update All
- Batch update: `./bin/obs-sync-update --include-done --min-score 0.8 --prune-days 7`
- Suggest links only: `./bin/obs-sync-suggest --min-score 0.85`

