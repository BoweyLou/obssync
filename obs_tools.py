#!/usr/bin/env python3
"""
obs-tools - Simplified launcher with managed virtual environment.

This bootstrap script ensures a dedicated virtual environment exists and then
executes the consolidated obs-sync CLI within it. All command routing and
argument parsing is handled by ``obs_sync.main``.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import venv
from pathlib import Path
from typing import List, Tuple

ROOT_DIR = Path(__file__).resolve().parent


def default_home() -> Path:
    """Return the default directory for managing the obs-tools venv."""
    override = os.environ.get("OBS_TOOLS_HOME")
    if override:
        return Path(override).expanduser().resolve()

    home = Path.home()
    system = platform.system()
    if system == "Darwin":
        return home / "Library" / "Application Support" / "obs-tools"
    if system == "Windows":
        return home / "AppData" / "Local" / "obs-tools"
    return home / ".local" / "share" / "obs-tools"


def venv_paths() -> Tuple[Path, Path]:
    """Return the virtualenv directory and python executable path."""
    venv_dir = default_home() / "venv"
    if platform.system() == "Windows":
        python_bin = venv_dir / "Scripts" / "python.exe"
    else:
        python_bin = venv_dir / "bin" / "python3"
    return venv_dir, python_bin


def ensure_venv(venv_dir: Path) -> None:
    """Create the venv if it does not already exist."""
    if (venv_dir / "pyvenv.cfg").exists():
        return

    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    builder = venv.EnvBuilder(with_pip=True, clear=False)
    builder.create(venv_dir)


def run_cli(argv: List[str]) -> int:
    """Execute obs_sync.main inside the managed virtual environment."""
    venv_dir, python_bin = venv_paths()
    ensure_venv(venv_dir)

    if not python_bin.exists():
        raise RuntimeError(f"Virtualenv python not found at {python_bin}")

    env = os.environ.copy()
    env.setdefault("OBS_TOOLS_HOME", str(venv_dir.parent))

    existing_path = env.get("PYTHONPATH")
    repo_path = str(ROOT_DIR)
    if existing_path:
        env["PYTHONPATH"] = os.pathsep.join([repo_path, existing_path])
    else:
        env["PYTHONPATH"] = repo_path

    cmd = [str(python_bin), "-m", "obs_sync.main", *argv]
    completed = subprocess.run(cmd, env=env)
    return completed.returncode


def main(argv: List[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        # Show help by delegating to the real CLI
        return run_cli(["--help"])

    return run_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
