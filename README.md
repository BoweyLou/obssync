# obs-sync

> **bidirectional task synchronisation between Obsidian and Apple Reminders**

Keep your Obsidian task lists in perfect sync with Apple Reminders. Work in your favourite markdown editor, access your tasks from any Apple device, and never worry about manual updates again.

[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux-blue)]()
[![Python](https://img.shields.io/badge/python-3.8%2B-blue)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()

---

> [!WARNING]
> **⚠️ Experimental Software - Use at Your Own Risk**
>
> This project is in active development and should be considered **experimental**. While it includes safety features like dry-run mode and comprehensive logging, you should:
> - **Backup your Obsidian vaults** before first sync
> - **Test with non-critical data** initially
> - **Review dry-run output carefully** before applying changes
>
> This tool was developed with assistance from [Claude Code](https://claude.ai/code), Anthropic's AI-powered development assistant.

---

## Table of Contents

- [Why obs-sync?](#why-obs-sync)
- [Key Features](#key-features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage Guide](#usage-guide)
- [Advanced Features](#advanced-features)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Architecture](#architecture)
- [Contributing](#contributing)
- [License](#license)

---

## Why obs-sync?

**The Problem**: You love Obsidian for note-taking and task management, but you also want your tasks accessible across all your Apple devices through Reminders. Manually keeping them in sync is tedious and error-prone.

**The Solution**: obs-sync provides **intelligent, bidirectional synchronisation** that:
- ✅ Automatically syncs tasks between Obsidian markdown files and Apple Reminders
- ✅ Preserves task metadata (due dates, completion status, priority, tags)
- ✅ Handles conflicts intelligently (most recent change wins)
- ✅ Supports multiple Obsidian vaults with separate Reminders lists
- ✅ Enables tag-based routing (e.g., `#work` tasks → Work calendar)
- ✅ Detects and removes duplicates automatically
- ✅ Safe dry-run mode to preview all changes before applying

**Perfect for**:
- 📝 Knowledge workers who live in Obsidian but need mobile task access
- 🎯 GTD practitioners managing tasks across contexts
- 👥 Teams using Obsidian for project management with Apple device integration
- 🔄 Anyone who wants seamless cross-platform task management

---

## Key Features

### 🔄 Bidirectional Sync
- Changes in Obsidian → Reflected in Apple Reminders
- Changes in Apple Reminders → Reflected in Obsidian
- Conflict resolution based on modification timestamps
- Safe preview mode (dry-run) before applying changes

### 🏷️ Tag-Based Routing
Route tasks to specific Reminders lists based on Obsidian tags:
```markdown
- [ ] Review quarterly goals #work
- [ ] Buy groceries #personal
- [ ] Research paper outline #research
```
Each tag can automatically route to its designated Reminders list.

### 🎯 Multi-Vault Support
Manage multiple Obsidian vaults, each syncing to different Reminders lists:
- Work vault → Work Reminders
- Personal vault → Personal Reminders
- Research vault → Research Reminders

### 🧹 Intelligent Deduplication
Automatically detects and resolves duplicate tasks:
- Interactive mode lets you choose which duplicates to keep
- Batch cleanup of accidental duplicates
- Preserves links to prevent orphaned tasks

### 📅 Calendar Integration
Sync calendar events to Obsidian daily notes:
```bash
obs-sync calendar
```
Creates timestamped entries in your daily note for today's meetings and events.

### 🔍 Task Metadata Preservation
Syncs all task properties:
- ✅ Completion status (`[ ]` / `[x]`)
- 📅 Due dates
- ⚡ Priority levels (high/medium/low)
- 🏷️ Tags
- 📝 Notes/descriptions
- 🕒 Created/modified timestamps

### 🛡️ Safe & Reliable
- **Dry-run by default**: Preview changes before applying
- **UUID-based tracking**: Stable task identity across syncs
- **Conflict detection**: Warns about simultaneous edits
- **Orphan cleanup**: Removes stale sync links automatically
- **Comprehensive logging**: Audit trail of all sync operations

---

## Installation

### Prerequisites

- **macOS**: 10.15+ (for Apple Reminders integration)
- **Python**: 3.8 or higher
- **Obsidian**: Any recent version

### One-Command Install (Recommended)

```bash
# Clone the repository
git clone https://github.com/BoweyLou/obssync.git
cd obssync

# Install with macOS dependencies
./install.sh --extras macos

# Reload your shell
source ~/.zshrc  # or ~/.bash_profile for bash
```

**What this does:**
- ✅ Creates managed virtual environment at `~/Library/Application Support/obs-tools/venv`
- ✅ Installs core dependencies + macOS extras (pyobjc, EventKit)
- ✅ Symlinks `obs-sync` to `~/.local/bin` (accessible from anywhere)
- ✅ Updates shell profile to include `~/.local/bin` on PATH

### Installation Options

**For development work:**
```bash
./install.sh --extras macos,dev
```
Includes pytest, black, mypy for testing and linting.

**For advanced matching algorithms:**
```bash
./install.sh --extras macos,optimisation
```
Includes scipy and munkres for Hungarian algorithm matching.

**Available extras:**
- `macos` - Apple EventKit/Reminders integration (required for macOS)
- `optimisation` - Scipy + munkres for advanced task matching
- `validation` - JSON schema validation for config files
- `dev` - Development tools (pytest, black, mypy)

### Verify Installation

```bash
obs-sync --help
```

You should see the command help menu. You're ready to go! 🎉

### Updating obs-sync

**Quick update (recommended):**

```bash
obs-sync update
```

This command automatically:
- ✅ Checks for available updates
- ✅ Pulls latest changes from git
- ✅ Reinstalls dependencies
- ✅ Prompts to refresh LaunchAgent if automation is enabled

**Manual update:**

If you prefer manual control:

```bash
# Navigate to the repo directory
cd /path/to/obssync

# Pull latest changes
git pull

# Reinstall dependencies if new extras were added
./install.sh --extras macos
```

**Important for LaunchAgent automation users:**

If you have automation enabled and the update includes LaunchAgent changes, refresh your agent:

```bash
# After updating, reconfigure automation to pick up new plist format
obs-sync setup --reconfigure
# Select option 8 (Automation settings)
# Choose 'n' to disable, then 'y' to re-enable with new settings
```

**What happens during update:**
- ✅ **Code changes** - Immediately active (editable install)
- ✅ **New dependencies** - Installed via `./install.sh`
- ✅ **Config schema changes** - Backward compatible, defaults applied
- ⚠️ **LaunchAgent changes** - Require manual refresh (see above)

**Update options:**

```bash
# Update with default extras (macos on macOS)
obs-sync update

# Update with specific extras
obs-sync update --extras macos,optimization

# Check current version
cd /path/to/obssync && git log -1 --oneline
```

---

## Quick Start

### 1. Initial Setup

Run the interactive setup wizard:

```bash
obs-sync setup
```

This will:
1. **Discover Obsidian vaults** on your system
2. **List available Reminders lists** from your Apple Reminders
3. **Map vaults to Reminders lists** (which vault syncs where)
4. **Configure tag-based routing** (optional but powerful!)

Example setup flow:
```
📚 Discovered vaults:
  1. Work Notes (/Users/you/Documents/Work)
  2. Personal (/Users/you/Documents/Personal)

📋 Available Reminders lists:
  1. Work
  2. Personal
  3. Shopping

Map Work Notes → Work
Map Personal → Personal

Configure tag routing for Work Notes?
  #urgent → Work (already mapped)
  #client → Work
  #admin → Work
```

### 2. First Sync (Dry Run)

Preview what would change:

```bash
obs-sync sync
```

Example output:
```
🔍 Syncing vault: Work Notes
📊 Summary:
  Obsidian: 45 tasks found
  Reminders: 38 tasks found
  Matched pairs: 35

📋 Planned changes:
  ✅ Obsidian → Reminders: 8 creates, 2 updates
  ✅ Reminders → Obsidian: 3 creates, 1 update
  🗑️  Deletions: 0

🔗 Tag routing:
  #client tasks → Work (5 tasks)
  #admin tasks → Work (2 tasks)

💡 Run with --apply to execute these changes
```

### 3. Apply Changes

Once you're happy with the preview:

```bash
obs-sync sync --apply
```

Tasks are now synchronised! ✨

### 4. Ongoing Sync

Just run the sync command whenever you want to synchronise:

```bash
obs-sync sync --apply
```

**Pro tip**: On macOS, enable built-in automation via `obs-sync setup --reconfigure` (option 8) to schedule automatic syncing.

---

## Usage Guide

### Basic Commands

#### Setup & Configuration

```bash
# Initial setup (interactive wizard)
obs-sync setup

# Add more vaults or Reminders lists
obs-sync setup --add

# Reconfigure existing settings
obs-sync setup --reconfigure
```

#### Sync Operations

```bash
# Preview changes (safe, read-only)
obs-sync sync

# Apply changes (bidirectional sync)
obs-sync sync --apply

# Sync specific vault
obs-sync sync --vault "Work Notes" --apply

# Verbose output for debugging
obs-sync sync --apply --verbose
```

#### Calendar Integration

```bash
# Sync today's calendar events to daily note
obs-sync calendar

# Specify date
obs-sync calendar --date 2024-10-15
```

### Task Format in Obsidian

obs-sync recognises standard Obsidian task syntax:

```markdown
## My Tasks

- [ ] Basic task
- [x] Completed task
- [ ] Task with due date 📅 2024-10-15
- [ ] High priority task ⏫
- [ ] Task with tags #work #urgent
- [ ] Task with note
  Additional details go here in the indented block.
```

**Supported metadata:**
- `[ ]` / `[x]` - Completion status
- `📅 YYYY-MM-DD` - Due date
- `⏫` / `🔼` / `🔽` - Priority (high/medium/low)
- `#tag` - Tags (also used for routing)

---

## Advanced Features

### Tag-Based Task Routing

Route tasks to specific Reminders lists based on tags:

**Setup routing:**
```bash
obs-sync setup --reconfigure
# Choose "Amend existing configuration"
# Select "Configure tag routes"
```

**Example configuration:**
- Tasks with `#work` → Work Reminders list
- Tasks with `#personal` → Personal Reminders list
- Tasks with `#urgent` → Priority Reminders list

**In practice:**
```markdown
- [ ] Prepare presentation #work         → Work list
- [ ] Buy birthday gift #personal        → Personal list
- [ ] Review contract ASAP #work #urgent → Work list (first match wins)
```

### Multi-Vault Workflows

Manage different projects in separate vaults:

```bash
# Setup multiple vaults
obs-sync setup --add

# Sync specific vault
obs-sync sync --vault "Project A" --apply

# Sync all vaults
obs-sync sync --apply
```

Each vault maintains independent configuration and sync state.

### Deduplication

Remove duplicate tasks across Obsidian and Reminders:

```bash
# Preview duplicates
obs-sync sync

# Interactive deduplication (prompts for each cluster)
obs-sync sync --apply
# When duplicates detected, you'll be prompted to choose which to keep
```

**Duplicate detection criteria:**
- Same description (fuzzy matching with 75% similarity threshold)
- Same or similar due dates (within 1 day tolerance)
- Detects both Obsidian-Obsidian and Reminders-Reminders duplicates

### Automated Sync (macOS)

Schedule obs-sync to run automatically using macOS LaunchAgents:

```bash
# Configure automation (interactive)
obs-sync setup --reconfigure
# Choose "Amend existing configuration"
# Select "Automation settings (macOS LaunchAgent)"
```

**Available schedules:**
- **Hourly** (every 3600 seconds) - Default, recommended
- **Twice daily** (every 43200 seconds / 12 hours)
- **Custom interval** - Specify any interval in seconds (60-604800)

**What happens:**
- LaunchAgent runs `obs-sync sync --apply` on schedule
- Logs written to `~/Library/Application Support/obs-tools/logs/`
  - `obs-sync-agent.stdout.log` - Sync output
  - `obs-sync-agent.stderr.log` - Error messages
- Calendar imports (if enabled) run once daily during sync

**Managing automation:**
```bash
# Enable/disable or change schedule
obs-sync setup --reconfigure
# Select option 8 (Automation settings)

# Check LaunchAgent status
launchctl list | grep obs-sync

# View recent logs
tail -f ~/Library/Application\ Support/obs-tools/logs/obs-sync-agent.stdout.log
```

**Important notes:**
- macOS only - gracefully skipped on other platforms
- Automation disabled by default - opt-in through setup
- Agent plist located at `~/Library/LaunchAgents/com.obs-sync.sync-agent.plist`
- Disabling automation unloads agent and removes plist

### Custom Configuration

Configuration stored in `~/.config/obs-sync/config.json` (or custom location):

```json
{
  "vaults": [...],
  "reminders_lists": [...],
  "vault_mappings": {...},
  "tag_routes": {...},
  "min_score": 0.75,
  "days_tolerance": 1,
  "include_completed": true
}
```

**Key settings:**
- `min_score` - Similarity threshold for matching (0.0-1.0)
- `days_tolerance` - Date matching tolerance in days
- `include_completed` - Whether to sync completed tasks

### Advanced Matching

With the `optimisation` extra installed, obs-sync uses the Hungarian algorithm for optimal task matching:

```bash
./install.sh --extras macos,optimisation
```

Benefits:
- Better matching for similar tasks
- Reduced false duplicates
- Optimal global assignment vs greedy matching

---

## Configuration

### Environment Variables

- `OBS_TOOLS_HOME` - Custom location for managed virtual environment
  ```bash
  export OBS_TOOLS_HOME=~/my-custom-location
  ```

- `OBS_SYNC_HOME` - Custom location for config/data files
  ```bash
  export OBS_SYNC_HOME=~/.my-sync-config
  ```

### Managed Virtual Environment

Location:
- **macOS**: `~/Library/Application Support/obs-tools/venv`
- **Linux**: `~/.local/share/obs-tools/venv`
- **Windows**: `~/AppData/Local/obs-tools/venv`

### Configuration Files

- `config.json` - Main configuration (vaults, mappings, automation settings)
- `sync_links.json` - UUID mappings between Obsidian and Reminders tasks
- `obsidian_tasks_index.json` - Cached Obsidian task index
- `reminders_tasks_index.json` - Cached Reminders task index

### LaunchAgent Files (macOS)

- `~/Library/LaunchAgents/com.obs-sync.sync-agent.plist` - Automation schedule
- `~/Library/Application Support/obs-tools/logs/obs-sync-agent.stdout.log` - Automation output
- `~/Library/Application Support/obs-tools/logs/obs-sync-agent.stderr.log` - Automation errors

### Logs

Logs are stored in:
- **macOS**: `~/Library/Application Support/obs-tools/logs/`
- **Linux**: `~/.local/share/obs-tools/logs/`

---

## Troubleshooting

### "command not found: obs-sync"

**Solution:**
```bash
# Reload your shell
source ~/.zshrc  # or ~/.bash_profile

# Verify ~/.local/bin is in PATH
echo $PATH | grep ".local/bin"

# Manually add if needed
export PATH="$HOME/.local/bin:$PATH"
```

### "EventKit not available"

**Solution:**
```bash
./install.sh --extras macos
```

**If still failing:**
- Go to **System Settings → Privacy & Security → Reminders**
- Enable access for **Terminal** or **iTerm2**
- Restart your terminal

### "Permission denied" when running install.sh

**Solution:**
```bash
# Make installer executable
chmod +x install.sh

# Or run with bash
bash install.sh --extras macos
```

### Sync shows unexpected deletions

**Likely causes:**
1. Tasks were manually deleted in Obsidian or Reminders
2. Tag routing changed (task moved to different list)
3. Vault path changed

**Solution:**
- Review dry-run output carefully: `obs-sync sync`
- Check orphaned task detection is working correctly
- Reconfigure if vault paths changed: `obs-sync setup --reconfigure`

### Tasks not syncing

**Debugging steps:**
```bash
# 1. Run with verbose output
obs-sync sync --verbose

# 2. Check logs
tail -f ~/Library/Application\ Support/obs-tools/logs/obs-sync.log

# 3. Verify task format
# Ensure tasks use proper markdown syntax: - [ ] Task description

# 4. Check configuration
cat ~/.config/obs-sync/config.json
```

### Installation fails

**Solution 1 - Clean reinstall:**
```bash
rm -rf ~/Library/Application\ Support/obs-tools/venv
./install.sh --extras macos
```

**Solution 2 - Custom location:**
```bash
export OBS_TOOLS_HOME=~/custom-sync-location
./install.sh --extras macos
```

### Automation not running (macOS)

**Check LaunchAgent status:**
```bash
# Check if agent is loaded
launchctl list | grep com.obs-sync.sync-agent

# Check recent logs
tail -50 ~/Library/Application\ Support/obs-tools/logs/obs-sync-agent.stdout.log
tail -50 ~/Library/Application\ Support/obs-tools/logs/obs-sync-agent.stderr.log
```

**Common issues:**

1. **Agent not loaded**: Re-enable via `obs-sync setup --reconfigure` → option 8
2. **Permission errors**: Ensure obs-sync executable is accessible
   ```bash
   which obs-sync  # Should return path like ~/.local/bin/obs-sync
   ```
3. **Path issues**: LaunchAgent may not have same PATH as your shell
   - Agent uses: `/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin`
   - Ensure obs-sync is in one of these directories or symlinked to ~/.local/bin

4. **Config/data permissions**: LaunchAgent runs under your user, check file permissions
   ```bash
   ls -la ~/.config/obs-sync/
   ls -la ~/Library/Application\ Support/obs-tools/
   ```

**Manual agent management:**
```bash
# Unload agent
launchctl unload ~/Library/LaunchAgents/com.obs-sync.sync-agent.plist

# Load agent
launchctl load ~/Library/LaunchAgents/com.obs-sync.sync-agent.plist

# Remove plist (disables automation)
rm ~/Library/LaunchAgents/com.obs-sync.sync-agent.plist
```

### Developer Scripts

Utility scripts for maintenance and debugging are in `scripts/`:
- `scripts/demos/` - Feature demonstrations
- `scripts/cleanup/` - Data cleanup utilities
- `scripts/testing/` - Test runners

See [`scripts/README.md`](scripts/README.md) for details.

---

## Architecture

### How It Works

1. **Task Discovery**
   - Scans Obsidian vault for markdown task syntax
   - Queries Apple Reminders via EventKit framework
   - Builds indexes with stable UUID identifiers

2. **Matching**
   - Links tasks using UUID-based sync links
   - Falls back to fuzzy matching for new tasks (description + due date similarity)
   - Uses Hungarian algorithm for optimal matching (with `optimisation` extra)

3. **Conflict Resolution**
   - Compares modification timestamps
   - Most recent change wins
   - Preserves all metadata during updates

4. **Sync Application**
   - Creates missing counterparts in Obsidian/Reminders
   - Updates changed tasks bidirectionally
   - Removes orphaned tasks (deleted on one side)
   - Persists sync links for future runs

### Key Components

- **obs_sync/sync/engine.py** - Core sync orchestration
- **obs_sync/sync/matcher.py** - Task matching algorithms
- **obs_sync/sync/resolver.py** - Conflict resolution
- **obs_sync/sync/deduplicator.py** - Duplicate detection
- **obs_sync/obsidian/tasks.py** - Obsidian task parser
- **obs_sync/reminders/gateway.py** - Apple Reminders integration

See [`docs/`](docs/) for detailed architecture documentation.

---

## Contributing

Contributions welcome! Here's how:

### Development Setup

```bash
# Clone and install with dev extras
git clone https://github.com/BoweyLou/obssync.git
cd obssync
./install.sh --extras macos,dev

# Run tests
pytest tests/

# Format code
black obs_sync/ tests/

# Type checking
mypy obs_sync/
```

### Running Tests

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_tag_routing.py

# Run with coverage
pytest --cov=obs_sync tests/
```

### Project Structure

```
obssync/
├── obs_sync/           # Main package
│   ├── commands/       # CLI commands
│   ├── core/          # Core models and config
│   ├── obsidian/      # Obsidian integration
│   ├── reminders/     # Apple Reminders integration
│   ├── sync/          # Sync engine
│   ├── calendar/      # Calendar integration
│   └── utils/         # Utilities
├── tests/             # Test suite (100 tests)
├── docs/              # Documentation
├── scripts/           # Utility scripts
└── bin/               # CLI wrappers
```

### Submitting Issues

Found a bug? Have a feature request?

1. Check [existing issues](https://github.com/BoweyLou/obssync/issues)
2. Create a new issue with:
   - Clear description
   - Steps to reproduce (for bugs)
   - Expected vs actual behaviour
   - System info (macOS version, Python version)

### Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Ensure tests pass (`pytest tests/`)
6. Commit with clear messages
7. Push to your fork
8. Open a Pull Request

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

## Acknowledgments

- Built with [pyobjc](https://pyobjc.readthedocs.io/) for macOS integration
- Uses [EventKit](https://developer.apple.com/documentation/eventkit) framework for Apple Reminders access
- Inspired by the Obsidian community's love for plain-text task management

---

## Support

- 📖 [Documentation](docs/)
- 🐛 [Issue Tracker](https://github.com/BoweyLou/obssync/issues)
- 💬 Discussions (coming soon)

---

**Made with ❤️ for the Obsidian community**
