"""
Enhanced bridge between PyQt6 and asyncio using qasync.
Provides reliable event loop management and task execution
with specific fixes for Windows event loop issues.
"""

# Standard library imports
import asyncio
import functools
import platform
import sys
import time
import traceback
from typing import Any, Awaitable, Callable, Coroutine, Optional, Union

# Qt imports
from PyQt6.QtCore import QCoreApplication, QEventLoop, QObject, QTimer, pyqtSignal, pyqtSlot

# Third-party imports
try:
    import qasync
except ImportError:
    print("qasync module not found. Please install it with 'pip install qasync'.")
    sys.exit(1)

# Local application imports
try:
    from src.utils.logging_utils import get_logger

    logger = get_logger(__name__)
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

# Global variables to track event loop state
_main_loop = None
_loop_initialized = False
_loop_running = False
_keep_alive_timer = None
_original_policy = None
_explicit_event_processing = True  # Enable explicit event processing


def configure_event_loop_policy():
    """
    Configure the correct event loop policy based on the platform.
    On Windows, forces the use of the SelectorEventLoop instead of ProactorEventLoop.
    """
    global _original_policy

    # Save the original policy for potential restoration
    _original_policy = asyncio.get_event_loop_policy()

    # Special handling for Windows platform
    if platform.system() == "Windows":
        logger.info("Windows platform detected, configuring SelectorEventLoop")

        # Create a policy that uses SelectorEventLoop
        try:
            # In Python 3.8+, we can create a WindowsSelectorEventLoopPolicy
            from asyncio import WindowsSelectorEventLoopPolicy
            asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())
            logger.info("Set Windows event loop policy to WindowsSelectorEventLoopPolicy")
        except (ImportError, AttributeError):
            # Fallback for older Python versions
            logger.warning("WindowsSelectorEventLoopPolicy not available, creating custom policy")

            class CustomEventLoopPolicy(asyncio.DefaultEventLoopPolicy):
                """Custom event loop policy that uses SelectorEventLoop on Windows"""

                def new_event_loop(self):
                    return asyncio.SelectorEventLoop()

            asyncio.set_event_loop_policy(CustomEventLoopPolicy())
            logger.info("Set custom event loop policy to use SelectorEventLoop on Windows")


def install(application=None):
    """
    Install the Qt event loop for asyncio with robust initialization.

    Args:
        application: Optional QApplication instance

    Returns:
        The installed qasync event loop
    """
    global _main_loop, _loop_initialized, _loop_running, _keep_alive_timer, _explicit_event_processing

    # Only initialize once
    if _loop_initialized and _main_loop is not None:
        logger.debug(f"Using existing qasync event loop: {id(_main_loop)}")
        return _main_loop

    try:
        # Configure the correct event loop policy first
        configure_event_loop_policy()

        # Get application instance
        from PyQt6.QtWidgets import QApplication
        app = application or QApplication.instance()
        if app is None:
            app = QApplication([])
            logger.debug("Created new QApplication instance")

        # For Windows, close any existing event loop before creating a new one
        if platform.system() == "Windows":
            try:
                existing_loop = asyncio.get_event_loop()
                if not existing_loop.is_closed():
                    logger.debug(f"Closing existing event loop: {id(existing_loop)}")
                    existing_loop.close()
            except RuntimeError:
                # No event loop exists, which is fine
                pass

        # Create new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        logger.debug(f"Created new asyncio event loop: {id(loop)}")

        # Windows-specific setup for qasync
        if platform.system() == "Windows":
            # On Windows, we need to manually create and configure the QEventLoop
            qt_loop = QEventLoop(app)

            # Process events in the Qt loop first
            qt_loop.processEvents(QEventLoop.ProcessEventsFlag.AllEvents)

            # Create qasync loop with explicit setup
            _main_loop = qasync.QEventLoop(app)
            _main_loop._explicit_event_processing = _explicit_event_processing

            # Run a test spin of the loop to make sure it's ready
            _main_loop._process_events([])
        else:
            # Non-Windows setup is simpler
            _main_loop = qasync.QEventLoop(app)

        # Set as default asyncio loop
        asyncio.set_event_loop(_main_loop)
        logger.debug(f"Installed qasync event loop: {id(_main_loop)}")

        # Set custom exception handler for better error reporting
        _main_loop.set_exception_handler(_exception_handler)

        # Create a keep-alive timer to ensure event processing
        _keep_alive_timer = QTimer()
        _keep_alive_timer.setInterval(10)  # 10ms
        _keep_alive_timer.timeout.connect(_process_pending_events)
        _keep_alive_timer.start()

        # Store reference to prevent garbage collection
        _main_loop._keep_alive_timer = _keep_alive_timer
        app._keep_alive_timer = _keep_alive_timer  # Also store on app

        # Save a reference to the app to prevent premature garbage collection
        _main_loop._app = app

        # Mark as initialized
        _loop_initialized = True

        # Windows needs additional setup to ensure event processing
        if platform.system() == "Windows":
            # Force process events several times
            for _ in range(5):  # Increased from 3 to 5
                app.processEvents()
                time.sleep(0.02)  # Slightly increased delay (20ms)
                if hasattr(_main_loop, '_process_events'):
                    _main_loop._process_events([])

            # Create and run a no-op coroutine to kickstart the loop
            async def _init_coroutine():
                # Modern async/await syntax instead of yield from
                await asyncio.sleep(0.001)
                return True

            try:
                # Directly run a simple task to initialize the loop
                # Using run_until_complete is more reliable than create_task
                _main_loop.run_until_complete(_init_coroutine())
                _loop_running = True
                logger.debug("Initialization coroutine completed, event loop is running")
            except Exception as e:
                logger.warning(f"Failed to run initialization coroutine: {e}")
                # Even if there's an exception, we'll proceed
        # Set _loop_running flag to True once we've done what we can
        _loop_running = True

        # Add cleanup handler
        app.aboutToQuit.connect(_cleanup_event_loop)

        # Start status check timer with increased frequency on Windows
        _start_status_check(interval=500 if platform.system() == "Windows" else 1000)

        logger.info(f"qasync event loop successfully installed: {id(_main_loop)}")
        return _main_loop

    except Exception as e:
        logger.critical(f"Failed to install qasync event loop: {str(e)}")
        logger.critical(traceback.format_exc())
        raise


