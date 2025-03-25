"""
Improved bridge between QML and asyncio using the qasync library.
Ensures consistent event loop usage throughout the application.
"""

import asyncio
import traceback
import functools
import sys
from typing import Any, Callable, Coroutine, Optional, Union, Type, Awaitable

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer, QCoreApplication

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
_install_complete = False # Flag to track if installation was completed

def install(application=None):
    """
    Install the Qt event loop for asyncio with improved initialization

    This function properly integrates the asyncio event loop with the Qt event loop
    using qasync, ensuring they work together correctly.

    Args:
        application: Optional QApplication instance, will use the current one if not provided

    Returns:
        The installed qasync event loop
    """
    global _main_loop, _loop_running, _install_complete

    # Avoid multiple installations
    if _install_complete and _main_loop is not None:
        logger.debug(f"Using existing qasync event loop: {id(_main_loop)}")
        return _main_loop

    try:
        # Use the application if provided, otherwise get the current one
        app = application or QCoreApplication.instance()
        if app is None:
            from PyQt6.QtWidgets import QApplication
            app = QApplication([])
            logger.debug("Created new QApplication instance")

        # Create the qasync event loop
        _main_loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(_main_loop)
        logger.debug(f"Installed qasync event loop: {id(_main_loop)}")

        # CRITICAL: Make sure the loop is properly connected to the application
        if hasattr(_main_loop, '_install_app_as_event_processor'):
            _main_loop._install_app_as_event_processor()

        # Set exception handler
        _main_loop.set_exception_handler(_exception_handler)

        # CRITICAL: Start the loop by scheduling and running a dummy task
        # This ensures the internal loop state is properly set
        dummy_future = asyncio.ensure_future(asyncio.sleep(0.01), loop=_main_loop)

        # Process Qt events to ensure the loop gets a chance to run
        app.processEvents()

        # Set up a QTimer to ensure the event loop processes asyncio events
        # This is critical for keeping the loop running
        timer = QTimer()
        timer.timeout.connect(lambda: None)  # Empty callback just to wake up the event loop
        timer.start(16)  # ~60fps - good balance for responsive UI

        # Set the timer as an attribute of the loop to prevent garbage collection
        if not hasattr(_main_loop, '_keep_alive_timer'):
            _main_loop._keep_alive_timer = timer

        # Mark loop as running and installation as complete
        _loop_running = True
        _install_complete = True

        # Add a hook to properly clean up the loop when the application quits
        app.aboutToQuit.connect(_cleanup_loop)

        logger.info(f"qasync event loop successfully installed and running: {id(_main_loop)}")
        return _main_loop
    except Exception as e:
        logger.critical(f"Failed to install qasync event loop: {str(e)}")
        logger.critical(traceback.format_exc())
        raise

def _cleanup_loop():
    """Clean up the event loop when the application is shutting down"""
    global _main_loop, _loop_running

    if _main_loop is not None:
        logger.debug(f"Cleaning up qasync event loop: {id(_main_loop)}")
        if hasattr(_main_loop, '_keep_alive_timer'):
            try:
                _main_loop._keep_alive_timer.stop()
                if hasattr(_main_loop._keep_alive_timer, 'deleteLater'):
                    _main_loop._keep_alive_timer.deleteLater()
            except Exception as e:
                logger.warning(f"Error stopping keep-alive timer: {str(e)}")

        try:
            # Close the event loop if it's still open
            if not _main_loop.is_closed():
                pending_tasks = asyncio.all_tasks(loop=_main_loop)
                if pending_tasks:
                    logger.debug(f"Cancelling {len(pending_tasks)} pending tasks")
                    for task in pending_tasks:
                        task.cancel()

                # Use a quick synchronous approach to shut down the loop
                if hasattr(_main_loop, 'shutdown_asyncgens'):
                    try:
                        _main_loop.run_until_complete(_main_loop.shutdown_asyncgens())
                    except (RuntimeError, asyncio.CancelledError):
                        pass

                try:
                    _main_loop.close()
                except Exception as e:
                    logger.warning(f"Error closing event loop: {str(e)}")
        except Exception as e:
            logger.warning(f"Error during event loop cleanup: {str(e)}")

        _loop_running = False
        logger.debug("Event loop cleanup complete")

