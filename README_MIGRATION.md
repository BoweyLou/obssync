# Migration Guide: obs-sync v2.0 (formerly obs-tools)

## Overview

obs-sync v2.0 introduces a dramatically simplified architecture that reduces complexity by 65% while maintaining all core functionality. Additionally, v2.1 introduces a new path management system with per-install working directories.

## What's New in v2.1

### Per-Install Working Directory
Configuration and data files are now stored in a `.obs-sync/` directory alongside the tool installation, rather than in a fixed home directory location. This allows:
- Multiple independent installations
- Better isolation between different versions
- Easier cleanup (just delete the tool directory)
- Automatic migration from legacy locations

### Path Management System
The new path resolution order:
1. **OBS_SYNC_HOME** environment variable (if set)
2. **`.obs-sync/`** in the tool installation directory
3. **`~/.config/obs-sync`** (legacy fallback)

### Migration Command
A new `obs-sync migrate` command helps move your configuration from legacy locations to the new structure.

## What Changed in v2.0

### Simplified Commands (3 instead of 20+)
- `obs-sync setup` - Initial configuration
- `obs-sync sync` - Main sync operation (dry-run by default, use --apply to execute)
- `obs-sync calendar` - Calendar to daily notes sync
- `obs-sync migrate` - Migrate configuration from legacy locations (new in v2.1)

### Removed Features
- TUI interface (use CLI commands)
- Backup system (rely on git/Time Machine)
- Duplicate detection/removal (not core functionality)
- Complex vault organization features

### New Architecture Benefits
- 65% fewer files
- Cleaner module structure
- Faster execution
- Easier maintenance

## Migration Steps

### Automatic Migration
The new version will automatically detect and migrate your configuration on first use:

```bash
# Simply run any command - migration happens automatically
obs-sync setup        # Will auto-migrate if legacy config exists
obs-sync sync         # Will auto-migrate if legacy config exists
```

### Manual Migration
For more control over the migration process:

1. **Check current configuration status**
   ```bash
   obs-sync migrate --check
   ```
   This shows:
   - Current working directory location
   - Any legacy configuration files found
   - Environment variable status

2. **Perform the migration**
   ```bash
   obs-sync migrate --apply
   ```
   This will:
   - Move configuration files to the new location
   - Preserve legacy files with `.pre-migration` backups
   - Show detailed progress

3. **Force migration (if conflicts exist)**
   ```bash
   obs-sync migrate --apply --force
   ```

### Custom Installation Location
To use a specific directory for configuration:

```bash
# Set environment variable
export OBS_SYNC_HOME="$HOME/.config/my-obs-sync"

# All commands will now use this location
obs-sync setup
obs-sync sync --apply
```

## File Locations

### New Structure (v2.1+)
```
<tool_directory>/           # Where obs_sync is installed
├── obs_sync/              # Package directory
└── .obs-sync/             # Working directory (NEW)
    ├── config.json        # Main configuration
    ├── data/              # Data files
    │   ├── sync_links.json
    │   ├── obsidian_tasks_index.json
    │   └── reminders_tasks_index.json
    ├── backups/           # Backup directory
    └── logs/              # Log files
```

### Legacy Structure (v2.0 and earlier)
```
~/.config/obs-sync/        # Fixed home directory location
├── config.json
├── sync_links.json        # Or in data/ subdirectory
└── data/
    ├── obsidian_tasks_index.json
    └── reminders_tasks_index.json
```

## Command Mapping

| Old Command | New Command |
|------------|-------------|
| obs-app | (removed - use CLI) |
| obs-sync-update && obs-sync apply | obs-sync sync --apply |
| obs-sync dry | obs-sync sync |
| obs-vaults discover | obs-sync setup |
| obs-reminders discover | obs-sync setup |
| obs-calendar-sync | obs-sync calendar |
| obs-duplicates | (removed) |
| obs-reset | rm -rf .obs-sync (in tool directory) |
| (manual config move) | obs-sync migrate --apply |

## Configuration

The configuration structure remains the same but the location has changed:

**Default location:** `<tool_directory>/.obs-sync/config.json`
**Override with:** `export OBS_SYNC_HOME=/custom/path`

```json
{
  "vaults": [...],
  "reminders_lists": [...],
  "sync": {
    "min_score": 0.75,
    "days_tolerance": 1,
    "include_completed": false
  },
  "paths": {
    "obsidian_index": "auto-generated",
    "reminders_index": "auto-generated",
    "links": "auto-generated"
  }
}
```

## Troubleshooting

### Finding Your Configuration

To see where your configuration is stored:
```bash
obs-sync migrate --check
```

This will show:
- Tool root directory
- Current working directory
- Legacy directory location
- OBS_SYNC_HOME value (if set)

### Configuration Not Found

If obs-sync can't find your configuration:

1. **Check for legacy files:**
   ```bash
   ls -la ~/.config/obs-sync/
   ls -la ~/.config/*.json
   ```

2. **Run migration:**
   ```bash
   obs-sync migrate --apply
   ```

3. **Or set custom location:**
   ```bash
   export OBS_SYNC_HOME="$HOME/.config/obs-sync"
   ```

### Permission Issues

If the tool directory is read-only (e.g., system installation):

1. **Use environment variable:**
   ```bash
   export OBS_SYNC_HOME="$HOME/.obs-sync"
   obs-sync setup
   ```

2. **Or reinstall in user directory:**
   ```bash
   pip install --user obs-sync
   ```

### Multiple Installations

If you have multiple obs-sync installations:

1. Each installation has its own `.obs-sync/` directory
2. Use `OBS_SYNC_HOME` to share configuration between them:
   ```bash
   export OBS_SYNC_HOME="$HOME/.config/shared-obs-sync"
   ```

### Cleaning Up Legacy Files

After successful migration:

1. **Verify new location works:**
   ```bash
   obs-sync sync  # Test dry-run
   ```

2. **Remove legacy files (optional):**
   ```bash
   # Backups are created with .pre-migration suffix
   rm -rf ~/.config/obs-sync
   rm ~/.config/sync_links.json.pre-migration
   ```

## Rollback

To rollback to a previous version:

### If using v2.1 with new paths:
```bash
# Restore from migration backups
cd ~/.config
mv obs-sync.pre-migration obs-sync
mv sync_links.json.pre-migration sync_links.json

# Or point new version to old location
export OBS_SYNC_HOME="$HOME/.config/obs-sync"
```

### If using v2.0:
```bash
# Simply reinstall old version
pip install obs-tools==1.0  # Or your previous version
```

## Environment Variables

### OBS_SYNC_HOME
Controls where obs-sync stores its configuration and data files.

```bash
# Examples
export OBS_SYNC_HOME="$HOME/.config/obs-sync"  # Use legacy location
export OBS_SYNC_HOME="$HOME/Documents/obs-sync-data"  # Custom location
export OBS_SYNC_HOME="/shared/team/obs-sync"  # Shared team configuration
```

### Benefits of OBS_SYNC_HOME:
- Override read-only installation directories
- Share configuration between multiple installations
- Use network/cloud storage for configuration
- Maintain backward compatibility with scripts

For additional help, please refer to the main README.md or file an issue on GitHub.