def _process_pending_events():
    """Process both Qt and asyncio events with improved reliability"""
    global _main_loop, _loop_running

    if _main_loop and hasattr(_main_loop, '_process_events'):
        try:
            # Process Qt events in the asyncio loop with error handling
            try:
                _main_loop._process_events([])
            except Exception as e:
                logger.warning(f"Error in _process_events: {e}")

            # On Windows, ensure the event loop is recognized as running
            if platform.system() == "Windows" and _loop_initialized:
                # Windows often has issues with asyncio.get_running_loop()
                _loop_running = True

                # Periodically trigger a no-op coroutine to keep the loop active
                if hasattr(_main_loop, 'call_soon'):
                    # This is safer than create_task for keeping the loop active
                    if not hasattr(_main_loop, '_ping_counter'):
                        _main_loop._ping_counter = 0

                    _main_loop._ping_counter += 1
                    if _main_loop._ping_counter % 10 == 0:  # Every 10 cycles
                        async def _ping():
                            await asyncio.sleep(0.001)

                        try:
                            # Using create_task as direct execution
                            # This avoids the get_running_loop check
                            _main_loop.create_task(_ping())
                        except Exception:
                            pass  # Ignore any issues with this keep-alive ping
            else:
                # Check if loop is running for non-Windows platforms
                try:
                    asyncio.get_running_loop()
                    _loop_running = True
                except RuntimeError:
                    # Only set to False on non-Windows platforms
                    if not platform.system() == "Windows":
                        _loop_running = False
                        logger.warning("Event loop is not running on non-Windows platform")

        except Exception as e:
            logger.warning(f"Error processing events: {str(e)}")


