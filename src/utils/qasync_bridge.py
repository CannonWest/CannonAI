"""
Enhanced qasync bridge with fixes for Python 3.12 and PyQt6 compatibility.
Fixes coroutine reuse issues and provides more reliable event loop management.
"""

import asyncio
import platform
import sys
import traceback
import inspect
from typing import Any, Awaitable, Callable, Optional, Union, Coroutine

# Import local event loop manager
from src.utils.event_loop_manager import EventLoopManager
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

# Cache to track used coroutines - helps prevent "cannot reuse already awaited coroutine" errors
_used_coroutines = set()

# In src/utils/qasync_bridge.py

# Global variable to store manager reference
_event_loop_manager = None


def get_event_loop_manager(app=None):
    """
    Get or create the global event loop manager

    Args:
        app: QApplication instance

    Returns:
        The EventLoopManager instance
    """
    global _event_loop_manager

    if _event_loop_manager is None:
        # Import here to avoid circular imports
        from src.utils.event_loop_manager import get_global_manager
        _event_loop_manager = get_global_manager(app)

    return _event_loop_manager

def patch_qasync():
    """
    Apply patches to the qasync module to fix compatibility issues.
    Updated for Python 3.12 and PyQt6 compatibility.
    """
    try:
        import qasync

        # Check qasync version and structure
        logger.info(f"Patching qasync version: {getattr(qasync, '__version__', 'unknown')}")

        # Only apply patches for the right version of qasync
        if hasattr(qasync, 'QEventLoop'):
            # Handle the newer qasync structure
            logger.info("Detected newer qasync structure, applying new patches")

            # Patch QEventLoop for better error handling
            original_run_forever = qasync.QEventLoop.run_forever

            def patched_run_forever(self):
                try:
                    return original_run_forever(self)
                except Exception as e:
                    logger.error(f"Error in QEventLoop.run_forever: {str(e)}")
                    raise

            qasync.QEventLoop.run_forever = patched_run_forever
            logger.info("Patched QEventLoop.run_forever")

            # Patch create_task to prevent coroutine reuse
            original_create_task = qasync.QEventLoop.create_task

            def patched_create_task(self, coro):
                # Check if we've seen this coroutine before
                global _used_coroutines
                if coro in _used_coroutines:
                    logger.warning("Attempting to reuse an already awaited coroutine - creating new wrapper")
                    # Create a wrapping coroutine to avoid the reuse issue
                    async def _wrap_coro():
                        # We can't directly await coro here, so create a new one
                        if hasattr(coro, '__qualname__') and hasattr(coro, '__self__'):
                            # This appears to be a bound method coroutine
                            method_name = coro.__qualname__.split('.')[-1]
                            if hasattr(coro.__self__, method_name):
                                # Get the original method and call it again
                                method = getattr(coro.__self__, method_name)
                                # Try to get the original arguments
                                frame = inspect.currentframe()
                                try:
                                    if frame and frame.f_back and frame.f_back.f_locals:
                                        # Look for coroutine in locals
                                        for key, value in frame.f_back.f_locals.items():
                                            if value is coro and key != 'coro':
                                                logger.debug(f"Found coroutine as {key} in locals")
                                                # Try to get args from the original call
                                                # This is a best-effort attempt
                                                return await method()
                                finally:
                                    del frame  # Avoid reference cycles

                                # Fallback without args
                                return await method()

                        # If all else fails, just return None
                        logger.warning("Could not recreate coroutine, returning None")
                        return None

                    return original_create_task(self, _wrap_coro())

                # Mark as used for future reference
                _used_coroutines.add(coro)
                # Call original method for fresh coroutines
                return original_create_task(self, coro)

            qasync.QEventLoop.create_task = patched_create_task
            logger.info("Patched QEventLoop.create_task to prevent coroutine reuse")

            # Add special exception handler
            def patched_exception_handler(self, context):
                exception = context.get('exception')
                message = context.get('message', '')

                if exception and isinstance(exception, asyncio.CancelledError):
                    # Just a cancelled task, not an error
                    return

                if "Event loop is closed" in message:
                    # Common during shutdown, not critical
                    logger.debug(f"Ignoring: {message}")
                    return

                logger.error(f"Asyncio exception: {message}")
                if exception:
                    logger.error(traceback.format_exc())

            # Add the exception handler to QEventLoop
            qasync.QEventLoop.default_exception_handler = patched_exception_handler
            logger.info("Added custom exception handler")

        else:
            # Handle older qasync structure with _QEventLoop
            logger.info("Cannot find expected qasync structure, skipping patches")

        # For all structures - add last_resort_exception_handler
        def last_resort_handler(loop, context):
            message = context.get('message', '')
            exception = context.get('exception', None)

            # Skip common shutdown errors
            if (isinstance(exception, asyncio.CancelledError) or
                "Event loop is closed" in message):
                return

            logger.error(f"Unhandled asyncio exception: {message}")
            if exception:
                logger.error(traceback.format_exc())

        # Set globally for asyncio
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

        # Try to add our handler to any existing event loop
        try:
            loop = asyncio.get_event_loop()
            loop.set_exception_handler(last_resort_handler)
        except RuntimeError:
            # No loop exists yet, that's fine
            pass

        logger.info("Successfully applied asyncio patches")
        return True
    except ImportError:
        logger.error("Failed to patch qasync - module not found")
        return False
    except Exception as e:
        logger.error(f"Error applying qasync patches: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def install(application=None):
    """
    Install the Qt event loop for asyncio with improved handling.
    This replaces the original install function.

    Args:
        application: Optional QApplication instance

    Returns:
        The installed event loop
    """
    # Apply patches first
    patch_qasync()

    # Get or create the event loop manager
    manager = get_event_loop_manager(application)

    # Initialize the event loop
    return manager.initialize()

def ensure_qasync_loop():
    """
    Ensure we have a properly initialized and running qasync event loop.
    Improved version with better error handling and guaranteed loop creation.

    Returns:
        The event loop
    """
    try:
        # First try to get the current running loop
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            # No running loop, continue with creation steps
            pass

        # Try to get the event loop using get_event_loop
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_closed():
                # If we got here, we have a valid loop
                return loop
        except RuntimeError:
            # No event loop in the current thread
            pass

        # Get the global event loop manager
        manager = get_event_loop_manager()

        # Try to get a loop from the manager
        loop = manager.get_loop()
        if loop and not loop.is_closed():
            # Set it as the current event loop
            asyncio.set_event_loop(loop)

            # Create a dummy task to ensure the loop is properly initialized
            try:
                loop.create_task(asyncio.sleep(0.01))
            except Exception:
                pass

            # Process Qt events to help activate the loop
            from PyQt6.QtCore import QCoreApplication
            if QCoreApplication.instance():
                QCoreApplication.instance().processEvents()

            logger.debug(f"Ensured qasync loop from manager: {id(loop)}")
            return loop

        # Last resort: Create a new event loop
        logger.warning("No valid event loop found, creating a new one")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Create a no-op task to help "prime" the loop
        loop.create_task(asyncio.sleep(0))

        return loop

    except Exception as e:
        logger.error(f"Error in ensure_qasync_loop: {str(e)}")
        # Ultimate fallback - create a simple new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


def run_coroutine(coro: Union[Coroutine, Callable[..., Coroutine]],
                 callback: Optional[Callable[[Any], None]] = None,
                 error_callback: Optional[Callable[[Exception], None]] = None,
                 timeout: Optional[float] = None):
    """
    Improved version of run_coroutine that handles non-running loops better
    and prevents coroutine reuse errors.

    Args:
        coro: The coroutine or coroutine function to run
        callback: Optional callback for result
        error_callback: Optional callback for errors
        timeout: Optional timeout in seconds

    Returns:
        A runner object that can be used to track/cancel the task
    """
    try:
        # Make sure we have a valid coroutine - with special handling for reuse
        if not asyncio.iscoroutine(coro):
            if callable(coro):
                try:
                    # Call the function to get a fresh coroutine
                    coro = coro()
                    if not asyncio.iscoroutine(coro):
                        if error_callback:
                            error_callback(TypeError(f"Expected a coroutine, got {type(coro)}"))
                        return None
                except Exception as e:
                    logger.error(f"Error calling coroutine function: {str(e)}")
                    if error_callback:
                        error_callback(e)
                    return None
            else:
                if error_callback:
                    error_callback(TypeError(f"Expected a coroutine, got {type(coro)}"))
                return None

        # Check for coroutine reuse
        global _used_coroutines
        if coro in _used_coroutines:
            logger.warning(f"Attempted to reuse coroutine in run_coroutine - this is not allowed")
            if error_callback:
                error_callback(RuntimeError("Cannot reuse already awaited coroutine"))
            return None

        # Mark the coroutine as used to prevent future reuse
        _used_coroutines.add(coro)

        # Get the event loop
        loop = ensure_qasync_loop()

        # Force the loop to be active
        if hasattr(loop, '_process_events'):
            # For qasync loops, process events to kickstart the loop
            try:
                loop._process_events([])
            except Exception:
                pass

            # Also process Qt events
            from PyQt6.QtCore import QCoreApplication
            if QCoreApplication.instance():
                QCoreApplication.instance().processEvents()

        # If the loop is not running, we need a different approach
        is_running = False
        try:
            asyncio.get_running_loop()
            is_running = True
        except RuntimeError:
            is_running = False

        # Create a wrapper task that handles callbacks
        async def wrapper():
            try:
                if timeout is not None:
                    result = await asyncio.wait_for(coro, timeout)
                else:
                    result = await coro

                if callback:
                    callback(result)

                return result
            except asyncio.CancelledError:
                logger.debug("Task was cancelled")
                raise
            except asyncio.TimeoutError:
                logger.warning(f"Task timed out after {timeout} seconds")
                if error_callback:
                    error_callback(TimeoutError(f"Operation timed out after {timeout} seconds"))
                raise
            except Exception as e:
                logger.error(f"Error in task: {str(e)}")
                if error_callback:
                    error_callback(e)
                raise

        # If loop is not running or we're on Windows, use event loop manager
        if not is_running or platform.system() == "Windows":
            try:
                # Get our event loop manager
                manager = get_event_loop_manager()

                # Use the manager's run_coroutine method which has better handling
                return manager.run_coroutine(wrapper(), callback, error_callback, timeout)
            except Exception as e:
                logger.error(f"Task creation error: {str(e)}")
                if error_callback:
                    error_callback(e)
                return None
        else:
            # Standard approach for non-Windows platforms with running loop
            if loop.is_closed():
                if error_callback:
                    error_callback(RuntimeError("Event loop is closed"))
                return None

            task = loop.create_task(wrapper())
            return task
    except Exception as e:
        logger.error(f"Error in run_coroutine: {str(e)}")
        if error_callback:
            error_callback(e)
        return None


def run_sync(coro):
    """
    Run a coroutine synchronously (blocking) with improved error handling

    Args:
        coro: The coroutine to run

    Returns:
        The result of the coroutine
    """
    # Ensure we have a coroutine
    if not asyncio.iscoroutine(coro):
        if callable(coro):
            coro = coro()
            if not asyncio.iscoroutine(coro):
                raise TypeError(f"Expected a coroutine, got {type(coro)}")
        else:
            raise TypeError(f"Expected a coroutine, got {type(coro)}")

    # Check for coroutine reuse
    global _used_coroutines
    if coro in _used_coroutines:
        raise RuntimeError("Cannot reuse already awaited coroutine")

    # Mark the coroutine as used to prevent future reuse
    _used_coroutines.add(coro)

    # Try several approaches to run the coroutine
    for attempt in range(3):
        try:
            # Approach 1: Try to use the current event loop
            try:
                loop = asyncio.get_running_loop()
                if not loop.is_closed():
                    # Use run_coroutine_threadsafe for running loop
                    future = asyncio.run_coroutine_threadsafe(coro, loop)
                    return future.result(30)  # 30 second timeout
            except RuntimeError:
                # No running loop, try next approach
                pass

            # Approach 2: Use event loop manager
            manager = get_event_loop_manager()
            loop = manager.get_loop()
            if not loop.is_closed():
                asyncio.set_event_loop(loop)
                # For qasync loops, process events to kickstart the loop
                if hasattr(loop, '_process_events'):
                    try:
                        loop._process_events([])
                    except Exception:
                        pass
                return loop.run_until_complete(coro)

            # Approach 3: Create a new event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        except Exception as e:
            if attempt == 2:  # Last attempt
                logger.error(f"Failed to run coroutine synchronously: {str(e)}")
                raise
            logger.warning(f"Error running coroutine (attempt {attempt + 1}): {str(e)}")

    # This should not be reachable, but just in case
    raise RuntimeError("Failed to run coroutine after multiple attempts")