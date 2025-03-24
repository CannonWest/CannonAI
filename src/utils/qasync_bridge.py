# src/utils/qasync_bridge.py

import sys
import asyncio
import signal
from functools import partial
from typing import Any, Callable, Coroutine, Optional, TypeVar, Generic, Union
import rx
from rx import operators as ops
from rx.subject import Subject, BehaviorSubject
from rx.core import Observable
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer, QCoreApplication, QSocketNotifier
from PyQt6.QtWidgets import QApplication

# Get logger
try:
    from src.utils.logging_utils import get_logger

    logger = get_logger(__name__)
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

# Type variable for generics
T = TypeVar('T')


class _QEventLoop(asyncio.AbstractEventLoop):
    """
    Qt-based event loop for asyncio integration
    """

    def __init__(self, app: QApplication = None):
        self._app = app or QCoreApplication.instance()
        self._is_running = False
        self._default_executor = None
        self._exception_handler = None
        self._notifiers = {}
        self._timers = {}
        self._schedule_timers = {}
        self._ready = []
        self._tasks = {}  # Add a dictionary to store tasks

        # Create a semaphore to prevent duplicate calls
        self._executing_callbacks = False

        # Connect quit signals
        signal.signal(signal.SIGINT, lambda *args: self.stop())

    # Override create_task method to implement it properly
    def create_task(self, coro):
        """Create a task from a coroutine"""
        if not asyncio.iscoroutine(coro):
            raise TypeError('A coroutine object is required')

        task = asyncio.Task(coro, loop=self)
        self._tasks[id(task)] = task

        def _on_task_done(task):
            del self._tasks[id(task)]

        task.add_done_callback(_on_task_done)
        return task

    # Required methods for AbstractEventLoop subclasses

    def run_forever(self):
        """Run the event loop until stop() is called"""
        if self._is_running:
            raise RuntimeError('Event loop is already running')

        self._is_running = True
        self._app.exec()
        self._is_running = False

    def run_until_complete(self, future):
        """Run until the future is done"""
        future = asyncio.ensure_future(future, loop=self)

        def _done_callback(fut):
            QCoreApplication.exit()

        future.add_done_callback(_done_callback)

        try:
            self.run_forever()
        finally:
            future.remove_done_callback(_done_callback)

        # Return the future's result or raise its exception
        if not future.done():
            raise RuntimeError('Future was not completed')

        return future.result()

    def stop(self):
        """Stop the event loop"""
        if not self._is_running:
            return

        self._app.quit()

    def is_running(self):
        """Return whether the event loop is currently running"""
        return self._is_running

    def close(self):
        """Close the event loop"""
        if self._is_running:
            raise RuntimeError('Event loop is running')

        # Close all notifiers and timers
        for notifier in list(self._notifiers.values()):
            notifier.setEnabled(False)
        self._notifiers.clear()

        for timer in list(self._timers.values()):
            timer.stop()
        self._timers.clear()

        for timer in list(self._schedule_timers.values()):
            timer.stop()
        self._schedule_timers.clear()

        # Cancel all tasks
        for task in list(self._tasks.values()):
            task.cancel()
        self._tasks.clear()

    # File descriptor methods

    def add_reader(self, fd, callback, *args):
        """Add a reader callback for a file descriptor"""
        self.remove_reader(fd)

        # Create a socket notifier for this file descriptor
        notifier = QSocketNotifier(fd, QSocketNotifier.Type.Read)

        # Connect the notifier to the callback
        notifier.activated.connect(lambda: self._ready.append(partial(callback, *args)))
        notifier.setEnabled(True)

        self._notifiers[(fd, QSocketNotifier.Type.Read)] = notifier

    def remove_reader(self, fd):
        """Remove a reader callback for a file descriptor"""
        key = (fd, QSocketNotifier.Type.Read)

        if key in self._notifiers:
            notifier = self._notifiers.pop(key)
            notifier.setEnabled(False)
            return True

        return False

    def add_writer(self, fd, callback, *args):
        """Add a writer callback for a file descriptor"""
        self.remove_writer(fd)

        # Create a socket notifier for this file descriptor
        notifier = QSocketNotifier(fd, QSocketNotifier.Type.Write)

        # Connect the notifier to the callback
        notifier.activated.connect(lambda: self._ready.append(partial(callback, *args)))
        notifier.setEnabled(True)

        self._notifiers[(fd, QSocketNotifier.Type.Write)] = notifier

    def remove_writer(self, fd):
        """Remove a writer callback for a file descriptor"""
        key = (fd, QSocketNotifier.Type.Write)

        if key in self._notifiers:
            notifier = self._notifiers.pop(key)
            notifier.setEnabled(False)
            return True

        return False

    # Timer methods

    def call_later(self, delay, callback, *args):
        """Schedule a callback to be called after a delay (in seconds)"""
        timer = QTimer()
        timer.setSingleShot(True)
        timer_handle = asyncio.TimerHandle(delay, callback, args, self)

        # Convert delay to milliseconds for QTimer
        timer.timeout.connect(lambda: self._ready.append(partial(timer_handle._run)))
        timer.start(int(delay * 1000))

        self._timers[timer_handle] = timer
        return timer_handle

    def call_at(self, when, callback, *args):
        """Schedule a callback to be called at a specific time"""
        now = self.time()
        delay = max(0, when - now)
        return self.call_later(delay, callback, *args)

    def call_soon(self, callback, *args):
        """Schedule a callback to be called soon"""
        timer_handle = asyncio.TimerHandle(0, callback, args, self)

        # Directly append to ready queue instead of using a timer
        self._ready.append(partial(timer_handle._run))

        # Process callbacks on next iteration
        if not self._executing_callbacks:
            QTimer.singleShot(0, self._process_callbacks)

        return timer_handle

    def time(self):
        """Return current time according to event loop's clock"""
        return asyncio.get_event_loop_policy().time()

    def _process_callbacks(self):
        """Process pending callbacks"""
        if self._executing_callbacks:
            return

        self._executing_callbacks = True

        # Make a copy of the ready queue
        ready = self._ready.copy()
        self._ready.clear()

        # Process all callbacks
        for callback in ready:
            try:
                callback()
            except Exception as e:
                self.default_exception_handler({
                    'message': 'Error in callback',
                    'exception': e,
                    'loop': self,
                })

        self._executing_callbacks = False

        # If more callbacks arrived during processing, schedule another processing
        if self._ready and not self._executing_callbacks:
            QTimer.singleShot(0, self._process_callbacks)