def _start_status_check(interval=1000):
    """Start a timer to periodically check and fix event loop status"""
    status_timer = QTimer()
    status_timer.setInterval(interval)  # Check interval in ms

    def check_status():
        """Check if event loop is running and fix if needed"""
        global _main_loop, _loop_running

        if _main_loop is None:
            return

        try:
            # Try to get running loop - will raise exception if not running
            try:
                asyncio.get_running_loop()
                is_running = True
            except RuntimeError:
                is_running = False

            # For Windows, apply more aggressive fixes if needed
            if platform.system() == "Windows":
                if not is_running and _loop_initialized:
                    logger.warning("Event loop not running on Windows - forcing restart")

                    # Set as current loop
                    asyncio.set_event_loop(_main_loop)

                    # Process Qt events aggressively
                    if hasattr(QCoreApplication, 'instance') and QCoreApplication.instance():
                        for _ in range(3):  # Process multiple times
                            QCoreApplication.instance().processEvents()
                            time.sleep(0.01)  # Short delay

                    # If the loop has process_events, call it directly
                    if hasattr(_main_loop, '_process_events'):
                        _main_loop._process_events([])

                    # Set flag to true - Windows needs this bypass
                    _loop_running = True

                    # Run a simple task to try to kick-start the loop
                    async def _restart_coroutine():
                        await asyncio.sleep(0.001)
                        return True

                    try:
                        # Bypass the running loop check with run_until_complete
                        _main_loop.call_soon_threadsafe(
                            lambda: _main_loop.create_task(_restart_coroutine())
                        )
                    except Exception as e:
                        logger.debug(f"Restart coroutine failed: {e}")

                    logger.debug(f"Windows loop restart attempt completed")

                # Always ensure loop_running is True on Windows
                _loop_running = True
            elif not is_running and _loop_initialized:
                # Non-Windows platform fixes
                logger.warning("Event loop not running - attempting to restart")

                # Set as current loop
                asyncio.set_event_loop(_main_loop)

                # Create a restart task
                if hasattr(_main_loop, 'run_until_complete'):
                    try:
                        async def _restart_check():
                            await asyncio.sleep(0.001)
                            return True

                        _main_loop.run_until_complete(_restart_check())
                        _loop_running = True
                        logger.debug("Event loop successfully restarted")
                    except Exception as e:
                        logger.warning(f"Failed to restart loop: {e}")

                # Process Qt events
                QCoreApplication.instance().processEvents()

                # Check if running now
                try:
                    asyncio.get_running_loop()
                    _loop_running = True
                except RuntimeError:
                    if not platform.system() == "Windows":
                        _loop_running = False

                logger.debug(f"Loop restart attempt completed, running flag: {_loop_running}")

        except Exception as e:
            logger.error(f"Error in loop status check: {str(e)}")

    status_timer.timeout.connect(check_status)
    status_timer.start()

    # Store reference to prevent garbage collection
    if _main_loop:
        _main_loop._status_timer = status_timer


def _cleanup_event_loop():
    """Clean up the event loop when the application is shutting down"""
    global _main_loop, _loop_running, _keep_alive_timer, _original_policy

    if _main_loop is not None:
        logger.debug(f"Cleaning up qasync event loop: {id(_main_loop)}")

        # Stop the keep-alive timer
        if _keep_alive_timer is not None:
            try:
                _keep_alive_timer.stop()
                if hasattr(_keep_alive_timer, 'deleteLater'):
                    _keep_alive_timer.deleteLater()
                _keep_alive_timer = None
            except Exception as e:
                logger.warning(f"Error stopping keep-alive timer: {str(e)}")

        try:
            # Cancel pending tasks
            try:
                pending = asyncio.all_tasks(_main_loop)
                if pending:
                    logger.debug(f"Cancelling {len(pending)} pending tasks")
                    for task in pending:
                        task.cancel()
            except RuntimeError:
                # Handle case where loop is not running
                pass

            # Close the loop
            if not _main_loop.is_closed():
                _main_loop.close()

            # Restore original event loop policy
            if _original_policy is not None:
                try:
                    asyncio.set_event_loop_policy(_original_policy)
                    logger.debug("Restored original event loop policy")
                except Exception as e:
                    logger.warning(f"Error restoring event loop policy: {str(e)}")

        except Exception as e:
            logger.warning(f"Error during event loop cleanup: {str(e)}")

        _loop_running = False
        logger.debug("Event loop cleanup complete")


def _exception_handler(loop, context):
    """Custom exception handler for the event loop"""
    exception = context.get('exception')
    message = context.get('message', 'No error message')

    if exception:
        if isinstance(exception, asyncio.CancelledError):
            logger.debug("Task cancelled")
        else:
            logger.error(f"Async error: {message}", exc_info=exception)
    else:
        logger.error(f"Async error: {message}")

    # On Windows, don't let event loop exceptions stop the loop
    if platform.system() == "Windows" and "no running event loop" in str(message):
        logger.warning("Ignoring 'no running event loop' error on Windows")
        # Force the loop running flag to True
        global _loop_running
        _loop_running = True


