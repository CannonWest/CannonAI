"""
Improved bridge between QML and asyncio using the qasync library.
Ensures consistent event loop usage throughout the application.
"""

import asyncio
import traceback
import functools
from typing import Any, Callable, Coroutine, Optional, Union

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
import qasync

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
    _main_loop = qasync.QEventLoop(application)
    asyncio.set_event_loop(_main_loop)
    return _main_loop


def get_event_loop():
    """Get the main event loop, creating it if necessary"""
    global _main_loop
    if _main_loop is not None:
        return _main_loop

    try:
        current_loop = asyncio.get_event_loop()
        if not isinstance(current_loop, qasync.QEventLoop):
            # We have an event loop, but it's not our QEventLoop
            logger.warning("Using a non-QEventLoop, may cause issues with Qt integration")
        return current_loop
    except RuntimeError:
        # No event loop in this thread, create a new one
        logger.warning("No event loop found, creating a new one. This may cause issues.")
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        return new_loop


def ensure_qasync_loop():
    """Ensure we're using the qasync event loop"""
    global _main_loop
    current_loop = asyncio.get_event_loop()
    if _main_loop is not None and current_loop is not _main_loop:
        asyncio.set_event_loop(_main_loop)
        return _main_loop
    return current_loop


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
    # Ensure we're using the qasync event loop
    ensure_qasync_loop()

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
            # Always use the main qasync event loop
            loop = ensure_qasync_loop()

            # Get the coroutine object
            if callable(self.coro) and not asyncio.iscoroutine(self.coro):
                actual_coro = self.coro()
            elif asyncio.iscoroutine(self.coro):
                actual_coro = self.coro
            else:
                raise TypeError(f"Expected a coroutine or coroutine function, got {type(self.coro)}")

            # Create a task using the loop
            self.task = loop.create_task(self._wrapped_coro(actual_coro))
            return self.task

        except Exception as e:
            logger.error(f"Error starting coroutine: {str(e)}", exc_info=True)
            if self.error_callback:
                self.error_callback(e)
            return None

    async def _wrapped_coro(self, coro):
        """Wrapper around the coroutine to handle callbacks"""
        try:
            # Double-check we're on the right loop
            loop = asyncio.get_running_loop()
            if loop is not ensure_qasync_loop():
                logger.warning("Running in a different loop than expected, may cause issues")

            result = await coro
            self.taskCompleted.emit(result)
            return result
        except Exception as e:
            logger.error(f"Error in coroutine: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
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
    # Ensure we have the right event loop
    loop = ensure_qasync_loop()

    # Check if we're already in an event loop
    try:
        running_loop = asyncio.get_running_loop()
        if running_loop is loop:
            # We're already in the event loop, can't use run_until_complete
            raise RuntimeError(
                "Cannot use run_sync inside a running event loop. Use run_coroutine instead."
            )
    except RuntimeError:
        # No running event loop, good to go
        pass

    # Use a synchronized future
    from concurrent.futures import Future
    future = Future()

    def on_complete(result):
        future.set_result(result)

    def on_error(error):
        future.set_exception(error)

    # Run the coroutine
    run_coroutine(coro, callback=on_complete, error_callback=on_error)

    # Wait for completion (will block)
    return future.result()