class QEventLoopPolicy(asyncio.DefaultEventLoopPolicy):
    """Event loop policy for using Qt with asyncio"""

    def __init__(self, application=None):
        super().__init__()
        self._application = application
        self._default_loop = None

    def get_event_loop(self):
        """Get the event loop for the current context"""
        if self._default_loop is None:
            self._default_loop = self.new_event_loop()
        return self._default_loop

    def new_event_loop(self):
        """Create a new event loop"""
        return _QEventLoop(self._application)


# Public API

def create_event_loop(application=None):
    """Create a new asyncio-compatible event loop using Qt"""
    return _QEventLoop(application)


def install(application=None):
    """Install the Qt event loop for asyncio"""
    policy = QEventLoopPolicy(application)
    asyncio.set_event_loop_policy(policy)
    return policy.get_event_loop()

class RunCoroutineInQt(QObject):
    """Helper class to run a coroutine from Qt code"""

    def __init__(self, coro, callback=None, error_callback=None):
        super().__init__()
        # Store the original coroutine or coroutine function
        self.coro = coro
        self.callback = callback
        self.error_callback = error_callback
        self.task = None
        self.loop = None

    def start(self):
        """Start the coroutine"""
        try:
            # Try to get the current event loop
            try:
                self.loop = asyncio.get_event_loop()
            except RuntimeError:
                # No event loop in this thread - create a temporary one
                self.loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self.loop)

            # Handle both coroutine functions and coroutine objects
            if asyncio.iscoroutinefunction(self.coro):
                # If it's a coroutine function, call it to get the coroutine object
                actual_coro = self.coro()
            elif asyncio.iscoroutine(self.coro):
                # If it's already a coroutine object, use it directly
                actual_coro = self.coro
            else:
                # Not a coroutine at all
                raise TypeError(f"Expected a coroutine or coroutine function, got {type(self.coro)}")

            # Schedule the coroutine to run right away
            if hasattr(self.loop, 'create_task') and callable(self.loop.create_task):
                self.task = self.loop.create_task(self._wrapped_coro(actual_coro))
            else:
                # Fallback for loops that don't implement create_task
                # Run in the background with a QTimer
                QTimer.singleShot(0, lambda: self._run_in_background(actual_coro))
        except Exception as e:
            logger.error(f"Error starting coroutine: {str(e)}", exc_info=True)
            if self.error_callback:
                self.error_callback(e)

    async def _wrapped_coro(self, coro):
        """Wrapper around the coroutine to handle callbacks"""
        try:
            result = await coro
            if self.callback:
                self.callback(result)
            return result
        except Exception as e:
            # Improve error logging with full traceback
            import traceback
            logger.error(f"Error in coroutine: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            if self.error_callback:
                self.error_callback(e)
            raise

    def _run_in_background(self, coro):
        """Run the coroutine in the background using a temporary event loop"""
        try:
            # Create a new event loop for this background task
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # Run the coroutine and get the result
            try:
                result = loop.run_until_complete(coro)
                if self.callback:
                    self.callback(result)
            except Exception as e:
                # Improve error logging with full traceback
                import traceback
                logger.error(f"Error in background coroutine: {str(e)}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                if self.error_callback:
                    self.error_callback(e)
        finally:
            # Clean up the temporary event loop
            loop.close()


def run_coroutine(coro: Union[Coroutine, Callable[[], Coroutine]],
                  callback: Optional[Callable[[Any], None]] = None,
                  error_callback: Optional[Callable[[Exception], None]] = None) -> None:
    """
    Run a coroutine from Qt code

    Args:
        coro: The coroutine or coroutine function to run
        callback: Optional callback to call with the result
        error_callback: Optional callback to call if an error occurs
    """
    # Create a runner and start it
    runner = RunCoroutineInQt(coro, callback, error_callback)
    runner.start()
    return runner