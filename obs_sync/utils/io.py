"""
Safe I/O operations with atomic writes and file locking.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional


def safe_read_json(file_path: str, default: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Safely read JSON from file with error handling.
    
    Args:
        file_path: Path to JSON file
        default: Default value to return if file doesn't exist or is invalid
    
    Returns:
        Parsed JSON data or default value
    """
    if default is None:
        default = {}
    
    file_path = os.path.expanduser(file_path)
    
    if not os.path.exists(file_path):
        return default
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Failed to read {file_path}: {e}")
        return default


def safe_write_json(file_path: str, data: Dict[str, Any], indent: int = 2) -> bool:
    """
    Safely write JSON to file with atomic write.
    
    Args:
        file_path: Path to write to
        data: Data to write
        indent: JSON indentation level
    
    Returns:
        True if successful, False otherwise
    """
    file_path = os.path.expanduser(file_path)
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    try:
        # Write to temporary file first
        with tempfile.NamedTemporaryFile(
            mode='w',
            dir=os.path.dirname(file_path),
            prefix='.tmp_',
            suffix='.json',
            delete=False,
            encoding='utf-8'
        ) as tmp_file:
            json.dump(data, tmp_file, indent=indent, ensure_ascii=False, sort_keys=True)
            tmp_path = tmp_file.name
        
        # Atomic rename
        os.replace(tmp_path, file_path)
        return True
        
    except Exception as e:
        print(f"Error writing to {file_path}: {e}")
        # Clean up temp file if it exists
        try:
            if 'tmp_path' in locals() and os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except:
            pass
        return False


def atomic_write(file_path: str, content: str) -> bool:
    """
    Atomically write content to file.
    
    Args:
        file_path: Path to write to
        content: Content to write
    
    Returns:
        True if successful, False otherwise
    """
    file_path = os.path.expanduser(file_path)
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    try:
        # Write to temporary file first
        with tempfile.NamedTemporaryFile(
            mode='w',
            dir=os.path.dirname(file_path),
            prefix='.tmp_',
            delete=False,
            encoding='utf-8'
        ) as tmp_file:
            tmp_file.write(content)
            tmp_path = tmp_file.name
        
        # Atomic rename
        os.replace(tmp_path, file_path)
        return True
        
    except Exception as e:
        print(f"Error writing to {file_path}: {e}")
        # Clean up temp file if it exists
        try:
            if 'tmp_path' in locals() and os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except:
            pass
        return False