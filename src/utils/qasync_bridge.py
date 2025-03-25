"""
Improved bridge between QML and asyncio using the qasync library.
Ensures consistent event loop usage throughout the application.
"""

import asyncio
import traceback
import functools
import sys
from typing import Any, Callable, Coroutine, Optional, Union

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer, QCoreApplication

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
_loop_running = False  # New flag to track if the loop is properly running

def install(application=None):
    """
    Install the Qt event loop for asyncio with improved initialization
    """
    global _main_loop, _loop_running
    try:
        # Use the application if provided, otherwise get the current one
        app = application or QCoreApplication.instance()
        if app is None:
            from PyQt6.QtWidgets import QApplication
            app = QApplication([])

        # Create the qasync event loop
        _main_loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(_main_loop)
        logger.debug(f"Installed qasync event loop: {id(_main_loop)}")

        # CRITICAL: Start the loop by scheduling and running a dummy task
        # This ensures the internal loop state is properly set
        dummy_future = asyncio.ensure_future(asyncio.sleep(0), loop=_main_loop)

        # Process Qt events to ensure the loop gets a chance to run
        app.processEvents()

        # Set up a QTimer to ensure the event loop processes asyncio events
        # This is critical for keeping the loop running
        timer = QTimer()
        timer.timeout.connect(lambda: None)  # Empty callback just to wake up the event loop
        timer.start(10)  # 10ms interval

        # Mark loop as running
        _loop_running = True

        # Keep a reference to the timer to prevent garbage collection
        _main_loop._keep_alive_timer = timer

        return _main_loop
    except Exception as e:
        logger.critical(f"Failed to install qasync event loop: {str(e)}")
        logger.critical(f"Traceback: {traceback.format_exc()}")
        raise

def get_event_loop():
    """Get the main event loop, creating it if necessary"""
    global _main_loop, _loop_running
    if _main_loop is not None and _loop_running:
        return _main_loop

    try:
        current_loop = asyncio.get_event_loop()
        if isinstance(current_loop, qasync.QEventLoop):
            _main_loop = current_loop
            _loop_running = True
            logger.debug(f"Using existing qasync loop: {id(_main_loop)}")
            return current_loop
        else:
            # We have a non-QEventLoop
            logger.warning(f"Found non-QEventLoop: {id(current_loop)}")
    except RuntimeError:
        # No event loop in this thread, create a new one
        logger.warning("No event loop found, creating a new one.")

    # If we get here, we need to create and install a new loop
    return install()

def ensure_qasync_loop():
    """
    Ensure we're using the qasync event loop and return it.
    This also ensures the loop is properly running.
    """
    global _main_loop, _loop_running

    # First, try to get the running loop - this is the cleanest approach if it works
    try:
        current_loop = asyncio.get_running_loop()
        # If we get here, there is a running loop
        if _main_loop is not None and current_loop is not _main_loop:
            logger.warning(f"Running with different loop than expected: {id(current_loop)} vs main {id(_main_loop)}")
        _loop_running = True
        return current_loop
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
                # Create and schedule a dummy task to ensure the loop is marked as running
                asyncio.ensure_future(asyncio.sleep(0), loop=current_loop)

                # Process Qt events to give the loop a chance to run
                app = QCoreApplication.instance()
                if app:
                    app.processEvents()

                # Set up the keep-alive timer if missing
                if not hasattr(current_loop, '_keep_alive_timer'):
                    timer = QTimer()
                    timer.timeout.connect(lambda: None)
                    timer.start(10)
                    current_loop._keep_alive_timer = timer

                _loop_running = True
                logger.debug(f"Started existing loop: {id(current_loop)}")

            return current_loop
    except RuntimeError:
        # No event loop set
        pass

    # If we get here, we need a new loop
    logger.debug("Creating new qasync event loop")
    return install()

def _start_loop_if_needed(loop):
    """Helper function to start the loop if it's not already running"""
    global _loop_running

    if not _loop_running or not loop.is_running():
        try:
            # Start the loop in a way that works with qasync
            asyncio.ensure_future(asyncio.sleep(0), loop=loop)

            # Process Qt events to give the loop a chance to run
            app = QCoreApplication.instance()
            if app:
                app.processEvents()

            _loop_running = True
            logger.debug(f"Started loop: {id(loop)}")
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
    # Use an existing event loop if possible
    try:
        loop = asyncio.get_event_loop()
        if hasattr(loop, 'run_until_complete'):
            return loop.run_until_complete(coro)
    except RuntimeError:
        pass

    # If no loop or incompatible loop, use a new one
    temp_loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(temp_loop)
        return temp_loop.run_until_complete(coro)
    finally:
        temp_loop.close()
        # Don't reset the event loop - can cause issues with qasync