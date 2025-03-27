"""
Enhanced event loop manager for PyQt6 with qasync integration.
Provides reliable lifecycle management and event loop recovery.
Updated for Python 3.12 compatibility.
"""

import asyncio
import platform
import sys
import time
import traceback
from typing import Optional, Any, Callable, Coroutine

from PyQt6.QtCore import QObject, QCoreApplication, QTimer

# Import qasync conditionally to handle potential import errors
try:
    import qasync
except ImportError:
    print("qasync module not found. Please install it with 'pip install qasync'.")
    sys.exit(1)

from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

class EventLoopManager(QObject):
    """
    Manages the asyncio event loop lifecycle when integrated with PyQt.
    Provides mechanisms to ensure the event loop stays active and recovers from errors.
    """

    def __init__(self, app=None):
        """
        Initialize the event loop manager.

        Args:
            app: The QApplication instance
        """
        super().__init__()
        self.app = app or QCoreApplication.instance()
        self.logger = get_logger(__name__ + ".EventLoopManager")

        # Event loop references
        self._main_loop = None
        self._original_policy = None
        self._loop_initialized = False
        self._loop_running = False

        # Monitoring
        self._keep_alive_timer = None
        self._monitor_timer = None
        self._health_check_timer = None
        self._recovery_attempts = 0
        self._max_recovery_attempts = 5

        # References to protect from garbage collection
        self._refs = {}

        self.logger.info("EventLoopManager initialized")

    def configure_policy(self):
        """Configure the correct event loop policy for the current platform"""
        # Save the original policy
        self._original_policy = asyncio.get_event_loop_policy()

        # Special handling for Windows
        if platform.system() == "Windows":
            try:
                # In Python 3.8+, use WindowsSelectorEventLoopPolicy
                # This is critical for Windows to avoid issues with ProactorEventLoop
                from asyncio import WindowsSelectorEventLoopPolicy
                asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())
                self.logger.info("Set Windows event loop policy to WindowsSelectorEventLoopPolicy")
            except (ImportError, AttributeError):
                # Fallback for older Python versions
                self.logger.warning("WindowsSelectorEventLoopPolicy not available, creating custom policy")

                class CustomEventLoopPolicy(asyncio.DefaultEventLoopPolicy):
                    """Custom policy that uses SelectorEventLoop on Windows"""
                    def new_event_loop(self):
                        return asyncio.SelectorEventLoop()

                asyncio.set_event_loop_policy(CustomEventLoopPolicy())
                self.logger.info("Set custom event loop policy to use SelectorEventLoop on Windows")

    def initialize(self):
        """Initialize the event loop with qasync"""
        if self._loop_initialized and self._main_loop and not self._main_loop.is_closed():
            self.logger.debug(f"Using existing qasync event loop: {id(self._main_loop)}")
            return self._main_loop

        try:
            # Configure policy first
            self.configure_policy()

            # Close any existing event loop cleanly
            try:
                existing_loop = asyncio.get_event_loop()
                if not existing_loop.is_closed():
                    self.logger.debug(f"Closing existing event loop: {id(existing_loop)}")
                    existing_loop.close()
            except RuntimeError:
                # No event loop exists, which is fine
                pass

            # Create a new event loop first
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.logger.debug(f"Created new event loop: {id(loop)}")

            # Process events to ensure Qt is ready
            if self.app:
                self.app.processEvents()

            try:
                # Try to create qasync loop with newest API
                self._main_loop = qasync.QEventLoop(self.app)
            except (TypeError, AttributeError):
                # Fallback for older qasync versions
                self.logger.debug("Older qasync API detected, trying alternate initialization")
                try:
                    self._main_loop = qasync.QEventLoop(self.app)
                except Exception as e:
                    self.logger.error(f"Failed to create QEventLoop: {str(e)}")
                    # Last resort - use standard asyncio loop
                    self._main_loop = asyncio.new_event_loop()

            # Set as the default event loop
            asyncio.set_event_loop(self._main_loop)

            # Set custom exception handler
            self._main_loop.set_exception_handler(self._exception_handler)

            # Set up health check timers
            self._setup_timers()

            # Mark as initialized
            self._loop_initialized = True
            self._loop_running = True

            self.logger.info(f"Initialized qasync event loop: {id(self._main_loop)}")

            # Process events to kickstart the loop
            if self.app:
                self.app.processEvents()

            return self._main_loop

        except Exception as e:
            self.logger.error(f"Error initializing event loop: {str(e)}", exc_info=True)
            # Try to create a minimal event loop as fallback
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                self._main_loop = loop
                return loop
            except Exception as e2:
                self.logger.critical(f"Could not create fallback event loop: {str(e2)}")
                raise

    def get_loop(self):
        """
        Get the current event loop, initializing if needed.

        Returns:
            The current asyncio event loop
        """
        if not self._loop_initialized:
            return self.initialize()

        try:
            # Try to get the current event loop
            loop = asyncio.get_event_loop()

            # Check if it's closed and recover if needed
            if loop.is_closed():
                self.logger.warning("Event loop is closed, attempting recovery")
                return self._recover_loop()

            return loop
        except RuntimeError:
            self.logger.warning("No running event loop found, reinitializing")
            return self.initialize()

    def _setup_timers(self):
        """Set up timers for keeping the event loop alive and monitoring its health"""
        # Timer to periodically create tasks to keep loop active
        self._keep_alive_timer = QTimer()
        self._keep_alive_timer.setInterval(100)  # 100ms interval
        self._keep_alive_timer.timeout.connect(self._keep_loop_alive)
        self._keep_alive_timer.start()

        # Timer to monitor event loop health
        self._monitor_timer = QTimer()
        self._monitor_timer.setInterval(1000)  # 1 second interval
        self._monitor_timer.timeout.connect(self._check_loop_health)
        self._monitor_timer.start()

        # Health check timer
        self._health_check_timer = QTimer()
        self._health_check_timer.setInterval(5000)  # 5 seconds interval
        self._health_check_timer.timeout.connect(self._deep_health_check)
        self._health_check_timer.start()

        # Store references to prevent garbage collection
        self._refs['keep_alive_timer'] = self._keep_alive_timer
        self._refs['monitor_timer'] = self._monitor_timer
        self._refs['health_check_timer'] = self._health_check_timer

    def _keep_loop_alive(self):
        """Create a dummy task to keep the event loop active"""
        if not self._main_loop or self._main_loop.is_closed():
            return

        try:
            # Create a dummy task
            async def _dummy():
                try:
                    await asyncio.sleep(0.001)
                except (RuntimeError, asyncio.CancelledError):
                    # Ignore errors from "no running event loop" or cancellation
                    pass

            # Add task to the loop - use create_task directly for simplicity
            # Don't use call_soon_threadsafe which can cause issues
            try:
                self._main_loop.create_task(_dummy())
            except RuntimeError:
                # Ignore "no running event loop" errors
                pass
        except Exception as e:
            # Ignore errors here - this is just a keepalive
            pass

    def _check_loop_health(self):
        """Check if the event loop is healthy and running"""
        try:
            # Skip if no loop is initialized
            if not self._main_loop:
                return

            # Check if loop is running
            is_running = False

            try:
                # Try to get the running loop
                asyncio.get_running_loop()
                is_running = True
            except RuntimeError:
                is_running = False

            # Special case for Windows - if we've initialized it, consider it running
            if platform.system() == "Windows" and self._loop_initialized:
                is_running = True

            # Update loop state
            self._loop_running = is_running

            # If not running, schedule a recovery attempt
            if not is_running and self._loop_initialized and not self._main_loop.is_closed():
                self.logger.warning("Event loop not running, attempting recovery")
                self._recover_loop()

        except Exception as e:
            self.logger.error(f"Error in loop health check: {str(e)}")

    def _deep_health_check(self):
        """Perform a deeper health check with an actual async task"""
        if not self._main_loop or not self._loop_initialized:
            return

        try:
            # Create a health check task
            async def _health_check():
                await asyncio.sleep(0.1)
                return True

            # Run it on the event loop
            if not self._main_loop.is_closed():
                try:
                    task = self._main_loop.create_task(_health_check())

                    # Set up a callback to verify task completion
                    def check_result(task):
                        try:
                            result = task.result()
                            if result:
                                self.logger.debug("Health check task completed successfully")
                        except (asyncio.CancelledError, Exception) as e:
                            self.logger.warning(f"Health check task failed: {str(e)}")

                    task.add_done_callback(check_result)
                except RuntimeError:
                    # Event loop might not be running
                    self.logger.warning("Event loop not running during health check")
                    self._recover_loop()
            else:
                self.logger.warning("Cannot perform health check - event loop is closed")
                self._recover_loop()

        except Exception as e:
            self.logger.error(f"Error in deep health check: {str(e)}")

    def _recover_loop(self):
        """Attempt to recover the event loop if it's closed or not running"""
        # Track recovery attempts
        self._recovery_attempts += 1

        if self._recovery_attempts > self._max_recovery_attempts:
            self.logger.error("Too many recovery attempts, giving up")
            return None

        self.logger.warning(f"Attempting to recover event loop (attempt {self._recovery_attempts}/{self._max_recovery_attempts})")

        try:
            # Reset loop and start fresh
            self._loop_initialized = False
            self._loop_running = False

            # Reinitialize the event loop
            loop = self.initialize()

            # Verify it's working
            if loop and not loop.is_closed():
                self.logger.info("Event loop successfully recovered")
                self._recovery_attempts = 0
                return loop

            return None

        except Exception as e:
            self.logger.error(f"Failed to recover event loop: {str(e)}")
            return None

    def _exception_handler(self, loop, context):
        """
        Custom exception handler for the event loop

        Args:
            loop: The event loop
            context: Exception context dictionary
        """
        exception = context.get('exception')
        message = context.get('message', 'No error message')

        if exception:
            # Handle cancellation errors differently
            if isinstance(exception, asyncio.CancelledError):
                self.logger.debug(f"Task cancelled: {message}")
                return

            # Handle Windows-specific errors
            if platform.system() == "Windows" and isinstance(exception, OSError):
                if "ERROR_ABANDONED_WAIT_0" in str(exception):
                    self.logger.debug("Windows handle abandoned error - this is normal during shutdown")
                    return

                # Handle network/socket errors
                if any(code in str(exception) for code in ["10054", "10053", "10049", "10061"]):
                    self.logger.warning(f"Network/socket error: {str(exception)}")
                    return

            # Log the error with traceback
            self.logger.error(f"Event loop error: {message}", exc_info=exception)
        else:
            # Log the error message
            self.logger.error(f"Event loop error: {message}")

        # Handle no running event loop errors
        if "no running event loop" in message.lower():
            try:
                # Reset the loop as current
                if loop and not loop.is_closed():
                    asyncio.set_event_loop(loop)
                    self.logger.debug("Reset event loop as current")
            except Exception as e:
                self.logger.error(f"Failed to reset event loop: {str(e)}")

    def run_coroutine(self, coro, callback=None, error_callback=None, timeout=None):
        """
        Run a coroutine on the event loop with proper error handling

        Args:
            coro: The coroutine to run
            callback: Optional callback for the result
            error_callback: Optional callback for errors
            timeout: Optional timeout in seconds

        Returns:
            A task object that can be used to track the coroutine
        """
        # Make sure we have an event loop
        loop = self.get_loop()

        # Make sure we have a valid coroutine
        if not asyncio.iscoroutine(coro):
            if callable(coro):
                try:
                    coro = coro()
                except Exception as e:
                    if error_callback:
                        error_callback(e)
                    return None
            else:
                if error_callback:
                    error_callback(TypeError(f"Expected a coroutine, got {type(coro)}"))
                return None

        # Verify again after potential conversion
        if not asyncio.iscoroutine(coro):
            if error_callback:
                error_callback(TypeError(f"Expected a coroutine, got {type(coro)}"))
            return None

        # Create a safe wrapper coroutine
        async def _safe_wrapper():
            try:
                # Run with timeout if specified
                if timeout:
                    try:
                        result = await asyncio.wait_for(coro, timeout)
                    except asyncio.TimeoutError:
                        if error_callback:
                            error_callback(TimeoutError(f"Operation timed out after {timeout} seconds"))
                        raise
                else:
                    result = await coro

                # Call the callback with the result
                if callback:
                    callback(result)

                return result
            except asyncio.CancelledError:
                # Task was cancelled, not an error
                raise
            except Exception as e:
                if error_callback:
                    error_callback(e)
                raise

        try:
            # Run on the event loop with proper handling
            if loop.is_closed():
                raise RuntimeError("Event loop is closed")

            # Create the task with proper Windows handling
            if platform.system() == "Windows":
                try:
                    # On Windows, use a more reliable approach
                    future = asyncio.run_coroutine_threadsafe(_safe_wrapper(), loop)

                    # Create a task-like object that supports cancellation
                    class TaskProxy:
                        def cancel(self):
                            future.cancel()

                    return TaskProxy()
                except RuntimeError:
                    # If that fails, try regular task creation
                    task = loop.create_task(_safe_wrapper())
                    return task
            else:
                # Normal case for non-Windows
                task = loop.create_task(_safe_wrapper())
                return task

        except Exception as e:
            self.logger.error(f"Error running coroutine: {str(e)}")
            if error_callback:
                error_callback(e)
            return None

    def close(self):
        """Properly close the event loop and clean up resources"""
        self.logger.info("Closing EventLoopManager")

        # Stop all timers
        for timer_name, timer in self._refs.items():
            if isinstance(timer, QTimer) and timer.isActive():
                timer.stop()

        # Clear references
        self._refs.clear()

        # Close the event loop if it exists
        if self._main_loop and not self._main_loop.is_closed():
            try:
                # Cancel all pending tasks
                try:
                    pending = asyncio.all_tasks(self._main_loop)
                    if pending:
                        self.logger.debug(f"Cancelling {len(pending)} pending tasks")
                        for task in pending:
                            task.cancel()
                except RuntimeError:
                    # No running event loop
                    pass

                # Close the loop
                self._main_loop.close()

                # Reset flags
                self._loop_initialized = False
                self._loop_running = False

                self.logger.info("Event loop closed successfully")
            except Exception as e:
                self.logger.error(f"Error closing event loop: {str(e)}")

        # Restore original event loop policy if it exists
        if self._original_policy:
            try:
                asyncio.set_event_loop_policy(self._original_policy)
                self.logger.debug("Restored original event loop policy")
            except Exception as e:
                self.logger.warning(f"Error restoring event loop policy: {str(e)}")