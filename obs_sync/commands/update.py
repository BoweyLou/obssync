"""Update command for upgrading obs-sync to the latest version."""

import subprocess
import sys
from pathlib import Path
from typing import Optional

from obs_sync.core.config import SyncConfig


class UpdateCommand:
    """Command to update obs-sync from git repository."""

    def __init__(self, config: SyncConfig, verbose: bool = False):
        """Initialize update command."""
        self.config = config
        self.verbose = verbose

    def run(self, extras: Optional[str] = None, channel: Optional[str] = None) -> bool:
        """
        Update obs-sync to the latest version.

        Args:
            extras: Comma-separated list of extras to install (e.g., "macos,optimization")
                   If None, uses default "macos" on macOS
            channel: Update channel to track ("stable" or "beta"). If provided, updates
                    the stored preference. If None, uses current config setting.

        Returns:
            True if update succeeded, False otherwise
        """
        print("obs-sync Update Assistant")
        print("=" * 40)

        # Determine active channel (CLI override or config default)
        active_channel = channel if channel else self.config.update_channel
        # Sanitize channel value
        if active_channel not in ["stable", "beta"]:
            active_channel = "stable"

        # Update config if channel was explicitly provided
        if channel:
            self.config.update_channel = active_channel

        # Find repo root
        repo_root = self._find_repo_root()
        if not repo_root:
            print("\n❌ Could not locate the obs-sync repository.")
            print("Manual update steps:")
            print("  1) cd /path/to/obssync")
            print("  2) run git pull")
            print("  3) run ./install.sh --extras macos")
            return False
        
        print(f"\n📁 Repository: {repo_root}")

        # Interactive channel selection (only if --channel was not provided)
        if channel is None:
            print(f"\n📡 Current channel: {active_channel}")
            choice = input("Switch update channel? (y/N): ").strip().lower()

            if choice == 'y':
                print("\nAvailable channels:")
                print("  1) stable - Production releases (main branch)")
                print("  2) beta   - Latest features and fixes (beta branch)")

                channel_choice = input("\nSelect channel (1/2): ").strip()

                if channel_choice == "1":
                    active_channel = "stable"
                    self.config.update_channel = "stable"
                    print("✓ Switched to stable channel")
                elif channel_choice == "2":
                    active_channel = "beta"
                    self.config.update_channel = "beta"
                    print("✓ Switched to beta channel")
                    print("⚠️  Beta channel may contain experimental features")
                else:
                    print(f"✓ Keeping current channel: {active_channel}")

        # Map channel to branch
        branch_map = {"stable": "main", "beta": "beta"}
        target_branch = branch_map[active_channel]

        print(f"\n📡 Update channel: {active_channel} (tracking origin/{target_branch})")
        if active_channel == "beta":
            print("💡 Switch back anytime with: obs-sync update --channel stable")

        # Check for uncommitted changes
        print("\n🔍 Checking repository state...")
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode != 0:
                print(f"❌ git status failed: {result.stderr.strip()}")
                return False

            if result.stdout.strip():
                print("❌ Repository has uncommitted changes. Please commit or stash them first.")
                print("\nUncommitted changes:")
                for line in result.stdout.strip().split('\n')[:10]:
                    print(f"  {line}")
                if len(result.stdout.strip().split('\n')) > 10:
                    print(f"  ... and {len(result.stdout.strip().split('\n')) - 10} more")
                return False

        except Exception as e:
            print(f"❌ Error checking git status: {e}")
            return False

        # Fetch and checkout target branch
        print(f"\n🔍 Switching to {active_channel} channel...")
        try:
            # Fetch latest from remote
            result = subprocess.run(
                ["git", "fetch"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode != 0:
                print(f"⚠️  git fetch failed: {result.stderr.strip()}")
                return False

            # Check if target branch exists on remote
            result = subprocess.run(
                ["git", "rev-parse", "--verify", f"origin/{target_branch}"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode != 0:
                print(f"❌ Branch 'origin/{target_branch}' not found on remote.")
                print(f"The {active_channel} channel may not be available in this repository.")
                return False

            # Checkout target branch
            result = subprocess.run(
                ["git", "checkout", target_branch],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode != 0:
                print(f"❌ Failed to checkout {target_branch}: {result.stderr.strip()}")
                return False

            # Set upstream tracking
            result = subprocess.run(
                ["git", "branch", f"--set-upstream-to=origin/{target_branch}", target_branch],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode != 0 and self.verbose:
                print(f"⚠️  Could not set upstream tracking: {result.stderr.strip()}")

            print(f"✓ Switched to {target_branch} branch")

            # Check if we're behind
            result = subprocess.run(
                ["git", "status", "-uno"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode != 0:
                print(f"❌ git status failed: {result.stderr.strip()}")
                return False
            
            status_output = result.stdout
            
            if "Your branch is up to date" in status_output:
                print("✅ You already have the latest version.")
                
                # Still offer to reinstall dependencies
                choice = input("\nReinstall dependencies anyway? (y/N): ").strip().lower()
                if choice != 'y':
                    return True
            elif "Your branch is behind" in status_output:
                print("📥 Updates are available.")
                
                # Show what would be updated - display versions and changes
                # Get current version tag
                current_tag_result = subprocess.run(
                    ["git", "describe", "--tags", "--abbrev=0", "HEAD"],
                    cwd=repo_root,
                    capture_output=True,
                    text=True,
                    check=False
                )
                current_version = current_tag_result.stdout.strip() if current_tag_result.returncode == 0 else "unknown"
                
                # Get latest version tag from upstream
                latest_tag_result = subprocess.run(
                    ["git", "describe", "--tags", "--abbrev=0", "@{u}"],
                    cwd=repo_root,
                    capture_output=True,
                    text=True,
                    check=False
                )
                latest_version = latest_tag_result.stdout.strip() if latest_tag_result.returncode == 0 else "unknown"
                
                if current_version != "unknown" and latest_version != "unknown":
                    print(f"\n📦 Update: {current_version} → {latest_version}")
                    
                    # Show commits in the range with better formatting
                    result = subprocess.run(
                        ["git", "log", "--format=%s", f"HEAD..@{{u}}"],
                        cwd=repo_root,
                        capture_output=True,
                        text=True,
                        check=False
                    )
                    
                    if result.returncode == 0 and result.stdout.strip():
                        print("\nIncoming changes:")
                        for line in result.stdout.strip().split('\n')[:5]:
                            print(f"  • {line}")
                        if len(result.stdout.strip().split('\n')) > 5:
                            print(f"  ... and {len(result.stdout.strip().split('\n')) - 5} more")
                else:
                    # Fallback to commit messages if tags aren't available
                    result = subprocess.run(
                        ["git", "log", "--format=%s", "HEAD..@{u}"],
                        cwd=repo_root,
                        capture_output=True,
                        text=True,
                        check=False
                    )
                    
                    if result.returncode == 0 and result.stdout.strip():
                        print("\nAdditional changes:")
                        for line in result.stdout.strip().split('\n')[:5]:
                            print(f"  • {line}")
                        if len(result.stdout.strip().split('\n')) > 5:
                            print(f"  ... and {len(result.stdout.strip().split('\n')) - 5} more")
                
                choice = input("\nProceed with the update? (Y/n): ").strip().lower()
                if choice == 'n':
                    print("Update cancelled—you remain on the current version.")
                    return False
            elif "Your branch is ahead" in status_output:
                print("⚠️ Local branch is ahead of the remote.")
                print("You likely have unpushed commits.")
                choice = input("\nProceed anyway? (y/N): ").strip().lower()
                if choice != 'y':
                    return False
            else:
                # Unknown status, proceed with caution
                print("⚠️ Git status was unclear—continuing with update.")
        
        except Exception as e:
            print(f"❌ Error checking git status: {e}")
            return False
        
        # Pull latest changes
        print("\n📥 Pulling the latest changes...")
        try:
            result = subprocess.run(
                ["git", "pull"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode != 0:
                print(f"❌ git pull failed: {result.stderr.strip()}")
                return False
            
            if self.verbose:
                print(result.stdout.strip())
            else:
                print("✓ Pull complete.")
        
        except Exception as e:
            print(f"❌ Error during git pull: {e}")
            return False
        
        # Reinstall dependencies
        print("\n📦 Reinstalling dependencies...")
        
        # Determine extras
        if extras is None:
            import platform
            if platform.system() == "Darwin":
                extras = "macos"
            else:
                extras = ""
        
        install_script = repo_root / "install.sh"
        
        if not install_script.exists():
            print(f"❌ Install script not found: {install_script}")
            return False
        
        try:
            cmd = ["bash", str(install_script)]
            if extras:
                cmd.extend(["--extras", extras])
            
            result = subprocess.run(
                cmd,
                cwd=repo_root,
                check=False
            )
            
            if result.returncode != 0:
                print("❌ Dependency installation failed.")
                return False
            
            print("✓ Dependencies reinstalled.")
        
        except Exception as e:
            print(f"❌ Error during installation: {e}")
            return False
        
        # Check if automation is enabled and prompt to refresh
        if self.config.automation_enabled:
            print("\n🤖 LaunchAgent automation is currently enabled.")
            print("If this update changes the LaunchAgent, refresh it to apply the new plist.")
            
            choice = input("Refresh LaunchAgent automation now? (Y/n): ").strip().lower()
            
            if choice != 'n':
                print("\n💡 To refresh automation:")
                print("  1. Run obs-sync setup --reconfigure.")
                print("  2. Select option 8 (Automation settings).")
                print("  3. Choose 'n' to disable, then 'y' to re-enable.")
                print("\nDoing so ensures the LaunchAgent picks up any plist changes.")
        
        print("\n✅ Update complete.")
        return True
    
    def _find_repo_root(self) -> Optional[Path]:
        """Find the repository root directory."""
        try:
            # Try using the venv utility
            from obs_sync.utils.venv import repo_root
            return repo_root()
        except Exception:
            # Fallback: try git rev-parse
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "--show-toplevel"],
                    capture_output=True,
                    text=True,
                    check=False
                )
                
                if result.returncode == 0:
                    return Path(result.stdout.strip())
            except Exception:
                pass
        
        return None