def _exception_handler(loop, context):
    """Custom exception handler for the event loop"""
    exception = context.get('exception')
    message = context.get('message', 'No error message')

    if exception:
        logger.error(f"Async error: {message}", exc_info=exception)
    else:
        logger.error(f"Async error: {message}")

def get_event_loop():
    """
    Get the main event loop, creating it if necessary

    Returns:
        The qasync event loop
    """
    global _main_loop, _loop_running

    # Check if we already have a running loop
    if _main_loop is not None and _loop_running:
        return _main_loop

    try:
        # Get the current event loop
        current_loop = asyncio.get_event_loop()

        # Check if it's already a QEventLoop
        if isinstance(current_loop, qasync.QEventLoop):
            _main_loop = current_loop
            _loop_running = True
            logger.debug(f"Using existing qasync loop: {id(_main_loop)}")
            return current_loop
        else:
            # We have a non-QEventLoop
            logger.warning(f"Found non-QEventLoop: {id(current_loop)}")
    except RuntimeError:
        # No event loop in this thread
        logger.warning("No event loop found, creating a new one.")

    # Call install() to get a properly set up QEventLoop
    return install()

def ensure_qasync_loop():
    """
    Ensure we're using the qasync event loop and return it.
    This also ensures the loop is properly running.

    Returns:
        The qasync event loop
    """
    global _main_loop, _loop_running

    # First, try to get the running loop - this is the cleanest approach if it works
    try:
        current_loop = asyncio.get_running_loop()
        # If we get here, there is a running loop

        # Check if it's a qasync loop
        if isinstance(current_loop, qasync.QEventLoop):
            if _main_loop is not None and current_loop is not _main_loop:
                logger.warning(f"Running with different loop than expected: {id(current_loop)} vs main {id(_main_loop)}")
            _main_loop = current_loop
            _loop_running = True
            return current_loop
        else:
            logger.warning(f"Current running loop is not a qasync.QEventLoop: {type(current_loop)}")
            # Replace the loop with a qasync loop
            return install()
    except RuntimeError:
        # No running loop, this is where we'll usually end up
        pass

    # Try to get the set event loop
    try:
        current_loop = asyncio.get_event_loop()
        if isinstance(current_loop, qasync.QEventLoop):
            _main_loop = current_loop

            # CRITICAL FIX: If the loop exists but isn't running, start it now
            if not _loop_running:
                _start_loop_if_needed(current_loop)

            return current_loop
        else:
            logger.warning(f"Current event loop is not a qasync.QEventLoop: {type(current_loop)}")
            return install()
    except RuntimeError:
        # No event loop set
        logger.warning("No event loop set")
        pass

    # If we get here, we need a new loop
    logger.debug("Creating new qasync event loop")
    return install()

def _start_loop_if_needed(loop):
    """Helper function to start the loop if it's not already running"""
    global _loop_running

    if not _loop_running or not loop.is_running():
        try:
            # CRITICAL: Make sure the loop is properly connected to the application
            if hasattr(loop, '_install_app_as_event_processor'):
                loop._install_app_as_event_processor()

            # Start the loop in a way that works with qasync
            dummy_task = asyncio.ensure_future(asyncio.sleep(0.01), loop=loop)

            # Process Qt events to give the loop a chance to run
            app = QCoreApplication.instance()
            if app:
                app.processEvents()

            # Set up or restart the keep-alive timer
            if not hasattr(loop, '_keep_alive_timer') or not loop._keep_alive_timer.isActive():
                timer = QTimer()
                timer.timeout.connect(lambda: None)  # Wake up event loop
                timer.start(16)  # ~60fps
                loop._keep_alive_timer = timer

            _loop_running = True
            logger.debug(f"Started event loop: {id(loop)}")
        except Exception as e:
            logger.error(f"Error starting loop: {str(e)}")

