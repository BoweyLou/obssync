"""
Migration command for moving configuration from legacy locations.
"""

import os
from pathlib import Path
from typing import Dict, List, Tuple
import shutil
import json

from ..core.paths import get_path_manager


class MigrateCommand:
    """Command for migrating configuration from legacy locations."""
    
    def __init__(self, verbose: bool = False):
        """
        Initialize migration command.
        
        Args:
            verbose: Enable verbose output
        """
        self.verbose = verbose
        self.path_manager = get_path_manager()
    
    def run(self, check_only: bool = False, force: bool = False) -> bool:
        """
        Run the migration process.
        
        Args:
            check_only: Only check for legacy files without migrating
            force: Force migration even if files exist in target location
        
        Returns:
            True if migration successful or no migration needed
        """
        print("obs-sync Configuration Migration")
        print("=" * 50)
        
        # Show current configuration
        self._show_current_config()
        
        # Check for legacy files
        has_legacy, legacy_files = self.path_manager.get_legacy_files()
        
        if not has_legacy:
            print("\n✅ No legacy configuration files found.")
            print("   Your configuration is already using the current structure.")
            return True
        
        # Show legacy files found
        print("\n📁 Legacy configuration files found:")
        for name, path in legacy_files.items():
            size = self._get_file_size(path)
            print(f"   • {name}: {path} ({size})")
        
        if check_only:
            print("\n💡 Run 'obs-sync migrate --apply' to migrate these files.")
            return True
        
        # Check for conflicts
        conflicts = self._check_conflicts(legacy_files)
        if conflicts and not force:
            print("\n⚠️  Conflicts detected - files already exist in target location:")
            for name, (source, target) in conflicts.items():
                print(f"   • {name}:")
                print(f"     Source: {source}")
                print(f"     Target: {target}")
            
            print("\n💡 Options:")
            print("   1. Backup and remove target files manually, then retry")
            print("   2. Use --force to overwrite target files")
            print("   3. Set OBS_SYNC_HOME to use a different location")
            return False
        
        # Confirm migration
        if not self._confirm_migration(legacy_files, conflicts, force):
            print("\n❌ Migration cancelled.")
            return False
        
        # Perform migration
        success = self._perform_migration(legacy_files, force)
        
        if success:
            print("\n✅ Migration completed successfully!")
            print(f"   Configuration is now in: {self.path_manager.working_dir}")
            
            # Offer to clean up legacy files
            if self._confirm_cleanup():
                self._cleanup_legacy_files(legacy_files)
                print("   Legacy files have been removed.")
            else:
                print("   Legacy files preserved for manual review.")
        else:
            print("\n❌ Migration failed. Please check the errors above.")
        
        return success
    
    def _show_current_config(self) -> None:
        """Display current path configuration."""
        print("\n📍 Current Configuration:")
        print(f"   Tool root:        {self.path_manager.tool_root}")
        print(f"   Working directory: {self.path_manager.working_dir}")
        print(f"   Legacy directory:  {self.path_manager.legacy_dir}")
        
        # Check environment variable
        env_home = os.environ.get("OBS_SYNC_HOME")
        if env_home:
            print(f"   OBS_SYNC_HOME:    {env_home} (active)")
        else:
            print(f"   OBS_SYNC_HOME:    (not set)")
        
        # Show if using legacy location
        if self.path_manager.working_dir == self.path_manager.legacy_dir:
            print("\n   ⚠️  Currently using legacy location")
            print("      Consider setting OBS_SYNC_HOME or ensuring tool directory is writable")
    
    def _get_file_size(self, path: Path) -> str:
        """Get human-readable file size."""
        try:
            size = path.stat().st_size
            for unit in ['B', 'KB', 'MB']:
                if size < 1024.0:
                    return f"{size:.1f} {unit}"
                size /= 1024.0
            return f"{size:.1f} GB"
        except Exception:
            return "unknown size"
    
    def _check_conflicts(self, legacy_files: Dict[str, Path]) -> Dict[str, Tuple[Path, Path]]:
        """Check for conflicts with existing files in target location."""
        conflicts = {}
        
        # Map legacy files to their target locations
        target_mappings = {
            'config': self.path_manager.config_path,
            'sync_links': self.path_manager.sync_links_path,
            'sync_links_data': self.path_manager.sync_links_path,
            'obsidian_index': self.path_manager.obsidian_index_path,
            'reminders_index': self.path_manager.reminders_index_path,
        }
        
        for name, source_path in legacy_files.items():
            if name in target_mappings:
                target_path = target_mappings[name]
                if target_path.exists():
                    conflicts[name] = (source_path, target_path)
        
        return conflicts
    
    def _confirm_migration(self, legacy_files: Dict[str, Path],
                          conflicts: Dict, force: bool) -> bool:
        """Confirm migration with user."""
        print("\n📋 Migration Plan:")
        print(f"   From: {self.path_manager.legacy_dir}")
        print(f"   To:   {self.path_manager.working_dir}")
        print(f"   Files to migrate: {len(legacy_files)}")
        
        if conflicts:
            if force:
                print(f"   ⚠️  Will overwrite {len(conflicts)} existing file(s)")
            else:
                print(f"   ⚠️  Conflicts detected: {len(conflicts)} file(s)")
        
        print("\n❓ Proceed with migration? (y/n): ", end="")
        response = input().strip().lower()
        return response == 'y'
    
    def _confirm_cleanup(self) -> bool:
        """Ask user if they want to remove legacy files."""
        print("\n❓ Remove legacy files after successful migration? (y/n): ", end="")
        response = input().strip().lower()
        return response == 'y'
    
    def _perform_migration(self, legacy_files: Dict[str, Path], force: bool) -> bool:
        """Perform the actual migration."""
        # Ensure target directories exist
        self.path_manager.ensure_directories()
        
        # Map legacy files to their target locations
        target_mappings = {
            'config': self.path_manager.config_path,
            'sync_links': self.path_manager.sync_links_path,
            'sync_links_data': self.path_manager.sync_links_path,
            'obsidian_index': self.path_manager.obsidian_index_path,
            'reminders_index': self.path_manager.reminders_index_path,
        }
        
        success_count = 0
        error_count = 0
        
        print("\n🚀 Migrating files...")
        
        for name, source_path in legacy_files.items():
            if name not in target_mappings:
                if self.verbose:
                    print(f"   ⚠️  Skipping unknown file type: {name}")
                continue
            
            target_path = target_mappings[name]
            
            # Skip if target exists and not forcing
            if target_path.exists() and not force:
                print(f"   ⏭️  Skipping {name} (target exists)")
                continue
            
            try:
                # Create target directory if needed
                target_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Handle special case: merging sync_links files
                if name in ('sync_links', 'sync_links_data') and target_path.exists():
                    self._merge_sync_links(source_path, target_path)
                    print(f"   ✅ Merged {name}")
                else:
                    # Copy the file
                    shutil.copy2(source_path, target_path)
                    print(f"   ✅ Migrated {name}")
                
                success_count += 1
                
            except Exception as e:
                print(f"   ❌ Failed to migrate {name}: {e}")
                error_count += 1
                if self.verbose:
                    import traceback
                    traceback.print_exc()
        
        # Create migration marker
        if success_count > 0:
            marker_path = self.path_manager.working_dir / ".migrated_from_legacy"
            try:
                import datetime
                marker_path.write_text(
                    f"Migrated from {self.path_manager.legacy_dir}\n"
                    f"Date: {datetime.datetime.now().isoformat()}\n"
                    f"Files migrated: {success_count}\n"
                )
            except Exception:
                pass
        
        print(f"\n📊 Migration summary:")
        print(f"   Successfully migrated: {success_count} file(s)")
        if error_count > 0:
            print(f"   Failed: {error_count} file(s)")
        
        return error_count == 0
    
    def _merge_sync_links(self, source_path: Path, target_path: Path) -> None:
        """Merge sync_links.json files, preserving unique links."""
        try:
            # Load source links
            with open(source_path, 'r') as f:
                source_data = json.load(f)
            source_links = source_data.get('links', [])
            
            # Load target links
            with open(target_path, 'r') as f:
                target_data = json.load(f)
            target_links = target_data.get('links', [])
            
            # Create a set of existing link keys in target
            existing_keys = set()
            for link in target_links:
                key = f"{link.get('obs_uuid')}:{link.get('rem_uuid')}"
                existing_keys.add(key)
            
            # Add unique links from source
            merged_count = 0
            for link in source_links:
                key = f"{link.get('obs_uuid')}:{link.get('rem_uuid')}"
                if key not in existing_keys:
                    target_links.append(link)
                    merged_count += 1
            
            # Save merged data
            with open(target_path, 'w') as f:
                json.dump({'links': target_links}, f, indent=2)
            
            if self.verbose:
                print(f"      Merged {merged_count} unique links")
                
        except Exception as e:
            # Fall back to simple copy
            if self.verbose:
                print(f"      Could not merge, copying instead: {e}")
            shutil.copy2(source_path, target_path)
    
    def _cleanup_legacy_files(self, legacy_files: Dict[str, Path]) -> None:
        """Remove legacy files after successful migration."""
        print("\n🧹 Cleaning up legacy files...")
        
        for name, path in legacy_files.items():
            try:
                # Create backup with .pre-migration suffix
                backup_path = path.with_suffix(path.suffix + '.pre-migration')
                shutil.copy2(path, backup_path)
                
                # Remove original
                path.unlink()
                
                if self.verbose:
                    print(f"   ✅ Removed {path}")
                    print(f"      Backup saved as {backup_path.name}")
            except Exception as e:
                print(f"   ⚠️  Could not remove {path}: {e}")
        
        # Try to remove empty legacy directories
        for directory in [self.path_manager.legacy_dir / "data", self.path_manager.legacy_dir]:
            if directory.exists():
                try:
                    # Only remove if empty
                    if not any(directory.iterdir()):
                        directory.rmdir()
                        if self.verbose:
                            print(f"   ✅ Removed empty directory: {directory}")
                except Exception:
                    pass