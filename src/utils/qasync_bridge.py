"""
Improved bridge between QML and asyncio using the qasync library.
Ensures consistent event loop usage throughout the application.
"""

import asyncio
import traceback
import functools
import sys
import time
from typing import Any, Callable, Coroutine, Optional, Union, Type, Awaitable

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer, QCoreApplication, QThread
from PyQt6.QtWidgets import QApplication

# Import qasync with better error handling
try:
    import qasync
except ImportError:
    raise ImportError("qasync module not found. Please install it with 'pip install qasync'.")

# Import logger
try:
    from src.utils.logging_utils import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

# Global reference to the main event loop
_main_loop = None
_loop_running = False  # Flag to track if the loop is properly running
_install_complete = False  # Flag to track if installation was completed
_keep_alive_timer = None  # Reference to keep-alive timer to prevent garbage collection

def install(application=None):
    """
    Install the Qt event loop for asyncio with robust initialization.

    This function properly integrates the asyncio event loop with the Qt event loop
    using qasync, ensuring they work together correctly.

    Args:
        application: Optional QApplication instance, will use the current one if not provided

    Returns:
        The installed qasync event loop
    """
    global _main_loop, _loop_running, _install_complete, _keep_alive_timer

    # Avoid multiple installations
    if _install_complete and _main_loop is not None:
        logger.debug(f"Using existing qasync event loop: {id(_main_loop)}")
        ensure_loop_running()  # Make sure the loop is actually running
        return _main_loop

    try:
        # Use the application if provided, otherwise get the current one
        app = application or QApplication.instance()
        if app is None:
            from PyQt6.QtWidgets import QApplication
            app = QApplication([])
            logger.debug("Created new QApplication instance")

        # Create the qasync event loop with specific settings
        _main_loop = qasync.QEventLoop(app)

        # Explicitly set debug if in development
        _main_loop.set_debug(True)

        # Set as the default event loop for the current thread
        asyncio.set_event_loop(_main_loop)
        logger.debug(f"Installed qasync event loop: {id(_main_loop)}")

        # Set custom exception handler to improve error reporting
        _main_loop.set_exception_handler(_exception_handler)

        # CRITICAL: Start the event loop properly
        # We need to create and run a small task to initialize internal loop state
        dummy_task = _main_loop.create_task(_dummy_coroutine())

        # Process Qt events immediately to kickstart the loop
        app.processEvents()

        # Set up a dedicated timer to keep the event loop active
        # This is crucial for reliable event loop operation
        _keep_alive_timer = QTimer()
        _keep_alive_timer.setInterval(5)  # 5ms for responsiveness
        _keep_alive_timer.timeout.connect(_process_all_events)
        _keep_alive_timer.start()

        # Store the timer as an attribute of the loop AND globally to prevent garbage collection
        _main_loop._keep_alive_timer = _keep_alive_timer

        # Mark as installed and running
        _loop_running = True
        _install_complete = True

        # Add a hook to properly clean up when the application quits
        app.aboutToQuit.connect(_cleanup_loop)

        # Create a separate periodic check to ensure the loop stays running
        _start_loop_status_check()

        logger.info(f"qasync event loop successfully installed and running: {id(_main_loop)}")
        return _main_loop
    except Exception as e:
        logger.critical(f"Failed to install qasync event loop: {str(e)}")
        logger.critical(traceback.format_exc())
        raise

async def _dummy_coroutine():
    """Dummy coroutine to help initialize the event loop"""
    await asyncio.sleep(0)

def _process_all_events():
    """Process both Qt and asyncio events to keep the loop responsive"""
    if _main_loop and hasattr(_main_loop, '_process_events'):
        try:
            # Process the Qt events in the asyncio loop
            _main_loop._process_events([])

            # Create a dummy task periodically to ensure the loop keeps running
            if asyncio.get_event_loop_policy().get_event_loop() == _main_loop:
                asyncio.ensure_future(_dummy_coroutine(), loop=_main_loop)
        except Exception as e:
            logger.warning(f"Error in event processing: {str(e)}")

def _start_loop_status_check():
    """Start a periodic check of event loop status"""
    status_timer = QTimer()
    status_timer.setInterval(1000)  # Check every second

    def check_status():
        """Check and fix event loop if needed"""
        global _loop_running

        if _main_loop is None:
            return

        try:
            # Check if loop is running
            running = _main_loop.is_running()
            if not running and _loop_running:
                logger.warning("Event loop marked as running but is not - attempting recovery")
                ensure_loop_running()
            elif not running:
                logger.warning("Event loop not running - attempting to start")
                ensure_loop_running()

            _loop_running = running
        except Exception as e:
            logger.error(f"Error in loop status check: {str(e)}")

    status_timer.timeout.connect(check_status)
    status_timer.start()

    # Store reference to prevent garbage collection
    if _main_loop:
        _main_loop._status_timer = status_timer

