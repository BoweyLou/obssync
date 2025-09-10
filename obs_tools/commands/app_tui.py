#!/usr/bin/env python3
"""
Refactored TUI Application - Modular architecture with enhanced functionality.

This is the new modular version of the TUI that coordinates between the view,
controller, and services modules to provide a maintainable and feature-rich
terminal interface for obs-tools.

Key improvements:
- Modular architecture with clear separation of concerns
- Concurrency guards to prevent overlapping operations
- Enhanced progress tracking and observability integration
- Better error handling and user feedback
- Improved menu navigation and responsiveness
"""

from __future__ import annotations

import curses
import time
import signal
import sys
import os

# Add the project root to the path for imports
sys.path.insert(0, os.path.dirname(__file__))

from tui.view import TUIView
from tui.controller import TUIController
from tui.services import get_service_manager, get_progress_tracker


class ModularTUIApp:
    """
    Main TUI application that coordinates between view, controller, and services.
    
    This class serves as the orchestrator that brings together the modular
    components and manages the main application lifecycle.
    """
    
    def __init__(self, stdscr):
        self.stdscr = stdscr
        
        # Initialize modular components
        self.view = TUIView(stdscr)
        self.service_manager = get_service_manager()
        self.progress_tracker = get_progress_tracker()
        self.controller = TUIController(self.view, self.service_manager)
        
        # Setup signal handling for graceful shutdown
        self._setup_signal_handlers()
        
        # Performance metrics
        self.last_render_time = 0
        self.render_count = 0
        
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        def handle_sigterm(signum, frame):
            """Handle termination signals gracefully."""
            self.controller.log_line("Received termination signal - shutting down...")
            self.service_manager.cancel_current_operation()
            self.controller.is_running = False
        
        def handle_sigint(signum, frame):
            """Handle interrupt signals gracefully."""
            # If an operation is running, try to cancel it first
            if self.service_manager.is_busy():
                self.controller.log_line("Cancelling current operation...")
                if self.service_manager.cancel_current_operation():
                    return
            
            # Otherwise, initiate shutdown
            self.controller.log_line("Interrupt received - shutting down...")
            self.controller.is_running = False
        
        signal.signal(signal.SIGTERM, handle_sigterm)
        signal.signal(signal.SIGINT, handle_sigint)
    
    def run(self):
        """
        Main application loop.
        
        Coordinates between the view and controller to handle input and rendering
        while managing the application lifecycle and error recovery.
        """
        self.controller.log_line("TUI application started (modular version)")
        
        while self.controller.is_running:
            try:
                # Update busy state from service manager
                self.controller.is_busy = self.service_manager.is_busy()
                
                # Render the current state
                self._render_with_metrics()
                
                # Handle input with timeout to allow for periodic updates
                self._handle_input_with_timeout()
                
            except curses.error as e:
                # Handle curses-specific errors (terminal resize, etc.)
                self._handle_curses_error(e)
                
            except KeyboardInterrupt:
                # Handle Ctrl+C gracefully
                if self.service_manager.is_busy():
                    self.controller.log_line("Cancelling operation due to keyboard interrupt...")
                    self.service_manager.cancel_current_operation()
                else:
                    self.controller.log_line("Keyboard interrupt - shutting down...")
                    break
                    
            except Exception as e:
                # Handle unexpected errors
                self.controller.log_line(f"Unexpected error: {e}")
                self.controller.status = f"Error: {e}"
                time.sleep(0.1)  # Prevent rapid error loops
        
        self._cleanup()
    
    def _render_with_metrics(self):
        """Render the UI with performance tracking."""
        start_time = time.time()
        
        try:
            # Get current state and add service manager info
            state = self.controller.get_current_state()
            progress_info = self.service_manager.get_progress_info()
            state.update(progress_info)
            
            # Render the main screen
            self.view.draw_main_screen(state)
            
        except curses.error as e:
            # If drawing fails completely, try to recover
            self._handle_curses_error(e)
        
        # Update performance metrics
        render_time = time.time() - start_time
        self.last_render_time = render_time
        self.render_count += 1
        
        # Log slow renders for debugging
        if render_time > 0.1:  # 100ms threshold
            self.controller.log_line(f"Slow render: {render_time:.3f}s")
    
    def _handle_input_with_timeout(self):
        """Handle input with timeout to allow for periodic UI updates."""
        # Set a short timeout so we can update the UI even when no input is received
        self.view.stdscr.timeout(100)  # 100ms timeout
        
        try:
            ch = self.view.get_user_input()
            if ch == -1:  # Timeout occurred
                return
            
            # Reset cursor to original position and process input
            self.view.stdscr.timeout(-1)  # Reset to blocking
            
            # Simulate the input by ungetting it and letting controller handle it
            curses.ungetch(ch)
            if not self.controller.handle_input():
                self.controller.is_running = False
                
        except curses.error:
            # Input error, continue
            pass
        finally:
            # Always reset timeout to blocking for normal operation
            self.view.stdscr.timeout(-1)
    
    def _handle_curses_error(self, error):
        """Handle curses-specific errors with recovery attempts."""
        try:
            # Attempt to recover by refreshing terminal dimensions
            self.view.handle_resize()
            self.controller.status = f"Display recovered from error: {error}"
            
            # Try a minimal render to test recovery
            height, width = self.view.stdscr.getmaxyx()
            if height > 0 and width > 10:
                self.view.stdscr.clear()
                self.view.stdscr.addstr(0, 0, "Display Error - Attempting Recovery...")
                self.view.stdscr.refresh()
            
        except curses.error:
            # If recovery fails, log it and continue
            self.controller.log_line(f"Failed to recover from curses error: {error}")
            time.sleep(0.5)  # Give terminal time to recover
    
    def _cleanup(self):
        """Perform cleanup operations before shutdown."""
        self.controller.log_line("TUI application shutting down...")
        
        # Cancel any running operations
        if self.service_manager.is_busy():
            self.controller.log_line("Cancelling running operations...")
            self.service_manager.cancel_current_operation()
            
            # Wait briefly for cancellation
            if not self.service_manager.wait_for_completion(timeout=2.0):
                self.controller.log_line("Warning: Operation did not cancel cleanly")
        
        # Log performance statistics
        if self.render_count > 0:
            avg_render_time = self.last_render_time
            self.controller.log_line(f"Performance: {self.render_count} renders, avg: {avg_render_time:.3f}s")
        
        # Log final status
        progress_stats = self.progress_tracker.get_current_status()
        metrics = progress_stats.get("metrics", {})
        self.controller.log_line(f"Session complete: {metrics.get('operations_completed', 0)} ops completed, {metrics.get('operations_failed', 0)} failed")


def main(argv: list[str] = None) -> int:
    """Main entry point for the TUI application."""
    def _run(stdscr):
        app = ModularTUIApp(stdscr)
        app.run()

    try:
        curses.wrapper(_run)
        return 0
    except KeyboardInterrupt:
        print("Application interrupted by user", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Application failed with error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))