def ensure_qasync_loop():
    """
    Ensure we have a properly initialized and running qasync event loop.

    Returns:
        The qasync event loop
    """
    global _main_loop, _loop_initialized, _loop_running

    # Return existing loop if initialized
    if _loop_initialized and _main_loop is not None:
        # Set it as the current loop
        asyncio.set_event_loop(_main_loop)

        # Special handling for Windows - always assume the loop is running
        # once it's been initialized
        if platform.system() == "Windows":
            _loop_running = True

        return _main_loop

    # Install a new loop if needed
    return install()


class RunCoroutineInQt(QObject):
    """
    Helper class to run a coroutine from Qt code with proper error handling.
    """
    taskCompleted = pyqtSignal(object)
    taskError = pyqtSignal(Exception)

    def __init__(self, coro, callback=None, error_callback=None, timeout=None):
        super().__init__()
        self.coro = coro
        self.callback = callback
        self.error_callback = error_callback
        self.timeout = timeout
        self.timer = None
        self.task = None

        # Connect signals
        if callback:
            self.taskCompleted.connect(lambda result: callback(result))
        if error_callback:
            self.taskError.connect(lambda error: error_callback(error))

    def start(self):
        """Start the coroutine using qasync with improved Windows handling"""
        try:
            # Ensure we have a running event loop
            loop = ensure_qasync_loop()
            logger.debug(f"Starting task with loop: {id(loop)}")

            # Verify we have a valid coroutine
            if not asyncio.iscoroutine(self.coro):
                raise TypeError(f"Expected a coroutine, got {type(self.coro)}")

            # Set up timeout if specified
            if self.timeout:
                self.timer = QTimer()
                self.timer.setSingleShot(True)
                self.timer.timeout.connect(self._on_timeout)
                self.timer.start(int(self.timeout * 1000))

            # Special handling for Windows
            if platform.system() == "Windows":
                # Windows often has issues with the running loop check
                # Use a more direct approach for Windows
                self._windows_execute()
                return self
            else:
                # Standard approach for non-Windows platforms
                try:
                    # Create the task
                    self.task = loop.create_task(self._safe_execute())
                except RuntimeError as e:
                    if "no running event loop" in str(e):
                        # Handle event loop issues even on non-Windows
                        self._windows_execute()  # Reuse Windows technique as fallback
                        return self
                    else:
                        raise

            return self

        except Exception as e:
            logger.error(f"Error starting coroutine: {str(e)}")

            if self.error_callback:
                # Use QTimer to ensure callback runs on main thread
                QTimer.singleShot(0, lambda: self.error_callback(e))

            return None

    def _windows_execute(self):
        """Special execution strategy for Windows or fallback cases"""

        def run_and_process():
            try:
                # Get the event loop - should be already set up by ensure_qasync_loop
                loop = asyncio.get_event_loop()

                # Force running flag to True for Windows
                global _loop_running
                _loop_running = True

                # Process any pending Qt events
                if QCoreApplication.instance():
                    QCoreApplication.instance().processEvents()

                # Try several approaches to execute the coroutine
                try:
                    # Approach 1: Create a task directly
                    task = loop.create_task(self._safe_execute())

                    # Manually pump the event loop a bit
                    for _ in range(3):
                        if hasattr(loop, '_process_events'):
                            loop._process_events([])
                        QCoreApplication.instance().processEvents()
                        time.sleep(0.01)
                except Exception as e1:
                    logger.debug(f"Approach 1 failed: {e1}")

                    try:
                        # Approach 2: Use call_soon_threadsafe to schedule the task
                        loop.call_soon_threadsafe(
                            lambda: loop.create_task(self._safe_execute())
                        )
                    except Exception as e2:
                        logger.debug(f"Approach 2 failed: {e2}")

                        try:
                            # Approach 3: Use run_until_complete as a last resort
                            # This is done in a safer way to not block the UI
                            async def wrapper():
                                try:
                                    result = await self.coro
                                    # Use QTimer to call on main thread
                                    QTimer.singleShot(
                                        0, lambda: self.taskCompleted.emit(result)
                                    )
                                    return result
                                except Exception as e:
                                    # Use QTimer to call on main thread
                                    QTimer.singleShot(
                                        0, lambda: self.taskError.emit(e)
                                    )
                                    raise

                            # Run in a separate call to avoid blocking
                            QTimer.singleShot(0, lambda: loop.run_until_complete(wrapper()))
                        except Exception as e3:
                            logger.debug(f"Approach 3 failed: {e3}")
                            # If all approaches fail, report the error
                            if self.error_callback:
                                QTimer.singleShot(
                                    0, lambda: self.error_callback(Exception(f"All execution approaches failed"))
                                )
            except Exception as e:
                logger.error(f"Error in _windows_execute: {str(e)}")
                if self.error_callback:
                    QTimer.singleShot(0, lambda: self.error_callback(e))

        # Execute in main thread after a short delay
        QTimer.singleShot(10, run_and_process)

    async def _safe_execute(self):
        """Safely execute the coroutine with exception handling"""
        try:
            # Execute the coroutine
            result = await self.coro

            # Emit result signal on the main thread
            self.taskCompleted.emit(result)
            return result

        except asyncio.CancelledError:
            logger.debug("Task was cancelled")
            raise

        except Exception as e:
            logger.error(f"Error executing coroutine: {str(e)}")

            # Emit error signal
            self.taskError.emit(e)

            # Re-raise for proper task failure
            raise

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

    def cancel(self):
        """Cancel the running task"""
        if self.task and not self.task.done():
            self.task.cancel()
            logger.debug("Task cancelled by request")

        if self.timer and self.timer.isActive():
            self.timer.stop()


