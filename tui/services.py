#!/usr/bin/env python3
"""
TUI Services Module - Handles subprocess orchestration and progress tracking.

This module provides subprocess management with concurrency controls,
progress tracking, and proper integration with the observability system.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
import signal
from typing import List, Callable, Optional, Any
from pathlib import Path
import curses


class ServiceManager:
    """
    Manages subprocess execution with concurrency controls and progress tracking.
    
    Provides thread-safe subprocess execution, prevents overlapping operations,
    and integrates with the TUI's progress tracking and logging systems.
    """
    
    def __init__(self):
        self._running_processes = {}
        self._operation_lock = threading.Lock()
        self._current_operation = None
        self._operation_thread = None
        self._cancel_requested = False
    
    def is_busy(self) -> bool:
        """Check if any operation is currently running."""
        with self._operation_lock:
            return self._current_operation is not None
    
    def get_current_operation(self) -> Optional[str]:
        """Get the name of the currently running operation."""
        with self._operation_lock:
            return self._current_operation
    
    def cancel_current_operation(self) -> bool:
        """
        Attempt to cancel the currently running operation.
        
        Returns:
            True if cancellation was attempted, False if no operation is running.
        """
        with self._operation_lock:
            if self._current_operation is None:
                return False
            
            self._cancel_requested = True
            
            # Try to terminate running processes
            terminated_count = 0
            for proc_name, proc in self._running_processes.items():
                try:
                    proc.terminate()
                    terminated_count += 1
                except ProcessLookupError:
                    pass  # Process already terminated
                except Exception:
                    pass  # Best effort
            
            return True
    
    def run_command(self, args: List[str], log_callback: Callable[[str], None], 
                   completion_callback: Optional[Callable[[], None]] = None):
        """
        Run a command asynchronously with concurrency protection.
        
        Args:
            args: Command and arguments to execute
            log_callback: Function to call for logging output
            completion_callback: Optional function to call when complete
        """
        if self.is_busy():
            log_callback("Operation already in progress - request ignored")
            return
        
        operation_name = self._extract_operation_name(args)
        
        def run_in_thread():
            self._run_command_impl(args, log_callback, completion_callback, operation_name)
        
        with self._operation_lock:
            self._current_operation = operation_name
            self._cancel_requested = False
            self._operation_thread = threading.Thread(target=run_in_thread, daemon=True)
            self._operation_thread.start()
    
    def run_interactive(self, args: List[str], title: str, view, log_callback: Callable[[str], None]):
        """
        Run a command interactively by temporarily handing control to the subprocess.
        
        Args:
            args: Command and arguments to execute
            title: Human-readable title for the operation
            view: TUI view instance for curses management
            log_callback: Function to call for logging
        """
        log_callback("Interactive: " + " ".join(args))
        
        # Clean up curses for subprocess
        view.cleanup_curses_for_subprocess()
        
        try:
            # Run the subprocess with full terminal access
            result = subprocess.call(args)
            log_callback(f"Interactive command completed with exit code {result}")
        except KeyboardInterrupt:
            log_callback("Interactive command interrupted by user")
        except Exception as e:
            log_callback(f"Interactive command failed: {e}")
        finally:
            # Restore curses UI
            view.restore_curses_after_subprocess()
    
    def _run_command_impl(self, args: List[str], log_callback: Callable[[str], None],
                         completion_callback: Optional[Callable[[], None]], operation_name: str):
        """Internal implementation of command execution."""
        try:
            log_callback("Running: " + " ".join(args))
            
            # Start the subprocess
            proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
                universal_newlines=True
            )
            
            # Register the process for potential cancellation
            with self._operation_lock:
                self._running_processes[operation_name] = proc
            
            # Read output in real-time
            self._stream_output(proc, log_callback)
            
            # Wait for completion
            return_code = proc.wait()
            
            # Log completion
            if self._cancel_requested:
                log_callback(f"Operation cancelled (exit {return_code})")
                # Update progress tracker if we have it
                try:
                    progress_tracker = get_progress_tracker()
                    progress_tracker.cancel_operation(operation_name)
                except Exception:
                    pass
            else:
                log_callback(f"Completed (exit {return_code})")
                
                # Call completion callback on success
                if return_code == 0 and completion_callback:
                    completion_callback()
        
        except Exception as e:
            log_callback(f"Exception: {e}")
        
        finally:
            # Clean up
            with self._operation_lock:
                self._running_processes.pop(operation_name, None)
                self._current_operation = None
                self._cancel_requested = False
    
    def _stream_output(self, proc: subprocess.Popen, log_callback: Callable[[str], None]):
        """Stream subprocess output to log in real-time."""
        # Use threading to read both stdout and stderr simultaneously
        stdout_lines = []
        stderr_lines = []
        stdout_done = threading.Event()
        stderr_done = threading.Event()
        
        def read_stdout():
            try:
                for line in proc.stdout:
                    if line:
                        line = line.rstrip()
                        stdout_lines.append(line)
                        log_callback(line)
            except Exception:
                pass
            finally:
                stdout_done.set()
        
        def read_stderr():
            try:
                for line in proc.stderr:
                    if line:
                        line = line.rstrip()
                        stderr_lines.append(line)
                        log_callback("ERR: " + line)
            except Exception:
                pass
            finally:
                stderr_done.set()
        
        # Start reader threads
        stdout_thread = threading.Thread(target=read_stdout, daemon=True)
        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        
        stdout_thread.start()
        stderr_thread.start()
        
        # Wait for both to complete or process to finish
        while proc.poll() is None:
            time.sleep(0.1)
            if self._cancel_requested:
                try:
                    proc.terminate()
                    time.sleep(0.5)  # Give it time to terminate gracefully
                    if proc.poll() is None:
                        proc.kill()  # Force kill if still running
                except Exception:
                    pass
                break
        
        # Wait for reader threads to finish (with timeout)
        stdout_done.wait(timeout=1.0)
        stderr_done.wait(timeout=1.0)
    
    def _extract_operation_name(self, args: List[str]) -> str:
        """Extract a human-readable operation name from command arguments."""
        if not args:
            return "unknown"
        
        script_name = Path(args[0]).stem
        if script_name == "python3" and len(args) > 1:
            script_name = Path(args[1]).stem
        
        # Map script names to operation names
        operation_map = {
            "collect_obsidian_tasks": "collect_obsidian",
            "collect_reminders_tasks": "collect_reminders", 
            "build_sync_links": "build_links",
            "obs_tools": "obs_tools",
            "discover_obsidian_vaults": "discover_vaults",
            "find_duplicate_tasks": "find_duplicates",
            "fix_obsidian_block_ids": "fix_block_ids",
            "reset_obs_tools": "reset"
        }
        
        operation = operation_map.get(script_name, script_name)
        
        # Add subcommand if present for obs_tools
        if script_name == "obs_tools" and len(args) > 2:
            subcommand = args[2]
            operation = f"{operation}_{subcommand}"
        
        return operation
    
    def get_progress_info(self) -> dict:
        """
        Get current progress information for display.
        
        Returns:
            Dictionary with progress information including:
            - is_running: bool
            - operation_name: str
            - can_cancel: bool
        """
        with self._operation_lock:
            return {
                "is_running": self._current_operation is not None,
                "operation_name": self._current_operation,
                "can_cancel": self._current_operation is not None and not self._cancel_requested,
                "cancel_requested": self._cancel_requested
            }
    
    def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for the current operation to complete.
        
        Args:
            timeout: Optional timeout in seconds
            
        Returns:
            True if operation completed, False if timeout occurred
        """
        if not self.is_busy():
            return True
        
        thread = None
        with self._operation_lock:
            thread = self._operation_thread
        
        if thread:
            thread.join(timeout)
            return not thread.is_alive()
        
        return True


