"""
Improved bridge between QML and asyncio using the qasync library.
Ensures consistent event loop usage throughout the application.
"""

import asyncio
import traceback
import functools
import sys
import threading
from typing import Any, Callable, Coroutine, Optional, Union

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer

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
        try:
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
    except Exception as e:
        logger.error(f"Error in ensure_qasync_loop: {str(e)}")
        # As a last resort, create a new loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


def run_coroutine(coro: Union[Coroutine, Callable[[], Coroutine]],
                  callback: Optional[Callable[[Any], None]] = None,
                  error_callback: Optional[Callable[[Exception], None]] = None):
    """
    Run a coroutine from Qt code with proper event loop handling

    This version avoids using create_task which requires a running event loop

    Args:
        coro: The coroutine or coroutine function to run
        callback: Optional callback to call with the result
        error_callback: Optional callback to call if an error occurs
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

        # Connect signals to callbacks
        if callback:
            self.taskCompleted.connect(lambda result: callback(result))
        if error_callback:
            self.taskError.connect(lambda error: error_callback(error))

    def start(self):
        """Start the coroutine using a safer approach"""
        try:
            # Always use a consistent event loop
            loop = ensure_qasync_loop()
            logger.debug(f"Starting task with loop: {id(loop)}")

            # Safety check - verify we have a valid coroutine
            if not asyncio.iscoroutine(self.coro):
                raise TypeError(f"Expected a coroutine, got {type(self.coro)}")

            # Use a thread-based approach if we can't run in the current context
            try:
                # This should work if we have a valid loop that's accessible
                if isinstance(loop, qasync.QEventLoop):
                    # For qasync, we'll use ensure_future which is more reliable
                    self.future = asyncio.ensure_future(self._safe_execute(), loop=loop)
                    return self.future
                else:
                    # For standard loop, try the same approach
                    self.future = asyncio.ensure_future(self._safe_execute(), loop=loop)
                    return self.future
            except RuntimeError:
                # If we can't use ensure_future, use a thread-based approach
                logger.warning("Falling back to thread-based coroutine execution")
                self._run_in_thread()
                return self

        except Exception as e:
            logger.error(f"Error starting coroutine: {str(e)}", exc_info=True)
            if self.error_callback:
                self.error_callback(e)
            return None

    def _run_in_thread(self):
        """Run the coroutine in a separate thread"""
        def target():
            try:
                # Create a new event loop for this thread
                thread_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(thread_loop)

                try:
                    # Run the coroutine
                    result = thread_loop.run_until_complete(self.coro)

                    # Use QTimer to safely emit the signal from the main thread
                    QTimer.singleShot(0, lambda: self.taskCompleted.emit(result))
                finally:
                    thread_loop.close()
            except Exception as e:
                logger.error(f"Error in thread coroutine: {str(e)}", exc_info=True)
                # Use QTimer to safely emit the signal from the main thread
                QTimer.singleShot(0, lambda: self.taskError.emit(e))

        # Start the thread
        thread = threading.Thread(target=target)
        thread.daemon = True
        thread.start()

    async def _safe_execute(self):
        """Safely execute the coroutine with exception handling"""
        try:
            result = await self.coro
            self.taskCompleted.emit(result)
            return result
        except Exception as e:
            logger.error(f"Error executing coroutine: {str(e)}", exc_info=True)
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
    # Create a helper event loop for synchronous execution
    temp_loop = asyncio.new_event_loop()
    try:
        return temp_loop.run_until_complete(coro)
    finally:
        temp_loop.close()