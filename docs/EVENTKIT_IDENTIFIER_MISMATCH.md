# EventKit Identifier Mismatch Issue

## Overview

The sync system is experiencing "reminder task not found" debug messages during link normalization. While these messages don't break functionality—day-to-day syncing continues to work—they indicate an underlying issue with Apple's EventKit identifier stability.

**Status**: Non-breaking regression introduced with `_normalize_links` validation
**Impact**: Debug noise in logs; no functional sync failures
**Root Cause**: Apple's `calendarItemIdentifier()` is not stable across iCloud operations

---

## Technical Details

### The Identifier Lifecycle

1. **Creation/Fetch** (`obs_sync/reminders/gateway.py`)
   - Line 319: `uuid = str(rem.calendarItemIdentifier())` - Initial fetch from EventKit
   - Line 452: `return str(reminder.calendarItemIdentifier())` - Return after creating new reminder
   
   The gateway retrieves identifiers directly from Apple's EventKit API using `calendarItemIdentifier()`.

2. **Task Model Assignment** (`obs_sync/reminders/tasks.py`)
   - Lines 46-47:
   ```python
   task = RemindersTask(
       uuid=rem.uuid,
       item_id=rem.uuid,  # Both fields set to same identifier - NO FALLBACK
   ```
   
   **Critical issue**: Both `uuid` and `item_id` are set to the same `calendarItemIdentifier()` value. There is no alternative identifier to fall back on when the primary identifier changes.

3. **Link Persistence** (`obs_sync/sync/engine.py`)
   - Line 399: When creating counterparts, `SyncLink.rem_uuid` captures the reminder's UUID:
   ```python
   link = SyncLink(
       obs_uuid=obs_task.uuid,
       rem_uuid=created_task.uuid,  # Stores calendarItemIdentifier
       score=1.0,
       last_synced=datetime.now(timezone.utc).isoformat(),
   )
   ```
   
   This link is persisted to disk and used for all future sync operations.

4. **Link Normalization Attempt** (`obs_sync/sync/engine.py`)
   - Line 620: `_normalize_links` tries to find the reminder using the stored UUID:
   ```python
   rem_task = None
   for rt in rem_tasks:
       if rt.uuid == link.rem_uuid:
           rem_task = rt
           break
   ```
   
   - Line 656: When lookup fails, logs the debug message:
   ```python
   self.logger.debug(
       f"Cannot normalize {link.obs_uuid}: reminder task not found"
   )
   ```

---

## Root Cause: EventKit Identifier Instability

Apple's EventKit `calendarItemIdentifier()` **is NOT guaranteed to remain stable**. The identifier can change when:

- Reminders sync across iCloud devices
- A reminder is moved between lists
- Completion status is toggled
- The reminder is edited (users have observed new IDs appearing after edits)
- Other iCloud synchronization events occur

This is undocumented behavior, but observed in production use.

### Why This Breaks Normalization

1. Sync creates a reminder and stores its UUID in `SyncLink.rem_uuid`
2. Link is persisted to `sync_links.json`
3. User edits the reminder in Apple Reminders app
4. EventKit assigns a new `calendarItemIdentifier()` to the reminder
5. Next sync fetches reminders with new identifier
6. `_normalize_links` tries to find `link.rem_uuid` in current reminder list
7. **Lookup fails** because the old identifier no longer exists
8. Debug message logged, but link left untouched

### No Fallback Mechanism

The current implementation has **no alternative identifiers** to recover from this scenario:

- `RemindersTask.item_id` is set to the same value as `uuid` (line 47 of `obs_sync/reminders/tasks.py`)
- No title hash, creation timestamp, or list ID is persisted in `SyncLink`
- No similarity-based recovery is attempted

---

## Current Behavior

### What Works
- **Day-to-day sync continues functioning**: The link remains in `sync_links.json` with the stale UUID
- **Tasks still sync**: Because matching happens independently of normalization
- **No data loss**: Obsidian tasks and Reminders both remain intact

### What Doesn't Work
- **Link normalization fails silently**: Cannot update stale UUIDs to current ones
- **Debug logs are noisy**: Almost every legacy link triggers the "reminder task not found" message
- **Link hygiene degrades**: Over time, more links accumulate stale reminder UUIDs

