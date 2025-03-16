"""
Tests for error handling in OpenAI API calls.
"""

import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.services.api import OpenAIAPIWorker


class TestAPIErrorHandling:
    """Tests for error handling in OpenAI API calls."""
    
    @pytest.fixture
    def base_settings(self):
        """Return base settings for API calls."""
        return {
            "api_type": "responses",
            "model": "gpt-4o",
            "temperature": 0.7,
            "max_output_tokens": 1024,
            "stream": False,
            "api_key": "test_api_key"
        }
    
    @pytest.fixture
    def base_messages(self):
        """Return base messages for API calls."""
        return [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello, this is a test message."}
        ]
    
    @patch('src.services.api.OpenAI')
    def test_authentication_error(self, mock_openai, base_settings, base_messages):
        """Test handling of authentication errors."""
        # Configure mock to raise an authentication error
        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        # Define an OpenAI-like error class
        class AuthenticationError(Exception):
            pass

        # Configure the mock client to raise the error when used
        mock_client.responses.create.side_effect = AuthenticationError("Invalid API key")

        # Set up the error properties on the mock module
        mock_openai.AuthenticationError = AuthenticationError

        # Create worker and error signal receiver
        worker = OpenAIAPIWorker(base_messages, base_settings)
        error_messages = []

        def capture_error(error_msg):
            error_messages.append(error_msg)

        worker.error_occurred.connect(capture_error)

        # Process the request
        worker.process()

        # Verify the error was captured
        assert len(error_messages) == 1
        assert "Authentication failed" in error_messages[0]

    @patch('src.services.api.OpenAI')
    def test_rate_limit_error(self, mock_openai, base_settings, base_messages):
        """Test handling of rate limit errors."""
        # Configure mock
        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        # Define an OpenAI-like error class
        class RateLimitError(Exception):
            pass

        # Assign the error class to the mock module
        mock_openai.RateLimitError = RateLimitError

        # Configure the client to raise the error
        mock_client.responses.create.side_effect = RateLimitError("Rate limit exceeded")

        # Create worker and error signal receiver
        worker = OpenAIAPIWorker(base_messages, base_settings)
        error_messages = []

        def capture_error(error_msg):
            error_messages.append(error_msg)

        worker.error_occurred.connect(capture_error)

        # Process the request
        worker.process()

        # Verify the error was captured with correct message
        assert len(error_messages) == 1
        assert "Rate limit exceeded" in error_messages[0]

    @patch('src.services.api.OpenAI')
    def test_timeout_error(self, mock_openai, base_settings, base_messages):
        """Test handling of timeout errors."""
        # Configure mock
        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        # Define an OpenAI-like error class
        class APITimeoutError(Exception):
            pass

        # Assign the error class to the mock module
        mock_openai.APITimeoutError = APITimeoutError

        # Configure the client to raise the error
        mock_client.responses.create.side_effect = APITimeoutError("Request timed out")

        # Create worker and error signal receiver
        worker = OpenAIAPIWorker(base_messages, base_settings)
        error_messages = []

        def capture_error(error_msg):
            error_messages.append(error_msg)

        worker.error_occurred.connect(capture_error)

        # Process the request
        worker.process()

        # Verify the error was captured
        assert len(error_messages) == 1
        assert "Request timed out" in error_messages[0]

    @patch('src.services.api.OpenAI')
    def test_connection_error(self, mock_openai, base_settings, base_messages):
        """Test handling of connection errors."""
        # Configure mock
        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        # Define an OpenAI-like error class
        class APIConnectionError(Exception):
            pass

        # Assign the error class to the mock module
        mock_openai.APIConnectionError = APIConnectionError

        # Configure the client to raise the error
        mock_client.responses.create.side_effect = APIConnectionError("Connection error")

        # Create worker and error signal receiver
        worker = OpenAIAPIWorker(base_messages, base_settings)
        error_messages = []

        def capture_error(error_msg):
            error_messages.append(error_msg)

        worker.error_occurred.connect(capture_error)

        # Process the request
        worker.process()

        # Verify the error was captured
        assert len(error_messages) == 1
        assert "Connection error" in error_messages[0]

    @patch('src.services.api.OpenAI')
    def test_bad_request_error(self, mock_openai, base_settings, base_messages):
        """Test handling of bad request errors."""
        # Configure mock
        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        # Define an OpenAI-like error class
        class BadRequestError(Exception):
            pass

        # Assign the error class to the mock module
        mock_openai.BadRequestError = BadRequestError

        # Configure the client to raise the error
        mock_client.responses.create.side_effect = BadRequestError("Invalid request parameters")

        # Create worker and error signal receiver
        worker = OpenAIAPIWorker(base_messages, base_settings)
        error_messages = []

        def capture_error(error_msg):
            error_messages.append(error_msg)

        worker.error_occurred.connect(capture_error)

        # Process the request
        worker.process()

        # Verify the error was captured
        assert len(error_messages) == 1
        assert "Bad request" in error_messages[0]

    @patch('src.services.api.OpenAI')
    def test_server_error(self, mock_openai, base_settings, base_messages):
        """Test handling of server errors."""
        # Configure mock
        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        # Define an OpenAI-like error class
        class InternalServerError(Exception):
            pass

        # Assign the error class to the mock module
        mock_openai.InternalServerError = InternalServerError

        # Configure the client to raise the error
        mock_client.responses.create.side_effect = InternalServerError("Internal server error")

        # Create worker and error signal receiver
        worker = OpenAIAPIWorker(base_messages, base_settings)
        error_messages = []

        def capture_error(error_msg):
            error_messages.append(error_msg)

        worker.error_occurred.connect(capture_error)

        # Process the request
        worker.process()

        # Verify the error was captured
        assert len(error_messages) == 1
        assert "OpenAI server error" in error_messages[0]

    @patch('src.services.api.OpenAI')
    def test_generic_error(self, mock_openai, base_settings, base_messages):
        """Test handling of generic errors."""
        # Configure mock
        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        # Configure the client to raise a generic error
        mock_client.responses.create.side_effect = Exception("Generic error")

        # Create worker and error signal receiver
        worker = OpenAIAPIWorker(base_messages, base_settings)
        error_messages = []

        def capture_error(error_msg):
            error_messages.append(error_msg)

        worker.error_occurred.connect(capture_error)

        # Process the request
        worker.process()

        # Verify the error was captured
        assert len(error_messages) == 1
        assert "Generic error" in error_messages[0]

    @patch('src.services.api.OpenAI')
    def test_client_creation_error(self, mock_openai, base_settings, base_messages):
        """Test handling of errors during client creation."""
        # Configure mock to raise an error during client creation
        mock_openai.side_effect = Exception("Client creation error")

        # Create worker and error signal receiver
        worker = OpenAIAPIWorker(base_messages, base_settings)
        error_messages = []

        def capture_error(error_msg):
            error_messages.append(error_msg)

        worker.error_occurred.connect(capture_error)

        # Process the request
        worker.process()

        # Verify the error was captured
        assert len(error_messages) >= 1
        assert "Error initializing API client" in error_messages[0]

    def test_cancel_during_processing(self, base_settings, base_messages):
        """Test cancellation during processing."""
        # Create worker without mocking API (we'll cancel before it's called)
        worker = OpenAIAPIWorker(base_messages, base_settings)

        # Set up mock signal receiver
        mock_receiver = MagicMock()
        worker.worker_finished.connect(mock_receiver)

        # Cancel the worker
        worker.cancel()

        # Start processing (should exit early due to cancellation)
        worker.process()

        # Verify worker_finished was emitted
        mock_receiver.assert_called_once()

        # Verify worker is marked as cancelled
        assert worker._is_cancelled