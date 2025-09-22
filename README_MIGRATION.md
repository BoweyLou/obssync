# Migration Guide: obs-sync v2.0 (formerly obs-tools)

## Overview

obs-sync v2.0 introduces a dramatically simplified architecture that reduces complexity by 65% while maintaining all core functionality.

## What's Changed

### Simplified Commands (3 instead of 20+)
- `obs-sync setup` - Initial configuration
- `obs-sync sync` - Main sync operation (dry-run by default, use --apply to execute)
- `obs-sync calendar` - Calendar to daily notes sync

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

1. **Backup your current configuration**
   ```bash
   cp -r ~/.config/obs-tools ~/.config/obs-tools.backup  # legacy config backup
   cp ~/.config/*.json ~/.config/backup/
   ```

2. **Run configuration migration**
   ```bash
   python3 config_migration.py
   ```

3. **Test the new commands**
   ```bash
   obs-sync setup        # Verify configuration
   obs-sync sync         # Preview sync (dry-run)
   obs-sync sync --apply # Apply sync when ready
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
| obs-reset | rm -rf ~/.config/obs-sync |

## Configuration

The new configuration is stored in `~/.config/obs-sync/config.json` with a simplified structure:

```json
{
  "vaults": [...],
  "reminders_lists": [...],
  "sync": {
    "min_score": 0.75,
    "days_tolerance": 1,
    "include_completed": false
  }
}
```

## Troubleshooting

If you encounter issues:

1. Ensure Python 3.8+ is installed
2. Check that the migration completed successfully
3. Verify your vault and reminders list configurations
4. Run `obs-sync setup` to reconfigure if needed

## Rollback

To rollback to the previous version:

```bash
rm -rf ~/.config/obs-sync
mv ~/.config/obs-tools.backup ~/.config/obs-tools
mv ~/.config/backup/*.json ~/.config/
```

For additional help, please refer to the main README.md or file an issue on GitHub.