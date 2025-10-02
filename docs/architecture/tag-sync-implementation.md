# Tag Sync Implementation

## Overview

Implemented bidirectional synchronization of hashtag-based tags between Obsidian tasks and Apple Reminders. Tags are preserved during sync operations and can be merged when conflicts arise. Additionally, tags can be used to route tasks to specific Reminders lists during synchronization.

## Architecture

### Storage Strategy

- **Obsidian**: Tags are stored inline in the markdown task text (e.g., `#work #important`)
- **Apple Reminders**: Tags are encoded in the notes field using a special delimiter `---tags---`

### Key Components

1. **Tag Utilities** (`obs_sync/utils/tags.py`)
   - `encode_tags_in_notes()`: Encodes tags into Reminders notes field while preserving user content
   - `decode_tags_from_notes()`: Extracts tags and user notes from combined field
   - `merge_tags()`: Merges tags from both sources, removing duplicates

2. **Model Updates**
   - Added `tags` field to `RemindersTask` model
   - Updated serialization/deserialization methods

3. **Gateway Layer**
   - `RemindersGateway`: Handles encoding/decoding when reading/writing to EventKit API
   - `ReminderData`: Added tags field for data transfer

4. **Task Managers**
   - `RemindersTaskManager`: Passes tags through CRUD operations
   - `ObsidianTaskManager`: Already supported tags via parser

5. **Sync Engine**
   - Creates tasks with tags intact when syncing in either direction
   - Applies tag updates based on conflict resolution

6. **Conflict Resolution**
   - `ConflictResolver`: Added tag conflict detection
   - Three resolution strategies:
     - `obs`: Obsidian tags win
     - `rem`: Reminders tags win  
     - `merge`: Combine unique tags from both sources (default when both have tags)

## Tag Format

### Delimiter Structure
```
<user notes>

---tags---
#tag1 #tag2 #tag3
```

### Features
- User notes are preserved above the delimiter
- Tags are space-separated below the delimiter
- Leading `#` is maintained for consistency
- Empty sections are handled gracefully

## Sync Behavior

1. **Obsidian → Reminders**
   - Tags from markdown are encoded into notes field
   - Existing user notes in Reminders are preserved

2. **Reminders → Obsidian**
   - Tags are decoded from notes field
   - Added to markdown task with `#from-reminders` marker
   - Tags appear inline in task description

3. **Conflict Resolution**
   - When tags differ, merge strategy is preferred
   - Preserves all unique tags from both systems
   - Obsidian tag order takes precedence

## Testing

Comprehensive test coverage in `test_tag_sync.py`:
- Tag encoding/decoding
- Tag merging logic
- Obsidian task tag parsing
- Reminders gateway integration
- Full sync engine round-trip
- Tag preservation during updates

## Backward Compatibility

- Tasks without tags continue to work normally
- Existing sync links remain valid
- Notes field without tags delimiter treated as pure user notes
- Graceful handling of missing tag fields in stored data

## Tag Routing

### Configuration

Tags can be configured to route tasks to specific Reminders lists during setup:
- During `obs-setup --reconfigure` (use the amend menu to add vaults or lists)
- Map tags like `#urgent` → Work list, `#personal` → Personal list
- First matching tag determines the destination list
- Tasks without matching tags use the vault's default list

### Sync Summary

The sync command now displays per-tag routing statistics:
```
📊 Tag Routing Summary:
  #urgent:
    → Work: 5 task(s)
  #personal:
    → Personal: 3 task(s)
  #shopping:
    → Shopping: 2 task(s)
```

This helps track how tasks are distributed across lists based on their tags.

## Usage Example

```python
# Obsidian task with tags

# Syncs to Reminders with notes field:
"""
Created from Obsidian

---tags---
#work #urgent #code-review
"""

# Updates from either side preserve tags
# Conflicts resolved by merging tag lists

# With tag routing configured:
# #urgent → Work list
# This task would sync to the Work list instead of the default list
```

## Implementation Notes

### Tag Format
- Tags are normalized with `#` prefix for consistency
- Duplicate tags are automatically removed
- Tag order preserved where possible (Obsidian first)
- Special tags like `#from-reminders` used for tracking origin
- No API changes required for existing sync operations

### Tag Routing Summary
- Collected by `SyncEngine._collect_tag_routing_summary()` method
- Analyzes linked tasks to determine distribution per tag
- Only counts tasks that are successfully synced (have links)
- Groups tasks by their routing tag and destination list
- Empty summary returned when no tag routes configured
- Displayed in sync command output when tag routes exist