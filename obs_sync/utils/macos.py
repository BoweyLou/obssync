"""macOS-specific helpers."""

from __future__ import annotations

import logging
import platform
from typing import Optional


def set_process_name(name: str, logger: Optional[logging.Logger] = None) -> bool:
    """Set the current process name on macOS when PyObjC is available."""
    if platform.system() != "Darwin":
        return False

    try:
        from Foundation import NSProcessInfo  # type: ignore
    except ImportError:
        if logger:
            logger.debug("PyObjC not installed; cannot set process name")
        return False
    except Exception as exc:  # pragma: no cover - defensive
        if logger:
            logger.warning("Unexpected error importing Foundation: %s", exc)
        return False

    try:
        process_info = NSProcessInfo.processInfo()
        current_name = process_info.processName()
        if current_name == name:
            return True
        process_info.setProcessName_(name)
        return True
    except Exception as exc:  # pragma: no cover - defensive
        if logger:
            logger.warning("Failed to set process name: %s", exc)
        return False