def _cleanup_loop():
    """Clean up the event loop when the application is shutting down"""
    global _main_loop, _loop_running, _keep_alive_timer

    if _main_loop is not None:
        logger.debug(f"Cleaning up qasync event loop: {id(_main_loop)}")

        # Stop the keep-alive timer first
        if _keep_alive_timer is not None:
            try:
                _keep_alive_timer.stop()
                if hasattr(_keep_alive_timer, 'deleteLater'):
                    _keep_alive_timer.deleteLater()
                _keep_alive_timer = None
            except Exception as e:
                logger.warning(f"Error stopping keep-alive timer: {str(e)}")

        try:
            # Stop any other timers attached to the loop
            for attr in dir(_main_loop):
                if attr.endswith('_timer') and hasattr(_main_loop, attr):
                    timer = getattr(_main_loop, attr)
                    if hasattr(timer, 'stop'):
                        timer.stop()

            # Cancel all pending tasks
            pending_tasks = asyncio.all_tasks(loop=_main_loop)
            if pending_tasks:
                logger.debug(f"Cancelling {len(pending_tasks)} pending tasks")
                for task in pending_tasks:
                    try:
                        task.cancel()
                    except:
                        pass

            # Clean up asyncgens if needed
            if not _main_loop.is_closed() and hasattr(_main_loop, 'shutdown_asyncgens'):
                try:
                    future = _main_loop.create_task(_main_loop.shutdown_asyncgens())
                    _main_loop.run_until_complete(future)
                except Exception as e:
                    logger.warning(f"Error in shutdown_asyncgens: {str(e)}")

            # Close the loop
            try:
                if not _main_loop.is_closed():
                    _main_loop.close()
            except Exception as e:
                logger.warning(f"Error closing event loop: {str(e)}")
        except Exception as e:
            logger.warning(f"Error during event loop cleanup: {str(e)}")

        _loop_running = False
        logger.debug("Event loop cleanup complete")

def _exception_handler(loop, context):
    """Custom exception handler for the event loop with improved diagnostics"""
    exception = context.get('exception')
    message = context.get('message', 'No error message')
    future = context.get('future')
    handle = context.get('handle')

    # Detailed logging
    if exception:
        logger.error(f"Async error: {message}", exc_info=exception)

        # Try to extract task information for better debugging
        if future and hasattr(future, 'get_coro'):
            try:
                coro = future.get_coro()
                logger.error(f"Occurred in coroutine: {coro.__qualname__}")
            except:
                pass
    else:
        logger.error(f"Async error: {message}")

    # Don't swallow CancelledError during cleanup
    if isinstance(exception, asyncio.CancelledError) and not loop.is_closed():
        # This is likely fine during cleanup
        logger.debug("Task cancelled")

def get_event_loop():
    """
    Get the main event loop, creating it if necessary and ensuring it's running.

    Returns:
        The qasync event loop
    """
    global _main_loop, _loop_running

    # Check if we already have a running loop
    if _main_loop is not None and _loop_running:
        return _main_loop

    try:
        # Try to get the current event loop
        current_loop = asyncio.get_event_loop()

        # Check if it's already a QEventLoop
        if isinstance(current_loop, qasync.QEventLoop):
            _main_loop = current_loop

            # Make sure it's actually running
            ensure_loop_running()
            return current_loop
        else:
            # We have a non-QEventLoop
            logger.warning(f"Found non-QEventLoop: {type(current_loop)}")
    except RuntimeError:
        # No event loop in this thread
        logger.warning("No event loop found, creating a new one.")

    # Create a new QEventLoop
    return install()

def ensure_loop_running():
    """
    Ensure the event loop is actually running.

    This is crucial as sometimes loops can be created but not running.
    """
    global _main_loop, _loop_running, _keep_alive_timer

    if _main_loop is None:
        # No loop yet, install one
        logger.debug("No event loop exists, installing one")
        install()
        return _main_loop

    # Check if the loop is running
    try:
        if hasattr(_main_loop, 'is_running') and _main_loop.is_running():
            # Loop is already running
            _loop_running = True
            return _main_loop

        # Loop exists but isn't running
        logger.debug("Event loop exists but isn't running, attempting to start it")

        # Make sure it's still the active loop for this thread
        asyncio.set_event_loop(_main_loop)

        # Create a dummy task to kickstart the loop
        _main_loop.create_task(_dummy_coroutine())

        # Process Qt events to give the loop a chance to run
        app = QCoreApplication.instance()
        if app:
            app.processEvents()

        # Restart the keep-alive timer if needed
        if not _keep_alive_timer or not _keep_alive_timer.isActive():
            if _keep_alive_timer:
                _keep_alive_timer.stop()

            _keep_alive_timer = QTimer()
            _keep_alive_timer.setInterval(5)
            _keep_alive_timer.timeout.connect(_process_all_events)
            _keep_alive_timer.start()

            # Store on the loop to prevent garbage collection
            _main_loop._keep_alive_timer = _keep_alive_timer

        # Mark as running
        _loop_running = True

        return _main_loop
    except Exception as e:
        logger.error(f"Error ensuring loop is running: {str(e)}")
        return _main_loop

