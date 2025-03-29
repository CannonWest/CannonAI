"""
Enhanced event loop manager for PyQt6 with qasync integration.
Provides reliable lifecycle management and event loop recovery.
Updated for Python 3.12 compatibility with improved Windows support.
"""

import asyncio
import platform
import sys
import time
import traceback
from typing import Optional, Any, Callable, Coroutine, Union

from PyQt6.QtCore import QObject, QCoreApplication, QTimer

# Import qasync conditionally to handle potential import errors
try:
    import qasync
except ImportError:
    print("qasync module not found. Please install it with 'pip install qasync'.")
    sys.exit(1)

from src.utils.logging_utils import get_logger

logger = get_logger(__name__)
# In src/utils/event_loop_manager.py

# Global variable to hold the global manager instance
_GLOBAL_MANAGER = None

class EventLoopManager(QObject):
    """
    Manages the asyncio event loop lifecycle when integrated with PyQt.
    """

    def __init__(self, app=None):
        # Always call QObject.__init__
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

        # Prevent circular references
        self._protected_tasks = set()

        # References to protect from garbage collection
        self._refs = {}

        # Flag to track initialization status
        self._is_initializing = False

        self.logger.info("EventLoopManager initialized")

    def _init_instance(self):
        """Initialize instance variables (called only once)"""
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

        # Prevent circular references
        self._protected_tasks = set()

        # References to protect from garbage collection
        self._refs = {}

        # Flag to track initialization status
        self._is_initializing = False

        self.logger.info("EventLoopManager singleton initialized")

    def initialize(self):
        """Initialize the event loop with qasync with improved error handling"""
        # Do nothing if already initialized
        if self._loop_initialized and self._main_loop and not self._main_loop.is_closed():
            self.logger.debug(f"Using existing qasync event loop: {id(self._main_loop)}")
            return self._main_loop

        # Prevent multiple simultaneous initializations
        if self._is_initializing:
            self.logger.debug("Initialization already in progress, waiting...")
            # Wait for initialization to complete
            for _ in range(10):  # Try for 1 second (10 * 0.1s)
                if self._loop_initialized and self._main_loop and not self._main_loop.is_closed():
                    return self._main_loop
                time.sleep(0.1)

        self._is_initializing = True

        try:
            # Configure policy first - only do once
            self.configure_policy()

            # Skip closing existing loop - we'll take over whatever is there

            # Process events to ensure Qt is ready
            if self.app:
                self.app.processEvents()

            # IMPORTANT: Create the QEventLoop first and IMMEDIATELY set as default
            try:
                self.logger.debug("Creating qasync QEventLoop")
                # Create the qasync event loop
                self._main_loop = qasync.QEventLoop(self.app)

                # Set as the default event loop immediately
                asyncio.set_event_loop(self._main_loop)
                self.logger.debug(f"Set qasync loop as default: {id(self._main_loop)}")
            except Exception as e:
                self.logger.error(f"Failed to create QEventLoop: {str(e)}")
                # Last resort - use standard asyncio loop
                self._main_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._main_loop)

            # Set custom exception handler
            self._main_loop.set_exception_handler(self._exception_handler)

            # Set up health check timers
            self._setup_timers()

            # Create a dummy task safely to kickstart the loop
            try:
                @self._main_loop.call_soon
                def _create_dummy_task():
                    future = self._main_loop.create_future()
                    self._main_loop.call_soon(future.set_result, None)
            except Exception as e:
                self.logger.error(f"Error creating dummy task: {str(e)}")

            # Process events to ensure loop activation
            if self.app:
                self.app.processEvents()

            # Mark as initialized
            self._loop_initialized = True
            self._loop_running = True

            # Set class variable to mark singleton as initialized
            EventLoopManager._initialized = True

            self.logger.info(f"Initialized qasync event loop: {id(self._main_loop)}")
            return self._main_loop

        except Exception as e:
            self.logger.error(f"Error initializing event loop: {str(e)}", exc_info=True)
            # Try to create a minimal event loop as fallback
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                self._main_loop = loop
                self._loop_initialized = True
                return loop
            except Exception as e2:
                self.logger.critical(f"Could not create fallback event loop: {str(e2)}")
                raise
        finally:
            self._is_initializing = False

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

    # Add this method to EventLoopManager
    async def _dummy_task(self):
        """A safer dummy task that doesn't use sleep directly"""
        try:
            # Use a very small delay that doesn't rely directly on asyncio.sleep
            await asyncio.wait_for(asyncio.shield(asyncio.Future()), 0.001)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            # This is expected, we're just using the timeout to create a small delay
            pass
        except Exception:
            # Ignore any other errors - this is just a keepalive
            pass

    def get_loop(self):
        """
        Get the current event loop, initializing if needed.
        Includes improved error checking and recovery.

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

    def run_during_init(self, coro, callback=None, error_callback=None):
        """
        Special method to run coroutines during initialization before the main event loop is running.
        Uses run_coroutine_threadsafe which doesn't require a running loop.

        Args:
            coro: The coroutine to run
            callback: Optional callback for the result
            error_callback: Optional callback for errors

        Returns:
            A Future-like object that can be used to get the result
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
            # Use run_coroutine_threadsafe which doesn't require a running loop
            future = asyncio.run_coroutine_threadsafe(_safe_wrapper(), loop)

            # Create a task-like object for compatibility
            class TaskLike:
                def cancel(self):
                    future.cancel()

                def result(self, timeout=None):
                    return future.result(timeout)

            return TaskLike()
        except Exception as e:
            self.logger.error(f"Error in run_during_init: {str(e)}")
            if error_callback:
                error_callback(e)
            return None

    def init_async_service(self, service, init_method='initialize', timeout=5.0):
        """
        Safely initialize an async service during application startup
        with improved error handling and fallback mechanisms.

        Args:
            service: The service object to initialize
            init_method: The name of the initialization method
            timeout: Maximum time to wait for initialization (seconds)

        Returns:
            True if initialization was successful, False otherwise
        """
        # Validate we have the required attributes
        if not hasattr(self, 'app') or self.app is None:
            self.logger.error("No app reference available for EventLoopManager")
            return False

        if not hasattr(service, init_method):
            self.logger.error(f"Service does not have '{init_method}' method")
            return False

        method = getattr(service, init_method)
        if not callable(method):
            self.logger.error(f"'{init_method}' is not callable")
            return False

        success = [False]  # Use list to allow modification from callback

        def on_success(result):
            success[0] = bool(result)
            self.logger.info(f"Service {service.__class__.__name__} initialized: {result}")

        def on_error(error):
            self.logger.error(f"Error initializing {service.__class__.__name__}: {str(error)}")

        # Use run_during_init to safely initialize without requiring a running loop
        task = self.run_during_init(
            method(),
            callback=on_success,
            error_callback=on_error
        )

        # Process events to help task completion
        end_time = time.time() + timeout
        while time.time() < end_time and not success[0]:
            if self.app:
                self.app.processEvents()
            time.sleep(0.05)

        # Special handling for Windows: try direct synchronous initialization if async approach fails
        if not success[0] and platform.system() == "Windows":
            try:
                self.logger.warning(f"Trying direct synchronous initialization for {service.__class__.__name__}")
                # Create a new event loop for direct execution
                direct_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(direct_loop)

                try:
                    result = direct_loop.run_until_complete(method())
                    success[0] = bool(result)
                    self.logger.info(f"Direct initialization of {service.__class__.__name__}: {result}")
                finally:
                    direct_loop.close()
            except Exception as e:
                self.logger.error(f"Error in direct initialization: {str(e)}")

        return success[0]

    def _setup_timers(self):
        """Set up timers for keeping the event loop alive and monitoring its health"""
        # Timer to periodically create tasks to keep loop active
        self._keep_alive_timer = QTimer()
        self._keep_alive_timer.setInterval(50)  # Reduced from 100ms to 50ms for more responsiveness
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
        """Create a dummy task to keep the event loop active with better error handling"""
        if not self._main_loop or self._main_loop.is_closed():
            return

        try:
            # Create a dummy task
            async def _dummy():
                try:
                    await asyncio.sleep(0.001)
                except (RuntimeError, asyncio.CancelledError, Exception):
                    # Ignore all errors - this is just a keepalive
                    pass

            # Add task to the loop - use call_soon_threadsafe for thread safety
            try:
                @self._main_loop.call_soon_threadsafe
                def _create_task():
                    try:
                        task = self._main_loop.create_task(_dummy())
                        # Don't track the task's completion - we don't care
                        task.add_done_callback(lambda _: None)
                    except Exception:
                        # Ignore all errors
                        pass
            except Exception:
                # Ignore errors here - this is just a keepalive
                pass
        except Exception:
            # Ignore all exceptions in keepalive
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
                try:
                    asyncio.get_running_loop()
                    is_running = True
                except RuntimeError:
                    is_running = False
            except Exception:
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
                    @self._main_loop.call_soon_threadsafe
                    def _create_task():
                        try:
                            task = self._main_loop.create_task(_health_check())

                            # Set up a callback to verify task completion
                            def check_result(task):
                                try:
                                    if task.done():
                                        if not task.cancelled():
                                            result = task.result()
                                            if result:
                                                self.logger.debug("Health check task completed successfully")
                                except Exception as e:
                                    self.logger.warning(f"Health check task error: {str(e)}")

                            task.add_done_callback(check_result)
                        except Exception as e:
                            self.logger.warning(f"Error creating health check task: {str(e)}")
                except Exception as e:
                    self.logger.warning(f"Error scheduling health check: {str(e)}")
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
                if hasattr(exception, 'winerror'):
                    if exception.winerror in (6, 995, 996, 121):  # Common Windows errors during operation
                        self.logger.debug(f"Windows-specific error: {str(exception)}")
                        return

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
                else:
                    # Try to recover with a new loop
                    new_loop = self.initialize()
                    if new_loop and not new_loop.is_closed():
                        asyncio.set_event_loop(new_loop)
                        self.logger.debug("Created new event loop to replace closed one")
            except Exception as e:
                self.logger.error(f"Failed to reset event loop: {str(e)}")

    def run_coroutine(self, coro, callback=None, error_callback=None, timeout=None):
        """
        Run a coroutine on the event loop with proper error handling
        and improved Windows compatibility.

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

        # IMPORTANT: Create a new coroutine instance for the wrapper to avoid
        # "cannot reuse already awaited coroutine" errors
        # We must be careful not to directly await the original coroutine here
        async def _safe_wrapper():
            local_coro = coro  # Reference the outer coroutine but don't await yet

            try:
                # Run with timeout if specified
                if timeout:
                    try:
                        result = await asyncio.wait_for(local_coro, timeout)
                    except asyncio.TimeoutError:
                        if error_callback:
                            error_callback(TimeoutError(f"Operation timed out after {timeout} seconds"))
                        raise
                else:
                    result = await local_coro

                # Call the callback with the result
                if callback:
                    callback(result)

                return result
            except asyncio.CancelledError:
                # Task was cancelled, not an error
                raise
            except Exception as e:
                self.logger.error(f"Error in _safe_wrapper: {str(e)}", exc_info=True)
                if error_callback:
                    error_callback(e)
                raise

        try:
            # Windows requires special handling
            if platform.system() == "Windows":
                # Skip if the loop is closed
                if loop.is_closed():
                    if error_callback:
                        error_callback(RuntimeError("Event loop is closed"))
                    return None

                try:
                    # Create the task safely to avoid "no running event loop" errors
                    task = loop.create_task(_safe_wrapper())

                    # Keep track of the task in our protected set
                    self._protected_tasks.add(task)

                    # Add cleanup callback to remove from protected set when done
                    def _cleanup_task(task):
                        if task in self._protected_tasks:
                            self._protected_tasks.remove(task)

                    task.add_done_callback(_cleanup_task)
                    return task
                except RuntimeError as e:
                    # If we get "no running event loop", try threadsafe approach
                    if "no running event loop" in str(e):
                        try:
                            # Direct threadsafe call
                            future = asyncio.run_coroutine_threadsafe(_safe_wrapper(), loop)

                            # Create a task-like interface
                            class TaskProxy:
                                def cancel(self):
                                    future.cancel()

                                def add_done_callback(self, callback):
                                    future.add_done_callback(callback)

                            return TaskProxy()
                        except Exception as inner_e:
                            self.logger.error(f"Failed to run task via threadsafe approach: {str(inner_e)}")
                            if error_callback:
                                error_callback(inner_e)
                            return None
                    else:
                        # Other RuntimeError
                        self.logger.error(f"RuntimeError in task creation: {str(e)}")
                        if error_callback:
                            error_callback(e)
                        return None
            else:
                # Non-Windows platforms
                if loop.is_closed():
                    raise RuntimeError("Event loop is closed")

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

        # Cancel all protected tasks
        for task in list(self._protected_tasks):
            try:
                if not task.done():
                    task.cancel()
            except Exception:
                pass

        self._protected_tasks.clear()

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

# Function to get the global instance - no class methods involved
def get_global_manager(app=None):
    """Get the global EventLoopManager instance"""
    global _GLOBAL_MANAGER
    if _GLOBAL_MANAGER is None:
        _GLOBAL_MANAGER = EventLoopManager(app)
    return _GLOBAL_MANAGER