---

## Regression Analysis

### Before `_normalize_links` (Old Behavior)

- Links were loaded from disk and used directly
- No validation that stored UUIDs still existed in current reminder lists
- **No logging of missing reminders**
- System worked as long as the Obsidian side of the link was valid

### After `_normalize_links` (Current Behavior)

- Links are validated during normalization
- When multiple unlinked Obsidian tasks exist for one stored UUID, system attempts to look up the reminder by `link.rem_uuid`
- **Validation failure triggers debug logging**
- Link is left unchanged (preserving old behavior), but now we see the noise

**Key insight**: The normalization code exposed pre-existing identifier drift that was always happening, but previously invisible.

---

## Test Coverage Gap

The test suite does not exercise real EventKit identifier drift:

**`test_uuid_normalization_regression.py:37`**:
```python
# Tests use fabricated "rem-..." UUIDs
uuid=f"rem-{uuid.uuid4().hex[:8]}"
```

These synthetic UUIDs never change because they're not real EventKit identifiers. The test cannot detect the identifier instability issue.

---

## Recommended Next Steps

### 1. Immediate: Reduce Debug Noise
Change log level from `debug` to `trace` or add throttling to reduce noise while maintaining diagnostic capability.

### 2. Short-term: Similarity-Based Recovery in `_normalize_links`

**Location**: `obs_sync/sync/engine.py:632`

When `link.rem_uuid` lookup fails:
1. Search unmatched reminders using existing `TaskMatcher._calculate_similarity()`
2. Match by title, due date, list, and other metadata
3. When confident match found (score ≥ threshold), **update `SyncLink.rem_uuid`** to the new identifier
4. Persist updated link back to `sync_links.json`

This provides automatic recovery from identifier drift.

### 3. Medium-term: Persist Auxiliary Identifiers

**Enhance `SyncLink` model** (obs_sync/core/models.py) to include:

```python
@dataclass
class SyncLink:
    obs_uuid: str
    rem_uuid: str
    score: float
    last_synced: str
    created_at: str = ""
    
    # New auxiliary identifiers for recovery
    rem_list_id: str = ""           # Calendar identifier (more stable)
    rem_title_hash: str = ""        # Hash of title for validation
    rem_created_at: str = ""        # Creation timestamp
    rem_last_known_title: str = ""  # Last known title for similarity matching
```

Store these when creating/updating links. Use them as additional anchors during recovery:
- If `rem_uuid` fails, try matching by `rem_list_id + rem_title_hash`
- Use `rem_created_at` as tie-breaker
- Use `rem_last_known_title` for similarity search

### 4. Long-term: External ID Support

Investigate whether EventKit provides more stable identifiers:
- `EKReminder.externalId` or similar properties
- Server-side iCloud identifiers
- Alternative APIs for stable referencing

---

## References

### Key Files and Lines
- `obs_sync/reminders/gateway.py:319` - Identifier fetch during listing
- `obs_sync/reminders/gateway.py:452` - Identifier return after creation  
- `obs_sync/reminders/tasks.py:46-47` - UUID and item_id both set (no fallback)
- `obs_sync/sync/engine.py:399` - SyncLink creation with rem_uuid
- `obs_sync/sync/engine.py:620` - Normalization lookup attempt
- `obs_sync/sync/engine.py:656` - Debug message logging
- `test_uuid_normalization_regression.py:37` - Synthetic UUIDs in tests

### Related Components
- `obs_sync/sync/matcher.py` - Contains `_calculate_similarity()` for recovery
- `obs_sync/core/models.py` - SyncLink and RemindersTask definitions
- `obs_sync/utils/text.py` - Similarity calculation utilities

---

## Conclusion

The "reminder task not found" issue is a **non-breaking regression** that exposes pre-existing EventKit identifier instability. The root cause is Apple's undocumented behavior where `calendarItemIdentifier()` can change, combined with our lack of fallback identifiers.

The immediate impact is debug noise. The long-term risk is degraded link hygiene as more identifiers drift over time.

The recommended fix is similarity-based recovery in `_normalize_links`, enhanced with auxiliary identifier persistence for more robust matching.