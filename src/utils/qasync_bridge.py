# src/utils/qasync_bridge.py

import sys
import asyncio
import signal
from functools import partial
from typing import Optional, Any, Callable, Coroutine

from PyQt6.QtCore import QObject, QSocketNotifier, QTimer, QCoreApplication
from PyQt6.QtWidgets import QApplication


# This implementation adapts the qasync library to our needs
# It allows running asyncio coroutines in a Qt application

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

        # Create a semaphore to prevent duplicate calls
        self._executing_callbacks = False

        # Connect quit signals
        signal.signal(signal.SIGINT, lambda *args: self.stop())

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


# Utility functions to run coroutines from Qt code

class RunCoroutineInQt(QObject):
    """Helper class to run a coroutine from Qt code"""

    def __init__(self, coro, callback=None, error_callback=None):
        super().__init__()
        self.coro = coro
        self.callback = callback
        self.error_callback = error_callback
        self.task = None

    def start(self):
        """Start the coroutine"""
        loop = asyncio.get_event_loop()
        self.task = loop.create_task(self.coro)
        self.task.add_done_callback(self._on_task_done)

    def _on_task_done(self, task):
        """Handle task completion"""
        try:
            result = task.result()
            if self.callback:
                self.callback(result)
        except Exception as e:
            if self.error_callback:
                self.error_callback(e)
            else:
                print(f"Unhandled exception in coroutine: {e}")


def run_coroutine(coro: Coroutine, callback: Callable[[Any], None] = None,
                  error_callback: Callable[[Exception], None] = None) -> None:
    """
    Run a coroutine from Qt code

    Args:
        coro: The coroutine to run
        callback: Optional callback to call with the result
        error_callback: Optional callback to call if an error occurs
    """
    runner = RunCoroutineInQt(coro, callback, error_callback)
    runner.start()
    return runner