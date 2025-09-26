# Task Deduplication Implementation

## Overview

This document outlines the complete implementation of task deduplication functionality in obs-sync. The feature automatically detects duplicate tasks across Obsidian and Reminders systems and provides interactive resolution during sync operations.

## Architecture

### Core Components

#### 1. Deduplication Engine (`obs_sync/sync/deduplicator.py`)
- **`DuplicateCluster`**: Data structure representing tasks with identical descriptions
- **`DeduplicationResults`**: Analysis results containing all clusters and statistics  
- **`TaskDeduplicator`**: Main class that detects duplicates and manages deletions

#### 2. Interactive Prompts (`obs_sync/utils/prompts.py`)
- **`display_duplicate_cluster()`**: Shows duplicate tasks in a user-friendly format
- **`prompt_for_keeps()`**: Interactive selection of tasks to preserve
- **`confirm_deduplication()`**: User confirmation before starting deduplication
- **`format_task_for_display()`**: Consistent task display formatting

#### 3. Sync Integration (`obs_sync/commands/sync.py`)
- **`_run_deduplication()`**: Orchestrates the complete deduplication workflow
- Integrated into existing `sync_command()` function
- Respects dry-run vs apply modes

#### 4. Configuration (`obs_sync/core/models.py`)
- **`enable_deduplication`**: Global toggle (default: True)
- **`dedup_auto_apply`**: Skip user prompts (default: False)

## Duplicate Detection Algorithm

### Normalization Strategy
Tasks are considered duplicates when their descriptions match after normalization:

```python
def _normalize_description(description):
    # Convert to lowercase and strip whitespace
    normalized = description.lower().strip()
    
    # Remove task markup (checkboxes, bullets)
    normalized = re.sub(r'^\s*[-\*]\s*\[[x\s]\]\s*', '', normalized)
    
    # Normalize whitespace
    normalized = re.sub(r'\s+', ' ', normalized)
    
    return normalized
```

### Cross-System Detection with Sync Link Exclusion
- **Obsidian tasks**: Uses the `description` field
- **Reminders tasks**: Uses the `title` field  
- Groups tasks from both systems into clusters by normalized description
- **CRITICAL**: Excludes already-synced task pairs to avoid flagging legitimate sync relationships as duplicates

### Sync Link Filtering
Before analyzing for duplicates, the system:
1. Loads existing sync links from the sync database
2. Creates exclusion sets of already-linked task UUIDs
3. Filters out linked tasks from duplicate analysis
4. Only analyzes remaining unlinked tasks for true duplicates

This prevents the common issue where properly synced Obsidian ↔ Reminders task pairs were incorrectly identified as duplicates.

## User Workflow

### Dry Run Mode (`obs-sync sync`)
1. Performs regular sync analysis
2. Runs deduplication analysis in read-only mode
3. Reports duplicate clusters found
4. Shows potential deletions without making changes

```
🔍 Deduplication Analysis:
  Found 2 duplicate cluster(s)
  Affecting 5 task(s)
  Would interactively resolve 3 duplicate(s)
```

### Apply Mode (`obs-sync sync --apply`)
1. Performs regular sync operations
2. Runs deduplication analysis
3. Prompts user to opt-in (unless `dedup_auto_apply` is enabled)
4. For each duplicate cluster:
   - Displays all duplicate tasks with context
   - Prompts user to select which tasks to keep
   - Deletes non-selected tasks
5. Shows summary of deletions made

### Interactive Resolution Example
```
🔍 Duplicate tasks found for: "Review quarterly budget"
   Found 3 tasks:
  1. [Obsidian] ⭕ Review quarterly budget
     📍 Work Vault:daily-notes/2024-01-15.md:10 | 📅 2024-01-15
  2. [Obsidian] ⭕ Review quarterly budget  
     📍 Work Vault:projects/finance.md:5 | 📅 2024-01-16
  3. [Reminders] ⭕ Review quarterly budget
     📍 Work Tasks | 📅 2024-01-15

❓ Which tasks would you like to keep? (1-3)
   Options:
   • Enter numbers separated by commas (e.g., '1,3')
   • Enter 'all' or 'skip' to keep everything
   • Enter 'none' to delete all tasks
   • Press Enter to skip this cluster
   Keep: 1,3

   ✅ Kept 2 task(s), deleted 1 task(s)
```

