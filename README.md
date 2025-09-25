# obs-sync

Bidirectional task synchronization between Obsidian and Apple Reminders.

## Quick Start

### Installation

To make the `obs-sync` command available system-wide, choose one of these options:

#### Option 1: Add to PATH (Recommended)
Add this to your `~/.zshrc` or `~/.bash_profile`:
```bash
export PATH="$PATH:$(pwd)/bin"
```
Then reload your shell:
```bash
source ~/.zshrc  # or ~/.bash_profile
```

#### Option 2: Create Symlink
```bash
ln -s $(pwd)/bin/obs-sync /usr/local/bin/obs-sync
```

#### Option 3: Use Direct Path
Use `./bin/obs-sync` from the project directory:
```bash
./bin/obs-sync install-deps --list
```

### First Time Setup

> **Heads up**: running any `obs-sync` command automatically provisions a dedicated
> virtual environment in `~/Library/Application Support/obs-tools/venv` (macOS)
> or the platform equivalent. No manual `pip` juggling required.

1. Install dependencies (macOS):
```bash
obs-sync install-deps macos
# or auto-install platform dependencies:
obs-sync install-deps --auto
```

2. Configure vaults and reminders:
```bash
obs-sync setup
```
Add more vaults or Reminders lists later without redoing everything:
```bash
obs-sync setup --add
```

3. Run your first sync:
```bash
obs-sync sync         # Preview changes (dry-run)
obs-sync sync --apply # Apply changes
```

## Commands

- `obs-sync setup` - Interactive configuration (`--add` to append, `--reconfigure` to restart)
- `obs-sync install-deps` - Install optional dependencies
- `obs-sync sync` - Synchronize tasks
- `obs-sync calendar` - Sync calendar events to daily notes

## Dependency Management

The system will automatically detect missing dependencies during setup and offer to install them. You can also manually manage dependencies:

```bash
# List available dependency groups
obs-sync install-deps --list

# Install specific group
obs-sync install-deps --group macos

# Auto-install platform dependencies
obs-sync install-deps --auto
```

## Troubleshooting

### "command not found: obs-sync"
The command isn't in your PATH. See Installation section above.

### "EventKit not available"
Install macOS dependencies:
```bash
obs-sync install-deps macos
```

### "externally-managed-environment" error
Your Python is managed by Homebrew. Options:
1. Use `pipx install obs-sync[macos]` for isolated installation
2. Create a virtual environment
3. Use `pip install --user obs-sync[macos]`