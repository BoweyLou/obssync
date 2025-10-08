# Bug: Reminders Completions Undone Due to Timestamp Type Mismatch

## Summary

Reminders task completions are incorrectly reverted to TODO state during sync because the conflict resolver fails to parse RemindersTask timestamps, causing Obsidian to always win conflict resolution even when Reminders has the newer modification time.

## Root Cause

**Location**: `obs_sync/sync/resolver.py:90-98`

The `ConflictResolver._parse_time()` method assumes timestamps are ISO 8601 strings:

```python
def _parse_time(self, time_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO timestamp string."""
    if not time_str:
        return None
    try:
        return datetime.fromisoformat(time_str.replace('Z', '+00:00'))
    except:
        return None
```

However, **RemindersTask** stores timestamps as `datetime` objects (not strings):

**From `obs_sync/core/models.py:260-263`:**
```python
@dataclass
class RemindersTask:
    # ...
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
```

**From `obs_sync/reminders/tasks.py:48-58`:**
```python
# Parse datetime fields from ISO strings
modified_at_dt = None
if rem.modified_at:
    try:
        modified_at_dt = datetime.fromisoformat(rem.modified_at)
    except (ValueError, TypeError):
        pass

task = RemindersTask(
    # ...
    modified_at=modified_at_dt,  # datetime object, not string
)
```

In contrast, **ObsidianTask** stores timestamps as strings:

**From `obs_sync/core/models.py:188-189`:**
```python
@dataclass
class ObsidianTask:
    # ...
    created_at: Optional[str] = None
    modified_at: Optional[str] = None
```

## Bug Flow

1. User completes a task in Apple Reminders
2. RemindersGateway fetches the update with `modified_at` as ISO string
3. RemindersTaskManager converts to `datetime` object and stores in RemindersTask
4. During sync, `ConflictResolver.resolve_conflicts()` is called (engine.py:495)
5. `_parse_time(rem_task.modified_at)` receives a `datetime` object
6. The `.replace('Z', '+00:00')` call throws AttributeError (datetime has no string replace method)
7. Exception is caught silently, returns `None`
8. `_compare_times(obs_time, rem_time=None)` favors Obsidian (line 106-108)
9. Status conflict resolves as `'obs'` winner
10. Reminders completion is overwritten back to TODO

## Evidence

**From `obs_sync/sync/resolver.py:27-28`:**
```python
obs_time = self._parse_time(obs_task.modified_at)  # Works: string
rem_time = self._parse_time(rem_task.modified_at)  # Fails: datetime object
```

**From `obs_sync/sync/engine.py:909,913`:**
The engine already handles this type difference when persisting:
```python
self._datetime_to_iso(rem_task.created_at)  # Converts datetime to string
self._datetime_to_iso(rem_task.modified_at) or created_at_iso
```

## Impact

- **Critical**: All Reminders-side changes lose conflict resolution
- **User-visible**: Completions in Reminders are reverted to TODO
- **Data loss**: Any field updated in Reminders (due date, priority, title) is overwritten
- **Trust erosion**: Users lose confidence in bidirectional sync reliability

## Current State

**No existing test coverage** for:
- Conflict resolution with RemindersTask datetime timestamps
- Status conflict when Reminders has newer modification time
- Edge case where `_parse_time` silently fails

The only test using `ConflictResolver` (`tests/test_tag_sync.py:226`) creates tasks without `modified_at` values, so no parsing occurs.

---

## Fix Options

### Option 1: Broaden `_parse_time` to Accept Both Types (Recommended)

**Approach**: Make `_parse_time` polymorphic to handle both `datetime` objects and ISO strings.

**Changes Required**:
1. Update `_parse_time` signature and implementation in `obs_sync/sync/resolver.py:90-98`

