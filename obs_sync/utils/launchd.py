"""LaunchAgent management for macOS automation."""

import os
import platform
import plistlib
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple
import logging


AGENT_LABEL = "com.obs-sync.sync-agent"
AGENT_FILENAME = f"{AGENT_LABEL}.plist"


def is_macos() -> bool:
    """Check if running on macOS."""
    return platform.system() == "Darwin"


def get_launchagent_path() -> Path:
    """Get the path where the LaunchAgent plist should be installed."""
    return Path.home() / "Library" / "LaunchAgents" / AGENT_FILENAME


def generate_plist(
    interval_seconds: int,
    obs_sync_path: str,
    log_dir: Path,
    logger: Optional[logging.Logger] = None
) -> Dict:
    """
    Generate LaunchAgent plist dictionary.
    
    Args:
        interval_seconds: Interval in seconds between runs
        obs_sync_path: Full path to obs-sync executable
        log_dir: Directory for stdout/stderr logs
        logger: Optional logger instance
        
    Returns:
        Dictionary representing the plist structure
    """
    if logger:
        logger.debug(f"Generating plist with interval={interval_seconds}s, exe={obs_sync_path}")
    
    # Ensure log directory exists
    log_dir.mkdir(parents=True, exist_ok=True)
    
    stdout_log = log_dir / "obs-sync-agent.stdout.log"
    stderr_log = log_dir / "obs-sync-agent.stderr.log"
    
    plist = {
        "Label": AGENT_LABEL,
        "ProgramArguments": [obs_sync_path, "sync", "--apply"],
        "StartInterval": interval_seconds,
        "RunAtLoad": False,  # Don't run immediately on login
        "StandardOutPath": str(stdout_log),
        "StandardErrorPath": str(stderr_log),
        "EnvironmentVariables": {
            "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        }
    }
    
    return plist


def install_agent(
    interval_seconds: int,
    obs_sync_path: str,
    log_dir: Path,
    logger: Optional[logging.Logger] = None
) -> Tuple[bool, Optional[str]]:
    """
    Install (write) the LaunchAgent plist file.
    
    Args:
        interval_seconds: Interval in seconds between runs
        obs_sync_path: Full path to obs-sync executable
        log_dir: Directory for logs
        logger: Optional logger instance
        
    Returns:
        (success, error_message) tuple
    """
    if not is_macos():
        return False, "LaunchAgent automation is only available on macOS"
    
    try:
        plist_path = get_launchagent_path()
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        
        plist_data = generate_plist(interval_seconds, obs_sync_path, log_dir, logger)
        
        with open(plist_path, "wb") as f:
            plistlib.dump(plist_data, f)
        
        if logger:
            logger.info(f"LaunchAgent plist installed at {plist_path}")
        
        return True, None
        
    except Exception as e:
        error = f"Failed to install LaunchAgent: {e}"
        if logger:
            logger.error(error)
        return False, error


def uninstall_agent(logger: Optional[logging.Logger] = None) -> Tuple[bool, Optional[str]]:
    """
    Uninstall (remove) the LaunchAgent plist file.
    
    Returns:
        (success, error_message) tuple
    """
    if not is_macos():
        return False, "LaunchAgent automation is only available on macOS"
    
    try:
        plist_path = get_launchagent_path()
        
        if not plist_path.exists():
            return True, None  # Already uninstalled
        
        plist_path.unlink()
        
        if logger:
            logger.info(f"LaunchAgent plist removed from {plist_path}")
        
        return True, None
        
    except Exception as e:
        error = f"Failed to uninstall LaunchAgent: {e}"
        if logger:
            logger.error(error)
        return False, error


def load_agent(logger: Optional[logging.Logger] = None) -> Tuple[bool, Optional[str]]:
    """
    Load the LaunchAgent (enable it).
    
    Returns:
        (success, error_message) tuple
    """
    if not is_macos():
        return False, "LaunchAgent automation is only available on macOS"
    
    try:
        plist_path = get_launchagent_path()
        
        if not plist_path.exists():
            return False, f"LaunchAgent plist not found at {plist_path}"
        
        result = subprocess.run(
            ["launchctl", "load", str(plist_path)],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode != 0:
            # launchctl load can fail if already loaded; check stderr
            if "already loaded" in result.stderr.lower():
                if logger:
                    logger.debug("LaunchAgent already loaded")
                return True, None
            
            error = f"launchctl load failed: {result.stderr.strip()}"
            if logger:
                logger.error(error)
            return False, error
        
        if logger:
            logger.info("LaunchAgent loaded successfully")
        
        return True, None
        
    except Exception as e:
        error = f"Failed to load LaunchAgent: {e}"
        if logger:
            logger.error(error)
        return False, error


def unload_agent(logger: Optional[logging.Logger] = None) -> Tuple[bool, Optional[str]]:
    """
    Unload the LaunchAgent (disable it).
    
    Returns:
        (success, error_message) tuple
    """
    if not is_macos():
        return False, "LaunchAgent automation is only available on macOS"
    
    try:
        plist_path = get_launchagent_path()
        
        result = subprocess.run(
            ["launchctl", "unload", str(plist_path)],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode != 0:
            # launchctl unload can fail if not loaded; check stderr
            if "could not find" in result.stderr.lower() or "no such" in result.stderr.lower():
                if logger:
                    logger.debug("LaunchAgent already unloaded")
                return True, None
            
            error = f"launchctl unload failed: {result.stderr.strip()}"
            if logger:
                logger.error(error)
            return False, error
        
        if logger:
            logger.info("LaunchAgent unloaded successfully")
        
        return True, None
        
    except Exception as e:
        error = f"Failed to unload LaunchAgent: {e}"
        if logger:
            logger.error(error)
        return False, error


def is_agent_loaded(logger: Optional[logging.Logger] = None) -> bool:
    """
    Check if the LaunchAgent is currently loaded.
    
    Returns:
        True if loaded, False otherwise
    """
    if not is_macos():
        return False
    
    try:
        result = subprocess.run(
            ["launchctl", "list", AGENT_LABEL],
            capture_output=True,
            text=True,
            check=False
        )
        
        return result.returncode == 0
        
    except Exception as e:
        if logger:
            logger.warning(f"Failed to check LaunchAgent status: {e}")
        return False


def get_obs_sync_executable() -> Optional[str]:
    """
    Find the obs-sync executable path.
    
    Returns:
        Full path to obs-sync, or None if not found
    """
    # Check common locations
    candidates = [
        Path.home() / ".local" / "bin" / "obs-sync",
        Path("/usr/local/bin/obs-sync"),
        Path("/opt/homebrew/bin/obs-sync"),
    ]
    
    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    
    # Fall back to `which obs-sync`
    try:
        result = subprocess.run(
            ["which", "obs-sync"],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode == 0:
            path = result.stdout.strip()
            if path:
                return path
    except Exception:
        pass
    
    return None


def describe_interval(seconds: int) -> str:
    """
    Human-readable description of an interval.
    
    Args:
        seconds: Interval in seconds
        
    Returns:
        Readable string like "every hour", "every 12 hours", etc.
    """
    if seconds < 60:
        return f"every {seconds} seconds"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"every {minutes} minute{'s' if minutes != 1 else ''}"
    elif seconds < 86400:
        hours = seconds // 3600
        return f"every {hours} hour{'s' if hours != 1 else ''}"
    else:
        days = seconds // 86400
        return f"every {days} day{'s' if days != 1 else ''}"
