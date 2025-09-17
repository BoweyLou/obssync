# Vault-Based Reminders Organization Design

## Overview

This document outlines the design for implementing vault-based organization where each Obsidian vault mirrors to its own Reminders list, with non-Obsidian reminders consolidated into a central catch-all file.

## Current Architecture Analysis

### Key Components
- **Schema v2**: UUID-based identity, lifecycle management, deterministic operations
- **Domain Models**: `ReminderItem`, `RemindersList`, `RemindersStoreSnapshot` in `lib/reminders_domain.py`
- **Config System**: Centralized paths in `app_config.py`, preferences in `AppPreferences`
- **Collectors**: EventKit + SQLite hybrid collection in `collect_reminders_tasks.py`
- **Sync Engine**: Link suggestion, apply, and create-missing phases

### Current Flow
1. **Discovery**: Find vaults (`obsidian_vaults.json`) and lists (`reminders_lists.json`)
2. **Collection**: Gather tasks from both systems with rich metadata
3. **Linking**: Build bipartite matching between tasks
4. **Sync**: Apply field-level changes bidirectionally
5. **Create**: Generate missing counterparts

## New Architecture: Vault-Based Organization

### Core Concept
- **Vault Lists**: Each vault gets a dedicated Reminders list (e.g., "Work", "Personal")
- **Catch-All File**: Non-Obsidian reminders go to `{default_vault}/OtherAppleReminders.md`
- **List Isolation**: Vault-local tasks stay within their designated list
- **Context Preservation**: External reminders organized by source list as headings

### Schema Extensions

#### 1. List Location Classification
```python
class ListLocationType(Enum):
    VAULT_DEDICATED = "vault_dedicated"  # Mirrors a specific vault
    CATCH_ALL_SOURCE = "catch_all_source"  # External list feeding catch-all file
    LEGACY = "legacy"  # Old mapping to be cleaned up
```

#### 2. Enhanced Domain Models

**Extended RemindersList**:
```python
@dataclass(frozen=True)
class RemindersList:
    # ... existing fields ...

    # New vault-based fields
    list_location_type: ListLocationType = ListLocationType.CATCH_ALL_SOURCE
    vault_identifier: Optional[str] = None  # UUID of associated vault
    vault_name: Optional[str] = None  # Human-readable vault name
    is_auto_created: bool = False  # True if created by sync system
    catch_all_target_file: Optional[str] = None  # Target file for catch-all content
```

**Enhanced RemindersStoreSnapshot**:
```python
@dataclass
class RemindersStoreSnapshot:
    # ... existing fields ...

    # New metadata
    vault_mappings: Dict[str, str] = field(default_factory=dict)  # vault_id -> list_id
    catch_all_mappings: Dict[str, str] = field(default_factory=dict)  # list_id -> target_file
    legacy_mappings: List[str] = field(default_factory=list)  # Lists to be cleaned up
```

#### 3. Configuration Schema

**Extended AppPreferences**:
```python
@dataclass
class AppPreferences:
    # ... existing fields ...

    # Vault-based organization
    default_vault_id: Optional[str] = None  # Primary vault for catch-all file
    catch_all_filename: str = "OtherAppleReminders.md"
    auto_create_vault_lists: bool = True
    cleanup_legacy_mappings: bool = False  # Feature flag for cleanup phase

    # List management
    list_naming_template: str = "{vault_name}"  # Template for auto-created lists
    preserve_list_colors: bool = True
    max_lists_per_cleanup: int = 5  # Safety limit for bulk operations
```

#### 4. Vault Discovery Extensions

**Enhanced Vault Structure**:
```python
@dataclass(frozen=True)
class Vault:
    name: str
    path: str
    # New fields
    vault_id: str  # Stable UUID for the vault
    is_default: bool = False  # Primary vault for catch-all
    associated_list_id: Optional[str] = None  # Reminders list UUID
    catch_all_file_path: Optional[str] = None  # Full path to OtherAppleReminders.md
```

### Implementation Plan

#### Phase 1: Schema and Domain Model Updates
1. **Extend `reminders_domain.py`**:
   - Add `ListLocationType` enum
   - Update `RemindersList` with vault fields
   - Add vault mapping structures to snapshot

2. **Update `app_config.py`**:
   - Add vault-based preferences
   - Extend vault discovery to include UUIDs
   - Add configuration validation

3. **Schema migration**:
   - Update JSON schemas for v3 compatibility
   - Add migration path from v2 to v3
   - Preserve backward compatibility

#### Phase 2: Collection and Discovery Updates
1. **Enhanced vault discovery**:
   - Generate stable UUIDs for vaults
   - Detect existing vault-list mappings
   - Identify default vault for catch-all

2. **List classification**:
   - Analyze existing lists to determine type
   - Map vault names to list names
   - Flag legacy mappings for cleanup

3. **Enriched collection**:
   - Tag reminders with vault association
   - Track list location metadata
   - Preserve external list context

#### Phase 3: Sync Mechanics
1. **Vault-to-list sync**:
   - Auto-create missing vault lists
   - Sync vault tasks to dedicated lists
   - Handle list naming conflicts

2. **List-to-markdown sync**:
   - Generate heading-based sections
   - Use anchor comments for stability
   - Preserve manual edits between anchors

3. **Bidirectional updates**:
   - Route changes to correct destinations
   - Maintain existing sync semantics
   - Add conflict resolution for cross-vault moves

