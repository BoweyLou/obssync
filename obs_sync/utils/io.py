"""
Safe I/O operations with atomic writes and cooperative file locking.
"""

import contextlib
import errno
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

try:  # fcntl is only available on POSIX platforms
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None  # type: ignore


DEFAULT_LOCK_TIMEOUT = 8.0  # seconds
LOCK_SLEEP_INTERVAL = 0.05  # seconds


def _lock_file_path(path: Path) -> Path:
    """Return the companion lock file path for the target file."""
    lock_name = f"{path.name}.lock"
    return path.parent / lock_name


@contextlib.contextmanager
def _file_lock(target_path: Path, exclusive: bool, timeout: float = DEFAULT_LOCK_TIMEOUT) -> Iterator[None]:
    """Acquire a cooperative file lock around the target path.

    Uses POSIX advisory locking via fcntl when available; otherwise acts as a no-op.
    """
    if fcntl is None:
        yield
        return

    lock_path = _lock_file_path(target_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    lock_type = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    deadline = time.monotonic() + timeout if timeout is not None else None

    with open(lock_path, "a") as lock_file:
        while True:
            try:
                flags = lock_type | fcntl.LOCK_NB if deadline is not None else lock_type
                fcntl.flock(lock_file.fileno(), flags)
                break
            except OSError as exc:  # pragma: no cover - depends on timing
                if exc.errno not in (errno.EACCES, errno.EAGAIN):
                    raise
                if deadline is not None and time.monotonic() >= deadline:
                    raise TimeoutError(f"Timed out waiting for lock on {target_path}") from exc
                time.sleep(LOCK_SLEEP_INTERVAL)

        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def safe_read_json(file_path: str, default: Optional[Dict] = None, *, lock_timeout: float = DEFAULT_LOCK_TIMEOUT) -> Dict[str, Any]:
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
    path_obj = Path(file_path)

    if not path_obj.exists():
        return default

    try:
        with _file_lock(path_obj, exclusive=False, timeout=lock_timeout):
            with path_obj.open('r', encoding='utf-8') as handle:
                return json.load(handle)
    except TimeoutError as exc:
        print(f"Warning: Timed out waiting to read {file_path}: {exc}")
        return default
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Warning: Failed to read {file_path}: {exc}")
        return default


def safe_write_json(file_path: str, data: Dict[str, Any], indent: int = 2, *, lock_timeout: float = DEFAULT_LOCK_TIMEOUT) -> bool:
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
    path_obj = Path(file_path)

    # Ensure directory exists
    path_obj.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = None
    try:
        with _file_lock(path_obj, exclusive=True, timeout=lock_timeout):
            with tempfile.NamedTemporaryFile(
                mode='w',
                dir=str(path_obj.parent),
                prefix='.tmp_',
                suffix='.json',
                delete=False,
                encoding='utf-8'
            ) as tmp_file:
                json.dump(data, tmp_file, indent=indent, ensure_ascii=False, sort_keys=True)
                tmp_path = Path(tmp_file.name)

            os.replace(str(tmp_path), str(path_obj))
        return True

    except TimeoutError as exc:
        print(f"Error writing to {file_path}: {exc}")
    except Exception as exc:
        print(f"Error writing to {file_path}: {exc}")
    finally:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass

    return False


def atomic_write(file_path: str, content: str, *, lock_timeout: float = DEFAULT_LOCK_TIMEOUT) -> bool:
    """
    Atomically write content to file.

    Args:
        file_path: Path to write to
        content: Content to write
    
    Returns:
        True if successful, False otherwise
    """
    file_path = os.path.expanduser(file_path)
    path_obj = Path(file_path)

    # Ensure directory exists
    path_obj.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = None
    try:
        with _file_lock(path_obj, exclusive=True, timeout=lock_timeout):
            with tempfile.NamedTemporaryFile(
                mode='w',
                dir=str(path_obj.parent),
                prefix='.tmp_',
                delete=False,
                encoding='utf-8'
            ) as tmp_file:
                tmp_file.write(content)
                tmp_path = Path(tmp_file.name)

            os.replace(str(tmp_path), str(path_obj))
        return True

    except TimeoutError as exc:
        print(f"Error writing to {file_path}: {exc}")
    except Exception as exc:
        print(f"Error writing to {file_path}: {exc}")
    finally:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass

    return False
