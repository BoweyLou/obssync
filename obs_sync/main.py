#!/usr/bin/env python3
"""
obs-sync - Simplified Obsidian ↔ Apple Reminders task synchronization.

This is the new streamlined entry point that replaces the complex obs_tools.py.
"""

import argparse
import logging
import sys
from pathlib import Path

from obs_sync.core import SyncConfig
from obs_sync.utils.macos import set_process_name
from obs_sync.core.config import load_config, save_config, get_default_config_path
from obs_sync.commands import (
    SetupCommand,
    SyncCommand,
    CalendarCommand,
    InstallDepsCommand,
    MigrateCommand,
    UpdateCommand,
    InsightsCommand
)


def main(argv=None):
    """Main entry point for obs-sync."""
    set_process_name("obs-sync")

    parser = argparse.ArgumentParser(
        description="Bidirectional task sync between Obsidian and Apple Reminders",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  obs-sync setup                 # Interactive setup
  obs-sync install-deps          # Install optional dependencies
  obs-sync sync                   # Run sync (dry-run by default)
  obs-sync sync --apply           # Apply sync changes
  obs-sync calendar               # Sync calendar events to daily note
  obs-sync update                 # Update to latest version
        """
    )
    
    # Use PathManager-derived default path for help text
    default_config = get_default_config_path()
    
    parser.add_argument(
        '--config',
        help=f'Path to configuration file (default: {default_config})',
        default=None  # Remove hardcoded default so PathManager fallback works
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Setup command
    setup_parser = subparsers.add_parser('setup', help='Interactive setup')
    setup_parser.add_argument(
        '--reconfigure',
        action='store_true',
        help='Reconfigure settings (choose between full reset or amending existing mappings)'
    )
    setup_parser.add_argument(
        '--add',
        action='store_true',
        help='Add vaults or Reminders lists without re-running full setup (deprecated; use --reconfigure)'
    )
    
    # Install dependencies command
    deps_parser = subparsers.add_parser('install-deps', help='Install optional dependencies')
    deps_parser.add_argument(
        '--group',
        choices=['macos', 'optimization', 'validation', 'dev', 'all'],
        help='Specific dependency group to install'
    )
    deps_parser.add_argument(
        '--auto',
        action='store_true',
        help='Automatically install platform-appropriate dependencies'
    )
    deps_parser.add_argument(
        '--list',
        action='store_true',
        help='List available dependency groups'
    )
    
    # Sync command
    sync_parser = subparsers.add_parser('sync', help='Sync tasks')
    sync_parser.add_argument(
        '--apply',
        action='store_true',
        help='Apply changes (default is dry-run)'
    )
    sync_parser.add_argument(
        '--direction',
        choices=['both', 'obs-to-rem', 'rem-to-obs'],
        default='both',
        help='Sync direction'
    )
    sync_parser.add_argument(
        '--no-dedup',
        action='store_true',
        help='Disable task deduplication for this run'
    )
    sync_parser.add_argument(
        '--dedup-auto-apply',
        action='store_true',
        help='Automatically apply deduplication without prompting'
    )
    
    # Calendar command
    calendar_parser = subparsers.add_parser('calendar', help='Sync calendar to daily notes')
    calendar_parser.add_argument(
        '--date',
        help='Date to sync (YYYY-MM-DD, default: today)'
    )
    calendar_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )
    
    # Insights command
    insights_parser = subparsers.add_parser('insights', help='Analyze task hygiene and show recommendations')
    insights_parser.add_argument(
        '--export',
        metavar='PATH',
        help='Export hygiene report to JSON file'
    )
    
    # Update command
    update_parser = subparsers.add_parser('update', help='Update obs-sync to latest version')
    update_parser.add_argument(
        '--extras',
        help='Extras to install (e.g., "macos,optimization"). Default: "macos" on macOS'
    )
    update_parser.add_argument(
        '--channel',
        choices=['stable', 'beta'],
        help='Update channel to track (stable=main branch, beta=beta branch). Persists in config.'
    )
    
    # Migrate command
    migrate_parser = subparsers.add_parser(
        'migrate',
        help='Migrate configuration from legacy locations'
    )
    migrate_parser.add_argument(
        '--check',
        action='store_true',
        help='Check for legacy files without migrating'
    )
    migrate_parser.add_argument(
        '--apply',
        action='store_true',
        help='Perform the migration'
    )
    migrate_parser.add_argument(
        '--force',
        action='store_true',
        help='Force migration even if target files exist'
    )
    
    args = parser.parse_args(argv)
    
    # Configure logging if verbose mode is enabled
    if args.verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    # Show help if no command specified
    if not args.command:
        parser.print_help()
        return 1
    
    # Load configuration
    config = load_config(args.config)
    
    # Show resolved config path when verbose
    if args.verbose:
        actual_config_path = args.config if args.config else get_default_config_path()
        print(f"Using config: {actual_config_path}")
    
    # Execute command
    try:
        if args.command == 'setup':
            cmd = SetupCommand(config, verbose=args.verbose)
            success = cmd.run(reconfigure=args.reconfigure, add=getattr(args, 'add', False))
            if success:
                save_config(config, args.config)
            
        elif args.command == 'install-deps':
            cmd = InstallDepsCommand(verbose=args.verbose)
            success = cmd.run(
                group=args.group,
                auto=args.auto,
                list_groups=args.list
            )
            
        elif args.command == 'sync':
            # Apply CLI deduplication overrides to config
            if hasattr(args, 'no_dedup') and args.no_dedup:
                config.enable_deduplication = False
            if hasattr(args, 'dedup_auto_apply') and args.dedup_auto_apply:
                config.dedup_auto_apply = True
                
            cmd = SyncCommand(config, verbose=args.verbose)
            success = cmd.run(apply_changes=args.apply, direction=args.direction)
            
        elif args.command == 'calendar':
            cmd = CalendarCommand(config, verbose=args.verbose)
            success = cmd.run(date_str=args.date, dry_run=args.dry_run)
            
        elif args.command == 'insights':
            cmd = InsightsCommand(config, verbose=args.verbose)
            success = cmd.run(export_json=args.export)
            
        elif args.command == 'update':
            cmd = UpdateCommand(config, verbose=args.verbose)
            success = cmd.run(extras=args.extras, channel=args.channel)
            if success:
                save_config(config, args.config)
            
        elif args.command == 'migrate':
            # Migrate command doesn't need config
            cmd = MigrateCommand(verbose=args.verbose)
            if args.check:
                success = cmd.run(check_only=True)
            elif args.apply or args.force:
                success = cmd.run(check_only=False, force=args.force)
            else:
                # Default to check mode if no flags specified
                success = cmd.run(check_only=True)
                if success:
                    print("\n💡 Run 'obs-sync migrate --apply' to perform the migration.")
            
        else:
            print(f"Unknown command '{args.command}'.")
            return 1
        
        return 0 if success else 1
        
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        return 130
    except Exception as e:
        print(f"Error: {e}")
        if not args.verbose:
            print("Re-run with --verbose for more detail.")
        else:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())