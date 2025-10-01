"""Utilities for managing the obs-sync dedicated virtual environment."""
from __future__ import annotations

import os
import platform
import subprocess
import sys
import venv
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Tuple

MANAGED_HOME_ENV = "OBS_TOOLS_HOME"


def repo_root() -> Path:
    """Return the repository root based on the module location."""
    return Path(__file__).resolve().parent.parent.parent


def _env_with_overrides(overrides: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    """Merge os.environ with optional overrides, prioritising the overrides."""
    env = os.environ.copy()
    if overrides:
        env.update(overrides)
    return env


def default_home(env: Optional[Mapping[str, str]] = None) -> Path:
    """Return the base directory that stores the managed virtual environment."""
    environ = os.environ if env is None else env
    override = environ.get(MANAGED_HOME_ENV)
    if override:
        return Path(override).expanduser().resolve()

    home = Path.home()
    system = platform.system()
    if system == "Darwin":
        return home / "Library" / "Application Support" / "obs-tools"
    if system == "Windows":
        return home / "AppData" / "Local" / "obs-tools"
    return home / ".local" / "share" / "obs-tools"


def venv_paths(env: Optional[Mapping[str, str]] = None) -> Tuple[Path, Path]:
    """Return the managed virtualenv directory and its Python executable."""
    venv_dir = default_home(env) / "venv"
    if platform.system() == "Windows":
        python_bin = venv_dir / "Scripts" / "python.exe"
    else:
        python_bin = venv_dir / "bin" / "python3"
    return venv_dir, python_bin


def ensure_venv(venv_dir: Path) -> None:
    """Create the managed virtual environment when it does not already exist."""
    if (venv_dir / "pyvenv.cfg").exists():
        return

    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    builder = venv.EnvBuilder(with_pip=True, clear=False)
    builder.create(venv_dir)


def build_env(repo: Optional[Path] = None, overrides: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    """Construct the subprocess environment for running inside the managed venv."""
    env = _env_with_overrides(overrides)
    env.setdefault(MANAGED_HOME_ENV, str(default_home(env)))

    repo_path = str(repo or repo_root())
    existing_path = env.get("PYTHONPATH")
    if existing_path:
        env["PYTHONPATH"] = os.pathsep.join([repo_path, existing_path])
    else:
        env["PYTHONPATH"] = repo_path

    return env


def run_module(module: str, argv: Iterable[str], overrides: Optional[Mapping[str, str]] = None) -> int:
    """Run a Python module entry point inside the managed virtual environment."""
    env = _env_with_overrides(overrides)
    venv_dir, python_bin = venv_paths(env)
    ensure_venv(venv_dir)

    if not python_bin.exists():
        raise RuntimeError(f"Managed virtualenv Python executable missing at {python_bin}")

    command = [str(python_bin), "-m", module, *argv]
    completed = subprocess.run(command, env=build_env(overrides=overrides))
    return completed.returncode


def run_obs_sync(argv: Iterable[str]) -> int:
    """Convenience wrapper for launching ``obs_sync.main`` inside the managed venv."""
    return run_module("obs_sync.main", list(argv))


def python_path(overrides: Optional[Mapping[str, str]] = None) -> Path:
    """Return the path to the managed virtualenv's Python interpreter."""
    env = _env_with_overrides(overrides)
    venv_dir, python_bin = venv_paths(env)
    ensure_venv(venv_dir)
    return python_bin


if __name__ == "__main__":  # pragma: no cover - debug helper
    sys.exit(run_obs_sync(sys.argv[1:]))
