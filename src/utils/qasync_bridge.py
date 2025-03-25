"""
Enhanced bridge between PyQt6 and asyncio using qasync.
Provides reliable event loop management and task execution.
"""

import asyncio
import functools
import sys
import time
import traceback
from typing import Any, Callable, Coroutine, Optional, Union, Awaitable

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer, QCoreApplication

# Import qasync with better error handling
try:
    import qasync
except ImportError:
    print("qasync module not found. Please install it with 'pip install qasync'.")
    sys.exit(1)

# Import logger
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


def install(application=None):
    """
    Install the Qt event loop for asyncio with robust initialization.

    Args:
        application: Optional QApplication instance

    Returns:
        The installed qasync event loop
    """
    global _main_loop, _loop_initialized, _loop_running, _keep_alive_timer

    # Only initialize once
    if _loop_initialized and _main_loop is not None:
        logger.debug(f"Using existing qasync event loop: {id(_main_loop)}")
        return _main_loop

    try:
        # Get application instance
        from PyQt6.QtWidgets import QApplication
        app = application or QApplication.instance()
        if app is None:
            app = QApplication([])
            logger.debug("Created new QApplication instance")

        # Create and set the event loop
        _main_loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(_main_loop)
        logger.debug(f"Installed qasync event loop: {id(_main_loop)}")

        # Set custom exception handler
        _main_loop.set_exception_handler(_exception_handler)

        # Create a keep-alive timer to ensure event processing
        _keep_alive_timer = QTimer()
        _keep_alive_timer.setInterval(10)  # 10ms
        _keep_alive_timer.timeout.connect(_process_pending_events)
        _keep_alive_timer.start()

        # Store reference to prevent garbage collection
        _main_loop._keep_alive_timer = _keep_alive_timer

        # Mark as initialized
        _loop_initialized = True

        # Process events to kick-start the loop
        app.processEvents()

        # Create a dummy task to help initialize the loop
        asyncio.ensure_future(_dummy_coroutine(), loop=_main_loop)

        # Process events again after creating the task
        app.processEvents()

        # Add cleanup handler
        app.aboutToQuit.connect(_cleanup_event_loop)

        # Start status check timer
        _start_status_check()

        logger.info(f"qasync event loop successfully installed: {id(_main_loop)}")
        return _main_loop

    except Exception as e:
        logger.critical(f"Failed to install qasync event loop: {str(e)}")
        logger.critical(traceback.format_exc())
        raise


async def _dummy_coroutine():
    """Dummy coroutine to help initialize the event loop"""
    try:
        await asyncio.sleep(0.01)
        global _loop_running
        _loop_running = True
    except Exception as e:
        logger.error(f"Error in dummy coroutine: {str(e)}")


def _process_pending_events():
    """Process both Qt and asyncio events"""
    global _main_loop, _loop_running

    if _main_loop and hasattr(_main_loop, '_process_events'):
        try:
            # Process Qt events in the asyncio loop
            _main_loop._process_events([])

            # Check if loop is now running
            if _main_loop.is_running():
                _loop_running = True

            # Create a dummy task periodically
            if _loop_running and asyncio.get_event_loop() == _main_loop:
                try:
                    asyncio.ensure_future(_dummy_coroutine(), loop=_main_loop)
                except RuntimeError:
                    # This should not happen with proper initialization
                    pass
        except Exception as e:
            logger.warning(f"Error processing events: {str(e)}")


def _start_status_check():
    """Start a timer to periodically check and fix event loop status"""
    status_timer = QTimer()
    status_timer.setInterval(1000)  # Check every second

    def check_status():
        """Check if event loop is running and fix if needed"""
        global _main_loop, _loop_running

        if _main_loop is None:
            return

        try:
            # Check if loop is running
            is_running = _main_loop.is_running()

            if not is_running and _loop_initialized:
                logger.warning("Event loop not running - attempting to restart")

                # Set as current loop
                asyncio.set_event_loop(_main_loop)

                # Create a dummy task
                asyncio.ensure_future(_dummy_coroutine(), loop=_main_loop)

                # Process Qt events
                QCoreApplication.instance().processEvents()

                # Update status
                _loop_running = _main_loop.is_running()

                logger.debug(f"Loop restart attempt completed, running: {_loop_running}")

        except Exception as e:
            logger.error(f"Error in loop status check: {str(e)}")

    status_timer.timeout.connect(check_status)
    status_timer.start()

    # Store reference to prevent garbage collection
    if _main_loop:
        _main_loop._status_timer = status_timer


def _cleanup_event_loop():
    """Clean up the event loop when the application is shutting down"""
    global _main_loop, _loop_running, _keep_alive_timer

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
            pending = asyncio.all_tasks(_main_loop)
            if pending:
                logger.debug(f"Cancelling {len(pending)} pending tasks")
                for task in pending:
                    task.cancel()

            # Close the loop
            if not _main_loop.is_closed():
                _main_loop.close()

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
        """Start the coroutine using qasync"""
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

            # Create the task
            self.task = loop.create_task(self._safe_execute())

            return self

        except Exception as e:
            logger.error(f"Error starting coroutine: {str(e)}")

            if self.error_callback:
                # Use QTimer to ensure callback runs on main thread
                QTimer.singleShot(0, lambda: self.error_callback(e))

            return None

    def cancel(self):
        """Cancel the running task"""
        if self.task and not self.task.done():
            self.task.cancel()
            logger.debug("Task cancelled by request")

        if self.timer and self.timer.isActive():
            self.timer.stop()

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

    # Create and start the runner
    runner = RunCoroutineInQt(actual_coro, callback, error_callback, timeout)
    return runner.start()


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

    # Create task
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

        # Avoid CPU hogging
        time.sleep(0.01)

    return future.result()