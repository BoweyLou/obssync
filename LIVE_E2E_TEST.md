# Live End-to-End Test (macOS + Apple Reminders)

This repository includes a live end-to-end test that exercises the full pipeline against your actual Apple Reminders data — but scoped to a dedicated test list you choose. It verifies that not only JSON files update correctly, but that real changes are applied to Reminders and Obsidian files.

Important: The test is opt-in and safe by default. It is skipped unless you explicitly set a dedicated Reminders list ID.

## What It Does
- Creates uniquely-prefixed test items in a dedicated Reminders list.
- Builds a temporary Obsidian vault with test tasks (including edge cases like code blocks and duplicate titles).
- Runs collectors → link builder → sync apply (–apply) → create-missing (–apply).
- Verifies:
  - The matched live reminder is actually marked completed when the Obsidian task is flipped to [x].
  - A new live reminder is created for an unlinked Obsidian task.
  - A new Obsidian task is created for an unlinked live reminder, into a temp inbox file.
  - Code-block “tasks” are ignored and links remain one-to-one.

## Prerequisites
- macOS (Darwin) with Apple Reminders available.
- PyObjC + EventKit available (the test imports EventKit via `reminders_gateway`).
- A dedicated Apple Reminders list you create for testing (empty or with only items you don’t mind being toggled/augmented).
- The list’s identifier (not just the name).

## Finding Your Reminders List Identifier
Use the discovery command to dump your Reminders lists:

- `python obs_tools.py reminders discover --config ~/.config/reminders_lists.json`
- Open the printed JSON and locate your dedicated test list’s `identifier` value.

Alternatively, run the integration test that prints list identifiers (if present in your suite), or inspect via a small script using `RemindersGateway().get_reminder_lists()`.

## Running the Live E2E Test
1) Export the test list identifier (example):

- `export E2E_REMINDERS_LIST_ID="A4F0...-GUID"`

2) Run only the live E2E test:

- `pytest -m e2e_live tests/e2e/test_end_to_end_live.py -v`

3) Or include it in a broader run (dangerous; still opt-in by env var):

- `pytest -m "e2e_live" -v`

The test auto-skips when:
- Not on macOS,
- EventKit is unavailable,
- `E2E_REMINDERS_LIST_ID` is not set.

## What It Writes
- Creates test items in your dedicated list, with a prefix `[E2E YYYYMMDDHHMMSS]`.
- Marks one of them complete during the test (does not delete).
- Writes Obsidian test files into a temporary directory only (it sets a temporary `HOME` so your real files aren’t touched).
- Writes backup and log artifacts under that temporary `HOME`.

## Cleanup
- The test marks created Reminders items completed where applicable, and uses a unique prefix. If you want to manually clean up later, delete or clear items in your dedicated test list.

## File Map
- Live test code: `tests/e2e/test_end_to_end_live.py`
- Simulated E2E and helpers: `tests/e2e/test_end_to_end_sync.py`, `tests/e2e/fake_reminders_gateway.py`

## Troubleshooting
- If authorization prompts don’t appear, open System Settings → Privacy & Security → Reminders and grant access to your Python app.
- If the test fails fetching reminders, confirm `E2E_REMINDERS_LIST_ID` is correct and accessible.
- If link suggestions are zero, ensure due dates and titles align (the test crafts matching items automatically, but your list must exist).

