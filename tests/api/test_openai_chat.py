"""
Tests for the OpenAI Chat Completions API functionality.
"""

import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.services.api import OpenAIAPIWorker


class TestOpenAIChatAPI:
    """Tests for the OpenAI Chat Completions API functionality."""
    
    @pytest.fixture
    def chat_response(self):
        """Create a mock chat completion response."""
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
        return mock_response

    @patch('src.services.api.OpenAI')
    def test_basic_chat_completion(self, mock_openai, chat_response):
        """Test basic Chat Completions API call."""
        # Configure the mock
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = chat_response
        mock_openai.return_value = mock_client

        # Create settings for Chat Completions API
        settings = {
            "api_type": "chat_completions",
            "model": "gpt-4o",
            "temperature": 0.7,
            "max_tokens": 1024,
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
        mock_client.chat.completions.create.assert_called_once()
        assert isinstance(mock_client.chat.completions.create.call_args[1]["messages"], list)

        # Check the message parameter formatting
        call_args = mock_client.chat.completions.create.call_args[1]
        assert len(call_args["messages"]) == 2
        assert call_args["messages"][0]["role"] == "system"
        assert call_args["messages"][1]["role"] == "user"

        # Verify signals were emitted
        assert mock_receiver.call_count >= 1

    @patch('src.services.api.OpenAI')
    def test_chat_with_conversation_history(self, mock_openai, chat_response):
        """Test Chat Completions API call with conversation history."""
        # Configure the mock
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = chat_response
        mock_openai.return_value = mock_client

        # Create settings for Chat Completions API
        settings = {
            "api_type": "chat_completions",
            "model": "gpt-4o",
            "temperature": 0.7,
            "max_tokens": 1024,
            "stream": False,
            "api_key": "test_api_key"
        }

        # Create sample messages with conversation history
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is the capital of France?"},
            {"role": "assistant", "content": "The capital of France is Paris."},
            {"role": "user", "content": "What about Italy?"}
        ]

        # Create worker
        worker = OpenAIAPIWorker(messages, settings)

        # Process the request
        worker.process()

        # Verify the correct API was called
        mock_client.chat.completions.create.assert_called_once()

        # Check all messages were passed correctly
        call_args = mock_client.chat.completions.create.call_args[1]
        assert len(call_args["messages"]) == 4

        # Verify order and roles
        assert call_args["messages"][0]["role"] == "system"
        assert call_args["messages"][1]["role"] == "user"
        assert "France" in call_args["messages"][1]["content"]
        assert call_args["messages"][2]["role"] == "assistant"
        assert "Paris" in call_args["messages"][2]["content"]
        assert call_args["messages"][3]["role"] == "user"
        assert "Italy" in call_args["messages"][3]["content"]

    @patch('src.services.api.OpenAI')
    def test_chat_with_attached_files(self, mock_openai, chat_response):
        """Test Chat Completions API call with attached files."""
        # Configure the mock
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = chat_response
        mock_openai.return_value = mock_client

        # Create settings for Chat Completions API
        settings = {
            "api_type": "chat_completions",
            "model": "gpt-4o",
            "temperature": 0.7,
            "max_tokens": 1024,
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
        mock_client.chat.completions.create.assert_called_once()

        # Check the attached files were included in the user message content
        call_args = mock_client.chat.completions.create.call_args[1]
        assert len(call_args["messages"]) == 2
        user_message = call_args["messages"][1]["content"]
        assert "test.txt" in user_message
        assert "This is test file content" in user_message

    @patch('src.services.api.OpenAI')
    def test_chat_with_json_format(self, mock_openai, chat_response):
        """Test Chat Completions API call with JSON format."""
        # Configure the mock
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = chat_response
        mock_openai.return_value = mock_client

        # Create settings for Chat Completions API with JSON format
        settings = {
            "api_type": "chat_completions",
            "model": "gpt-4o",
            "temperature": 0.7,
            "max_tokens": 1024,
            "stream": False,
            "response_format": {"type": "json_object"},
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
        mock_client.chat.completions.create.assert_called_once()

        # Check the response_format parameter
        call_args = mock_client.chat.completions.create.call_args[1]
        assert call_args["response_format"] == {"type": "json_object"}

    @patch('src.services.api.OpenAIAPIWorker._handle_streaming_response')
    @patch('src.services.api.OpenAI')
    def test_chat_streaming(self, mock_openai, mock_handle_streaming):
        """Test streaming Chat Completions API call."""
        # Configure the mock
        mock_client = MagicMock()
        mock_stream = MagicMock()
        mock_client.chat.completions.create.return_value = mock_stream
        mock_openai.return_value = mock_client

        # Create settings for streaming Chat Completions API
        settings = {
            "api_type": "chat_completions",
            "model": "gpt-4o",
            "temperature": 0.7,
            "max_tokens": 1024,
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
        mock_client.chat.completions.create.assert_called_once()
        call_args = mock_client.chat.completions.create.call_args[1]
        assert call_args["stream"] is True

        # Verify streaming handler was called
        mock_handle_streaming.assert_called_once_with(mock_stream, "chat_completions")

    @patch('src.services.api.OpenAI')
    def test_chat_completion_with_parameters(self, mock_openai, chat_response):
        """Test Chat Completions API call with various parameters."""
        # Configure the mock
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = chat_response
        mock_openai.return_value = mock_client

        # Create settings with various parameters
        settings = {
            "api_type": "chat_completions",
            "model": "gpt-4o",
            "temperature": 0.5,
            "max_tokens": 2000,
            "top_p": 0.9,
            "frequency_penalty": 0.2,
            "presence_penalty": 0.1,
            "stream": False,
            "stop": ["END", "."],
            "user": "test_user_123",
            "api_key": "test_api_key"
        }

        # Create sample messages
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello, test parameters."}
        ]

        # Create worker
        worker = OpenAIAPIWorker(messages, settings)

        # Process the request
        worker.process()

        # Verify the correct API was called
        mock_client.chat.completions.create.assert_called_once()

        # Check all parameters were passed correctly
        call_args = mock_client.chat.completions.create.call_args[1]
        assert call_args["model"] == "gpt-4o"
        assert call_args["temperature"] == 0.5
        assert call_args["top_p"] == 0.9

        # These parameters might be handled differently depending on model
        if "max_tokens" in call_args:
            assert call_args["max_tokens"] == 2000
        elif "max_completion_tokens" in call_args:  # For some models
            assert call_args["max_completion_tokens"] == 2000

    @patch('src.services.api.OpenAI')
    def test_token_count_tracking_chat(self, mock_openai, chat_response):
        """Test token count tracking in Chat Completions API call."""
        # Configure the mock
        mock_client = MagicMock()

        # Add detailed token usage to mock response
        chat_response.usage.prompt_tokens = 15
        chat_response.usage.completion_tokens = 25
        chat_response.usage.total_tokens = 40

        mock_client.chat.completions.create.return_value = chat_response
        mock_openai.return_value = mock_client

        # Create settings for Chat Completions API
        settings = {
            "api_type": "chat_completions",
            "model": "gpt-4o",
            "temperature": 0.7,
            "max_tokens": 1024,
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