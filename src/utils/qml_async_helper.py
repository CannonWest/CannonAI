"""
Enhanced helper module for integrating QML with async Python code using qasync.
Provides reliable utilities for running async code from QML signals.
"""

import asyncio
import traceback
import uuid
import time
from typing import Any, Callable, Dict, Optional, List, Union

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QVariant, QTimer

from src.utils.qasync_bridge import run_coroutine, ensure_qasync_loop
from src.utils.logging_utils import get_logger

# Get a logger for this module
logger = get_logger(__name__)

class QmlAsyncHelper(QObject):
    """
    Helper class to safely run async code from QML using qasync.

    This class provides a reliable bridge between QML signals and async Python code,
    with proper error handling, task tracking, progress reporting, and timeout support.
    """
    # Signals for communicating results back to QML
    taskStarted = pyqtSignal(str)  # Task ID
    taskFinished = pyqtSignal(str, 'QVariant')  # Task ID, Result
    taskError = pyqtSignal(str, str)  # Task ID, Error message
    taskProgress = pyqtSignal(str, int)  # Task ID, Progress percentage
    taskCancelled = pyqtSignal(str)  # Task ID

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_tasks = {}
        self.logger = get_logger(__name__ + ".QmlAsyncHelper")

        # Set up a timer to periodically check task status
        self._task_monitor = QTimer()
        self._task_monitor.setInterval(5000)  # 5 seconds
        self._task_monitor.timeout.connect(self._check_active_tasks)
        self._task_monitor.start()

    @pyqtSlot(str, str, 'QVariant', result=str)
    def run_async_task(self, task_name: str, method_name: str, params=None) -> str:
        """
        Run an async method from QML with reliable task tracking.

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
            error_msg = f"Method {method_name} not found"
            self.logger.error(error_msg)
            self.taskError.emit(task_id, error_msg)
            return task_id

        # Process parameters
        if params is None:
            params = []
        elif not isinstance(params, list):
            params = [params]

        # Run the coroutine using improved qasync approach
        try:
            # Make sure we have a coroutine
            coro = method(*params)
            if not asyncio.iscoroutine(coro):
                error_msg = f"Method {method_name} is not a coroutine"
                self.logger.error(error_msg)
                self.taskError.emit(task_id, error_msg)
                return task_id

            # Make sure the event loop is properly running
            ensure_qasync_loop()

            # Track the task - start time for monitoring
            self._active_tasks[task_id] = {
                'start_time': time.time(),
                'method': method_name,
                'runner': None,
                'last_activity': time.time()
            }

            # Emit started signal
            self.taskStarted.emit(task_id)

            # Create wrapper callbacks that track activity time
            def success_callback(result):
                self.logger.debug(f"Task {task_id} completed successfully")
                self._handle_task_success(task_id, result)

            def error_callback(error):
                self.logger.error(f"Task {task_id} failed: {str(error)}")
                self._handle_task_error(task_id, error)

            def progress_callback(progress):
                # Update last activity time for monitoring
                if task_id in self._active_tasks:
                    self._active_tasks[task_id]['last_activity'] = time.time()
                # Forward progress
                self.taskProgress.emit(task_id, progress)

            # Run the coroutine with timeout and progress tracking
            runner = run_coroutine(
                coro,
                callback=success_callback,
                error_callback=error_callback,
                timeout=120  # 2 minute timeout by default
            )

            # Store the runner for potential cancellation
            if task_id in self._active_tasks:
                self._active_tasks[task_id]['runner'] = runner

            return task_id
        except Exception as e:
            self.logger.error(f"Error starting task {task_id}: {str(e)}")
            self.taskError.emit(task_id, f"Error starting task: {str(e)}")
            return task_id

    def _handle_task_success(self, task_id: str, result: Any):
        """
        Handle successful task completion.

        Args:
            task_id: The task ID
            result: The result data
        """
        # Emit result to QML
        self.taskFinished.emit(task_id, result)

        # Clean up task tracking
        if task_id in self._active_tasks:
            del self._active_tasks[task_id]

    def _handle_task_error(self, task_id: str, error: Exception):
        """
        Handle task error with improved diagnostics.

        Args:
            task_id: The task ID
            error: The exception that occurred
        """
        # Get error details
        error_msg = str(error)
        error_type = type(error).__name__

        # Log with traceback for debugging
        self.logger.error(f"Task {task_id} failed [{error_type}]: {error_msg}")
        self.logger.error(traceback.format_exc())

        # Emit error to QML
        self.taskError.emit(task_id, error_msg)

        # Clean up task tracking
        if task_id in self._active_tasks:
            del self._active_tasks[task_id]

    @pyqtSlot(str, int)
    def report_progress(self, task_id: str, progress: int):
        """
        Report task progress to QML.

        Args:
            task_id: The task ID
            progress: Progress percentage (0-100)
        """
        # Update last activity time
        if task_id in self._active_tasks:
            self._active_tasks[task_id]['last_activity'] = time.time()

        # Emit progress signal
        self.taskProgress.emit(task_id, progress)

    @pyqtSlot(str)
    def cancel_task(self, task_id: str):
        """
        Cancel a running task.

        Args:
            task_id: The task ID to cancel
        """
        if task_id in self._active_tasks:
            self.logger.debug(f"Cancelling task {task_id}")

            # Get the runner
            task_info = self._active_tasks[task_id]
            runner = task_info.get('runner')

            # Cancel if possible
            if runner and hasattr(runner, 'cancel'):
                runner.cancel()

            # Emit cancelled signal
            self.taskCancelled.emit(task_id)

            # Remove from tracking
            del self._active_tasks[task_id]

    def _check_active_tasks(self):
        """Periodically check active tasks for timeouts or stalled operations."""
        if not self._active_tasks:
            return

        current_time = time.time()

        # Check each task
        for task_id, info in list(self._active_tasks.items()):
            start_time = info.get('start_time', 0)
            last_activity = info.get('last_activity', 0)
            method = info.get('method', 'unknown')

            # Check for tasks running too long (10 minutes maximum)
            if current_time - start_time > 600:  # 10 minutes
                self.logger.warning(f"Task {task_id} ({method}) running for over 10 minutes - cancelling")
                self.cancel_task(task_id)

            # Check for stalled tasks (no activity for 2 minutes)
            elif current_time - last_activity > 120:  # 2 minutes
                self.logger.warning(f"Task {task_id} ({method}) has had no activity for 2 minutes - may be stalled")
                # We don't auto-cancel stalled tasks, just log a warning

    async def cleanup(self):
        """
        Clean up resources when shutting down.

        This method cancels all active tasks and performs other cleanup.
        """
        self.logger.debug(f"Cleaning up {len(self._active_tasks)} active tasks")

        # Stop the monitoring timer
        if self._task_monitor.isActive():
            self._task_monitor.stop()

        # Cancel all active tasks
        for task_id, info in list(self._active_tasks.items()):
            try:
                runner = info.get('runner')
                if runner and hasattr(runner, 'cancel'):
                    runner.cancel()
                    self.logger.debug(f"Cancelled task {task_id} during cleanup")
            except Exception as e:
                self.logger.error(f"Error cancelling task {task_id}: {str(e)}")

        # Clear the tasks dictionary
        self._active_tasks.clear()

    # Example async methods that can be called from QML

    async def search_conversations(self, search_term, conversation_id=None):
        """
        Search conversations for messages containing the search term.

        Args:
            search_term: The text to search for
            conversation_id: Optional ID to limit search to a specific conversation

        Returns:
            List of matching message dictionaries
        """
        from src.services.database import AsyncConversationService

        # Get the conversation service
        conversation_service = AsyncConversationService()

        # Initialize if necessary
        if not hasattr(conversation_service, '_initialized') or not conversation_service._initialized:
            await conversation_service.initialize()

        # Perform the search
        results = await conversation_service.search_conversations(search_term, conversation_id)
        return results

    async def get_all_conversations(self):
        """
        Get all conversations.

        Returns:
            List of conversation dictionaries
        """
        from src.services.database import AsyncConversationService

        # Get the conversation service
        conversation_service = AsyncConversationService()

        # Initialize if necessary
        if not hasattr(conversation_service, '_initialized') or not conversation_service._initialized:
            await conversation_service.initialize()

        # Get all conversations
        conversations = await conversation_service.get_all_conversations()

        # Convert to list of dicts
        result = []
        for conv in conversations:
            result.append({
                'id': conv.id,
                'name': conv.name,
                'modified_at': conv.modified_at.isoformat() if conv.modified_at else None,
                'created_at': conv.created_at.isoformat() if conv.created_at else None
            })

        return result

    async def process_file(self, file_url):
        """
        Process a file for attachment with progress reporting.

        Args:
            file_url: URL to the file (e.g., "file:///path/to/file.txt")

        Returns:
            Dictionary with file information
        """
        import os
        from src.utils.async_file_utils import get_file_info_async

        # Convert QML URL to file path
        if hasattr(file_url, 'toString'):
            file_url = file_url.toString()

        if file_url.startswith('file:///'):
            # Handle Windows paths differently
            if os.name == 'nt':
                file_path = file_url[8:]  # Remove 'file:///'
            else:
                file_path = file_url[7:]  # Remove 'file://'
        else:
            file_path = file_url

        # Track progress for UI updates
        task_id = f"file_{os.path.basename(file_path)}"

        def update_progress(progress):
            self.report_progress(task_id, progress)

        # Process the file with progress tracking
        file_info = await get_file_info_async(
            file_path,
            progress_callback=update_progress
        )

        if file_info:
            return {
                'fileName': file_info['file_name'],
                'filePath': file_path,
                'fileSize': self._format_file_size(file_info['size']),
                'tokenCount': file_info['token_count']
            }
        else:
            return None

    def _format_file_size(self, size):
        """Format file size to human-readable string"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"