**Proposed Implementation**:
```python
def _parse_time(self, time_value: Optional[Union[str, datetime]]) -> Optional[datetime]:
    """Parse timestamp from ISO string or datetime object."""
    if not time_value:
        return None
    
    # Already a datetime object
    if isinstance(time_value, datetime):
        return time_value
    
    # Parse ISO string
    try:
        return datetime.fromisoformat(time_value.replace('Z', '+00:00'))
    except (AttributeError, ValueError):
        return None
```

**Advantages**:
- ✅ Minimal code change (1 file, ~8 lines)
- ✅ No ripple effects across codebase
- ✅ Aligns with existing `_datetime_to_iso` helper in engine.py
- ✅ Preserves semantic meaning: timestamps are temporal values, not strings
- ✅ Future-proof: works regardless of upstream type changes
- ✅ Explicit type handling with clear intent

**Disadvantages**:
- ⚠️ Allows type heterogeneity (could mask future inconsistencies)
- ⚠️ Requires `Union` type import

**Files Modified**: 1
- `obs_sync/sync/resolver.py`

---

### Option 2: Normalize RemindersTask to Use Strings

**Approach**: Convert all RemindersTask timestamps to ISO strings at construction time.

**Changes Required**:

1. **Update dataclass** in `obs_sync/core/models.py:260-263`:
```python
@dataclass
class RemindersTask:
    # ...
    created_at: Optional[str] = None      # Changed from datetime
    modified_at: Optional[str] = None     # Changed from datetime
```

2. **Update RemindersTaskManager** in `obs_sync/reminders/tasks.py:48-58`:
```python
# Convert to ISO strings instead of datetime objects
created_at_str = None
if rem.created_at:
    try:
        dt = datetime.fromisoformat(rem.created_at)
        created_at_str = dt.isoformat()
    except (ValueError, TypeError):
        pass

modified_at_str = None
if rem.modified_at:
    try:
        dt = datetime.fromisoformat(rem.modified_at)
        modified_at_str = dt.isoformat()
    except (ValueError, TypeError):
        pass

task = RemindersTask(
    # ...
    created_at=created_at_str,
    modified_at=modified_at_str,
)
```

3. **Remove `_datetime_to_iso` conversions** in `obs_sync/sync/engine.py:909,913`:
```python
# Before:
self._datetime_to_iso(rem_task.created_at)
# After:
rem_task.created_at  # Already a string
```

4. **Update all timestamp consumers**:
   - `obs_sync/reminders/tasks.py` - create/update methods
   - Any analytics/insights code expecting datetime objects
   - Test fixtures in multiple test files

**Advantages**:
- ✅ Uniform type across both task models
- ✅ Simpler mental model: all timestamps are strings
- ✅ Potential slight performance gain (no repeated conversions)

**Disadvantages**:
- ⚠️ Large surface area: 4+ files modified
- ⚠️ Requires updating all RemindersTask consumers
- ⚠️ Loses type safety: strings are less semantically meaningful than datetime
- ⚠️ Breaks existing code that expects datetime objects
- ⚠️ Higher regression risk
- ⚠️ More test updates required

**Files Modified**: 4+
- `obs_sync/core/models.py`
- `obs_sync/reminders/tasks.py`
- `obs_sync/sync/engine.py`
- `tests/test_reminders_manager.py`
- Any other code accessing `RemindersTask.modified_at`

---

## Recommendation: **Option 1**

**Rationale**:
1. **Minimal blast radius**: Changes isolated to conflict resolver
2. **Type-safe**: Preserves semantic datetime types where they make sense
3. **Consistent with existing patterns**: `engine.py` already has `_datetime_to_iso` helper
4. **Lower regression risk**: Doesn't touch task construction or persistence logic
5. **Explicit handling**: Type check makes polymorphism clear and intentional

The timestamp type mismatch is fundamentally an **interface boundary issue** between two subsystems with different conventions. Option 1 handles this at the boundary (conflict resolver) without forcing uniform types across unrelated subsystems.

---

## Implementation Steps (Option 1)

### 1. Update ConflictResolver._parse_time()

**File**: `obs_sync/sync/resolver.py`