## CLI Integration

### New Command Options
```bash
# Disable deduplication for this sync
obs-sync sync --apply --no-dedup

# Enable automatic deduplication without prompts  
obs-sync sync --apply --dedup-auto-apply
```

### Configuration Options
```json
{
  "enable_deduplication": true,    // Enable deduplication by default
  "dedup_auto_apply": false        // Require user confirmation
}
```

## Implementation Details

### File Structure
```
obs_sync/
├── sync/
│   ├── deduplicator.py          # Core deduplication logic
│   └── __init__.py              # Export new classes
├── utils/
│   ├── prompts.py               # Interactive UI utilities
│   └── __init__.py              # Export prompt functions
├── commands/
│   └── sync.py                  # Integration with sync command
├── core/
│   └── models.py                # Configuration additions
└── main.py                      # CLI argument parsing

tests/
└── test_deduplication.py        # Comprehensive test suite

docs/
├── deduplication-implementation.md  # This document
└── tag-sync-implementation.md       # Related feature docs
```

### Key Design Decisions

1. **Exact Text Matching**: Duplicates defined solely by matching description text for precision
2. **Cross-System Detection**: Single pass evaluates both Obsidian and Reminders together  
3. **Sync Link Exclusion**: Already-synced task pairs are excluded from duplicate analysis to prevent false positives
4. **Interactive Resolution**: User maintains full control over which tasks to keep
5. **Dry-Run Safety**: Read-only analysis prevents accidental deletions
6. **Integration Pattern**: Runs after regular sync to avoid interfering with existing logic

### Error Handling
- Graceful degradation if deduplication fails
- Individual task deletion failures don't abort entire process  
- Comprehensive logging for troubleshooting
- User-friendly error messages

## Testing Coverage

### Test Suite (`test_deduplication.py`)
- **Unit Tests**: Individual component functionality
- **Integration Tests**: End-to-end workflow simulation
- **Mock Tests**: CLI prompts and user interactions
- **Edge Cases**: Empty inputs, invalid selections, API failures

### Test Categories
1. Data structure validation (`DuplicateCluster`, `DeduplicationResults`)
2. Duplicate detection algorithm accuracy
3. Task formatting and display logic  
4. Interactive prompt handling
5. Deletion statistics tracking
6. Configuration integration
7. Dry run vs apply mode behavior

## Performance Considerations

### Efficiency Optimizations
- **O(n) clustering**: Single pass through tasks for grouping
- **Lazy imports**: Avoid circular dependencies with deferred loading
- **Minimal memory usage**: Process clusters individually rather than batching

### Scalability
- Designed to handle large task sets (1000+ tasks)
- Memory-efficient duplicate detection
- Fast text normalization using compiled regexes

## Future Enhancements

### Potential Improvements
1. **Smart clustering**: Consider due dates, tags for similarity scoring
2. **Bulk operations**: Select multiple clusters for batch processing
3. **Undo functionality**: Reverse deduplication operations
4. **Export capability**: Save duplicate analysis to file
5. **Scheduling**: Automatic periodic deduplication

### Configuration Extensions
- Customizable normalization rules
- Per-vault deduplication settings
- Whitelist/blacklist patterns
- Similarity thresholds for fuzzy matching

## Related Features

This implementation builds upon and integrates with:
- **Tag Sync**: Preserves tags during deduplication
- **Sync Engine**: Leverages existing task management infrastructure  
- **Configuration System**: Uses established config patterns
- **CLI Framework**: Follows existing argument parsing conventions

## Migration and Compatibility

### Backward Compatibility
- No breaking changes to existing sync workflows
- All new features are opt-in by default
- Configuration fields have sensible defaults
- Existing sync links remain valid

### Data Safety
- Dry run mode prevents accidental deletions
- User confirmation required before any destructive operations
- Comprehensive logging for audit trail
- No automatic deletion without explicit user choice