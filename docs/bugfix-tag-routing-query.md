# Bug Fix: Tag Routing Second-Sync Deletion Issue

## Problem

When an Obsidian task with a routed tag (e.g., `#work` → Work calendar) was synced:
1. **First sync**: Task created in routed calendar (Work) ✓
2. **Second sync**: Task appeared "deleted" and was removed from Obsidian ✗

### Root Cause

`SyncEngine.sync()` only queried the default calendar when `list_ids` was not explicitly provided. Routed tasks created in other calendars weren't fetched, causing the orphan detection logic to incorrectly identify them as deleted.

**Location**: `obs_sync/sync/engine.py:167`

```python
# BEFORE (buggy):
if not list_ids and self.vault_default_calendar:
    list_ids = [self.vault_default_calendar]  # Only default calendar
```

## Solution

Modified `SyncEngine.sync()` to automatically collect all relevant calendar IDs including routed calendars when `list_ids` is not explicitly provided.

**Location**: `obs_sync/sync/engine.py:167-180`

```python
# AFTER (fixed):
if not list_ids:
    list_ids = []
    if self.vault_default_calendar:
        list_ids.append(self.vault_default_calendar)
    
    # Add calendars from tag routes to ensure routed tasks are queried
    if self.sync_config and self.vault_id:
        for route in self.sync_config.get_tag_routes_for_vault(self.vault_id):
            calendar_id = route.get("calendar_id")
            if calendar_id and calendar_id not in list_ids:
                list_ids.append(calendar_id)
```

## Test Coverage

Added `test_tag_routing_bug.py` to reproduce and verify the fix:
- Simulates two-sync scenario with routed tags
- Confirms no spurious deletions occur
- Validates correct calendar querying behavior

All existing tests in `test_tag_routing_scenarios.py` continue to pass.

## Impact

- **Fixes**: Spurious deletion of Obsidian tasks with routed tags
- **Behavior**: Engine now queries all relevant calendars (default + routed)
- **Backward Compatible**: No breaking changes to existing configurations