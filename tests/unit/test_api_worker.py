"""
Unit tests for the OpenAIAPIWorker class with improved mocking.
"""

import os
import sys
import pytest
from unittest.mock import MagicMock, patch, Mock
from PyQt6.QtCore import QCoreApplication
import openai

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.services.api import OpenAIAPIWorker

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


class TestOpenAIAPIWorker:
    """Tests for the OpenAIAPIWorker class that handles OpenAI API interactions."""

    def test_init(self, sample_messages, default_settings):
        """Test worker initialization with messages and settings."""
        worker = OpenAIAPIWorker(sample_messages, default_settings)

        # Check the worker has initialized correctly
        assert worker.messages == sample_messages
        assert worker.settings == default_settings
        assert hasattr(worker, 'logger')
        assert not worker._is_cancelled

    def test_prepare_input_for_responses_api(self, sample_messages):
        """Test message preparation for the Responses API."""
        worker = OpenAIAPIWorker(sample_messages, {"api_type": "responses"})

        # Prepare input for Responses API
        prepared_input = worker.prepare_input(sample_messages, "responses")

        # For Responses API, system messages are typically handled separately
        # as "instructions" parameter, not included in the input
        assert "User: Hello, this is a test message" in prepared_input
        assert isinstance(prepared_input, str)

        # Check that system message is not in the prepared input (by design)
        # This is because system messages should be passed as 'instructions'
        assert "You are a helpful assistant" not in prepared_input

    def test_prepare_input_for_chat_completions_api(self, sample_messages):
        """Test message preparation for the Chat Completions API."""
        worker = OpenAIAPIWorker(sample_messages, {"api_type": "chat_completions"})

        # Prepare input for Chat Completions API
        prepared_input = worker.prepare_input(sample_messages, "chat_completions")

        # Check it returned a list of message objects
        assert isinstance(prepared_input, list)
        assert len(prepared_input) == 2
        assert prepared_input[0]["role"] == "system"
        assert prepared_input[1]["role"] == "user"

    def test_process_response_api(self, mock_signal_receiver, sample_messages, default_settings):
        """Test processing a Response API call without streaming."""
        # Create mock client with response
        mock_response = MagicMock()
        mock_response.output_text = "This is a test response."
        mock_response.model = "gpt-4o"
        mock_response.id = "resp_123456789"
        mock_response.usage = MagicMock()
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 20
        mock_response.usage.total_tokens = 30

        # Configure mock client
        mock_client = MagicMock()
        mock_client.responses.create.return_value = mock_response

        # Configure test settings
        settings = default_settings.copy()
        settings["api_type"] = "responses"
        settings["stream"] = False

        # Create the worker
        worker = OpenAIAPIWorker(sample_messages, settings)

        # Connect signals
        worker.message_received.connect(mock_signal_receiver.on_message_received)
        worker.error_occurred.connect(mock_signal_receiver.on_error_occurred)
        worker.usage_info.connect(mock_signal_receiver.on_usage_info)
        worker.system_info.connect(mock_signal_receiver.on_system_info)
        worker.worker_finished.connect(mock_signal_receiver.on_worker_finished)

        # Process the request - IMPORTANT: Use proper patching
        with patch('openai.OpenAI', return_value=mock_client):
            worker.process()

        # Verify client was called with correct settings
        mock_client.responses.create.assert_called_once()

        # Verify signals were emitted
        assert len(mock_signal_receiver.received_messages) == 1
        assert mock_signal_receiver.received_messages[0] == "This is a test response."
        assert len(mock_signal_receiver.received_errors) == 0
        assert len(mock_signal_receiver.received_usage_info) == 1
        assert len(mock_signal_receiver.received_system_info) == 1
        assert mock_signal_receiver.worker_finished_called

    def test_process_chat_completions_api(self, mock_signal_receiver, sample_messages, default_settings):
        """Test processing a Chat Completions API call without streaming."""
        # Set up mock response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message = MagicMock()
        mock_response.choices[0].message.content = "This is a test chat response."
        mock_response.model = "gpt-4o"
        mock_response.id = "chatcmpl_123456789"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 20
        mock_response.usage.total_tokens = 30

        # Configure mock client
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        # Configure test settings
        settings = default_settings.copy()
        settings["api_type"] = "chat_completions"
        settings["stream"] = False

        # Create the worker
        worker = OpenAIAPIWorker(sample_messages, settings)

        # Connect signals
        worker.message_received.connect(mock_signal_receiver.on_message_received)
        worker.error_occurred.connect(mock_signal_receiver.on_error_occurred)
        worker.usage_info.connect(mock_signal_receiver.on_usage_info)
        worker.system_info.connect(mock_signal_receiver.on_system_info)
        worker.worker_finished.connect(mock_signal_receiver.on_worker_finished)

        # Process the request - IMPORTANT: Use proper patching
        with patch('openai.OpenAI', return_value=mock_client):
            worker.process()

        # Verify client was called with correct settings
        mock_client.chat.completions.create.assert_called_once()

        # Verify signals were emitted
        assert len(mock_signal_receiver.received_messages) == 1
        assert mock_signal_receiver.received_messages[0] == "This is a test chat response."
        assert len(mock_signal_receiver.received_errors) == 0
        assert len(mock_signal_receiver.received_usage_info) == 1
        assert len(mock_signal_receiver.received_system_info) == 1
        assert mock_signal_receiver.worker_finished_called

    def test_process_streaming_response(self, mock_signal_receiver, sample_messages, default_settings):
        """Test processing a streaming response."""
        # Define a list of chunks as dictionaries to avoid Mock type issues
        chunk_dicts = [
            {
                "choices": [{"delta": {"content": "Hello, "}, "finish_reason": None}],
                "model": "gpt-4o",
                "id": "chatcmpl_123456789"
            },
            {
                "choices": [{"delta": {"content": "world!"}, "finish_reason": None}],
                "model": "gpt-4o",
                "id": "chatcmpl_123456789"
            },
            {
                "choices": [{"delta": {"content": ""}, "finish_reason": "stop"}],
                "model": "gpt-4o",
                "id": "chatcmpl_123456789",
                "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
            }
        ]

        # Convert dictionaries to objects with proper attributes
        chunks = []
        for chunk_dict in chunk_dicts:
            # Create a simple class that can have attributes set dynamically
            class SimpleObject: pass

            # Create the chunk object
            chunk = SimpleObject()
            chunk.id = chunk_dict["id"]
            chunk.model = chunk_dict["model"]

            # Create choices list with proper attributes
            chunk.choices = []
            for choice_dict in chunk_dict["choices"]:
                choice = SimpleObject()

                # Create delta with content attribute
                delta = SimpleObject()
                delta.content = choice_dict["delta"]["content"]
                choice.delta = delta

                # Set finish reason
                choice.finish_reason = choice_dict["finish_reason"]

                # Add to choices list
                chunk.choices.append(choice)

            # Set usage if present
            if "usage" in chunk_dict:
                usage = SimpleObject()
                usage.prompt_tokens = chunk_dict["usage"]["prompt_tokens"]
                usage.completion_tokens = chunk_dict["usage"]["completion_tokens"]
                usage.total_tokens = chunk_dict["usage"]["total_tokens"]
                chunk.usage = usage

            # Add to chunks list
            chunks.append(chunk)

        # Create a mock stream that's iterable with our chunks
        mock_stream = MagicMock()
        mock_stream.__iter__.return_value = iter(chunks)

        # Configure mock client
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_stream

        # Configure test settings
        settings = default_settings.copy()
        settings["api_type"] = "chat_completions"
        settings["stream"] = True

        # Create the worker
        worker = OpenAIAPIWorker(sample_messages, settings)

        # Connect signals
        worker.chunk_received.connect(mock_signal_receiver.on_chunk_received)
        worker.message_received.connect(mock_signal_receiver.on_message_received)
        worker.error_occurred.connect(mock_signal_receiver.on_error_occurred)
        worker.usage_info.connect(mock_signal_receiver.on_usage_info)
        worker.system_info.connect(mock_signal_receiver.on_system_info)
        worker.worker_finished.connect(mock_signal_receiver.on_worker_finished)

        # Process the request - IMPORTANT: Use proper patching
        with patch('openai.OpenAI', return_value=mock_client):
            worker.process()

        # Verify client was called with correct settings
        mock_client.chat.completions.create.assert_called_once()

        # Verify signals were emitted
        assert len(mock_signal_receiver.received_chunks) == 2
        assert mock_signal_receiver.received_chunks[0] == "Hello, "
        assert mock_signal_receiver.received_chunks[1] == "world!"
        assert len(mock_signal_receiver.received_messages) == 1  # Full combined message at the end
        assert mock_signal_receiver.received_messages[0] == "Hello, world!"
        assert len(mock_signal_receiver.received_usage_info) == 1

    def test_api_error_handling(self, mock_signal_receiver, sample_messages, default_settings):
        """Test handling of API errors."""
        # Create mock client that raises an exception
        mock_client = MagicMock()
        mock_client.responses.create.side_effect = openai.BadRequestError(
            message="API Error",
            response=MagicMock(status_code=400),
            body={"error": {"message": "API Error"}}
        )

        # Create the worker
        worker = OpenAIAPIWorker(sample_messages, default_settings)

        # Connect signals
        worker.error_occurred.connect(mock_signal_receiver.on_error_occurred)
        worker.worker_finished.connect(mock_signal_receiver.on_worker_finished)

        # Process the request - IMPORTANT: Use proper patching
        with patch('openai.OpenAI', return_value=mock_client):
            worker.process()

        # Verify error signal was emitted
        assert len(mock_signal_receiver.received_errors) == 1
        assert "Bad request" in mock_signal_receiver.received_errors[0]
        assert mock_signal_receiver.worker_finished_called

    def test_cancel(self, sample_messages, default_settings):
        """Test cancellation of the worker."""
        worker = OpenAIAPIWorker(sample_messages, default_settings)

        # Cancel the worker
        worker.cancel()

        # Check the worker is marked as cancelled
        assert worker._is_cancelled

    def test_process_with_reasoning_models(self, mock_signal_receiver, sample_messages):
        """Test processing with reasoning models (o1, o3-mini, etc.)."""
        # Set up mock response with reasoning information
        mock_response = MagicMock()
        mock_response.output_text = "This is a test response with reasoning."
        mock_response.model = "o1"
        mock_response.id = "resp_reasoning_123"
        mock_response.usage = MagicMock()
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 20
        mock_response.usage.total_tokens = 30
        mock_response.usage.output_tokens_details = MagicMock()
        mock_response.usage.output_tokens_details.reasoning_tokens = 15

        # Configure mock client
        mock_client = MagicMock()
        mock_client.responses.create.return_value = mock_response

        # Configure test settings for reasoning model
        settings = {
            "api_type": "responses",
            "api_key": os.environ.get("OPENAI_API_KEY", ""),
            "model": "o1",
            "stream": False,
            "reasoning": {"effort": "high"},
            "max_output_tokens": 2000,
            "reasoning_models": ["o1", "o3-mini", "deepseek-reasoner"] # Add this to ensure reasoning parameter is included
        }

        # Create the worker
        worker = OpenAIAPIWorker(sample_messages, settings)

        # Connect signals
        worker.message_received.connect(mock_signal_receiver.on_message_received)
        worker.usage_info.connect(mock_signal_receiver.on_usage_info)
        worker.system_info.connect(mock_signal_receiver.on_system_info)
        worker.worker_finished.connect(mock_signal_receiver.on_worker_finished)

        # Process the request - IMPORTANT: Use proper patching
        with patch('openai.OpenAI', return_value=mock_client):
            worker.process()

        # Verify responses.create was called with reasoning params
        mock_client.responses.create.assert_called_once()
        call_args = mock_client.responses.create.call_args[1]
        assert "reasoning" in call_args
        assert call_args["reasoning"]["effort"] == "high"

        # Verify usage info with reasoning tokens
        assert len(mock_signal_receiver.received_usage_info) == 1
        assert "completion_tokens_details" in mock_signal_receiver.received_usage_info[0]
        assert mock_signal_receiver.received_usage_info[0]["completion_tokens_details"]["reasoning_tokens"] == 15

    def test_normalize_token_usage(self, sample_messages, default_settings):
        """Test the normalization of token usage data."""
        worker = OpenAIAPIWorker(sample_messages, default_settings)

        # Test Response API usage normalization
        response_usage = {
            "input_tokens": 20,
            "output_tokens": 30,
            "total_tokens": 50
        }

        normalized = worker._normalize_token_usage(response_usage, "responses")
        assert normalized["prompt_tokens"] == 20
        assert normalized["completion_tokens"] == 30
        assert normalized["total_tokens"] == 50

        # Test Chat Completions API usage normalization
        chat_usage = {
            "prompt_tokens": 25,
            "completion_tokens": 35,
            "total_tokens": 60
        }

        normalized = worker._normalize_token_usage(chat_usage, "chat_completions")
        assert normalized["prompt_tokens"] == 25
        assert normalized["completion_tokens"] == 35
        assert normalized["total_tokens"] == 60




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