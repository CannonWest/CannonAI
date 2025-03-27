"""
Patched qasync bridge that fixes Windows-specific issues.
Apply these patches to your existing qasync_bridge.py file.
"""

import asyncio
import platform

# Import local event loop manager
from src.utils.event_loop_manager import EventLoopManager
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

# Global event loop manager
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
        _event_loop_manager = EventLoopManager(app)

    return _event_loop_manager

def ensure_qasync_loop():
    """
    Ensure we have a properly initialized and running qasync event loop.
    This is a replacement for the original function.

    Returns:
        The event loop
    """
    manager = get_event_loop_manager()
    return manager.get_loop()

def run_coroutine(coro, callback=None, error_callback=None, timeout=None):
    """
    Improved version of run_coroutine that uses the event loop manager.

    Args:
        coro: The coroutine to run
        callback: Optional callback for result
        error_callback: Optional callback for errors
        timeout: Optional timeout in seconds

    Returns:
        A runner object that can be used to track/cancel the task
    """
    manager = get_event_loop_manager()
    return manager.run_coroutine(coro, callback, error_callback, timeout)

def patch_qasync():
    """
    Apply patches to the qasync module to fix Windows-specific issues.
    Call this function before initializing the application.
    """
    try:
        import qasync

        # 1. Patch QEventLoop._process_events for Windows
        if platform.system() == "Windows" and hasattr(qasync, '_QEventLoop'):
            original_process_events = qasync._QEventLoop._process_events

            def patched_process_events(self, events):
                try:
                    return original_process_events(self, events)
                except OSError as e:
                    if "ERROR_ABANDONED_WAIT_0" in str(e):
                        logger.debug("Ignoring Windows abandoned wait error in _process_events")
                        return
                    raise

            qasync._QEventLoop._process_events = patched_process_events
            logger.info("Patched qasync._QEventLoop._process_events for Windows")

        # 2. Patch _windows._EventPoller.run for Windows
        if platform.system() == "Windows" and hasattr(qasync, '_windows'):
            if hasattr(qasync._windows, '_EventPoller'):
                original_run = qasync._windows._EventPoller.run

                def patched_run(self):
                    try:
                        return original_run(self)
                    except OSError as e:
                        if "ERROR_ABANDONED_WAIT_0" in str(e):
                            logger.debug("Ignoring Windows abandoned wait error in _EventPoller.run")
                            return
                        raise

                qasync._windows._EventPoller.run = patched_run
                logger.info("Patched qasync._windows._EventPoller.run for Windows")

        # 3. Ensure select method handles connection errors gracefully
        if platform.system() == "Windows" and hasattr(qasync, '_windows'):
            if hasattr(qasync._windows, '_IocpProactor'):
                original_select = qasync._windows._IocpProactor.select

                def patched_select(self, timeout=None):
                    try:
                        return original_select(self, timeout)
                    except OSError as e:
                        error_codes = ["10054", "10053", "10049", "10061", "735"]
                        if any(code in str(e) for code in error_codes):
                            logger.debug(f"Ignoring network error in select: {str(e)}")
                            return []
                        raise

                qasync._windows._IocpProactor.select = patched_select
                logger.info("Patched qasync._windows._IocpProactor.select for Windows")

        # 4. Patch run_until_complete to handle event loop already running
        if hasattr(qasync, '_QEventLoop'):
            original_run_until_complete = qasync._QEventLoop.run_until_complete

            def patched_run_until_complete(self, future):
                try:
                    return original_run_until_complete(self, future)
                except RuntimeError as e:
                    if "Event loop is already running" in str(e):
                        # Create a separate loop for this operation
                        logger.warning("Event loop already running, using separate loop for run_until_complete")
                        loop = asyncio.new_event_loop()
                        try:
                            asyncio.set_event_loop(loop)
                            result = loop.run_until_complete(future)
                            return result
                        finally:
                            loop.close()
                    raise

            qasync._QEventLoop.run_until_complete = patched_run_until_complete
            logger.info("Patched qasync._QEventLoop.run_until_complete")

        logger.info("Successfully applied qasync patches")
        return True
    except ImportError:
        logger.error("Failed to patch qasync - module not found")
        return False
    except Exception as e:
        logger.error(f"Error applying qasync patches: {str(e)}")
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

def run_sync(coro):
    """
    Run a coroutine synchronously (blocking) with improved error handling

    Args:
        coro: The coroutine to run

    Returns:
        The result of the coroutine
    """
    # Get the event loop manager
    manager = get_event_loop_manager()
    loop = manager.get_loop()

    # Make sure it's a coroutine
    if not asyncio.iscoroutine(coro):
        if callable(coro):
            coro = coro()
            if not asyncio.iscoroutine(coro):
                raise TypeError(f"Expected a coroutine, got {type(coro)}")
        else:
            raise TypeError(f"Expected a coroutine, got {type(coro)}")

    # Use try/except to handle Windows-specific issues
    try:
        # First attempt - use run_until_complete
        if not loop.is_closed():
            return loop.run_until_complete(coro)
    except RuntimeError as e:
        if "no running event loop" in str(e) or "Event loop is closed" in str(e):
            logger.warning(f"Error in run_sync: {str(e)}, trying fallback")

            # Fallback - create a temporary loop
            temp_loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(temp_loop)
                return temp_loop.run_until_complete(coro)
            finally:
                temp_loop.close()
                # Restore our main loop
                if not loop.is_closed():
                    asyncio.set_event_loop(loop)
        else:
            raise
    except Exception as e:
        logger.error(f"Error in run_sync: {str(e)}")
        raise