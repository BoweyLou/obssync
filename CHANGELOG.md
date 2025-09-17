# Changelog

All notable changes to ObsSync will be documented in this file.

## [v2.0] - 2025-09-17

### Breaking Changes

#### ⚠️ Priority Mapping Inversion

**Priority values have been inverted to match Apple's native priority scheme:**

- **Before v2.0**: `high=9, medium=5, low=1`
- **After v2.0**: `high=1, medium=5, low=9`

**Impact**: This change aligns with Apple Reminders' native priority system where lower numeric values represent higher priority levels.

**Migration Required**: Existing reminders with stored priority values will need migration to preserve their intended priority levels:
- Old `high` priority (9) → New `low` priority (9)
- Old `low` priority (1) → New `high` priority (1)
- Old `medium` priority (5) → Unchanged (5)

**Files Affected**:
- `obs_tools/commands/task_operations.py` (lines ~449, ~525)

**Migration Plan**:
1. Run priority migration tool before upgrading to v2.0
2. Or manually review and adjust reminder priorities after upgrade
3. Future versions will include automatic migration detection and conversion

### Added
- Comprehensive priority mapping documentation
- Migration warnings and TODOs for priority handling

### Technical Details
- Priority mapping is now consistent with EventKit's EKReminder.priority property
- Both `update_reminder()` and `create_reminder()` methods use the new mapping
- Added clear documentation explaining the rationale for this breaking change