class ProgressTracker:
    """
    Enhanced progress tracking for long-running operations.
    
    Integrates with the obs-tools observability system to provide
    detailed progress information and metrics.
    """
    
    def __init__(self):
        self.current_operations = {}
        self.operation_history = []
        self.metrics = {
            "operations_started": 0,
            "operations_completed": 0,
            "operations_failed": 0,
            "operations_cancelled": 0
        }
    
    def start_operation(self, operation_id: str, operation_type: str, details: dict = None):
        """Start tracking a new operation."""
        self.current_operations[operation_id] = {
            "type": operation_type,
            "start_time": time.time(),
            "details": details or {},
            "progress": 0.0,
            "status": "running",
            "logs": []
        }
        self.metrics["operations_started"] += 1
    
    def update_progress(self, operation_id: str, progress: float, message: str = ""):
        """Update progress for an operation."""
        if operation_id in self.current_operations:
            op = self.current_operations[operation_id]
            op["progress"] = max(0.0, min(1.0, progress))
            if message:
                op["logs"].append({
                    "timestamp": time.time(),
                    "message": message
                })
    
    def complete_operation(self, operation_id: str, success: bool = True, final_message: str = ""):
        """Mark an operation as completed."""
        if operation_id not in self.current_operations:
            return
        
        op = self.current_operations[operation_id]
        op["end_time"] = time.time()
        op["duration"] = op["end_time"] - op["start_time"]
        op["status"] = "completed" if success else "failed"
        op["progress"] = 1.0 if success else op["progress"]
        
        if final_message:
            op["logs"].append({
                "timestamp": time.time(),
                "message": final_message
            })
        
        # Move to history
        self.operation_history.append(op)
        del self.current_operations[operation_id]
        
        # Update metrics
        if success:
            self.metrics["operations_completed"] += 1
        else:
            self.metrics["operations_failed"] += 1
    
    def cancel_operation(self, operation_id: str):
        """Mark an operation as cancelled."""
        if operation_id not in self.current_operations:
            return
        
        op = self.current_operations[operation_id]
        op["end_time"] = time.time()
        op["duration"] = op["end_time"] - op["start_time"]
        op["status"] = "cancelled"
        
        # Move to history
        self.operation_history.append(op)
        del self.current_operations[operation_id]
        
        # Update metrics
        self.metrics["operations_cancelled"] += 1
    
    def get_current_status(self) -> dict:
        """Get current status of all operations."""
        return {
            "active_operations": dict(self.current_operations),
            "metrics": dict(self.metrics),
            "recent_history": self.operation_history[-10:]  # Last 10 operations
        }
    
    def cleanup_history(self, max_entries: int = 100):
        """Clean up operation history to prevent memory growth."""
        if len(self.operation_history) > max_entries:
            self.operation_history = self.operation_history[-max_entries:]


# Global instances for use by the TUI
_service_manager = ServiceManager()
_progress_tracker = ProgressTracker()


def get_service_manager() -> ServiceManager:
    """Get the global service manager instance."""
    return _service_manager


def get_progress_tracker() -> ProgressTracker:
    """Get the global progress tracker instance."""
    return _progress_tracker