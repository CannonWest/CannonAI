"""
Tests for the base client functionality in the Gemini Chat CLI.
"""

import json
import os
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import sys
# Add the parent directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from base_client import BaseGeminiClient


class TestBaseGeminiClient(unittest.TestCase):
    """Test cases for the BaseGeminiClient class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.api_key = "test_api_key"
        self.model = "test-model"
        self.test_dir = Path("test_conversations")
        
        # Create a client for testing
        self.client = BaseGeminiClient(
            api_key=self.api_key,
            model=self.model,
            conversations_dir=self.test_dir
        )
    
    def tearDown(self):
        """Clean up after tests."""
        # Clean up any test files/directories if needed
        if self.test_dir.exists():
            # Only for test directories - be careful with this!
            if str(self.test_dir).startswith("test_"):
                import shutil
                shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_initialization(self):
        """Test client initialization with explicit parameters."""
        self.assertEqual(self.client.api_key, self.api_key)
        self.assertEqual(self.client.model, self.model)
        self.assertEqual(self.client.base_directory, self.test_dir)
        
    def test_initialization_defaults(self):
        """Test client initialization with default parameters."""
        # Temporarily set environment variable for testing
        with patch.dict(os.environ, {"GEMINI_API_KEY": "env_api_key"}):
            client = BaseGeminiClient()
            self.assertEqual(client.api_key, "env_api_key")
            self.assertEqual(client.model, BaseGeminiClient.DEFAULT_MODEL)
    
    def test_ensure_directories(self):
        """Test directory creation."""
        self.client.ensure_directories(self.test_dir)
        self.assertTrue(self.test_dir.exists())
    
    def test_format_filename(self):
        """Test filename formatting with various inputs."""
        # Test with a simple title
        title = "Test Conversation"
        conversation_id = "12345678-abcd-1234-efgh-123456789abc"
        filename = self.client.format_filename(title, conversation_id)
        self.assertEqual(filename, "Test_Conversation_12345678.json")
        
        # Test with special characters
        title = "Test: Special! Characters?"
        filename = self.client.format_filename(title, conversation_id)
        self.assertEqual(filename, "Test__Special__Characters__12345678.json")
    
    def test_create_message_structure(self):
        """Test creating a message structure."""
        role = "user"
        text = "Hello, AI!"
        model = "test-model"
        params = {"temperature": 0.7}
        token_usage = {"total_token_count": 10}
        
        message = self.client.create_message_structure(role, text, model, params, token_usage)
        
        self.assertEqual(message["type"], "message")
        self.assertEqual(message["content"]["role"], role)
        self.assertEqual(message["content"]["text"], text)
        self.assertEqual(message["content"]["model"], model)
        self.assertEqual(message["content"]["params"], params)
        self.assertEqual(message["content"]["token_usage"], token_usage)
    
    def test_create_metadata_structure(self):
        """Test creating metadata structure."""
        title = "Test Conversation"
        model = "test-model"
        params = {"temperature": 0.7}
        
        metadata = self.client.create_metadata_structure(title, model, params)
        
        self.assertEqual(metadata["type"], "metadata")
        self.assertEqual(metadata["content"]["title"], title)
        self.assertEqual(metadata["content"]["model"], model)
        self.assertEqual(metadata["content"]["params"], params)
        self.assertIn("created_at", metadata["content"])
        self.assertIn("updated_at", metadata["content"])
        self.assertEqual(metadata["content"]["message_count"], 0)
        self.assertEqual(metadata["content"]["version"], self.client.VERSION)
        
    def test_extract_token_usage(self):
        """Test token usage extraction from response."""
        # Create a mock response
        mock_response = MagicMock()
        mock_response.usage_metadata = MagicMock()
        mock_response.usage_metadata.prompt_token_count = 5
        mock_response.usage_metadata.candidates_token_count = 10
        mock_response.usage_metadata.total_token_count = 15
        
        token_usage = self.client.extract_token_usage(mock_response)
        
        self.assertEqual(token_usage["prompt_token_count"], 5)
        self.assertEqual(token_usage["candidates_token_count"], 10)
        self.assertEqual(token_usage["total_token_count"], 15)
        
        # Test with missing attributes
        mock_response = MagicMock()
        mock_response.usage_metadata = MagicMock()
        # Only set one attribute
        mock_response.usage_metadata.total_token_count = 15
        
        token_usage = self.client.extract_token_usage(mock_response)
        
        self.assertEqual(len(token_usage), 1)
        self.assertEqual(token_usage["total_token_count"], 15)
        
        # Test with no usage_metadata
        mock_response = MagicMock(spec=[])  # No attributes
        
        token_usage = self.client.extract_token_usage(mock_response)
        
        self.assertEqual(token_usage, {})


if __name__ == "__main__":
    unittest.main()
