"""
Centralized path management for obs-sync.

This module handles all directory resolution, migration, and provides
a consistent API for accessing configuration and data files.
"""

import os
import shutil
import sys
from pathlib import Path
from typing import Optional, Tuple
import logging


class PathManager:
    """Manages obs-sync file paths with migration and fallback support."""
    
    # Directory names
    WORKING_DIR_NAME = ".obs-sync"
    LEGACY_DIR_NAME = "obs-sync"
    
    # File names
    CONFIG_FILE = "config.json"
    SYNC_LINKS_FILE = "sync_links.json"
    OBSIDIAN_INDEX_FILE = "obsidian_tasks_index.json"
    REMINDERS_INDEX_FILE = "reminders_tasks_index.json"
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize path manager."""
        self.logger = logger or logging.getLogger(__name__)
        self._working_dir: Optional[Path] = None
        self._is_migrated = False
        
    @property
    def tool_root(self) -> Path:
        """Get the root directory of the obs-sync tool installation."""
        # Priority 1: Check if we're running from a repo checkout
        # Look for obs_tools.py (the bootstrap script) in the repo root
        repo_root = self._find_repo_root()
        if repo_root:
            return repo_root
        
        # Priority 2: Use the obs_sync package location
        # This will be site-packages for installed packages
        try:
            import obs_sync
            module_path = Path(obs_sync.__file__).parent
            return module_path.parent
        except Exception:
            # Fallback: use script location
            if hasattr(sys, 'argv') and sys.argv:
                script_path = Path(sys.argv[0]).resolve()
                # Go up until we find obs_sync directory
                current = script_path.parent
                while current != current.parent:
                    if (current / 'obs_sync').is_dir():
                        return current
                    current = current.parent
            
            # Last resort: current working directory
            return Path.cwd()
    
    def _find_repo_root(self) -> Optional[Path]:
        """Find the repository root by looking for obs_tools.py marker."""
        # Check PYTHONPATH entries for a repo checkout
        python_path = os.environ.get('PYTHONPATH', '')
        for path_entry in python_path.split(os.pathsep):
            if not path_entry:
                continue
            candidate = Path(path_entry).resolve()
            if (candidate / 'obs_tools.py').exists() and (candidate / 'obs_sync').is_dir():
                self.logger.debug(f"Found repo root via PYTHONPATH: {candidate}")
                return candidate
        
        # Check current working directory and parents
        current = Path.cwd()
        for _ in range(5):  # Check up to 5 levels up
            if (current / 'obs_tools.py').exists() and (current / 'obs_sync').is_dir():
                self.logger.debug(f"Found repo root via cwd: {current}")
                return current
            if current == current.parent:
                break
            current = current.parent
        
        # Check sys.argv[0] location
        if hasattr(sys, 'argv') and sys.argv:
            script_path = Path(sys.argv[0]).resolve()
            current = script_path.parent
            for _ in range(5):
                if (current / 'obs_tools.py').exists() and (current / 'obs_sync').is_dir():
                    self.logger.debug(f"Found repo root via argv: {current}")
                    return current
                if current == current.parent:
                    break
                current = current.parent
        
        return None
    
    @property
    def legacy_dir(self) -> Path:
        """Get the legacy configuration directory path."""
        return Path.home() / ".config" / self.LEGACY_DIR_NAME
    
    def _default_user_dir(self) -> Path:
        """Platform-appropriate per-user data directory."""
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / self.LEGACY_DIR_NAME
        if sys.platform.startswith("win"):
            appdata = os.environ.get("APPDATA")
            if appdata:
                return Path(appdata) / self.LEGACY_DIR_NAME
            return Path.home() / "AppData" / "Roaming" / self.LEGACY_DIR_NAME
        return Path.home() / ".config" / self.LEGACY_DIR_NAME

    def _path_is_cloud_synced(self, path: Path) -> bool:
        """Heuristically detect cloud-synced volumes (iCloud, Dropbox, etc.)."""
        try:
            resolved = path.resolve()
        except Exception:
            resolved = path

        cloud_markers = [
            "Library/Mobile Documents",  # iCloud Drive
            "Library/CloudStorage",
            "Dropbox",
            "OneDrive",
            "Google Drive",
            "iCloud Drive",
            "Box/Box",
        ]
        resolved_str = str(resolved)
        return any(marker in resolved_str for marker in cloud_markers)

    @property
    def working_dir(self) -> Path:
        """
        Get the working directory for obs-sync data.

        Priority order:
        1. OBS_SYNC_HOME environment variable (explicit override)
        2. .obs-sync/ in tool installation directory (if writable)
           - For repo checkouts: <repo>/.obs-sync
           - For installed packages: <site-packages-parent>/.obs-sync (usually not writable)
        3. ~/.config/obs-sync (legacy fallback for read-only installs)
        
        This ensures repo-local development uses repo-local storage,
        while read-only system installs fall back to user home directory.
        """
        if self._working_dir is not None:
            return self._working_dir
            
        # Check environment variable override
        env_override = os.environ.get("OBS_SYNC_HOME")
        if env_override:
            env_path = Path(env_override).expanduser().resolve()
            self.logger.debug(f"Using OBS_SYNC_HOME override: {env_path}")
            self._working_dir = env_path
            return self._working_dir

        # Try tool installation directory
        tool_dir = self.tool_root / self.WORKING_DIR_NAME
        is_cloud_path = self._path_is_cloud_synced(tool_dir)

        if not is_cloud_path and self._is_writable_location(tool_dir):
            self.logger.debug(f"Using writable tool directory: {tool_dir}")
            self._working_dir = tool_dir
        else:
            if is_cloud_path:
                fallback_dir = self._default_user_dir()
                self.logger.debug(f"Tool directory is cloud-synced; using user data directory: {fallback_dir}")
            else:
                fallback_dir = self.legacy_dir
                self.logger.debug(f"Tool directory not writable, using legacy: {fallback_dir}")
            self._working_dir = fallback_dir

        return self._working_dir
    
    def _is_writable_location(self, path: Path) -> bool:
        """Check if a location is writable."""
        # If directory exists, check if we can write to it
        if path.exists():
            try:
                test_file = path / ".write_test"
                test_file.touch()
                test_file.unlink()
                return True
            except (OSError, PermissionError):
                return False
        
        # If directory doesn't exist, check if we can create it
        parent = path.parent
        while not parent.exists() and parent != parent.parent:
            parent = parent.parent
        
        if parent.exists():
            try:
                # Try to create the directory
                path.mkdir(parents=True, exist_ok=True)
                return True
            except (OSError, PermissionError):
                return False
        
        return False
    
    def ensure_directories(self) -> None:
        """Ensure all required directories exist."""
        dirs_to_create = [
            self.working_dir,
            self.data_dir,
            self.backup_dir,
            self.log_dir,
            self.documents_dir,
            self.documents_inbox_dir,
            self.documents_archive_dir,
        ]
        
        for directory in dirs_to_create:
            directory.mkdir(parents=True, exist_ok=True)
            self.logger.debug(f"Ensured directory exists: {directory}")
    
    @property
    def data_dir(self) -> Path:
        """Get the data directory for indices and links."""
        return self.working_dir / "data"
    
    @property
    def backup_dir(self) -> Path:
        """Get the backup directory."""
        return self.working_dir / "backups"
    
    @property
    def log_dir(self) -> Path:
        """Get the log directory."""
        return self.working_dir / "logs"

    @property
    def documents_dir(self) -> Path:
        """Working directory for document ingestion artefacts."""
        return self.working_dir / "documents"

    @property
    def documents_archive_dir(self) -> Path:
        """Default archive directory for processed documents."""
        return self.documents_dir / "archive"

    @property
    def documents_inbox_dir(self) -> Path:
        """Default inbox directory for new handwritten notes."""
        return self.documents_dir / "inbox"

    @property
    def documents_temp_dir(self) -> Path:
        """Scratch directory for temporary OCR outputs."""
        return self.documents_dir / "tmp"
    
    # File path properties
    @property
    def config_path(self) -> Path:
        """Get the configuration file path."""
        return self.working_dir / self.CONFIG_FILE
    
    @property
    def sync_links_path(self) -> Path:
        """Get the sync links file path."""
        return self.data_dir / self.SYNC_LINKS_FILE
    
    @property
    def obsidian_index_path(self) -> Path:
        """Get the Obsidian tasks index file path."""
        return self.data_dir / self.OBSIDIAN_INDEX_FILE
    
    @property
    def reminders_index_path(self) -> Path:
        """Get the Reminders tasks index file path."""
        return self.data_dir / self.REMINDERS_INDEX_FILE
    
    def get_file_with_fallback(self, filename: str) -> Optional[Path]:
        """
        Get file path with fallback to legacy location if it exists there.
        
        Args:
            filename: Name of the file to find
            
        Returns:
            Path to the file, preferring new location but falling back to legacy
        """
        # First check new location
        new_path = self.working_dir / filename
        if new_path.exists():
            return new_path
        
        # Check data subdirectory in new location
        data_path = self.data_dir / filename
        if data_path.exists():
            return data_path
        
        # Check legacy location
        legacy_path = self.legacy_dir / filename
        if legacy_path.exists():
            self.logger.debug(f"Found {filename} in legacy location: {legacy_path}")
            return legacy_path
        
        # Check legacy data subdirectory
        legacy_data_path = self.legacy_dir / "data" / filename
        if legacy_data_path.exists():
            self.logger.debug(f"Found {filename} in legacy data location: {legacy_data_path}")
            return legacy_data_path
        
        # Return new location as default (even if doesn't exist yet)
        return new_path if filename == self.CONFIG_FILE else data_path
    
    def migrate_from_legacy(self, force: bool = False) -> bool:
        """
        Migrate configuration from legacy location to new location.
        
        Args:
            force: Force migration even if files exist in new location
            
        Returns:
            True if migration was performed, False otherwise
        """
        # Don't migrate if we're using the legacy location
        if self.working_dir == self.legacy_dir:
            self.logger.debug("Using legacy location, no migration needed")
            return False
        
        # Check if legacy location exists
        if not self.legacy_dir.exists():
            self.logger.debug("No legacy configuration found")
            return False
        
        # Check if already migrated
        if self._is_migrated and not force:
            return False
        
        # Check if new location already has files
        if not force and self.config_path.exists():
            self.logger.info("Configuration already exists in new location")
            self._is_migrated = True
            return False
        
        self.logger.info(f"Migrating configuration from {self.legacy_dir} to {self.working_dir}")
        
        # Ensure target directories exist
        self.ensure_directories()
        
        # Files to migrate with their target locations
        migrations = [
            (self.legacy_dir / self.CONFIG_FILE, self.config_path),
            (self.legacy_dir / "sync_links.json", self.sync_links_path),
            (self.legacy_dir / "obsidian_tasks_index.json", self.obsidian_index_path),
            (self.legacy_dir / "reminders_tasks_index.json", self.reminders_index_path),
            # Also check legacy data directory
            (self.legacy_dir / "data" / "sync_links.json", self.sync_links_path),
            (self.legacy_dir / "data" / "obsidian_tasks_index.json", self.obsidian_index_path),
            (self.legacy_dir / "data" / "reminders_tasks_index.json", self.reminders_index_path),
        ]
        
        migrated_count = 0
        for source, target in migrations:
            if source.exists():
                # Skip if target exists and force is False
                if target.exists() and not force:
                    self.logger.debug(f"Skipping {source.name}, already exists at target")
                    continue
                
                try:
                    # Create target directory if needed
                    target.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Copy the file
                    shutil.copy2(source, target)
                    self.logger.info(f"Migrated {source.name} to {target}")
                    migrated_count += 1
                    
                except Exception as e:
                    self.logger.error(f"Failed to migrate {source.name}: {e}")
        
        if migrated_count > 0:
            self.logger.info(f"Successfully migrated {migrated_count} file(s)")
            
            # Create a migration marker file
            marker = self.working_dir / ".migrated_from_legacy"
            try:
                marker.write_text(f"Migrated from {self.legacy_dir} on {os.environ.get('USER', 'unknown')}@{os.uname().nodename}\n")
            except Exception:
                pass
            
            self._is_migrated = True
            return True
        else:
            self.logger.debug("No files were migrated")
            return False
    
    def resolve_user_path(self, path: str) -> Path:
        """
        Resolve a user-provided path, handling ~ expansion and relative paths.
        
        Args:
            path: User-provided path string
            
        Returns:
            Resolved absolute Path object
        """
        expanded = os.path.expanduser(path)
        resolved = Path(expanded).resolve()
        return resolved
    
    def get_legacy_files(self) -> Tuple[bool, dict]:
        """
        Check for files in legacy locations.
        
        Returns:
            Tuple of (has_legacy_files, dict of legacy file paths)
        """
        legacy_files = {}
        
        # Check home directory .config locations
        legacy_locations = [
            (Path.home() / ".config" / "sync_links.json", "sync_links"),
            (Path.home() / ".config" / "obsidian_tasks_index.json", "obsidian_index"),
            (Path.home() / ".config" / "reminders_tasks_index.json", "reminders_index"),
            (self.legacy_dir / "config.json", "config"),
            (self.legacy_dir / "sync_links.json", "sync_links"),
            (self.legacy_dir / "data" / "sync_links.json", "sync_links_data"),
        ]
        
        for path, name in legacy_locations:
            if path.exists():
                legacy_files[name] = path
        
        return len(legacy_files) > 0, legacy_files


# Global instance for convenience
_path_manager = None


def get_path_manager() -> PathManager:
    """Get or create the global PathManager instance."""
    global _path_manager
    if _path_manager is None:
        _path_manager = PathManager()
    return _path_manager


# Convenience functions for backward compatibility
def get_config_path() -> Path:
    """Get the configuration file path."""
    return get_path_manager().config_path


def get_sync_links_path() -> Path:
    """Get the sync links file path."""
    return get_path_manager().sync_links_path


def get_obsidian_index_path() -> Path:
    """Get the Obsidian index file path."""
    return get_path_manager().obsidian_index_path


def get_reminders_index_path() -> Path:
    """Get the Reminders index file path."""
    return get_path_manager().reminders_index_path


def get_data_dir() -> Path:
    """Get the data directory."""
    return get_path_manager().data_dir


def get_backup_dir() -> Path:
    """Get the backup directory."""
    return get_path_manager().backup_dir


def get_log_dir() -> Path:
    """Get the log directory."""
    return get_path_manager().log_dir