**Changes**:
```python
# Line 1: Add Union import
from typing import Dict, Optional, Tuple, List, Union  # Add Union
from datetime import datetime

# Lines 90-98: Replace _parse_time method
def _parse_time(self, time_value: Optional[Union[str, datetime]]) -> Optional[datetime]:
    """Parse timestamp from ISO string or datetime object.
    
    Args:
        time_value: Either an ISO 8601 string or a datetime object
        
    Returns:
        datetime object if parsing succeeds, None otherwise
    """
    if not time_value:
        return None
    
    # Already a datetime object (from RemindersTask)
    if isinstance(time_value, datetime):
        return time_value
    
    # Parse ISO string (from ObsidianTask)
    try:
        return datetime.fromisoformat(time_value.replace('Z', '+00:00'))
    except (AttributeError, ValueError):
        return None
```

**Validation**:
- Verify type annotation with mypy/pyright
- Confirm no other methods need updates

---

### 2. Add Regression Test

**File**: `tests/test_regression.py`

**New Test Class**:
```python
class TestConflictResolutionTimestamps:
    """Regression test for timestamp type handling in conflict resolution."""
    
    def test_reminders_datetime_wins_over_older_obsidian_string(self):
        """
        Test that Reminders completion with datetime modified_at beats
        older Obsidian string timestamp.
        
        Regression: Bug where _parse_time failed on datetime objects,
        causing Reminders to always lose conflicts.
        """
        from datetime import datetime, timezone, timedelta
        from obs_sync.sync.resolver import ConflictResolver
        from obs_sync.core.models import ObsidianTask, RemindersTask, TaskStatus
        
        resolver = ConflictResolver()
        
        # Obsidian task completed 1 hour ago (ISO string)
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        obs_task = ObsidianTask(
            uuid="obs-123",
            vault_id="v1",
            vault_name="Test",
            vault_path="/tmp/test",
            file_path="todo.md",
            line_number=5,
            block_id="abc",
            status=TaskStatus.TODO,  # Still TODO in Obsidian
            description="Buy milk",
            raw_line="- [ ] Buy milk",
            modified_at=one_hour_ago.isoformat()  # String timestamp
        )
        
        # Reminders task completed just now (datetime object)
        now = datetime.now(timezone.utc)
        rem_task = RemindersTask(
            uuid="obs-123",  # Same UUID
            item_id="rem-456",
            calendar_id="cal-1",
            list_name="Shopping",
            status=TaskStatus.DONE,  # Completed in Reminders
            title="Buy milk",
            modified_at=now  # datetime object (NOT string)
        )
        
        # Resolve conflicts
        conflicts = resolver.resolve_conflicts(obs_task, rem_task)
        
        # Reminders should win because it has newer timestamp
        assert conflicts['status_winner'] == 'rem', \
            f"Expected Reminders to win status conflict (newer timestamp), got {conflicts['status_winner']}"
    
    def test_parse_time_handles_both_types(self):
        """Test that _parse_time correctly handles both strings and datetime objects."""
        from datetime import datetime, timezone
        from obs_sync.sync.resolver import ConflictResolver
        
        resolver = ConflictResolver()
        
        # Test with datetime object
        dt_obj = datetime(2025, 1, 15, 12, 30, 0, tzinfo=timezone.utc)
        parsed_dt = resolver._parse_time(dt_obj)
        assert parsed_dt == dt_obj, "Should return datetime object as-is"
        
        # Test with ISO string
        iso_str = "2025-01-15T12:30:00+00:00"
        parsed_str = resolver._parse_time(iso_str)
        assert parsed_str == dt_obj, "Should parse ISO string correctly"
        
        # Test with None
        parsed_none = resolver._parse_time(None)
        assert parsed_none is None, "Should return None for None input"
        
        # Test with invalid string
        parsed_invalid = resolver._parse_time("not-a-date")
        assert parsed_invalid is None, "Should return None for invalid string"
```