#### Phase 4: Cleanup and Migration
1. **Legacy mapping detection**:
   - Identify old catch-all patterns
   - Find orphaned lists/files
   - Generate migration plan

2. **Safe cleanup operations**:
   - Archive before deletion
   - Migrate content to new structure
   - Remove duplicates using UUID identity

3. **Rollback capability**:
   - Backup all changes
   - Enable restoration of previous state
   - Log all cleanup actions

### File Structure Changes

#### New Configuration Files
- `vault_list_mappings.json`: Vault-to-list associations
- `catch_all_config.json`: External list routing rules
- `cleanup_plan.json`: Pending cleanup operations

#### Enhanced Index Structure
```json
{
  "meta": {
    "schema": 3,
    "vault_organization_enabled": true,
    "default_vault_id": "uuid-1234",
    "catch_all_file": "/path/to/vault/OtherAppleReminders.md"
  },
  "vault_mappings": {
    "vault-uuid-1": {
      "vault_name": "Work",
      "list_id": "list-uuid-1",
      "list_name": "Work",
      "auto_created": true
    }
  },
  "catch_all_mappings": {
    "list-uuid-2": {
      "list_name": "Personal Projects",
      "target_section": "## Personal Projects",
      "anchor_start": "<!-- obs-tools:section:personal-projects:start -->",
      "anchor_end": "<!-- obs-tools:section:personal-projects:end -->"
    }
  },
  "tasks": {
    "task-uuid-1": {
      // ... existing task fields ...
      "vault_association": {
        "type": "vault_dedicated",
        "vault_id": "vault-uuid-1",
        "list_id": "list-uuid-1"
      }
    }
  }
}
```

### Sync Flow Changes

#### 1. Enhanced Discovery Phase
```
1. Discover vaults → assign UUIDs → detect existing mappings
2. Discover lists → classify by type → identify cleanup targets
3. Build vault-list mapping table
4. Generate cleanup plan if needed
```

#### 2. Collection Phase
```
1. Collect vault tasks → tag with vault_id
2. Collect reminders → classify by destination type
3. Enrich with vault association metadata
4. Build unified index with location routing
```

#### 3. Sync Planning Phase
```
1. Plan vault-to-list syncs (isolated by vault)
2. Plan list-to-markdown syncs (grouped by target file)
3. Plan cross-vault moves (if any)
4. Generate create-missing operations
```

#### 4. Apply Phase
```
1. Apply vault list changes (parallel processing)
2. Apply catch-all file updates (with anchor preservation)
3. Handle cross-vault moves
4. Create missing counterparts with proper routing
```

#### 5. Cleanup Phase (Optional)
```
1. Archive legacy mappings
2. Migrate orphaned content
3. Remove duplicate entries
4. Update configuration files
```

### Migration Strategy

#### Backward Compatibility
- Schema v2 continues to work unchanged
- Vault organization is opt-in via feature flag
- Existing sync links remain valid
- No data loss during migration

#### Migration Steps
1. **Detection**: Analyze current setup, identify migration opportunities
2. **Planning**: Generate migration plan with user confirmation
3. **Backup**: Create comprehensive backup of current state
4. **Execute**: Apply changes with rollback capability
5. **Validate**: Verify all data preserved and routed correctly

#### Risk Mitigation
- Atomic operations with rollback
- Comprehensive backup before changes
- User confirmation for destructive operations
- Dry-run mode for all cleanup operations
- Observability and logging throughout

### Configuration UI Changes

#### New TUI Sections
1. **Vault Organization Setup**:
   - Enable/disable vault-based organization
   - Map vaults to lists
   - Configure catch-all settings

2. **List Management**:
   - View vault-list mappings
   - Create/rename vault lists
   - Configure auto-creation templates

3. **Cleanup Operations**:
   - Review cleanup plan
   - Execute safe cleanup
   - Monitor cleanup progress

#### Command Line Extensions
```bash
# New vault-based commands
./bin/obs-vault-setup          # Interactive vault organization setup
./bin/obs-list-manage          # List creation and mapping
./bin/obs-cleanup-legacy       # Cleanup legacy mappings

# Enhanced existing commands
./bin/obs-sync-update --vault-mode  # Use vault-based routing
./bin/obs-vaults discover --assign-uuids  # Generate stable IDs
```

### Testing Strategy

#### Unit Tests
- Schema migration v2 → v3
- Vault-list mapping logic
- Anchor-based section management
- Cleanup operation safety

#### Integration Tests
- End-to-end vault-based sync
- Cross-vault task movement
- Legacy mapping migration
- Conflict resolution scenarios

#### Performance Tests
- Large vault collections
- Multi-vault sync performance
- Cleanup operation efficiency
- Memory usage with vault metadata

#### Safety Tests
- Rollback functionality
- Data preservation during migration
- Concurrent access during cleanup
- Error recovery scenarios

### Success Criteria

#### Functional Requirements
- ✅ Each vault syncs to dedicated Reminders list
- ✅ External reminders organized in catch-all file
- ✅ Existing sync semantics preserved
- ✅ Automatic cleanup of legacy mappings
- ✅ Safe migration from current system

#### Non-Functional Requirements
- ✅ No data loss during migration
- ✅ Performance comparable to current system
- ✅ Rollback capability for all changes
- ✅ Observable and debuggable operations
- ✅ Backward compatibility with v2 schema

#### User Experience
- ✅ Clear setup workflow
- ✅ Automatic vault detection
- ✅ Intuitive list organization
- ✅ Transparent cleanup process
- ✅ Comprehensive error reporting