class RunCoroutineInQt(QObject):
    """Helper class to run a coroutine from Qt code"""

    # Define signals for communication
    taskCompleted = pyqtSignal(object)
    taskError = pyqtSignal(Exception)

    def __init__(self, coro, callback=None, error_callback=None):
        super().__init__()
        self.coro = coro
        self.callback = callback
        self.error_callback = error_callback
        self.future = None
        self.task = None

        # Connect signals to callbacks if provided
        if callback:
            self.taskCompleted.connect(lambda result: callback(result))
        if error_callback:
            self.taskError.connect(lambda error: error_callback(error))

    def start(self):
        """Start the coroutine using qasync"""
        try:
            # Always use a consistent event loop - CRITICAL: We ensure it's running
            loop = ensure_qasync_loop()
            logger.debug(f"Starting task with loop: {id(loop)}")

            # Safety check - verify we have a valid coroutine
            if not asyncio.iscoroutine(self.coro):
                raise TypeError(f"Expected a coroutine, got {type(self.coro)}")

            # CRITICAL FIX: Make sure the loop is in a valid state first
            _start_loop_if_needed(loop)

            # Use create_task directly when we know the loop is running
            self.task = loop.create_task(self._safe_execute())
            return self
        except Exception as e:
            logger.error(f"Error starting coroutine: {str(e)}", exc_info=True)
            if self.error_callback:
                # Use a QTimer to ensure error callback runs on main thread
                QTimer.singleShot(0, lambda: self.error_callback(e))
            return None

    def cancel(self):
        """Cancel the running task"""
        if self.task and not self.task.done():
            self.task.cancel()
            logger.debug("Task cancelled")

    async def _safe_execute(self):
        """Safely execute the coroutine with exception handling"""
        try:
            result = await self.coro
            # Emit signal on the main thread
            self.taskCompleted.emit(result)
            return result
        except asyncio.CancelledError:
            logger.debug("Task was cancelled")
            raise
        except Exception as e:
            logger.error(f"Error executing coroutine: {str(e)}", exc_info=True)
            # Emit signal on the main thread
            self.taskError.emit(e)
            raise


def run_coroutine(coro: Union[Coroutine, Callable[[], Coroutine]],
                  callback: Optional[Callable[[Any], None]] = None,
                  error_callback: Optional[Callable[[Exception], None]] = None):
    """
    Run a coroutine from Qt code with proper event loop handling

    This function is the central mechanism for running async code from sync code.
    It correctly handles any coroutine to ensure it's executed in the qasync event loop.

    Args:
        coro: The coroutine or coroutine function to run
        callback: Optional callback to call with the result
        error_callback: Optional callback to call if an error occurs

    Returns:
        A runner object that can be used to cancel the task
    """
    global _loop_running

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
    loop = ensure_qasync_loop()
    logger.debug(f"Running coroutine with loop: {id(loop)}")

    # CRITICAL: Force the loop to be in a running state
    _start_loop_if_needed(loop)

    # Create a runner to manage the coroutine execution
    runner = RunCoroutineInQt(actual_coro, callback, error_callback)
    return runner.start()


# Function to run async code synchronously (blocking) - should be used sparingly
def run_sync(coro):
    """
    Run a coroutine synchronously (will block until complete)
    Only use this during application initialization or in tests.

    Args:
        coro: Coroutine to run

    Returns:
        Result of the coroutine
    """
    # Try to use qasync first
    try:
        loop = ensure_qasync_loop()
        if hasattr(loop, 'run_until_complete'):
            app = QCoreApplication.instance()

            # Define a helper to periodically process Qt events during the blocking wait
            def process_events():
                if app and not app.closingDown():
                    app.processEvents()
                    return True
                return False

            # Create a special runner that processes Qt events while waiting
            # This is crucial to avoid freezing the UI
            class EventProcessingRunner:
                def __init__(self, loop, coro):
                    self.loop = loop
                    self.coro = coro
                    self.task = None
                    self.result = None
                    self.done = False
                    self.exception = None

                def _on_task_done(self, task):
                    try:
                        self.result = task.result()
                    except Exception as e:
                        self.exception = e
                    self.done = True

                def run(self):
                    # Create and start the task
                    self.task = self.loop.create_task(self.coro)
                    self.task.add_done_callback(self._on_task_done)

                    # Process events while waiting for the task to complete
                    timer = QTimer()
                    timer.start(1)  # 1ms interval for responsive UI

                    while not self.done:
                        process_events()
                        if not timer.isActive():
                            timer.start(1)

                    timer.stop()

                    # If there was an exception, raise it
                    if self.exception:
                        raise self.exception

                    return self.result

            # Run the coroutine with event processing
            runner = EventProcessingRunner(loop, coro)
            return runner.run()

    except Exception as e:
        logger.warning(f"Error using qasync for run_sync: {str(e)}")

    # Fall back to a new asyncio loop if necessary
    logger.warning("Falling back to standard asyncio for run_sync")
    temp_loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(temp_loop)
        return temp_loop.run_until_complete(coro)
    finally:
        temp_loop.close()