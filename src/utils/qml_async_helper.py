"""
Enhanced helper module for integrating QML with async Python code using qasync.
Provides reliable utilities for running async code from QML signals.
"""

import asyncio
import traceback
import uuid
from typing import Any, Callable, Dict, Optional

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QVariant

from src.utils.qasync_bridge import run_coroutine, ensure_qasync_loop
from src.utils.logging_utils import get_logger

# Get a logger for this module
logger = get_logger(__name__)

class QmlAsyncHelper(QObject):
    """
    Helper class to safely run async code from QML using qasync

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

        # Run the coroutine using qasync
        try:
            coro = method(*params)
            if not asyncio.iscoroutine(coro):
                self.logger.error(f"Method {method_name} is not a coroutine")
                self.taskError.emit(task_id, f"Method {method_name} is not a coroutine")
                return task_id

            # Track the task
            self._active_tasks[task_id] = True
            self.taskStarted.emit(task_id)

            # Run the coroutine with qasync
            runner = run_coroutine(
                coro,
                callback=lambda result: self._handle_task_success(task_id, result),
                error_callback=lambda error: self._handle_task_error(task_id, error)
            )

            # Store the task for potential cancellation
            self._active_tasks[task_id] = runner

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
        """Cancel a running task using qasync cancellation"""
        if task_id in self._active_tasks:
            self.logger.debug(f"Cancelling task {task_id}")
            task = self._active_tasks[task_id]

            if hasattr(task, 'cancel'):
                task.cancel()

            del self._active_tasks[task_id]

    async def cleanup(self):
        """Clean up resources when shutting down"""
        self.logger.debug(f"Cleaning up {len(self._active_tasks)} active tasks")

        # Cancel all tasks
        for task_id, task in list(self._active_tasks.items()):
            try:
                if hasattr(task, 'cancel'):
                    task.cancel()
            except Exception as e:
                self.logger.error(f"Error cancelling task {task_id}: {str(e)}")

        self._active_tasks.clear()

    # Example async methods that can be called from QML

    async def search_conversations(self, search_term, conversation_id=None):
        """
        Search conversations for messages containing the search term

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
        Get all conversations

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
        Process a file for attachment

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
        progress_dict = {}

        def update_progress(progress):
            progress_dict['progress'] = progress
            self.report_progress(os.path.basename(file_path), progress)

        # Process the file
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