def run_coroutine(coro, callback=None, error_callback=None, timeout=None):
    """
    Run a coroutine from Qt code with proper error handling.

    Args:
        coro: The coroutine to run
        callback: Optional callback for result
        error_callback: Optional callback for errors
        timeout: Optional timeout in seconds

    Returns:
        A runner object that can be used to cancel the task
    """
    # Handle both coroutine and coroutine function
    if callable(coro) and not asyncio.iscoroutine(coro):
        try:
            actual_coro = coro()
        except Exception as e:
            logger.error(f"Error calling coroutine function: {str(e)}")
            if error_callback:
                QTimer.singleShot(0, lambda: error_callback(e))
            return None
    else:
        actual_coro = coro

    # Verify we have a coroutine
    if not asyncio.iscoroutine(actual_coro):
        error = TypeError(f"Expected a coroutine, got {type(actual_coro)}")
        logger.error(str(error))
        if error_callback:
            QTimer.singleShot(0, lambda: error_callback(error))
        return None

    # Create and start the runner with explicit process events on Windows
    runner = RunCoroutineInQt(actual_coro, callback, error_callback, timeout)
    result = runner.start()

    # For Windows, process events immediately
    if platform.system() == "Windows" and QCoreApplication.instance():
        QCoreApplication.instance().processEvents()

    return result


def run_sync(coro):
    """
    Run a coroutine synchronously (blocking).
    Only use this during application initialization.

    Args:
        coro: The coroutine to run

    Returns:
        The result of the coroutine
    """
    loop = ensure_qasync_loop()
    app = QCoreApplication.instance()

    # Create a future for the result
    future = asyncio.Future(loop=loop)

    async def wrapper():
        try:
            result = await coro
            future.set_result(result)
        except Exception as e:
            future.set_exception(e)

    # Windows-specific approach that bypasses the running loop check
    if platform.system() == "Windows":
        # This approach doesn't use create_task which requires running loop
        async def _sync_wrapper():
            try:
                # Use await instead of yield from
                result = await coro
                return result
            except Exception as e:
                raise e

        try:
            # Use run_until_complete which has special handling in qasync
            return loop.run_until_complete(_sync_wrapper())
        except RuntimeError as e:
            if "no running event loop" in str(e):
                # Final fallback for Windows - create a temp loop
                logger.warning("Using temporary event loop for synchronous execution")
                temp_loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(temp_loop)
                    return temp_loop.run_until_complete(coro)
                finally:
                    temp_loop.close()
                    # Restore our main loop
                    asyncio.set_event_loop(loop)
            else:
                raise
    else:
        # Standard approach for non-Windows
        task = asyncio.ensure_future(wrapper(), loop=loop)

    # Wait with timeout and process events
    timeout = 30  # 30 seconds
    start_time = time.time()

    while not future.done():
        if app:
            app.processEvents()

        # Check for timeout
        if time.time() - start_time > timeout:
            task.cancel()
            raise TimeoutError(f"Operation timed out after {timeout} seconds")

        # Process events multiple times on Windows
        if platform.system() == "Windows":
            # Process events multiple times
            for _ in range(3):
                if app:
                    app.processEvents()
                time.sleep(0.001)  # Very short delay
                # Also process the asyncio events if possible
                if hasattr(loop, '_process_events'):
                    loop._process_events([])
        else:
            # Avoid CPU hogging with a small delay
            time.sleep(0.01)

    return future.result()