**Integration Test** (optional, add to `tests/test_tag_sync.py`):
```python
def test_reminders_completion_survives_sync():
    """
    End-to-end test: Completing a task in Reminders should survive sync.
    
    Regression: Reminders completions were reverted due to timestamp parsing bug.
    """
    # ... setup vault, create linked tasks ...
    # ... complete task in Reminders ...
    # ... run sync ...
    # ... assert task remains DONE, not reverted to TODO ...
```

---

### 3. Validate Downstream Consumers

**Files to Review**:

1. **`obs_sync/sync/engine.py`**:
   - ✅ Lines 909, 913 already use `_datetime_to_iso()` helper
   - ✅ No changes required
   
2. **`obs_sync/analytics/streaks.py`**:
   - Review if it accesses `RemindersTask.modified_at` directly
   - Expected: Should work with datetime objects (no change needed)
   
3. **`obs_sync/utils/insights.py`**:
   - Review for timestamp usage
   - Expected: Works with task objects, not timestamps directly

4. **`obs_sync/calendar/daily_notes.py`**:
   - Review insights injection logic
   - Expected: No direct timestamp access

**Action**: Read each file and confirm no breakage

---

### 4. Documentation Updates

**File**: `docs/architecture/sync-design.md` (or create if missing)

**Add Section**:
```markdown
## Timestamp Handling

### Type Conventions

**ObsidianTask**: Stores timestamps as ISO 8601 strings
- `created_at: Optional[str]`
- `modified_at: Optional[str]`
- Rationale: Parsed from markdown metadata as strings

**RemindersTask**: Stores timestamps as datetime objects
- `created_at: Optional[datetime]`
- `modified_at: Optional[datetime]`
- Rationale: EventKit API returns dates, converted to datetime for semantic clarity

### Conflict Resolution

`ConflictResolver._parse_time()` accepts both types via polymorphic handling:
- datetime objects: returned as-is
- ISO strings: parsed via `datetime.fromisoformat()`

This design accommodates different upstream conventions without forcing unnecessary type conversions.

### Persistence

When persisting RemindersTask data, use `SyncEngine._datetime_to_iso()` to convert datetime objects to strings for JSON serialization.
```

---

## Testing Checklist

- [ ] Unit test: `_parse_time` with datetime object
- [ ] Unit test: `_parse_time` with ISO string
- [ ] Unit test: `_parse_time` with None
- [ ] Unit test: `_parse_time` with invalid input
- [ ] Regression test: Reminders completion with newer timestamp wins
- [ ] Regression test: Obsidian update with newer timestamp wins
- [ ] Integration test: End-to-end sync preserves Reminders completions
- [ ] Manual test: Complete task in Reminders, run sync, verify status persists
- [ ] Manual test: Complete task in Obsidian, run sync, verify status persists
- [ ] Manual test: Conflicting edits (both sides modified) resolve to latest

---

## Rollout Plan

1. **Implement**: Update `_parse_time` method (5 minutes)
2. **Test**: Add regression tests (15 minutes)
3. **Validate**: Review downstream consumers (10 minutes)
4. **Document**: Update architecture docs (10 minutes)
5. **Manual QA**: Test on real vault with Reminders (10 minutes)
6. **Ship**: Merge to main, release in next version

**Total estimated time**: ~1 hour

**Risk level**: Low (isolated change, comprehensive tests)

---

## Future Improvements

1. **Type Consistency Audit**: Consider standardizing timestamp types across all models in v2.0
2. **Strict Type Checking**: Enable mypy/pyright to catch these mismatches earlier
3. **ConflictResolver Tests**: Expand test coverage for all conflict resolution scenarios
4. **Logging**: Add debug logging when `_parse_time` receives unexpected types

---

## References

- Issue discovered: 2025-01-08
- Related files:
  - `obs_sync/sync/resolver.py:90-98`
  - `obs_sync/core/models.py:188-189, 260-263`
  - `obs_sync/reminders/tasks.py:48-58`
  - `obs_sync/sync/engine.py:909,913`
- Test location: `tests/test_regression.py` (new TestConflictResolutionTimestamps class)
