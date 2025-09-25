#!/usr/bin/env python3
"""
Clean Slate Migration Script: Strip Block IDs from Obsidian Vault

This script removes ALL block IDs from task lines in markdown files to prepare
for a fresh sync with the new deterministic UUID system.

It identifies both old and new block ID formats:
- Old format: ^t-{12 hex chars} (e.g., ^t-6bad3d72ba60)
- New format: ^{8 alphanum} (e.g., ^dktfvwg2)
"""

import os
import re
import argparse
from typing import List, Tuple
import logging

# Block ID patterns
OLD_BLOCK_ID_PATTERN = r'\s*\^t-[a-f0-9]{12}\s*$'
NEW_BLOCK_ID_PATTERN = r'\s*\^[a-zA-Z0-9]{8}\s*$'
ALL_BLOCK_ID_PATTERN = r'\s*\^[a-zA-Z0-9-]{8,}\s*$'

# Task line pattern
TASK_PATTERN = r'^(\s*)[-*]\s+\[([xX ])\]\s+(.*)$'

def strip_block_ids_from_line(line: str, dry_run: bool = True) -> Tuple[str, bool]:
    """
    Strip block IDs from a task line.

    Returns:
        (cleaned_line, was_modified)
    """
    original_line = line

    # Remove old format block IDs: ^t-{12 hex}
    line = re.sub(OLD_BLOCK_ID_PATTERN, '', line)

    # Remove new format block IDs: ^{8 alphanum}
    line = re.sub(NEW_BLOCK_ID_PATTERN, '', line)

    # Clean up any trailing whitespace
    line = line.rstrip() + '\n' if original_line.endswith('\n') else line.rstrip()

    was_modified = line != original_line

    if was_modified and not dry_run:
        print(f"  STRIPPED: '{original_line.strip()}' -> '{line.strip()}'")
    elif was_modified and dry_run:
        print(f"  WOULD STRIP: '{original_line.strip()}' -> '{line.strip()}'")

    return line, was_modified

def process_file(file_path: str, dry_run: bool = True) -> Tuple[int, int]:
    """
    Process a single markdown file to strip block IDs.

    Returns:
        (total_tasks, modified_tasks)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        modified_lines = []
        total_tasks = 0
        modified_tasks = 0

        for line_num, line in enumerate(lines, 1):
            # Check if this is a task line
            if re.match(TASK_PATTERN, line):
                total_tasks += 1

                # Strip block IDs from task line
                cleaned_line, was_modified = strip_block_ids_from_line(line, dry_run)

                if was_modified:
                    modified_tasks += 1
                    if not dry_run:
                        print(f"    Line {line_num}: Modified task")

                modified_lines.append(cleaned_line)
            else:
                modified_lines.append(line)

        # Write back if not dry run and modifications were made
        if not dry_run and modified_tasks > 0:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(modified_lines)
            print(f"  ✅ Updated {file_path}")

        return total_tasks, modified_tasks

    except Exception as e:
        print(f"  ❌ Error processing {file_path}: {e}")
        return 0, 0

def find_markdown_files(vault_path: str) -> List[str]:
    """Find all markdown files in the vault."""
    md_files = []

    for root, dirs, files in os.walk(vault_path):
        for file in files:
            if file.endswith('.md'):
                md_files.append(os.path.join(root, file))

    return sorted(md_files)

def main():
    parser = argparse.ArgumentParser(description='Strip block IDs from Obsidian vault tasks')
    parser.add_argument('vault_path', help='Path to Obsidian vault')
    parser.add_argument('--apply', action='store_true', help='Apply changes (default is dry-run)')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()

    if not os.path.exists(args.vault_path):
        print(f"❌ Vault path does not exist: {args.vault_path}")
        return 1

    dry_run = not args.apply

    print(f"🧹 {'DRY RUN - ' if dry_run else ''}Stripping Block IDs from Vault")
    print(f"📁 Vault: {args.vault_path}")
    print(f"🔄 Mode: {'DRY RUN' if dry_run else 'APPLY CHANGES'}")
    print("=" * 60)

    # Find all markdown files
    md_files = find_markdown_files(args.vault_path)
    print(f"📄 Found {len(md_files)} markdown files")

    total_files_with_tasks = 0
    total_tasks = 0
    total_modified_tasks = 0
    modified_files = 0

    for file_path in md_files:
        rel_path = os.path.relpath(file_path, args.vault_path)

        if args.verbose:
            print(f"\n📝 Processing: {rel_path}")

        file_tasks, file_modified = process_file(file_path, dry_run)

        if file_tasks > 0:
            total_files_with_tasks += 1
            total_tasks += file_tasks
            total_modified_tasks += file_modified

            if file_modified > 0:
                modified_files += 1
                if not args.verbose:
                    print(f"📝 {rel_path}: {file_modified}/{file_tasks} tasks modified")

    print("\n" + "=" * 60)
    print(f"📊 SUMMARY:")
    print(f"  Files processed: {len(md_files)}")
    print(f"  Files with tasks: {total_files_with_tasks}")
    print(f"  Files {'modified' if not dry_run else 'to modify'}: {modified_files}")
    print(f"  Total tasks found: {total_tasks}")
    print(f"  Tasks {'stripped' if not dry_run else 'to strip'}: {total_modified_tasks}")

    if dry_run:
        print(f"\n⚠️  This was a DRY RUN. Use --apply to make changes.")
        if total_modified_tasks > 0:
            print(f"💡 Run with --apply to strip {total_modified_tasks} block IDs")
    else:
        print(f"\n✅ Block ID stripping complete!")
        if total_modified_tasks > 0:
            print(f"🎯 Successfully stripped {total_modified_tasks} block IDs")

    return 0

if __name__ == '__main__':
    exit(main())