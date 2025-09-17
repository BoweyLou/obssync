# Priority Migration Guide - ObsSync v2.0

## Overview

ObsSync v2.0 introduces a **breaking change** in how reminder priorities are handled. The priority mapping has been inverted to align with Apple's native priority scheme.

## Breaking Change Details

### Old Mapping (v1.x)
```
high   = 9 (higher number = higher priority)
medium = 5
low    = 1 (lower number = lower priority)
```

### New Mapping (v2.0+)
```
high   = 1 (lower number = higher priority)
medium = 5
low    = 9 (higher number = lower priority)
```

## Why This Change?

The new mapping aligns with Apple EventKit's native priority system:
- Consistent with Apple Reminders app behavior
- Matches industry standard where 1 = highest priority
- Reduces confusion when debugging or working with raw EventKit values

## Migration Required

**⚠️ Important**: Existing reminders with stored priority values need migration to preserve their intended priority levels.

### What Gets Converted

| Old Priority | Intent | New Priority | Action Needed |
|--------------|--------|--------------|---------------|
| 9 (high)     | High   | 1 (high)     | ✅ Convert    |
| 5 (medium)   | Medium | 5 (medium)   | ✨ Unchanged  |
| 1 (low)      | Low    | 9 (low)      | ✅ Convert    |
| 0 (none)     | None   | 0 (none)     | ✨ Unchanged  |

## Migration Process

### Step 1: Analyze Current State
```bash
# Check what needs to be migrated
python priority_migration.py --analyze
```

### Step 2: Test Migration (Dry Run)
```bash
# Simulate the migration process
python priority_migration.py --migrate --dry-run
```

### Step 3: Perform Migration
```bash
# Actually migrate the priorities
python priority_migration.py --migrate --apply
```

### Step 4: Verify Results
```bash
# Re-analyze to confirm migration success
python priority_migration.py --analyze
```

## Migration Utility Features

- **Safe Analysis**: Scans all reminders without making changes
- **Dry Run Mode**: Simulates migration to preview changes
- **Detailed Reporting**: Shows exactly what will be changed
- **Error Handling**: Graceful handling of permission and access issues
- **Batch Processing**: Handles large numbers of reminders efficiently

## Manual Migration Alternative

If the automated migration tool doesn't work, you can manually update priorities:

1. **Review High Priority Items**: Find reminders with priority = 1 (old mapping)
   - These will become low priority in v2.0
   - Manually change them to priority = 1 (new high)

2. **Review Low Priority Items**: Find reminders with priority = 9 (old mapping)
   - These will become high priority in v2.0
   - Manually change them to priority = 9 (new low)

3. **Medium Priority**: Items with priority = 5 remain unchanged

## Rollback Plan

If you need to rollback to v1.x priority mapping:

```bash
# The migration utility can reverse the process
python priority_migration.py --migrate --apply --reverse
```

## Timeline

- **Before upgrading to v2.0**: Run the migration utility
- **After upgrading**: Verify all priorities appear correctly
- **Future releases**: Will include automatic migration detection

## Support

If you encounter issues with the migration:

1. Check the migration utility output for specific error messages
2. Ensure you have proper EventKit permissions
3. Try running the analysis first to identify specific problem reminders
4. Manual migration may be needed for edge cases

## Files Modified

- `obs_tools/commands/task_operations.py` (priority mapping logic)
- `priority_migration.py` (migration utility)
- `CHANGELOG.md` (breaking change documentation)