"""
Enhanced helper module for integrating QML with async Python code.
Provides reliable utilities for running async code from QML signals.
"""

import asyncio
import traceback
import uuid
from typing import Any, Callable, Dict, Optional

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QVariant

from src.utils.qasync_bridge import run_coroutine
from src.utils.logging_utils import get_logger

# Get a logger for this module
logger = get_logger(__name__)

class QmlAsyncHelper(QObject):
    """
    Helper class to safely run async code from QML
    
    This provides a reliable bridge between QML signals and async Python code,
    with proper error handling and result propagation.
    """
    # Signals for communicating results back to QML
    taskStarted = pyqtSignal(str)  # Task ID
    taskFinished = pyqtSignal(str, 'QVariant')  # Task ID, Result
    taskError = pyqtSignal(str, str)  # Task ID, Error message
    taskProgress = pyqtSignal(str, int)  # Task ID, Progress percentage
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_tasks = {}
        self.logger = get_logger(__name__ + ".QmlAsyncHelper")
    
    @pyqtSlot(str, str, 'QVariant', result=str)
    def run_async_task(self, task_name: str, method_name: str, params=None) -> str:
        """
        Run an async method from QML
        
        Args:
            task_name: Name/category of the task (for logging/tracking)
            method_name: Name of the method to call
            params: Parameters to pass to the method
            
        Returns:
            Task ID for tracking
        """
        # Generate a unique task ID
        task_id = f"{task_name}_{uuid.uuid4()}"
        self.logger.debug(f"Starting async task: {task_id} (method: {method_name})")
        
        # Get the method to call
        method = getattr(self, method_name, None)
        if not method:
            self.logger.error(f"Method {method_name} not found")
            self.taskError.emit(task_id, f"Method {method_name} not found")
            return task_id
        
        # Process parameters
        if params is None:
            params = []
        elif not isinstance(params, list):
            params = [params]
        
        # Run the coroutine
        try:
            coro = method(*params)
            if not asyncio.iscoroutine(coro):
                self.logger.error(f"Method {method_name} is not a coroutine")
                self.taskError.emit(task_id, f"Method {method_name} is not a coroutine")
                return task_id
                
            # Track the task
            self._active_tasks[task_id] = True
            self.taskStarted.emit(task_id)
            
            # Run the coroutine and handle results
            run_coroutine(
                coro,
                callback=lambda result: self._handle_task_success(task_id, result),
                error_callback=lambda error: self._handle_task_error(task_id, error)
            )
            
            return task_id
        except Exception as e:
            self.logger.error(f"Error starting task {task_id}: {str(e)}")
            self.taskError.emit(task_id, f"Error starting task: {str(e)}")
            return task_id
    
    def _handle_task_success(self, task_id: str, result: Any):
        """Handle successful task completion"""
        self.logger.debug(f"Task {task_id} completed successfully")
        self.taskFinished.emit(task_id, result)
        if task_id in self._active_tasks:
            del self._active_tasks[task_id]
    
    def _handle_task_error(self, task_id: str, error: Exception):
        """Handle task error"""
        error_msg = str(error)
        self.logger.error(f"Task {task_id} failed: {error_msg}")
        self.logger.error(traceback.format_exc())
        self.taskError.emit(task_id, error_msg)
        if task_id in self._active_tasks:
            del self._active_tasks[task_id]
    
    @pyqtSlot(str, int)
    def report_progress(self, task_id: str, progress: int):
        """Report task progress to QML"""
        self.taskProgress.emit(task_id, progress)
    
    @pyqtSlot(str)
    def cancel_task(self, task_id: str):
        """Cancel a running task (if possible)"""
        if task_id in self._active_tasks:
            self.logger.debug(f"Cancelling task {task_id}")
            # Note: actual cancellation depends on how run_coroutine is implemented
            # This just marks the task as no longer active
            del self._active_tasks[task_id]
            
    def cleanup(self):
        """Clean up resources when shutting down"""
        self.logger.debug(f"Cleaning up {len(self._active_tasks)} active tasks")
        self._active_tasks.clear()
        
    # Add your async methods here
    # They will be callable from QML via run_async_task
    
    async def example_async_method(self, param1, param2=None):
        """Example async method that can be called from QML"""
        # This is just an example - implement your actual methods
        await asyncio.sleep(1)  # Simulate work
        return {"result": f"Processed {param1} with {param2}"}