def ensure_qasync_loop():
    """
    Ensure we're using the qasync event loop and return it.
    Also ensures the loop is properly running.

    Returns:
        The qasync event loop
    """
    # Get or create the loop
    loop = get_event_loop()

    # Double-check that it's actually running
    if _main_loop and not _main_loop.is_running():
        ensure_loop_running()

    return loop

class RunCoroutineInQt(QObject):
    """
    Enhanced helper class to run a coroutine from Qt code with improved reliability.

    This class provides a safe way to run async code from sync code with:
    - Robust error handling
    - Timeouts
    - Progress tracking
    - Proper event loop integration
    """
    # Define signals for communication
    taskCompleted = pyqtSignal(object)
    taskError = pyqtSignal(Exception)
    taskProgress = pyqtSignal(int)

    def __init__(self, coro, callback=None, error_callback=None, timeout=None):
        super().__init__()
        self.coro = coro
        self.callback = callback
        self.error_callback = error_callback
        self.future = None
        self.task = None
        self.timeout = timeout
        self.timeout_timer = None
        self.start_time = None

        # Connect signals to callbacks if provided
        if callback:
            self.taskCompleted.connect(lambda result: callback(result))
        if error_callback:
            self.taskError.connect(lambda error: error_callback(error))

    def start(self):
        """Start the coroutine using qasync with improved reliability"""
        try:
            # Always use a consistent event loop
            loop = ensure_qasync_loop()
            logger.debug(f"Starting task with loop: {id(loop)}")

            # Safety check - verify we have a valid coroutine
            if not asyncio.iscoroutine(self.coro):
                raise TypeError(f"Expected a coroutine, got {type(self.coro)}")

            # Record start time for monitoring
            self.start_time = time.time()

            # Set up timeout if specified
            if self.timeout:
                self.timeout_timer = QTimer()
                self.timeout_timer.setSingleShot(True)
                self.timeout_timer.timeout.connect(self._on_timeout)
                self.timeout_timer.start(int(self.timeout * 1000))

            # Create the task with our safe execution wrapper
            self.task = loop.create_task(self._safe_execute())

            # Ensure proper cleanup
            self.task.add_done_callback(self._on_task_done)

            return self
        except Exception as e:
            logger.error(f"Error starting coroutine: {str(e)}", exc_info=True)

            if self.error_callback:
                # Use a QTimer to ensure error callback runs on main thread
                QTimer.singleShot(0, lambda: self.error_callback(e))

            return None

    def cancel(self):
        """Cancel the running task with proper cleanup"""
        if self.task and not self.task.done():
            self.task.cancel()
            logger.debug("Task cancelled by request")

        if self.timeout_timer and self.timeout_timer.isActive():
            self.timeout_timer.stop()

    def _on_timeout(self):
        """Handle task timeout"""
        if self.task and not self.task.done():
            logger.warning(f"Task timed out after {self.timeout} seconds")

            # Create a timeout error
            error = TimeoutError(f"Task timed out after {self.timeout} seconds")

            # Emit the error signal
            self.taskError.emit(error)

            # Cancel the task
            self.task.cancel()

    def _on_task_done(self, future):
        """Handle task completion or failure"""
        # Stop the timeout timer if active
        if self.timeout_timer and self.timeout_timer.isActive():
            self.timeout_timer.stop()

        # Only process if we haven't already handled this via _safe_execute
        if not future.cancelled():
            try:
                # This will re-raise exceptions if any occurred
                future.result()
            except asyncio.CancelledError:
                logger.debug("Task was cancelled")
            except Exception as e:
                # Handle exception if _safe_execute didn't already do it
                logger.error(f"Task error (from done callback): {str(e)}")
                self.taskError.emit(e)

    async def _safe_execute(self):
        """Safely execute the coroutine with comprehensive exception handling"""
        try:
            # Execute the actual coroutine
            result = await self.coro

            # Calculate execution time for logging
            execution_time = time.time() - self.start_time
            logger.debug(f"Task completed in {execution_time:.3f} seconds")

            # Emit signal on the main thread for the result
            self.taskCompleted.emit(result)
            return result
        except asyncio.CancelledError:
            logger.debug("Task was cancelled during execution")
            # Let this propagate for proper cancellation
            raise
        except Exception as e:
            logger.error(f"Error executing coroutine: {str(e)}", exc_info=True)

            # Emit error signal on the main thread
            self.taskError.emit(e)

            # Re-raise to ensure the task is properly marked as failed
            raise

