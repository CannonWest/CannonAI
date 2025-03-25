"""
Improved bridge between QML and asyncio using the qasync library.
Ensures consistent event loop usage throughout the application.
"""

import asyncio
import traceback
import functools
import sys
from typing import Any, Callable, Coroutine, Optional, Union

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

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
        _main_loop = qasync.QEventLoop(application)
        asyncio.set_event_loop(_main_loop)
        logger.debug(f"Installed qasync event loop: {id(_main_loop)}")
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
        current_loop = asyncio.get_running_loop()
        # If it's running and it's not our main loop, we can't change it
        # but we should warn about this situation
        if _main_loop is not None and current_loop is not _main_loop:
            logger.warning(f"Running in a different loop than expected: {id(current_loop)} vs main {id(_main_loop)}")
        return current_loop
    except RuntimeError:
        # No running loop, check if we have a main loop
        if _main_loop is not None:
            # Set our main loop as the current thread's loop
            asyncio.set_event_loop(_main_loop)
            logger.debug(f"Set main loop as current: {id(_main_loop)}")
            return _main_loop

        # No main loop either, get or create one
        try:
            loop = asyncio.get_event_loop()
            logger.debug(f"Using thread's event loop: {id(loop)}")
            return loop
        except RuntimeError:
            # No event loop in this thread, create a new one
            logger.warning("Creating new event loop - this might indicate an architectural issue")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop


def run_coroutine(coro: Union[Coroutine, Callable[[], Coroutine]],
                  callback: Optional[Callable[[Any], None]] = None,
                  error_callback: Optional[Callable[[Exception], None]] = None):
    """
    Run a coroutine from Qt code with proper event loop handling

    Args:
        coro: The coroutine or coroutine function to run
        callback: Optional callback to call with the result
        error_callback: Optional callback to call if an error occurs
    """
    # Get a consistent event loop
    loop = ensure_qasync_loop()
    logger.debug(f"Running coroutine with loop: {id(loop)}")

    # Create a runner and run it
    runner = RunCoroutineInQt(coro, callback, error_callback)
    return runner.start()


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
        self.task = None

        # Connect signals to callbacks
        if callback:
            self.taskCompleted.connect(lambda result: callback(result))
        if error_callback:
            self.taskError.connect(lambda error: error_callback(error))

    def start(self):
        """Start the coroutine"""
        try:
            # Always use a consistent event loop
            loop = ensure_qasync_loop()
            logger.debug(f"Starting task with loop: {id(loop)}")

            # Get the coroutine object
            if callable(self.coro) and not asyncio.iscoroutine(self.coro):
                actual_coro = self.coro()
            elif asyncio.iscoroutine(self.coro):
                actual_coro = self.coro
            else:
                raise TypeError(f"Expected a coroutine or coroutine function, got {type(self.coro)}")

            # Create a task using the loop
            self.task = loop.create_task(self._wrapped_coro(actual_coro))

            # Add a done callback to ensure we catch any unhandled exceptions
            self.task.add_done_callback(self._on_task_done)

            return self.task

        except Exception as e:
            logger.error(f"Error starting coroutine: {str(e)}", exc_info=True)
            if self.error_callback:
                self.error_callback(e)
            return None

    def _on_task_done(self, task):
        """Handle task completion/failure even if _wrapped_coro doesn't catch everything"""
        try:
            # Check if there was an exception that wasn't handled
            if task.exception() and not task.cancelled():
                # This should generally not happen since _wrapped_coro should catch exceptions
                # But it's a safety measure
                exception = task.exception()
                logger.error(f"Unhandled task exception: {str(exception)}")
                logger.error(f"Traceback: {traceback.format_exc()}")

                # Emit the error signal if there's an error callback
                if self.error_callback:
                    self.taskError.emit(exception)
        except asyncio.CancelledError:
            # Task was cancelled - that's normal
            pass
        except Exception as e:
            logger.error(f"Error in task.done callback: {str(e)}")

    async def _wrapped_coro(self, coro):
        """Wrapper around the coroutine to handle callbacks"""
        try:
            # Double-check we're on the right loop
            current_loop = asyncio.get_running_loop()
            logger.debug(f"Task running in loop: {id(current_loop)}")

            # Add a timeout to detect hanging tasks
            try:
                # 30 second timeout for potentially long-running tasks
                result = await asyncio.wait_for(coro, timeout=30.0)
                logger.debug("Task completed successfully")
                self.taskCompleted.emit(result)
                return result
            except asyncio.TimeoutError:
                logger.error("Task timed out after 30 seconds")
                self.taskError.emit(Exception("Task timed out after 30 seconds"))
                return None

        except asyncio.CancelledError:
            # Task was cancelled, don't emit error
            logger.debug("Async task was cancelled")
            raise
        except Exception as e:
            # Log detailed error information
            logger.error(f"Error in async task: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")

            # Emit error signal
            self.taskError.emit(e)
            raise


# Function to run async code synchronously (blocking)
def run_sync(coro):
    """
    Run a coroutine synchronously (will block until complete)

    Args:
        coro: Coroutine to run

    Returns:
        Result of the coroutine
    """
    # Ensure we have a consistent event loop
    loop = ensure_qasync_loop()
    logger.debug(f"Running coroutine synchronously with loop: {id(loop)}")

    # Check if we're already in an event loop
    try:
        running_loop = asyncio.get_running_loop()
        if running_loop is loop:
            # We're already in the event loop, can't use run_until_complete
            raise RuntimeError(
                "Cannot use run_sync inside a running event loop. Use run_coroutine instead."
            )
    except RuntimeError:
        # No running event loop, good to proceed
        pass

    # Use a synchronized future with timeout
    from concurrent.futures import Future
    future = Future()

    def on_complete(result):
        if not future.done():
            future.set_result(result)

    def on_error(error):
        if not future.done():
            future.set_exception(error)

    # Run the coroutine
    run_coroutine(coro, callback=on_complete, error_callback=on_error)

    try:
        # Wait for completion with timeout (will block)
        return future.result(timeout=30)  # 30 second timeout
    except Exception as e:
        logger.error(f"Error or timeout in run_sync: {str(e)}")
        # If it's a timeout, give a more helpful message
        if "timeout" in str(e).lower():
            logger.error("Task appears to be hanging - possible deadlock or infinite loop")
        raise