"""
Tests for the OpenAI Response API functionality.
"""

import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.services.api import OpenAIAPIWorker


class TestOpenAIResponseAPI:
    """Tests for the OpenAI Response API functionality."""
    
    @pytest.fixture
    def response_result(self):
        """Create a mock Response API response."""
        mock_response = MagicMock()
        mock_response.output_text = "This is a test response."
        mock_response.model = "gpt-4o"
        mock_response.id = "resp_123456789"
        mock_response.usage = MagicMock()
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 20
        mock_response.usage.total_tokens = 30
        return mock_response

    @patch('src.services.api.OpenAI')
    def test_basic_response(self, mock_openai, response_result):
        """Test basic Response API call."""
        # Configure the mock
        mock_client = MagicMock()
        mock_client.responses.create.return_value = response_result
        mock_openai.return_value = mock_client

        # Create settings for Response API
        settings = {
            "api_type": "responses",
            "model": "gpt-4o",
            "temperature": 0.7,
            "max_output_tokens": 1024,
            "stream": False,
            "api_key": "test_api_key"
        }

        # Create sample messages
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello, this is a test message."}
        ]

        # Create worker and mock signal receiver
        worker = OpenAIAPIWorker(messages, settings)
        mock_receiver = MagicMock()
        worker.message_received.connect(mock_receiver)
        worker.usage_info.connect(mock_receiver)
        worker.system_info.connect(mock_receiver)
        worker.completion_id.connect(mock_receiver)

        # Process the request
        worker.process()

        # Verify the correct API was called
        mock_client.responses.create.assert_called_once()

        # Check the input parameter formatting
        call_args = mock_client.responses.create.call_args[1]
        assert isinstance(call_args["input"], str)
        assert "Hello, this is a test message" in call_args["input"]

        # Verify signals were emitted
        assert mock_receiver.call_count >= 1

    @patch('src.services.api.OpenAI')
    def test_response_with_instructions(self, mock_openai, response_result):
        """Test Response API call with instructions parameter."""
        # Configure the mock
        mock_client = MagicMock()
        mock_client.responses.create.return_value = response_result
        mock_openai.return_value = mock_client

        # Create settings for Response API with instructions
        settings = {
            "api_type": "responses",
            "model": "gpt-4o",
            "temperature": 0.7,
            "max_output_tokens": 1024,
            "stream": False,
            "api_key": "test_api_key"
        }

        # Create sample messages (first is system message)
        messages = [
            {"role": "system", "content": "You are a helpful assistant for testing."},
            {"role": "user", "content": "Hello, test the instructions."}
        ]

        # Create worker
        worker = OpenAIAPIWorker(messages, settings)

        # Process the request
        worker.process()

        # Verify the correct API was called
        mock_client.responses.create.assert_called_once()

        # Check the system message was sent as instructions
        call_args = mock_client.responses.create.call_args[1]
        assert "instructions" in call_args
        assert call_args["instructions"] == "You are a helpful assistant for testing."

    @patch('src.services.api.OpenAI')
    def test_response_with_attached_files(self, mock_openai, response_result):
        """Test Response API call with attached files."""
        # Configure the mock
        mock_client = MagicMock()
        mock_client.responses.create.return_value = response_result
        mock_openai.return_value = mock_client

        # Create settings for Response API
        settings = {
            "api_type": "responses",
            "model": "gpt-4o",
            "temperature": 0.7,
            "max_output_tokens": 1024,
            "stream": False,
            "api_key": "test_api_key"
        }

        # Create sample messages with attached files
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {
                "role": "user",
                "content": "Analyze this file.",
                "attached_files": [
                    {
                        "file_name": "test.txt",
                        "mime_type": "text/plain",
                        "content": "This is test file content.",
                        "token_count": 10
                    }
                ]
            }
        ]

        # Create worker
        worker = OpenAIAPIWorker(messages, settings)

        # Process the request
        worker.process()

        # Verify the correct API was called
        mock_client.responses.create.assert_called_once()

        # Check the attached files were included in the input
        call_args = mock_client.responses.create.call_args[1]
        assert "ATTACHED FILES" in call_args["input"]
        assert "test.txt" in call_args["input"]
        assert "This is test file content" in call_args["input"]

    @patch('src.services.api.OpenAI')
    def test_response_with_json_format(self, mock_openai, response_result):
        """Test Response API call with JSON format."""
        # Configure the mock
        mock_client = MagicMock()
        mock_client.responses.create.return_value = response_result
        mock_openai.return_value = mock_client

        # Create settings for Response API with JSON format
        settings = {
            "api_type": "responses",
            "model": "gpt-4o",
            "temperature": 0.7,
            "max_output_tokens": 1024,
            "stream": False,
            "text": {"format": {"type": "json_object"}},
            "api_key": "test_api_key"
        }

        # Create sample messages
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Return a JSON object with name and age."}
        ]

        # Create worker
        worker = OpenAIAPIWorker(messages, settings)

        # Process the request
        worker.process()

        # Verify the correct API was called
        mock_client.responses.create.assert_called_once()

        # Check the text format parameter
        call_args = mock_client.responses.create.call_args[1]
        assert call_args["text"] == {"format": {"type": "json_object"}}

    @patch('src.services.api.OpenAIAPIWorker._handle_streaming_response')
    @patch('src.services.api.OpenAI')
    def test_response_streaming(self, mock_openai, mock_handle_streaming):
        """Test streaming Response API call."""
        # Configure the mock
        mock_client = MagicMock()
        mock_stream = MagicMock()
        mock_client.responses.create.return_value = mock_stream
        mock_openai.return_value = mock_client

        # Create settings for streaming Response API
        settings = {
            "api_type": "responses",
            "model": "gpt-4o",
            "temperature": 0.7,
            "max_output_tokens": 1024,
            "stream": True,
            "api_key": "test_api_key"
        }

        # Create sample messages
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello, test streaming."}
        ]

        # Create worker
        worker = OpenAIAPIWorker(messages, settings)

        # Process the request
        worker.process()

        # Verify the correct API was called with stream=True
        mock_client.responses.create.assert_called_once()
        call_args = mock_client.responses.create.call_args[1]
        assert call_args["stream"] is True

        # Verify streaming handler was called
        mock_handle_streaming.assert_called_once_with(mock_stream, "responses")

    @patch('src.services.api.OpenAI')
    def test_token_count_tracking(self, mock_openai, response_result):
        """Test token count tracking in Response API call."""
        # Configure the mock
        mock_client = MagicMock()

        # Add detailed token usage to mock response
        response_result.usage.input_tokens = 15
        response_result.usage.output_tokens = 25
        response_result.usage.total_tokens = 40

        mock_client.responses.create.return_value = response_result
        mock_openai.return_value = mock_client

        # Create settings for Response API
        settings = {
            "api_type": "responses",
            "model": "gpt-4o",
            "temperature": 0.7,
            "max_output_tokens": 1024,
            "stream": False,
            "api_key": "test_api_key"
        }

        # Create sample messages
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello, test token tracking."}
        ]

        # Create worker and usage signal receiver
        worker = OpenAIAPIWorker(messages, settings)
        usage_data = []

        def capture_usage(info):
            usage_data.append(info)

        worker.usage_info.connect(capture_usage)

        # Process the request
        worker.process()

        # Verify token usage data was captured correctly
        assert len(usage_data) == 1
        assert usage_data[0]["prompt_tokens"] == 15
        assert usage_data[0]["completion_tokens"] == 25
        assert usage_data[0]["total_tokens"] == 40

    @patch('src.services.api.OpenAI')
    def test_reasoning_models(self, mock_openai, response_result):
        """Test Response API call with reasoning models (o1, o3-mini)."""
        # Configure the mock
        mock_client = MagicMock()

        # Add reasoning tokens to mock response
        response_result.usage.output_tokens_details = MagicMock()
        response_result.usage.output_tokens_details.reasoning_tokens = 15

        mock_client.responses.create.return_value = response_result
        mock_openai.return_value = mock_client

        # Create settings for reasoning model
        settings = {
            "api_type": "responses",
            "model": "o1-mini",
            "temperature": 0.7,
            "max_output_tokens": 1024,
            "stream": False,
            "reasoning": {"effort": "high"},
            "api_key": "test_api_key"
        }

        # Create sample messages
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello, test reasoning."}
        ]

        # Create worker and usage signal receiver
        worker = OpenAIAPIWorker(messages, settings)
        usage_data = []

        def capture_usage(info):
            usage_data.append(info)

        worker.usage_info.connect(capture_usage)

        # Process the request
        worker.process()

        # Verify reasoning parameters were included
        call_args = mock_client.responses.create.call_args[1]
        assert "reasoning" in call_args
        assert call_args["reasoning"] == {"effort": "high"}

        # Verify reasoning tokens were captured
        assert len(usage_data) == 1
        assert "completion_tokens_details" in usage_data[0]
        assert usage_data[0]["completion_tokens_details"]["reasoning_tokens"] == 15