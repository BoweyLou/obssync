# End-to-End Test Plan

Purpose: Validate that end-to-end behavior matches user-visible outcomes across both systems (Obsidian files and Apple Reminders), catching gaps where JSON appears correct but real changes are not applied.

## Modes
- Simulated (default): Uses a fake Reminders gateway with EventKit-like objects. Safe, deterministic, CI-friendly.
- Live (optional): Runs against real Apple Reminders with a dedicated list. Marked and skipped unless explicitly enabled.

## What It Verifies
- Discovery/collection finds new tasks (Obsidian, Reminders).
- Deterministic, schema-v2 indices are produced with stable UUIDs.
- Link building enforces one-to-one mapping, with due-date tolerance and score threshold.
- Apply sync mutates both sides:
  - Edits the Markdown line for Obsidian tasks identified by block id.
  - Calls the Reminders gateway and verifies real mutation (in fake mode: in-memory; in live mode: EventKit).
- Create-missing generates counterparts in the correct system, respects caps and recency, and updates links accordingly.
- Edge cases:
  - Code blocks are ignored by the task parser.
  - Duplicate titles across contexts link deterministically, not many-to-one.
  - Priority mapping (high/medium/low) applies both directions.
  - Completed state toggles propagate both ways.
  - Due-date tolerance applied when dates differ within settings.

## Structure
- `tests/e2e/fake_reminders_gateway.py`: In-memory fake gateway and EventKit-like objects.
- `tests/e2e/test_end_to_end_sync.py`: Simulated E2E covering the full pipeline.
- Optional live tests (suggested): `tests/e2e/test_end_to_end_live.py` with markers `e2e_live`, `macos`, `eventkit`.

## Running
- Simulated: `pytest -m e2e tests/e2e/test_end_to_end_sync.py -v`
- Full suite (includes e2e): `pytest -m 'not e2e_live' -v`
- Live (dangerous; macOS only):
  - Preconditions: `export E2E_REMINDERS_LIST_ID='...'` pointing to a dedicated test list.
  - Run: `pytest -m e2e_live -v` (only on macOS with EventKit available).

## Live Test Safety (Recommended Approach)
- Use a dedicated Reminders list ID via env var; never default calendars.
- Create uniquely-prefixed test items and mark them done instead of deleting to clean up.
- Time-bound the test and skip if authorization fails.

## Notes
- The E2E simulated test uses monkeypatch to inject the fake gateway into modules that import `RemindersGateway`.
- JSON artifacts are written to temp paths to avoid interfering with user data/config.
- The test asserts both JSON state and actual end effects on the fake gateway and the Markdown files.

