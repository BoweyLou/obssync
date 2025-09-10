#!/usr/bin/env python3
"""
Setup command for installing optional dependencies.

This command provides a user-friendly way to install optional dependency groups
without runtime dependency installation.
"""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
from typing import List, Dict


def get_dependency_groups() -> Dict[str, Dict[str, any]]:
    """Get available dependency groups with descriptions."""
    return {
        "macos": {
            "packages": ["pyobjc>=8.0", "pyobjc-framework-EventKit>=8.0"],
            "description": "macOS integration (Apple Reminders, EventKit)",
            "platform_required": "Darwin"
        },
        "optimization": {
            "packages": ["scipy>=1.5.0", "munkres>=1.1.0"],
            "description": "Enhanced matching algorithms and performance optimizations",
            "platform_required": None
        },
        "validation": {
            "packages": ["jsonschema>=3.0.0"],
            "description": "Enhanced data validation and schema checking",
            "platform_required": None
        },
        "dev": {
            "packages": ["pytest>=6.0", "pytest-cov>=2.10", "black>=21.0", "mypy>=0.900"],
            "description": "Development tools (testing, linting, type checking)",
            "platform_required": None
        }
    }


def get_venv_python() -> str:
    """Get the Python executable in the obs-tools venv."""
    home = os.path.expanduser("~")
    if platform.system() == "Darwin":
        base = os.path.join(home, "Library", "Application Support", "obs-tools")
    else:
        base = os.path.join(home, ".local", "share", "obs-tools")
    
    venv_dir = os.path.join(base, "venv")
    if platform.system() == "Windows":
        python_bin = os.path.join(venv_dir, "Scripts", "python.exe")
    else:
        python_bin = os.path.join(venv_dir, "bin", "python3")
    
    return python_bin


def check_venv_exists(python_bin: str) -> bool:
    """Check if the obs-tools venv exists."""
    return os.path.exists(python_bin)


