# Create Missing Counterparts Feature

The "Create Missing Counterparts" feature automatically creates missing tasks in the opposite system for unlinked items. This allows you to have comprehensive task coverage across both Obsidian and Apple Reminders.

## Overview

This feature identifies tasks that exist in one system (Obsidian or Apple Reminders) but have no corresponding counterpart in the other system, then creates the missing counterparts with proper field mapping and linking.

### Key Features

- **Bidirectional Creation**: Create tasks in either direction (Obsidian ↔ Reminders)
- **Smart Field Mapping**: Automatic translation of task properties between systems
- **Configurable Rules**: Custom mapping rules based on tags, lists, and other criteria
- **Safety First**: Dry-run mode, idempotency checks, and comprehensive error handling
- **Incremental Operation**: Filters to avoid overwhelming with old tasks

## Quick Start

### Command Line Usage

```bash
# Show what would be created (dry-run)
./bin/obs-sync-create --dry-run

# Create Reminders from unlinked Obsidian tasks
./bin/obs-sync-create --apply --direction obs-to-rem

# Create Obsidian tasks from unlinked Reminders
./bin/obs-sync-create --apply --direction rem-to-obs

# Create counterparts in both directions
./bin/obs-sync-create --apply --direction both

# Only process recent tasks (last 7 days)
./bin/obs-sync-create --apply --since 7

# Limit number of creations per run
./bin/obs-sync-create --apply --max 25

# Include completed tasks
./bin/obs-sync-create --apply --include-done
```

### TUI (Interactive) Usage

1. Launch the TUI: `./bin/obs-app`
2. Select "Create Missing Counterparts"
3. Choose your options:
   - **Dry-run**: Show what would be created
   - **Create Obsidian → Reminders**: One direction only
   - **Create Reminders → Obsidian**: One direction only
   - **Create both directions**: Comprehensive sync

## How It Works

### 1. Task Identification

The system identifies unlinked tasks by:
- Loading existing task indices (`obsidian_tasks_index.json`, `reminders_tasks_index.json`)
- Loading existing links (`sync_links.json`)
- Building sets of already-linked task UUIDs
- Finding tasks that exist in one system but have no counterpart link

### 2. Filtering

Tasks are filtered based on:
- **Linked Status**: Skip tasks that already have counterparts
- **Lifecycle State**: Skip deleted or missing tasks
- **Completion Status**: Optionally skip completed tasks (`--include-done`)
- **Recency**: Optionally limit to recently modified tasks (`--since DAYS`)
- **Quantity**: Optionally limit total creations per run (`--max N`)

### 3. Field Mapping

Smart field translation between systems:

#### Obsidian → Reminders
- **Title**: `description` → `title`
- **Due Date**: `due` → `due_date` (normalized to YYYY-MM-DD)
- **Priority**: `high/medium/low` → `EventKit 9/5/1`
- **Notes**: File path, line number, and tags as context
- **URL**: Deep-link to Obsidian (`obsidian://open?vault=...&file=...#^block`)

#### Reminders → Obsidian
- **Description**: `title` → `description`
- **Status**: `is_completed` → `todo/done`
- **Due Date**: `due_date` → `due` (normalized to YYYY-MM-DD)
- **Priority**: `EventKit 9/5/1` → `high/medium/low`
- **Tags**: List name converted to hashtag (e.g., "Work" → `#work`)

### 4. Target Determination

Where to create new tasks:

#### Obsidian Tasks
- **Default**: Configured inbox file (`~/Documents/Obsidian/Default/Tasks.md`)
- **Custom Rules**: List-based mapping (e.g., "Work" list → `~/work/tasks.md`)
- **Fallback**: Always creates target file if it doesn't exist

#### Reminders Tasks
- **Default**: Configured default calendar
- **Custom Rules**: Tag-based mapping (e.g., `#work` tag → Work calendar)
- **Fallback**: System default calendar if no configuration

## Configuration

### App Configuration

Extend your app configuration (`~/.config/obs-tools/app.json`):

```json
{
  "creation_defaults": {
    "obs_inbox_file": "~/Documents/Obsidian/MyVault/Inbox.md",
    "rem_default_calendar_id": "calendar-uuid-here",
    "max_creates_per_run": 50,
    "since_days": 30,
    "include_done": false
  },
  "obs_to_rem_rules": [
    {"tag": "#work", "calendar_id": "work-calendar-uuid"},
    {"tag": "#personal", "calendar_id": "personal-calendar-uuid"}
  ],
  "rem_to_obs_rules": [
    {"list_name": "Work", "target_file": "~/Documents/Obsidian/MyVault/Work/Tasks.md", "heading": "Imported"},
    {"list_name": "Personal", "target_file": "~/Documents/Obsidian/MyVault/Personal/Tasks.md"}
  ]
}
```

### Configuration Options

#### Creation Defaults
- **`obs_inbox_file`**: Default Obsidian file for new tasks
- **`rem_default_calendar_id`**: Default Reminders calendar UUID
- **`max_creates_per_run`**: Limit creations to prevent overwhelming
- **`since_days`**: Default recency filter
- **`include_done`**: Whether to include completed tasks by default

