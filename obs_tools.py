#!/usr/bin/env python3
"""
obs-tools - Simplified launcher with managed virtual environment.

This bootstrap script ensures a dedicated virtual environment exists and then
executes the consolidated obs-sync CLI within it. All command routing and
argument parsing is handled by ``obs_sync.main``.
"""

from __future__ import annotations

import sys
from typing import List

# Import the shared venv helper - handles all bootstrap logic
from obs_sync.utils.venv import run_obs_sync


def main(argv: List[str] | None = None) -> int:
    """Entry point that delegates to obs_sync.main inside managed venv."""
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        # Show help by delegating to the real CLI
        return run_obs_sync(["--help"])

    return run_obs_sync(argv)


if __name__ == "__main__":
    raise SystemExit(main())
