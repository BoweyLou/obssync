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
from obs_sync.core.config import load_config, save_config
from obs_sync.commands import (
    SetupCommand,
    SyncCommand,
    CalendarCommand,
    InstallDepsCommand
)


def main(argv=None):
    """Main entry point for obs-sync."""
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
        """
    )
    
    parser.add_argument(
        '--config',
        help='Path to configuration file',
        default='~/.config/obs-sync/config.json'
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
        help='Reconfigure even if already set up'
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
    
    # Execute command
    try:
        if args.command == 'setup':
            cmd = SetupCommand(config, verbose=args.verbose)
            success = cmd.run(reconfigure=args.reconfigure)
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
            cmd = SyncCommand(config, verbose=args.verbose)
            success = cmd.run(apply_changes=args.apply, direction=args.direction)
            
        elif args.command == 'calendar':
            cmd = CalendarCommand(config, verbose=args.verbose)
            success = cmd.run(date_str=args.date, dry_run=args.dry_run)
            
        else:
            print(f"Unknown command: {args.command}")
            return 1
        
        return 0 if success else 1
        
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        return 130
    except Exception as e:
        print(f"Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())