def install_dependency_group(group_name: str, packages: List[str], python_bin: str) -> bool:
    """
    Install a dependency group using pip.
    
    Returns:
        True if installation succeeded, False otherwise.
    """
    print(f"\nInstalling {group_name} dependencies...")
    print(f"Packages: {', '.join(packages)}")
    
    # First upgrade pip
    print("Upgrading pip...")
    result = subprocess.run([python_bin, "-m", "pip", "install", "--upgrade", "pip"], 
                          capture_output=False, text=True)
    if result.returncode != 0:
        print("Warning: Failed to upgrade pip, continuing anyway...")
    
    # Install the packages
    cmd = [python_bin, "-m", "pip", "install"] + packages
    print(f"Running: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, capture_output=False, text=True)
    
    if result.returncode == 0:
        print(f"✓ Successfully installed {group_name} dependencies")
        return True
    else:
        print(f"✗ Failed to install {group_name} dependencies")
        return False


def test_dependency_group(group_name: str, python_bin: str) -> bool:
    """Test if a dependency group is properly installed."""
    if group_name == "macos":
        test_cmd = [python_bin, "-c", "import objc, EventKit; print('OK')"]
    elif group_name == "optimization":
        test_cmd = [python_bin, "-c", "import scipy, munkres; print('OK')"]
    elif group_name == "validation":
        test_cmd = [python_bin, "-c", "import jsonschema; print('OK')"]
    elif group_name == "dev":
        test_cmd = [python_bin, "-c", "import pytest, black, mypy; print('OK')"]
    else:
        return False
    
    result = subprocess.run(test_cmd, capture_output=True, text=True)
    return result.returncode == 0 and result.stdout.strip() == "OK"


def interactive_setup():
    """Interactive setup workflow."""
    print("obs-tools Setup - Optional Dependency Installation")
    print("=" * 50)
    
    python_bin = get_venv_python()
    
    if not check_venv_exists(python_bin):
        print(f"Error: obs-tools venv not found at {python_bin}")
        print("Please run obs-tools at least once to create the virtual environment.")
        return 1
    
    dependency_groups = get_dependency_groups()
    current_platform = platform.system()
    
    print(f"Python executable: {python_bin}")
    print(f"Current platform: {current_platform}")
    print()
    
    # Show available groups
    print("Available dependency groups:")
    for i, (group_name, info) in enumerate(dependency_groups.items(), 1):
        platform_note = ""
        if info["platform_required"] and info["platform_required"] != current_platform:
            platform_note = f" (requires {info['platform_required']})"
        
        # Check if already installed
        installed = test_dependency_group(group_name, python_bin)
        status = "✓ installed" if installed else "✗ not installed"
        
        print(f"  {i}. {group_name}: {info['description']}{platform_note} [{status}]")
    
    print(f"  {len(dependency_groups) + 1}. all: Install all applicable groups")
    print(f"  {len(dependency_groups) + 2}. quit: Exit setup")
    print()
    
    # Get user selection
    while True:
        try:
            choice = input(f"Select group to install (1-{len(dependency_groups) + 2}): ").strip()
            if choice.lower() in ['q', 'quit']:
                return 0
            
            choice_num = int(choice)
            if choice_num == len(dependency_groups) + 1:  # all
                selected_groups = list(dependency_groups.keys())
                break
            elif choice_num == len(dependency_groups) + 2:  # quit
                return 0
            elif 1 <= choice_num <= len(dependency_groups):
                selected_groups = [list(dependency_groups.keys())[choice_num - 1]]
                break
            else:
                print(f"Please enter a number between 1 and {len(dependency_groups) + 2}")
        except (ValueError, KeyboardInterrupt):
            print("\nSetup cancelled.")
            return 1
        except EOFError:
            print("\nSetup cancelled.")
            return 1
    
    # Filter out groups that aren't compatible with current platform
    installable_groups = []
    for group_name in selected_groups:
        info = dependency_groups[group_name]
        if info["platform_required"] and info["platform_required"] != current_platform:
            print(f"Skipping {group_name} (requires {info['platform_required']}, current: {current_platform})")
        else:
            installable_groups.append(group_name)
    
    if not installable_groups:
        print("No compatible groups selected.")
        return 0
    
    # Confirm installation
    print(f"\nWill install: {', '.join(installable_groups)}")
    try:
        confirm = input("Proceed? (y/N): ").strip().lower()
        if confirm not in ['y', 'yes']:
            print("Installation cancelled.")
            return 0
    except (KeyboardInterrupt, EOFError):
        print("\nInstallation cancelled.")
        return 1
    
    # Install groups
    success_count = 0
    for group_name in installable_groups:
        info = dependency_groups[group_name]
        if install_dependency_group(group_name, info["packages"], python_bin):
            success_count += 1
    
    print(f"\nSetup complete: {success_count}/{len(installable_groups)} groups installed successfully")
    return 0 if success_count == len(installable_groups) else 1


def main(argv: List[str]) -> int:
    """Main entry point for setup command."""
    parser = argparse.ArgumentParser(description="Install optional dependencies for obs-tools")
    parser.add_argument("--list", action="store_true", help="List available dependency groups")
    parser.add_argument("--group", help="Install specific dependency group")
    parser.add_argument("--all", action="store_true", help="Install all applicable dependency groups")
    parser.add_argument("--test", help="Test if a dependency group is installed")
    parser.add_argument("--interactive", action="store_true", help="Run interactive setup (default)")
    
    args = parser.parse_args(argv)
    
    dependency_groups = get_dependency_groups()
    python_bin = get_venv_python()
    current_platform = platform.system()
    
    if args.list:
        print("Available dependency groups:")
        for group_name, info in dependency_groups.items():
            platform_note = ""
            if info["platform_required"] and info["platform_required"] != current_platform:
                platform_note = f" (requires {info['platform_required']})"
            
            installed = test_dependency_group(group_name, python_bin)
            status = "✓ installed" if installed else "✗ not installed"
            
            print(f"  {group_name}: {info['description']}{platform_note} [{status}]")
            print(f"    Packages: {', '.join(info['packages'])}")
        return 0
    
    if args.test:
        if args.test not in dependency_groups:
            print(f"Unknown dependency group: {args.test}")
            return 1
        
        if not check_venv_exists(python_bin):
            print(f"Error: obs-tools venv not found at {python_bin}")
            return 1
        
        installed = test_dependency_group(args.test, python_bin)
        print(f"{args.test}: {'✓ installed' if installed else '✗ not installed'}")
        return 0 if installed else 1
    
    if args.group:
        if args.group not in dependency_groups:
            print(f"Unknown dependency group: {args.group}")
            print(f"Available groups: {', '.join(dependency_groups.keys())}")
            return 1
        
        if not check_venv_exists(python_bin):
            print(f"Error: obs-tools venv not found at {python_bin}")
            return 1
        
        info = dependency_groups[args.group]
        if info["platform_required"] and info["platform_required"] != current_platform:
            print(f"Error: {args.group} requires {info['platform_required']} (current: {current_platform})")
            return 1
        
        return 0 if install_dependency_group(args.group, info["packages"], python_bin) else 1
    
    if args.all:
        if not check_venv_exists(python_bin):
            print(f"Error: obs-tools venv not found at {python_bin}")
            return 1
        
        installable_groups = []
        for group_name, info in dependency_groups.items():
            if not info["platform_required"] or info["platform_required"] == current_platform:
                installable_groups.append(group_name)
        
        success_count = 0
        for group_name in installable_groups:
            info = dependency_groups[group_name]
            if install_dependency_group(group_name, info["packages"], python_bin):
                success_count += 1
        
        print(f"\nInstallation complete: {success_count}/{len(installable_groups)} groups installed successfully")
        return 0 if success_count == len(installable_groups) else 1
    
    # Default to interactive setup
    return interactive_setup()


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))