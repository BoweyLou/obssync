"""
Install dependencies command for obs-sync.

Modern dependency management using standard pip with extras.
"""

import platform
import subprocess
import sys
from typing import Optional, Dict, List


class InstallDepsCommand:
    """Command to install optional dependencies."""
    
    def __init__(self, verbose: bool = False):
        """
        Initialize install-deps command.
        
        Args:
            verbose: Enable verbose output
        """
        self.verbose = verbose
    
    def get_dependency_groups(self) -> Dict[str, Dict[str, any]]:
        """Get available dependency groups with descriptions."""
        return {
            "macos": {
                "packages": ["pyobjc>=8.0", "pyobjc-framework-EventKit>=8.0"],
                "description": "macOS integration (Apple Reminders, EventKit)",
                "platform_required": "Darwin",
                "pip_extra": "macos"
            },
            "optimization": {
                "packages": ["scipy>=1.5.0"],
                "description": "Enhanced matching algorithms and performance optimizations", 
                "platform_required": None,
                "pip_extra": "optimization"
            },
            "validation": {
                "packages": ["jsonschema>=3.0.0"],
                "description": "Enhanced data validation and schema checking",
                "platform_required": None,
                "pip_extra": "validation"
            },
            "dev": {
                "packages": ["pytest>=6.0", "pytest-cov>=2.10", "black>=21.0", "mypy>=0.900"],
                "description": "Development tools (testing, linting, type checking)",
                "platform_required": None,
                "pip_extra": "dev"
            }
        }
    
    def test_dependency_group(self, group_name: str) -> bool:
        """Test if a dependency group is properly installed."""
        test_imports = {
            "macos": ["objc", "EventKit"],
            "optimization": ["scipy"],
            "validation": ["jsonschema"],
            "dev": ["pytest", "black", "mypy"]
        }
        
        if group_name not in test_imports:
            return False
            
        imports = test_imports[group_name]
        test_cmd = [sys.executable, "-c", f"import {', '.join(imports)}; print('OK')"]
        
        try:
            result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=10)
            return result.returncode == 0 and result.stdout.strip() == "OK"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def install_dependency_group(self, group_name: str, use_pip_extra: bool = True) -> bool:
        """
        Install a dependency group using pip.
        
        Args:
            group_name: Name of the dependency group
            use_pip_extra: Whether to use pip extras (recommended) or individual packages
            
        Returns:
            True if installation succeeded, False otherwise.
        """
        groups = self.get_dependency_groups()
        if group_name not in groups:
            print(f"❌ Unknown dependency group: {group_name}")
            return False
            
        group_info = groups[group_name]
        
        # Check platform compatibility
        if group_info["platform_required"]:
            current_platform = platform.system()
            if group_info["platform_required"] != current_platform:
                print(f"⚠️ Skipping {group_name} (requires {group_info['platform_required']}, current: {current_platform})")
                return True  # Not an error, just not applicable
        
        print(f"\n📦 Installing {group_name} dependencies...")
        print(f"Description: {group_info['description']}")
        
        if use_pip_extra and group_info.get("pip_extra"):
            # Use pip extras (recommended)
            package_spec = f"obs-sync[{group_info['pip_extra']}]"
            cmd = [sys.executable, "-m", "pip", "install", package_spec]
        else:
            # Install individual packages
            packages = group_info["packages"]
            cmd = [sys.executable, "-m", "pip", "install"] + packages
        
        if self.verbose:
            print(f"Running: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(cmd, capture_output=not self.verbose, text=True)
            
            if result.returncode == 0:
                print(f"✅ Successfully installed {group_name} dependencies")
                return True
            else:
                print(f"❌ Failed to install {group_name} dependencies")
                if not self.verbose and result.stderr:
                    print(f"Error: {result.stderr.strip()}")
                return False
                
        except FileNotFoundError:
            print("❌ pip not found. Please ensure Python and pip are installed.")
            return False
        except Exception as e:
            print(f"❌ Unexpected error installing {group_name}: {e}")
            return False
    
    def get_auto_install_groups(self) -> List[str]:
        """Get dependency groups that should be auto-installed for current platform."""
        groups_to_install = []
        current_platform = platform.system()
        
        # Always try to install platform-specific dependencies
        if current_platform == "Darwin":
            groups_to_install.append("macos")
            
        return groups_to_install
    
    def run(
        self, 
        group: Optional[str] = None,
        auto: bool = False,
        list_groups: bool = False
    ) -> bool:
        """
        Run install-deps command.
        
        Args:
            group: Specific group to install
            auto: Auto-install platform-appropriate dependencies
            list_groups: List available groups and exit
            
        Returns:
            True if operation completed successfully
        """
        dependency_groups = self.get_dependency_groups()
        current_platform = platform.system()
        
        if list_groups:
            print("Available dependency groups:")
            print("=" * 40)
            
            for group_name, info in dependency_groups.items():
                platform_note = ""
                if info["platform_required"] and info["platform_required"] != current_platform:
                    platform_note = f" (requires {info['platform_required']})"
                
                # Check if already installed
                installed = self.test_dependency_group(group_name)
                status = "✅ installed" if installed else "❌ not installed"
                
                print(f"\n{group_name}: {info['description']}{platform_note}")
                print(f"  Status: {status}")
                print(f"  Packages: {', '.join(info['packages'])}")
            
            return True
        
        if group:
            # Install specific group
            if group == "all":
                # Install all applicable groups
                success_count = 0
                applicable_groups = []
                
                for group_name, info in dependency_groups.items():
                    if not info["platform_required"] or info["platform_required"] == current_platform:
                        applicable_groups.append(group_name)
                
                for group_name in applicable_groups:
                    if self.install_dependency_group(group_name):
                        success_count += 1
                
                print(f"\n📊 Installation complete: {success_count}/{len(applicable_groups)} groups installed successfully")
                return success_count == len(applicable_groups)
            else:
                return self.install_dependency_group(group)
        
        if auto:
            # Auto-install platform-appropriate dependencies
            auto_groups = self.get_auto_install_groups()
            if not auto_groups:
                print("🤷 No platform-specific dependencies to auto-install")
                return True
            
            print(f"🚀 Auto-installing dependencies for {current_platform}: {', '.join(auto_groups)}")
            
            success_count = 0
            for group_name in auto_groups:
                if self.install_dependency_group(group_name):
                    success_count += 1
            
            print(f"\n📊 Auto-installation complete: {success_count}/{len(auto_groups)} groups installed successfully")
            return success_count == len(auto_groups)
        
        # Interactive mode
        print("obs-sync Dependency Installation")
        print("=" * 40)
        print(f"Platform: {current_platform}")
        print()
        
        # Show available groups
        print("Available dependency groups:")
        for i, (group_name, info) in enumerate(dependency_groups.items(), 1):
            platform_note = ""
            if info["platform_required"] and info["platform_required"] != current_platform:
                platform_note = f" (requires {info['platform_required']})"
            
            # Check if already installed
            installed = self.test_dependency_group(group_name)
            status = "✅ installed" if installed else "❌ not installed"
            
            print(f"  {i}. {group_name}: {info['description']}{platform_note} [{status}]")
        
        print(f"  {len(dependency_groups) + 1}. all: Install all applicable groups")
        print(f"  {len(dependency_groups) + 2}. auto: Auto-install platform dependencies")
        print(f"  {len(dependency_groups) + 3}. quit: Exit")
        print()
        
        # Get user selection
        while True:
            try:
                choice = input(f"Select group to install (1-{len(dependency_groups) + 3}): ").strip()
                if choice.lower() in ['q', 'quit']:
                    return True
                
                choice_num = int(choice)
                if choice_num == len(dependency_groups) + 1:  # all
                    return self.run(group="all")
                elif choice_num == len(dependency_groups) + 2:  # auto
                    return self.run(auto=True)
                elif choice_num == len(dependency_groups) + 3:  # quit
                    return True
                elif 1 <= choice_num <= len(dependency_groups):
                    selected_group = list(dependency_groups.keys())[choice_num - 1]
                    return self.run(group=selected_group)
                else:
                    print(f"Please enter a number between 1 and {len(dependency_groups) + 3}")
            except (ValueError, KeyboardInterrupt, EOFError):
                print("\nInstallation cancelled.")
                return True