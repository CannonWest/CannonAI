# Step 1: Install qasync
# pip install qasync

# Step 2: Update src/utils/qasync_bridge.py with this simplified wrapper

"""
Simplified bridge between QML and asyncio using the qasync library.
"""

import asyncio
import traceback
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


def install(application=None):
    """Install the Qt event loop for asyncio"""
    loop = qasync.QEventLoop(application)
    asyncio.set_event_loop(loop)
    return loop


def run_coroutine(coro: Union[Coroutine, Callable[[], Coroutine]],
                  callback: Optional[Callable[[Any], None]] = None,
                  error_callback: Optional[Callable[[Exception], None]] = None):
    """
    Run a coroutine from Qt code

    Args:
        coro: The coroutine or coroutine function to run
        callback: Optional callback to call with the result
        error_callback: Optional callback to call if an error occurs
    """
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
            loop = asyncio.get_event_loop()

            # Get the coroutine object
            if asyncio.iscoroutinefunction(self.coro):
                actual_coro = self.coro()
            elif asyncio.iscoroutine(self.coro):
                actual_coro = self.coro
            else:
                raise TypeError(f"Expected a coroutine or coroutine function, got {type(self.coro)}")

            # Create a task
            self.task = asyncio.ensure_future(self._wrapped_coro(actual_coro), loop=loop)
            return self.task

        except Exception as e:
            logger.error(f"Error starting coroutine: {str(e)}", exc_info=True)
            if self.error_callback:
                self.error_callback(e)
            return None

    async def _wrapped_coro(self, coro):
        """Wrapper around the coroutine to handle callbacks"""
        try:
            result = await coro
            self.taskCompleted.emit(result)
            return result
        except Exception as e:
            logger.error(f"Error in coroutine: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            self.taskError.emit(e)
            raise