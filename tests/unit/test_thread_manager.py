"""
Unit tests for the OpenAIThreadManager class.
"""

import os
import sys
import pytest
import time
from unittest.mock import MagicMock, patch
from PyQt6.QtCore import QThread, QCoreApplication, QTimer

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.services.api import OpenAIThreadManager, OpenAIAPIWorker


class TestOpenAIThreadManager:
    """Tests for the OpenAIThreadManager class that manages worker threads."""
    
    def test_init(self):
        """Test thread manager initialization."""
        manager = OpenAIThreadManager()
        
        # Check the manager has initialized correctly
        assert hasattr(manager, 'active_threads')
        assert isinstance(manager.active_threads, dict)
        assert len(manager.active_threads) == 0
        assert hasattr(manager, 'logger')
    
    def test_create_worker(self, sample_messages, default_settings):
        """Test creating a worker thread."""
        manager = OpenAIThreadManager()
        
        # Create a worker
        thread_id, worker = manager.create_worker(sample_messages, default_settings)
        
        # Check the worker was created correctly
        assert thread_id is not None
        assert isinstance(worker, OpenAIAPIWorker)
        assert thread_id in manager.active_threads
        assert len(manager.active_threads) == 1
        
        # Check that the thread and worker are stored
        thread, stored_worker = manager.active_threads[thread_id]
        assert isinstance(thread, QThread)
        assert stored_worker is worker
        
        # Check that the worker is moved to the thread
        assert worker.thread() is thread
        
        # Instead of checking receivers() which is not available in PyQt6
        # Just verify that the worker exists in the active_threads dictionary
        assert thread_id in manager.active_threads

    @patch('PyQt6.QtCore.QThread')
    def test_start_worker(self, mock_qthread, sample_messages, default_settings):
        """Test starting a worker thread."""
        manager = OpenAIThreadManager()

        # Create a worker with mocked thread
        mock_thread = MagicMock()
        mock_worker = MagicMock()

        # Mock the thread creation
        mock_qthread.return_value = mock_thread

        # Manually insert the mock thread and worker
        thread_id = id(mock_thread)
        manager.active_threads[thread_id] = (mock_thread, mock_worker)

        # Start the worker
        result = manager.start_worker(thread_id)

        # Check the worker was started correctly
        assert result is True
        mock_thread.start.assert_called_once()

    def test_start_worker_invalid_id(self):
        """Test starting a worker with an invalid thread ID."""
        manager = OpenAIThreadManager()

        # Try to start a worker that doesn't exist
        result = manager.start_worker(12345)

        # Check the result indicates failure
        assert result is False

    @patch('PyQt6.QtCore.QThread')
    def test_cancel_worker(self, mock_qthread, sample_messages, default_settings):
        """Test cancelling a worker thread."""
        manager = OpenAIThreadManager()

        # Create a worker with mocked thread
        mock_thread = MagicMock()
        mock_worker = MagicMock()
        mock_thread.isRunning.return_value = True
        mock_thread.wait.return_value = True  # Thread finishes within timeout

        # Manually insert the mock thread and worker
        thread_id = id(mock_thread)
        manager.active_threads[thread_id] = (mock_thread, mock_worker)

        # Cancel the worker
        result = manager.cancel_worker(thread_id)

        # Check the worker was cancelled correctly
        assert result is True
        mock_worker.cancel.assert_called_once()
        mock_thread.wait.assert_called_once_with(3000)  # 3 second timeout

        # Check the thread and worker were removed from active_threads
        assert thread_id not in manager.active_threads

    @patch('PyQt6.QtCore.QThread')
    def test_cancel_worker_with_timeout(self, mock_qthread):
        """Test cancelling a worker thread that doesn't finish within timeout."""
        manager = OpenAIThreadManager()

        # Create a worker with mocked thread
        mock_thread = MagicMock()
        mock_worker = MagicMock()
        mock_thread.isRunning.return_value = True
        mock_thread.wait.return_value = False  # Thread doesn't finish within timeout

        # Manually insert the mock thread and worker
        thread_id = id(mock_thread)
        manager.active_threads[thread_id] = (mock_thread, mock_worker)

        # Cancel the worker
        result = manager.cancel_worker(thread_id)

        # Check the worker was cancelled correctly
        assert result is True
        mock_worker.cancel.assert_called_once()
        mock_thread.wait.assert_called_once_with(3000)  # 3 second timeout
        mock_thread.terminate.assert_called_once()  # Thread should be forcibly terminated

        # Check the thread and worker were removed from active_threads
        assert thread_id not in manager.active_threads

    def test_cancel_worker_invalid_id(self):
        """Test cancelling a worker with an invalid thread ID."""
        manager = OpenAIThreadManager()

        # Try to cancel a worker that doesn't exist
        result = manager.cancel_worker(12345)

        # Check the result indicates failure
        assert result is False

    @patch('PyQt6.QtCore.QThread')
    def test_cancel_all(self, mock_qthread):
        """Test cancelling all worker threads."""
        manager = OpenAIThreadManager()

        # Create multiple mock threads and workers
        mock_threads = []
        mock_workers = []
        thread_ids = []

        for i in range(3):
            mock_thread = MagicMock()
            mock_worker = MagicMock()
            mock_thread.isRunning.return_value = True
            mock_thread.wait.return_value = True

            thread_id = id(mock_thread) + i  # Ensure unique IDs
            manager.active_threads[thread_id] = (mock_thread, mock_worker)

            mock_threads.append(mock_thread)
            mock_workers.append(mock_worker)
            thread_ids.append(thread_id)

        # Cancel all workers
        manager.cancel_all()

        # Check all workers were cancelled
        for mock_worker in mock_workers:
            mock_worker.cancel.assert_called_once()

        # Check all threads were waited on
        for mock_thread in mock_threads:
            mock_thread.wait.assert_called_once_with(3000)

        # Check all threads and workers were removed
        assert len(manager.active_threads) == 0

    def test_cleanup_thread(self):
        """Test the _cleanup_thread method."""
        manager = OpenAIThreadManager()

        # Create a mock thread and worker
        mock_thread = MagicMock()
        mock_worker = MagicMock()

        # Manually insert the mock thread and worker
        thread_id = id(mock_thread)
        manager.active_threads[thread_id] = (mock_thread, mock_worker)

        # Clean up the thread
        manager._cleanup_thread(thread_id)

        # Check the thread and worker were removed
        assert thread_id not in manager.active_threads

    @patch('src.services.api.OpenAIThreadManager._cleanup_thread')
    def test_thread_finished_signal(self, mock_cleanup_thread):
        """Test that thread finished signal triggers cleanup."""
        manager = OpenAIThreadManager()

        # Create a real worker to test signal connections
        thread_id, worker = manager.create_worker([], {})
        thread, _ = manager.active_threads[thread_id]

        # Get the thread from active_threads
        mock_cleanup_thread.reset_mock()

        # Manually emit the finished signal
        thread.finished.emit()

        # Wait a small amount of time for the signal to be processed
        QCoreApplication.processEvents()

        # Check that _cleanup_thread was called with the thread_id
        mock_cleanup_thread.assert_called_once_with(thread_id)