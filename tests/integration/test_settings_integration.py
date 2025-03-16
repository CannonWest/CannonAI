"""
Integration tests for settings affecting API calls.
"""

import os
import sys
import pytest
from unittest.mock import MagicMock, patch, Mock

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# Important: Use a patch decorator to mock OpenAI before it's imported
@pytest.mark.usefixtures("mock_openai_client")
class TestSettingsAPIIntegration:
    """Tests for how settings affect API calls."""

    @pytest.fixture
    def mock_openai_client(self, monkeypatch):
        """Create a mock OpenAI client for testing."""
        # Create mock client and responses
        mock_client = Mock()

        # Mock Response API response
        mock_response = Mock()
        mock_response.output_text = "This is a test response."
        mock_response.model = "gpt-4o"
        mock_response.id = "resp_123456789"
        mock_response.usage = Mock()
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 20
        mock_response.usage.total_tokens = 30

        # Mock Chat Completions API response
        mock_chat_response = Mock()
        mock_chat_response.choices = [Mock()]
        mock_chat_response.choices[0].message = Mock()
        mock_chat_response.choices[0].message.content = "This is a test chat response."
        mock_chat_response.model = "gpt-4o"
        mock_chat_response.id = "chatcmpl_123456789"
        mock_chat_response.usage = Mock()
        mock_chat_response.usage.prompt_tokens = 10
        mock_chat_response.usage.completion_tokens = 20
        mock_chat_response.usage.total_tokens = 30

        # Configure mock client to return our mock responses
        mock_client.responses = Mock()
        mock_client.responses.create = Mock(return_value=mock_response)
        mock_client.chat = Mock()
        mock_client.chat.completions = Mock()
        mock_client.chat.completions.create = Mock(return_value=mock_chat_response)

        # Create a mock OpenAI constructor that returns our mock client
        mock_openai = Mock(return_value=mock_client)

        # Patch both places where OpenAI might be imported
        monkeypatch.setattr('openai.OpenAI', mock_openai)
        monkeypatch.setattr('src.services.api.OpenAI', mock_openai)

        # Also patch environment to prevent real API calls
        monkeypatch.setenv("OPENAI_API_KEY", "test_api_key")

        yield mock_openai, mock_client

    def test_response_api_settings(self, mock_openai_client):
        """Test Response API call with various settings."""
        mock_openai, mock_client = mock_openai_client

        # Import here to ensure the patch is already in place
        from src.services.api import OpenAIAPIWorker

        # Create custom settings
        settings = {
            "api_type": "responses",
            "model": "gpt-4o",
            "temperature": 0.5,
            "max_output_tokens": 2000,
            "top_p": 0.9,
            "text": {"format": {"type": "text"}},
            "stream": False,
            "reasoning": {"effort": "high"},
            "api_key": "test_api_key",
            "reasoning_models": ["gpt-4o"]  # Add this to include gpt-4o as a reasoning model
        }

        # Create sample messages
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello, this is a test message."}
        ]

        # Create worker with the settings
        worker = OpenAIAPIWorker(messages, settings)

        # Mock signal receiver
        mock_receiver = MagicMock()
        worker.message_received.connect(mock_receiver)

        # Process the request
        worker.process()

        # Verify client was created with correct API key
        mock_openai.assert_called_once()
        assert mock_openai.call_args[1]["api_key"] == "test_api_key"

        # Verify responses.create was called with the right parameters
        mock_client.responses.create.assert_called_once()
        call_args = mock_client.responses.create.call_args[1]

        # Check all settings were properly passed to the API
        assert call_args["model"] == "gpt-4o"
        assert call_args["temperature"] == 0.5
        assert call_args["max_output_tokens"] == 2000
        assert call_args["top_p"] == 0.9
        assert call_args["stream"] is False
        assert call_args["text"] == {"format": {"type": "text"}}
        assert call_args["reasoning"] == {"effort": "high"}

        # Verify signal was emitted with response
        mock_receiver.assert_called_once()
        assert mock_receiver.call_args[0][0] == "This is a test response."

    def test_chat_completions_api_settings(self, mock_openai_client):
        """Test Chat Completions API call with various settings."""
        mock_openai, mock_client = mock_openai_client

        # Import here to ensure the patch is already in place
        from src.services.api import OpenAIAPIWorker

        # Create custom settings
        settings = {
            "api_type": "chat_completions",
            "model": "gpt-4o",
            "temperature": 0.5,
            "max_tokens": 2000,  # Different parameter name for chat completions
            "top_p": 0.9,
            "frequency_penalty": 0.2,
            "presence_penalty": 0.1,
            "stream": False,
            "response_format": {"type": "json_object"},
            "api_key": "test_api_key"
        }

        # Create sample messages
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello, this is a test message."}
        ]

        # Create worker with the settings
        worker = OpenAIAPIWorker(messages, settings)

        # Mock signal receiver
        mock_receiver = MagicMock()
        worker.message_received.connect(mock_receiver)

        # Process the request
        worker.process()

        # Verify client was created with correct API key
        mock_openai.assert_called_once()
        assert mock_openai.call_args[1]["api_key"] == "test_api_key"

        # Verify chat.completions.create was called with the right parameters
        mock_client.chat.completions.create.assert_called_once()
        call_args = mock_client.chat.completions.create.call_args[1]

        # Check all settings were properly passed to the API
        assert call_args["model"] == "gpt-4o"
        assert call_args["temperature"] == 0.5
        assert isinstance(call_args["messages"], list)
        assert len(call_args["messages"]) == 2
        assert call_args["top_p"] == 0.9
        assert call_args["frequency_penalty"] == 0.2
        assert call_args["presence_penalty"] == 0.1
        assert call_args["stream"] is False
        assert call_args["response_format"] == {"type": "json_object"}

        # Parameter handling is different for different APIs
        if "max_tokens" in call_args:
            assert call_args["max_tokens"] == 2000
        elif "max_completion_tokens" in call_args:  # o1 models use this
            assert call_args["max_completion_tokens"] == 2000

        # Verify signal was emitted with response
        mock_receiver.assert_called_once()
        assert mock_receiver.call_args[0][0] == "This is a test chat response."

    def test_o1_model_specific_settings(self, mock_openai_client):
        """Test o1 model-specific settings handling."""
        mock_openai, mock_client = mock_openai_client

        # Import here to ensure the patch is already in place
        from src.services.api import OpenAIAPIWorker

        # Create custom settings for o1 model
        settings = {
            "api_type": "responses",
            "model": "o1-mini",
            "temperature": 0.5,
            "max_output_tokens": 5000,
            "reasoning": {"effort": "high"},
            "stream": False,
            "api_key": "test_api_key",
            "reasoning_models": ["o1", "o1-mini", "o3-mini"]  # Add this to ensure model is recognized
        }

        # Create sample messages
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello, this is a test message."}
        ]

        # Create worker with the settings
        worker = OpenAIAPIWorker(messages, settings)

        # Process the request
        worker.process()

        # Verify responses.create was called with the right parameters
        mock_client.responses.create.assert_called_once()
        call_args = mock_client.responses.create.call_args[1]

        # Check o1-specific parameters
        assert call_args["model"] == "o1-mini"
        assert call_args["reasoning"] == {"effort": "high"}
        assert call_args["max_output_tokens"] == 5000

    def test_json_format_settings(self, mock_openai_client):
        """Test JSON format settings handling."""
        mock_openai, mock_client = mock_openai_client

        # Import here to ensure the patch is already in place
        from src.services.api import OpenAIAPIWorker

        # Test with Response API
        response_settings = {
            "api_type": "responses",
            "model": "gpt-4o",
            "text": {"format": {"type": "json_object"}},
            "stream": False,
            "api_key": "test_api_key"
        }

        # Create sample messages
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Return a JSON object with name and age."}
        ]

        # Create worker and process the request
        worker = OpenAIAPIWorker(messages, response_settings)
        worker.process()

        # Verify responses.create was called with the right parameters
        mock_client.responses.create.assert_called_once()
        response_call_args = mock_client.responses.create.call_args[1]

        # Check JSON format parameters
        assert response_call_args["text"] == {"format": {"type": "json_object"}}

        # Reset mocks
        mock_openai.reset_mock()
        mock_client.responses.create.reset_mock()
        mock_client.chat.completions.create.reset_mock()

        # Test with Chat Completions API
        chat_settings = {
            "api_type": "chat_completions",
            "model": "gpt-4o",
            "response_format": {"type": "json_object"},
            "stream": False,
            "api_key": "test_api_key"
        }

        # Create worker and process the request
        worker = OpenAIAPIWorker(messages, chat_settings)
        worker.process()

        # Verify chat.completions.create was called with the right parameters
        mock_client.chat.completions.create.assert_called_once()
        chat_call_args = mock_client.chat.completions.create.call_args[1]

        # Check JSON format parameters
        assert chat_call_args["response_format"] == {"type": "json_object"}