#### Mapping Rules
- **`obs_to_rem_rules`**: Tag-based routing to specific calendars
- **`rem_to_obs_rules`**: List-based routing to specific files/headings

## Safety Features

### Idempotency

The system prevents duplicate creation through:
- **Pre-creation Checks**: Verifies no existing link or exact match
- **Deep-link Integration**: Sets Obsidian URLs in Reminders for recognition
- **Block ID Tracking**: Ensures stable identifiers for future matching

### Error Handling

Comprehensive error recovery:
- **Authorization Errors**: Graceful handling of EventKit permission issues
- **File System Errors**: Automatic directory creation and permission handling
- **Partial Failures**: Continues processing even if individual creations fail
- **Rollback Capability**: Changeset tracking for undoing operations

### Backup System

All operations are tracked:
- **File Changes**: Obsidian file modifications with line-level tracking
- **Reminders Creation**: EventKit object identifiers for cleanup
- **Link Updates**: Atomic updates to sync_links.json with rollback support

## Integration Workflow

### Recommended Workflow

1. **Initial Sync**: Run existing sync operations to establish baseline links
2. **Create Missing**: Use this feature to fill gaps
3. **Field Sync**: Run regular sync to align field values
4. **Ongoing**: Periodic runs to catch new unlinked tasks

### TUI Integration

After creating counterparts, the TUI offers:
- **Immediate Field Sync**: Option to run sync operation right after creation
- **Progress Tracking**: Real-time progress and error reporting
- **Result Summary**: Detailed counts and success/failure breakdown

## Performance Considerations

### Optimized for Scale

- **Incremental Processing**: Only processes unlinked tasks
- **Batch Operations**: Groups multiple creations for efficiency
- **Memory Efficient**: Streams large datasets without loading everything
- **Progress Reporting**: Real-time feedback for long operations

### Resource Management

- **Rate Limiting**: Respects system limits for EventKit operations
- **Memory Usage**: Minimal memory footprint even with large task sets
- **File I/O**: Atomic operations with proper locking

## Troubleshooting

### Common Issues

1. **No Tasks Created**
   - Check that indices are up-to-date (`./bin/obs-sync-update`)
   - Verify filtering settings (`--since`, `--include-done`)
   - Review existing links (may already be linked)

2. **Permission Errors**
   - macOS: Grant EventKit permissions in System Preferences
   - File System: Ensure write permissions to target directories

3. **Mapping Issues**
   - Review configuration rules in app.json
   - Check target calendar IDs are valid
   - Verify Obsidian file paths exist

### Debug Mode

Use verbose output for detailed information:
```bash
./bin/obs-sync-create --dry-run --verbose
```

### Log Analysis

Check component logs for detailed operation history:
```bash
tail -f ~/.config/obs-tools/logs/create_missing_counterparts.log
```

## API Reference

### Command Line Interface

```bash
obs_tools.py sync create [OPTIONS]
```

#### Options
- `--obs PATH`: Obsidian tasks index path
- `--rem PATH`: Reminders tasks index path  
- `--links PATH`: Sync links file path
- `--apply`: Actually create counterparts (default: dry-run)
- `--direction {both,obs-to-rem,rem-to-obs}`: Creation direction
- `--include-done`: Include completed tasks
- `--since DAYS`: Only process tasks from last N days
- `--max N`: Maximum creations per run
- `--verbose`: Detailed output
- `--plan-out PATH`: Save creation plan to JSON file

### Python API

```python
from obs_tools.commands.create_missing_counterparts import MissingCounterpartsCreator, CreationConfig

# Configure creation settings
config = CreationConfig(
    obs_inbox_file="~/vault/inbox.md",
    rem_default_calendar_id="cal-uuid",
    max_creates_per_run=25
)

# Create counterparts
creator = MissingCounterpartsCreator(config)
plan = creator.create_plan(obs_index, rem_index, links_data)
result = creator.execute_plan(plan, links_path, run_id)
```

## Examples

### Example 1: Basic Usage

```bash
# Check what would be created
./bin/obs-sync-create --dry-run --verbose

# Create counterparts for recent work tasks
./bin/obs-sync-create --apply --since 7 --direction obs-to-rem
```

### Example 2: Bulk Migration

```bash
# Create all missing counterparts (both directions)
./bin/obs-sync-create --apply --direction both --include-done --max 100

# Follow up with field sync
./bin/obs-sync apply --apply
```

### Example 3: Filtered Creation

```bash
# Only recent, incomplete tasks in both directions
./bin/obs-sync-create --apply --since 14 --max 25 --direction both
```

## Changelog

### Version 1.0.0 (Feature Implementation)
- ✅ Core algorithm implementation
- ✅ CLI interface with full argument support
- ✅ TUI integration with interactive workflows
- ✅ Configuration system extensions
- ✅ Comprehensive test coverage
- ✅ Safety features and error handling
- ✅ Documentation and examples

### Future Enhancements
- Advanced filtering options (priority, tag patterns)
- Bulk configuration management
- Template-based task creation
- Cross-platform clipboard integration
- Webhook notifications for automated workflows