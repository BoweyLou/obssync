#!/usr/bin/env python3
"""
Global pytest configuration and fixtures.

This module provides:
- Platform-specific test skipping (macOS/EventKit tests)
- Optional dependency handling (scipy, munkres)
- Common test fixtures and utilities
- Test environment setup and teardown
"""

import os
import platform
import sys
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, Generator

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Check for optional dependencies
HAS_SCIPY = False
HAS_MUNKRES = False
HAS_EVENTKIT = False

try:
    import scipy
    HAS_SCIPY = True
except ImportError:
    pass

try:
    import munkres
    HAS_MUNKRES = True
except ImportError:
    pass

try:
    if platform.system() == "Darwin":
        import objc
        import EventKit
        HAS_EVENTKIT = True
except ImportError:
    pass


def pytest_configure(config):
    """Configure pytest environment."""
    # Add custom markers programmatically if needed
    config.addinivalue_line("markers", "requires_scipy: test requires scipy library")
    config.addinivalue_line("markers", "requires_munkres: test requires munkres library")
    config.addinivalue_line("markers", "requires_eventkit: test requires EventKit framework")


def pytest_collection_modifyitems(config, items):
    """
    Modify test collection to skip platform-specific tests.
    
    Automatically skip macOS/EventKit tests on non-Darwin platforms.
    """
    skip_macos = pytest.mark.skip(reason="macOS/EventKit tests require Darwin platform")
    skip_scipy = pytest.mark.skip(reason="Test requires scipy library")
    skip_munkres = pytest.mark.skip(reason="Test requires munkres library")
    skip_eventkit = pytest.mark.skip(reason="Test requires EventKit framework")
    
    for item in items:
        # Skip macOS tests on non-Darwin platforms
        if "macos" in item.keywords and platform.system() != "Darwin":
            item.add_marker(skip_macos)
        
        # Skip EventKit tests if EventKit not available
        if "eventkit" in item.keywords and not HAS_EVENTKIT:
            item.add_marker(skip_eventkit)
        
        # Skip scipy-dependent tests if scipy not available
        if "requires_scipy" in item.keywords and not HAS_SCIPY:
            item.add_marker(skip_scipy)
        
        # Skip munkres-dependent tests if munkres not available
        if "requires_munkres" in item.keywords and not HAS_MUNKRES:
            item.add_marker(skip_munkres)


def pytest_runtest_setup(item):
    """Setup for each test run."""
    # Additional per-test setup if needed
    pass


# Common test fixtures

@pytest.fixture
def temp_dir() -> Generator[str, None, None]:
    """Create a temporary directory for test isolation."""
    temp_path = tempfile.mkdtemp(prefix="obs_tools_test_")
    try:
        yield temp_path
    finally:
        shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def mock_obsidian_vault(temp_dir: str) -> str:
    """Create a mock Obsidian vault with test files."""
    vault_path = os.path.join(temp_dir, "test_vault")
    os.makedirs(vault_path)
    
    # Create test daily note
    daily_note = os.path.join(vault_path, "2023-12-15.md")
    daily_content = """# Daily Note 2023-12-15

## Tasks
- [ ] Buy groceries 📅 2023-12-15 #personal
- [ ] Finish project report 📅 2023-12-16 #work ⏫
- [x] Call dentist ✅ 2023-12-14

## Notes
Some notes here.
"""
    with open(daily_note, 'w', encoding='utf-8') as f:
        f.write(daily_content)
    
    # Create test project file
    project_file = os.path.join(vault_path, "Project Alpha.md")
    project_content = """# Project Alpha

## Milestones
- [ ] Design phase 🛫 2023-12-01 📅 2023-12-20 #work #design
- [ ] Development phase 🛫 2023-12-21 📅 2024-01-15 #work #dev
- [x] Planning phase ✅ 2023-11-30 #work

## Notes
Project documentation here.
"""
    with open(project_file, 'w', encoding='utf-8') as f:
        f.write(project_content)
    
    return vault_path


@pytest.fixture
def mock_config_dir(temp_dir: str) -> str:
    """Create a mock configuration directory."""
    config_path = os.path.join(temp_dir, "config")
    os.makedirs(config_path)
    return config_path


@pytest.fixture
def sample_obsidian_tasks() -> Dict[str, Any]:
    """Sample Obsidian tasks data for testing."""
    return {
        "meta": {
            "schema": 2,
            "generated_at": "2023-12-15T10:00:00Z",
            "vault_count": 1,
            "file_count": 2,
            "task_count": 4
        },
        "tasks": {
            "obs-uuid-1": {
                "uuid": "obs-uuid-1",
                "vault_name": "Test Vault",
                "vault_path": "/test/vault",
                "file_path": "2023-12-15.md",
                "line_number": 4,
                "status": "todo",
                "description": "Buy groceries",
                "due_date": "2023-12-15",
                "tags": ["personal"],
                "created_at": "2023-12-15T09:00:00Z",
                "updated_at": "2023-12-15T09:00:00Z"
            },
            "obs-uuid-2": {
                "uuid": "obs-uuid-2",
                "vault_name": "Test Vault",
                "vault_path": "/test/vault",
                "file_path": "2023-12-15.md",
                "line_number": 5,
                "status": "todo",
                "description": "Finish project report",
                "due_date": "2023-12-16",
                "tags": ["work"],
                "priority": "highest",
                "created_at": "2023-12-15T09:00:00Z",
                "updated_at": "2023-12-15T09:00:00Z"
            }
        }
    }


@pytest.fixture
def sample_reminders_tasks() -> Dict[str, Any]:
    """Sample Reminders tasks data for testing."""
    return {
        "meta": {
            "schema": 2,
            "generated_at": "2023-12-15T10:00:00Z",
            "list_count": 1,
            "task_count": 2
        },
        "tasks": {
            "rem-uuid-1": {
                "uuid": "rem-uuid-1",
                "title": "Buy groceries today",
                "completed": False,
                "list_name": "Tasks",
                "due_date": "2023-12-15",
                "created_at": "2023-12-15T09:00:00Z",
                "updated_at": "2023-12-15T09:00:00Z"
            },
            "rem-uuid-2": {
                "uuid": "rem-uuid-2",
                "title": "Project report deadline",
                "completed": False,
                "list_name": "Tasks",
                "due_date": "2023-12-16",
                "created_at": "2023-12-15T09:00:00Z",
                "updated_at": "2023-12-15T09:00:00Z"
            }
        }
    }


@pytest.fixture
def dependency_info() -> Dict[str, bool]:
    """Information about available optional dependencies."""
    return {
        "scipy": HAS_SCIPY,
        "munkres": HAS_MUNKRES,
        "eventkit": HAS_EVENTKIT,
        "is_darwin": platform.system() == "Darwin"
    }


# Helper functions for tests

def create_corrupted_json_file(file_path: str) -> None:
    """Create a corrupted JSON file for testing error handling."""
    with open(file_path, 'w') as f:
        f.write('{"incomplete": "json file without closing brace"')


def create_large_json_file(file_path: str, size_mb: int = 1) -> None:
    """Create a large JSON file for testing size limits."""
    # Create a JSON structure that will be approximately the requested size
    large_data = {
        "meta": {"schema": 2, "size": "large"},
        "data": ["x" * (1024 * 100)] * (size_mb * 10)  # Approximate size
    }
    with open(file_path, 'w') as f:
        import json
        json.dump(large_data, f)