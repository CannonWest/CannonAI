"""
Asynchronous helper utilities for UI integration with asyncio
"""

import asyncio
import threading
import functools
from typing import Any, Callable, Coroutine, TypeVar, Optional

T = TypeVar('T')

class AsyncHelper:
    """Helper class for running async operations in a tkinter application"""
    
    def __init__(self):
        """Initialize the async helper with its own event loop"""
        self.loop = asyncio.new_event_loop()
        self.thread = None
        
    def start_background_loop(self) -> None:
        """Start the event loop in a background thread"""
        if self.thread is not None and self.thread.is_alive():
            print("Background loop already running")
            return
            
        print("Starting asyncio event loop in background thread")
        
        def run_event_loop():
            """Run the event loop until stopped"""
            asyncio.set_event_loop(self.loop)
            try:
                self.loop.run_forever()
            except Exception as e:
                print(f"Error in asyncio loop: {e}")
            finally:
                print("Asyncio loop stopped")
                
        self.thread = threading.Thread(target=run_event_loop, daemon=True)
        self.thread.start()
        
    def run_coroutine(self, coro: Coroutine) -> asyncio.Future:
        """Run a coroutine in the background loop
        
        Args:
            coro: The coroutine to run
            
        Returns:
            A Future that will be resolved with the result of the coroutine
        """
        return asyncio.run_coroutine_threadsafe(coro, self.loop)
        
    def stop(self) -> None:
        """Stop the background event loop"""
        if self.loop.is_running():
            print("Stopping asyncio event loop")
            self.loop.call_soon_threadsafe(self.loop.stop)
            
    def tk_sleep(self, root: Any, ms: int) -> None:
        """Non-blocking sleep in tkinter
        
        Args:
            root: tkinter root window
            ms: milliseconds to sleep
        """
        var = threading.Event()
        root.after(ms, var.set)
        var.wait()
