"""
Enhanced utilities for integrating asyncio with Qt.
Provides functions for running coroutines from Qt code
and managing async context.
"""

import sys
import asyncio
import traceback
from typing import Any, Callable, Coroutine, Optional, TypeVar

from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QCoreApplication

from src.utils.qasync_bridge import run_coroutine as _run_coroutine
from src.utils.logging_utils import get_logger

# Configure logging
logger = get_logger(__name__)

# Type variable for return type
T = TypeVar('T')


class AsyncRunner(QObject):
    """
    Enhanced helper class for running async coroutines from Qt code
    with better error handling and signal management.
    """
    # Define signals
    resultReady = pyqtSignal(object)  # Signal emitted when result is ready
    errorOccurred = pyqtSignal(str)   # Signal emitted on error
    started = pyqtSignal()            # Signal emitted when coroutine starts
    finished = pyqtSignal()           # Signal emitted when coroutine finishes (success or error)

    def __init__(self, 
                 coro: Coroutine, 
                 callback: Optional[Callable[[Any], None]] = None,
                 error_callback: Optional[Callable[[Exception], None]] = None,
                 parent: Optional[QObject] = None):
        """
        Initialize the AsyncRunner
        
        Args:
            coro: The coroutine to run
            callback: Optional callback to call with the result
            error_callback: Optional callback to call if an error occurs
            parent: Optional parent QObject
        """
        super().__init__(parent)
        self.coro = coro
        self.task = None
        
        # Connect signals to callbacks if provided
        if callback:
            self.resultReady.connect(callback)
        if error_callback:
            self.errorOccurred.connect(lambda msg: error_callback(Exception(msg)))

    def start(self):
        """Start running the coroutine"""
        self.started.emit()
        
        # Get the current event loop
        try:
            loop = asyncio.get_event_loop()
            if loop and loop.is_running():
                # Create the task
                self.task = loop.create_task(self._run_coro())
            else:
                # Log error and emit signal
                msg = "No running event loop found"
                logger.error(msg)
                self.errorOccurred.emit(msg)
                self.finished.emit()
        except Exception as e:
            # Log the error
            logger.error(f"Error starting AsyncRunner: {str(e)}")
            self.errorOccurred.emit(f"Error starting async task: {str(e)}")
            self.finished.emit()

    async def _run_coro(self):
        """Run the coroutine and handle results/errors"""
        try:
            # Run the coroutine
            result = await self.coro
            
            # Emit the result signal
            self.resultReady.emit(result)
            return result
        except asyncio.CancelledError:
            # Task was cancelled, don't emit error
            logger.debug("Async task was cancelled")
        except Exception as e:
            # Log the error with traceback
            logger.error(f"Error in async task: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Emit error signal
            self.errorOccurred.emit(str(e))
        finally:
            # Always emit finished signal
            self.finished.emit()

    def cancel(self):
        """Cancel the running task if possible"""
        if self.task and not self.task.done():
            self.task.cancel()
            logger.debug("Async task cancelled")


def run_coro(coro: Coroutine[Any, Any, T], 
             callback: Optional[Callable[[T], None]] = None,
             error_callback: Optional[Callable[[Exception], None]] = None,
             parent: Optional[QObject] = None) -> AsyncRunner:
    """
    Run a coroutine from Qt code with enhanced error handling
    
    Args:
        coro: The coroutine to run
        callback: Optional callback to call with the result
        error_callback: Optional callback to call if an error occurs
        parent: Optional parent QObject
        
    Returns:
        AsyncRunner instance that can be used to cancel the task
    """
    runner = AsyncRunner(coro, callback, error_callback, parent)
    runner.start()
    return runner


def ensure_future(coro: Coroutine) -> asyncio.Future:
    """
    Ensure a coroutine is scheduled as a future/task in the current event loop
    
    Args:
        coro: The coroutine to schedule
        
    Returns:
        The created future/task
    """
    try:
        loop = asyncio.get_event_loop()
        return asyncio.ensure_future(coro, loop=loop)
    except RuntimeError:
        # If we don't have an event loop, we're probably not in an async context
        logger.warning("No event loop found in ensure_future, using run_coroutine")
        _run_coroutine(coro)
        return None  # Can't return a Future in this case


class AsyncContext:
    """
    Context manager for async operations that ensures event loop is properly set up
    
    This is useful for functions that may be called from both async and sync contexts
    """
    def __init__(self, create_if_needed=True):
        self.loop = None
        self.create_if_needed = create_if_needed
        self.created_loop = False

    async def __aenter__(self):
        try:
            self.loop = asyncio.get_event_loop()
        except RuntimeError:
            if self.create_if_needed:
                self.loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self.loop)
                self.created_loop = True
            else:
                raise
        return self.loop

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.created_loop:
            self.loop.close()
            self.loop = None


def get_event_loop():
    """
    Get the current event loop or create a new one if necessary
    
    Returns:
        asyncio.AbstractEventLoop: The event loop
    """
    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        # No event loop in this thread, create a new one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


# Set up periodic callback for processing async tasks in the Qt event loop
def setup_async_task_processor(interval_ms=50):
    """
    Set up a timer to periodically process async tasks in the Qt event loop
    
    Args:
        interval_ms: Interval in milliseconds for processing
    """
    timer = QTimer()
    timer.timeout.connect(process_async_tasks)
    timer.start(interval_ms)
    return timer


def process_async_tasks():
    """
    Process pending async tasks in the event loop
    """
    try:
        loop = asyncio.get_event_loop()
        loop.call_soon(lambda: None)  # This forces the event loop to process any pending callbacks
    except Exception as e:
        # Improve error logging with full traceback
        import traceback
        logger.error(f"Error processing async tasks: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")


# Utility function to make a method async-safe (can be called from both sync and async contexts)
def async_safe(func):
    """
    Decorator to make a method async-safe (can be called from both sync and async contexts)
    
    If called from sync context, will run the coroutine through run_coro
    If called from async context, can be awaited normally
    
    Example:
        @async_safe
        async def my_method(self, arg1, arg2):
            # Async code here
            
        # Can be called both ways:
        await obj.my_method(1, 2)  # In async context
        obj.my_method(1, 2)        # In sync context
    """
    def wrapper(*args, **kwargs):
        coro = func(*args, **kwargs)
        
        try:
            # Check if we're in an async context
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return coro  # Return coroutine for awaiting
        except RuntimeError:
            # Not in async context, use run_coro
            pass
            
        # In sync context, run the coroutine
        return run_coro(coro)
        
    return wrapper
