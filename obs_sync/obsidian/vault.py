"""
Obsidian vault discovery and management.
"""

import os
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from obs_sync.core.models import Vault


def find_vaults(search_paths: Optional[List[str]] = None, max_depth: int = 2) -> List[Vault]:
    """
    Find Obsidian vaults in common locations.
    
    A vault is identified by the presence of a .obsidian directory.
    
    Args:
        search_paths: Optional list of paths to search. Uses defaults if not provided.
        max_depth: Maximum directory depth to search
    
    Returns:
        List of discovered vaults
    """
    if search_paths is None:
        # Default search locations
        home = Path.home()
        search_paths = [
            str(home / "Documents"),
            str(home / "Desktop"),
            str(home / "Library" / "Mobile Documents" / "iCloud~md~obsidian" / "Documents"),
            str(home / "Dropbox"),
            str(home / "OneDrive"),
            str(home / "Google Drive"),
        ]
    
    vaults = []
    seen_paths = set()
    
    for search_path in search_paths:
        search_path = os.path.expanduser(search_path)
        if not os.path.exists(search_path):
            continue
        
        # Search for .obsidian directories
        for root, dirs, _ in os.walk(search_path):
            # Check depth
            depth = root[len(search_path):].count(os.sep)
            if depth > max_depth:
                dirs.clear()  # Don't descend further
                continue
            
            # Skip hidden directories (except .obsidian)
            dirs[:] = [d for d in dirs if not d.startswith('.') or d == '.obsidian']
            
            # Check if this is a vault
            obsidian_dir = os.path.join(root, '.obsidian')
            if os.path.isdir(obsidian_dir):
                vault_path = root
                if vault_path not in seen_paths:
                    seen_paths.add(vault_path)
                    vault_name = os.path.basename(vault_path)
                    vaults.append(Vault(
                        name=vault_name,
                        path=vault_path,
                        vault_id=str(uuid4())
                    ))
                # Don't search inside vaults
                dirs.clear()
    
    return vaults


class VaultManager:
    """Manages Obsidian vault operations."""
    
    def __init__(self, vaults: List[Vault]):
        """
        Initialize vault manager.
        
        Args:
            vaults: List of vaults to manage
        """
        self.vaults = vaults
        self._vault_by_id = {v.vault_id: v for v in vaults}
        self._vault_by_path = {v.path: v for v in vaults}
    
    def get_vault_by_id(self, vault_id: str) -> Optional[Vault]:
        """Get vault by ID."""
        return self._vault_by_id.get(vault_id)
    
    def get_vault_by_path(self, path: str) -> Optional[Vault]:
        """Get vault by path."""
        path = os.path.abspath(os.path.expanduser(path))
        return self._vault_by_path.get(path)
    
    def get_default_vault(self) -> Optional[Vault]:
        """Get the default vault."""
        for vault in self.vaults:
            if vault.is_default:
                return vault
        # Return first vault if no default set
        return self.vaults[0] if self.vaults else None
    
    def iter_markdown_files(self, vault: Vault) -> List[str]:
        """
        Iterate through all markdown files in a vault.
        
        Args:
            vault: Vault to search
        
        Returns:
            List of absolute paths to markdown files
        """
        markdown_files = []
        
        # Directories to skip
        skip_dirs = {'.obsidian', '.trash', '.git', 'node_modules'}
        
        for root, dirs, files in os.walk(vault.path):
            # Filter out directories to skip
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            
            # Find markdown files
            for file in files:
                if file.endswith('.md'):
                    markdown_files.append(os.path.join(root, file))
        
        return markdown_files