def run_coroutine(coro: Union[Coroutine, Callable[[], Coroutine]],
                  callback: Optional[Callable[[Any], None]] = None,
                  error_callback: Optional[Callable[[Exception], None]] = None,
                  timeout: Optional[float] = None):
    """
    Run a coroutine from Qt code with comprehensive error handling.

    This function is the central mechanism for running async code from sync code.
    It properly handles any coroutine to ensure it's executed in the qasync event loop.

    Args:
        coro: The coroutine or coroutine function to run
        callback: Optional callback to call with the result
        error_callback: Optional callback to call if an error occurs
        timeout: Optional timeout in seconds

    Returns:
        A runner object that can be used to cancel the task
    """
    # Get the coroutine object
    if callable(coro) and not asyncio.iscoroutine(coro):
        try:
            actual_coro = coro()
        except Exception as e:
            logger.error(f"Error calling coroutine function: {str(e)}")
            if error_callback:
                # Make sure callback runs on main thread
                QTimer.singleShot(0, lambda: error_callback(e))
            return None
    elif asyncio.iscoroutine(coro):
        actual_coro = coro
    else:
        error = TypeError(f"Expected a coroutine or coroutine function, got {type(coro)}")
        logger.error(str(error))
        if error_callback:
            # Make sure callback runs on main thread
            QTimer.singleShot(0, lambda: error_callback(error))
        return None

    # Get a consistent event loop and ensure it's running
    ensure_qasync_loop()

    # Create a runner to manage the coroutine execution
    runner = RunCoroutineInQt(actual_coro, callback, error_callback, timeout)
    return runner.start()

def run_sync(coro):
    """
    Run a coroutine synchronously (will block until complete)
    Only use this during application initialization or in tests.

    This implementation ensures that Qt events continue to be processed
    while waiting for the coroutine to complete.

    Args:
        coro: Coroutine to run

    Returns:
        Result of the coroutine
    """
    # Always ensure we have a running loop
    loop = ensure_qasync_loop()
    app = QCoreApplication.instance()

    # Define a custom event processing future to avoid UI freezing
    class EventProcessingFuture:
        def __init__(self, coro):
            self.coro = coro
            self.result_value = None
            self.exception = None
            self.done = False
            self.start_time = time.time()

        def _process_events(self):
            """Process Qt events to keep UI responsive"""
            if app and not app.closingDown():
                app.processEvents()
                return True
            return False

        async def _wrapped_coro(self):
            """Wrapper around the original coroutine to handle results/exceptions"""
            try:
                self.result_value = await self.coro
            except Exception as e:
                self.exception = e
            finally:
                self.done = True

        def get_result(self):
            """Block until the coroutine completes, processing Qt events while waiting"""
            # Create the task
            if loop.is_running():
                # If loop is already running, create the task
                task = loop.create_task(self._wrapped_coro())
            else:
                # Loop wasn't running, so we need to start it
                try:
                    # Set the loop as the current thread's event loop
                    asyncio.set_event_loop(loop)

                    # Create and start a task for our wrapped coroutine
                    task = asyncio.ensure_future(self._wrapped_coro(), loop=loop)
                except Exception as e:
                    logger.error(f"Error creating task in run_sync: {str(e)}")
                    raise

            # Process events while waiting for task completion
            timeout_seconds = 60  # Safety timeout
            interval_ms = 10  # Check interval
            elapsed = 0

            while not self.done and elapsed < timeout_seconds:
                if not task.done():
                    # Process Qt events while waiting
                    self._process_events()

                    # Let the loop run briefly
                    if hasattr(loop, '_process_events'):
                        loop._process_events([])

                    # Sleep briefly to avoid hogging CPU
                    time.sleep(interval_ms / 1000)
                    elapsed += interval_ms / 1000
                else:
                    # Task completed, get result
                    self.done = True
                    break

            # Handle timeout
            if not self.done:
                task.cancel()
                raise TimeoutError(f"Operation timed out after {timeout_seconds} seconds")

            # Check for exceptions
            if self.exception:
                raise self.exception

            # Return the result
            return self.result_value

    # Run the coroutine synchronously with Qt event processing
    try:
        processor = EventProcessingFuture(coro)
        return processor.get_result()
    except Exception as e:
        logger.error(f"Error in run_sync: {str(e)}")
        raise