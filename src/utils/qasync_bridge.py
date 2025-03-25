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
    # Add this to make sure qasync is fully imported
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

def install(application=None):
    """Install the Qt event loop for asyncio"""
    global _main_loop
    try:
        # Use the application if provided, otherwise get the current one
        app = application or QCoreApplication.instance()
        if app is None:
            from PyQt6.QtWidgets import QApplication
            app = QApplication([])

        _main_loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(_main_loop)
        logger.debug(f"Installed qasync event loop: {id(_main_loop)}")

        # IMPORTANT: Make the loop running by scheduling a dummy task
        # This addresses the "no running event loop" issue
        asyncio.ensure_future(asyncio.sleep(0), loop=_main_loop)

        return _main_loop
    except Exception as e:
        logger.critical(f"Failed to install qasync event loop: {str(e)}")
        logger.critical(f"Traceback: {traceback.format_exc()}")
        raise

def get_event_loop():
    """Get the main event loop, creating it if necessary"""
    global _main_loop
    if _main_loop is not None:
        return _main_loop

    try:
        current_loop = asyncio.get_event_loop()
        if not isinstance(current_loop, qasync.QEventLoop):
            # We have a non-QEventLoop, warn but continue
            logger.warning(f"Using a non-QEventLoop: {id(current_loop)}")
        return current_loop
    except RuntimeError:
        # No event loop in this thread, create a new one
        logger.warning("No event loop found, creating a new one.")
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        return new_loop

def ensure_qasync_loop():
    """
    Ensure we're using the qasync event loop and return it.
    This should be called at the beginning of any function that uses asyncio.
    """
    global _main_loop

    try:
        # First check if we have a running loop
        try:
            current_loop = asyncio.get_running_loop()
            # If it's running and it's not our main loop, we can't change it
            # but we should warn about this situation
            if _main_loop is not None and current_loop is not _main_loop:
                logger.warning(f"Running in a different loop than expected: {id(current_loop)} vs main {id(_main_loop)}")
            return current_loop
        except RuntimeError:
            # No running loop, use the get_event_loop instead
            loop = asyncio.get_event_loop()

            # CRITICAL FIX: call run_forever in non-blocking mode
            # to make the loop "running" for asyncio.create_task() calls
            if not loop.is_running():
                logger.debug(f"Starting event loop: {id(loop)}")
                # Schedule the loop to run in a non-blocking way
                QTimer.singleShot(0, lambda: _start_loop_if_needed(loop))

            return loop
    except Exception as e:
        logger.error(f"Error in ensure_qasync_loop: {str(e)}")
        # As a last resort, create a new loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop

def _start_loop_if_needed(loop):
    """Helper function to start the loop if it's not already running"""
    if not loop.is_running():
        try:
            # Start the loop in a way that works with qasync
            asyncio.ensure_future(asyncio.sleep(0), loop=loop)
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
            # Always use a consistent event loop
            loop = ensure_qasync_loop()
            logger.debug(f"Starting task with loop: {id(loop)}")

            # Safety check - verify we have a valid coroutine
            if not asyncio.iscoroutine(self.coro):
                raise TypeError(f"Expected a coroutine, got {type(self.coro)}")

            # CRITICAL FIX: Use asyncio.ensure_future instead of create_task
            # as it works better with qasync and doesn't require a "running" loop
            self.task = asyncio.ensure_future(self._safe_execute(), loop=loop)
            return self
        except Exception as e:
            logger.error(f"Error starting coroutine: {str(e)}", exc_info=True)
            if self.error_callback:
                self.error_callback(e)
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
    # Get the coroutine object
    if callable(coro) and not asyncio.iscoroutine(coro):
        try:
            actual_coro = coro()
        except Exception as e:
            logger.error(f"Error calling coroutine function: {str(e)}")
            if error_callback:
                error_callback(e)
            return None
    elif asyncio.iscoroutine(coro):
        actual_coro = coro
    else:
        error = TypeError(f"Expected a coroutine or coroutine function, got {type(coro)}")
        logger.error(str(error))
        if error_callback:
            error_callback(error)
        return None

    # Get a consistent event loop
    loop = ensure_qasync_loop()
    logger.debug(f"Running coroutine with loop: {id(loop)}")

    # Create a runner and run it
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
    # Use a helper event loop for synchronous execution
    old_loop = None
    try:
        # Save the current event loop if any
        try:
            old_loop = asyncio.get_event_loop()
        except RuntimeError:
            pass

        # Create a new event loop
        temp_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(temp_loop)

        # Run the coroutine
        return temp_loop.run_until_complete(coro)
    finally:
        # Clean up
        try:
            temp_loop.close()
        except:
            pass

        # Restore the old loop if any
        if old_loop:
            asyncio.set_event_loop(old_loop)