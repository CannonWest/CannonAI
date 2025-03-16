"""
Unit tests for the file_utils module.
"""

import os
import sys
import pytest
import tempfile
import threading
import hashlib
from unittest.mock import patch, MagicMock, Mock

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from PyQt6.QtCore import QThread

from src.utils.file_utils import (
    get_file_mime_type, read_text_file, count_tokens, get_file_info, extract_display_text, format_size,
    calculate_file_hash, process_large_text_file, get_file_info_async, FileProcessingWorker, FileCacheManager
)


class TestBasicFileUtils:
    """Tests for basic file utility functions."""

    def test_get_file_mime_type(self):
        """Test determination of MIME type from a file path."""
        # Test with common file types
        assert get_file_mime_type("test.txt") == "text/plain"
        assert get_file_mime_type("test.py") == "text/x-python"
        assert get_file_mime_type("test.html") == "text/html"
        assert get_file_mime_type("test.json") == "application/json"
        assert get_file_mime_type("test.md") == "text/markdown"

        # Test with unknown file extension
        assert get_file_mime_type("test.unknown") == "text/plain"  # Should default to text/plain

    def test_read_text_file(self):
        """Test reading text files with different encodings."""
        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False) as temp_file:
            temp_file.write("Hello, world!")
            temp_path = temp_file.name

        try:
            # Test reading UTF-8 file
            content = read_text_file(temp_path)
            assert content == "Hello, world!"

            # Test with a non-existent file (should raise exception)
            with pytest.raises(Exception):
                read_text_file("non_existent_file.txt")
        finally:
            # Clean up
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @patch('tiktoken.encoding_for_model')
    def test_count_tokens(self, mock_encoding_for_model):
        """Test token counting with tiktoken."""
        # Set up mock encoding
        mock_encoding = MagicMock()
        mock_encoding.encode.return_value = [1, 2, 3, 4, 5]  # 5 tokens
        mock_encoding_for_model.return_value = mock_encoding

        # Test counting tokens
        count = count_tokens("This is a test text", model="gpt-4o")

        # Check encoding_for_model was called with right model
        mock_encoding_for_model.assert_called_once_with("gpt-4o")

        # Check encode was called with the right text
        mock_encoding.encode.assert_called_once_with("This is a test text")

        # Check count is correct
        assert count == 5

    @patch('tiktoken.encoding_for_model')
    @patch('tiktoken.get_encoding')
    def test_count_tokens_fallback(self, mock_get_encoding, mock_encoding_for_model):
        """Test token counting falls back if model not found."""
        # Make encoding_for_model raise KeyError
        mock_encoding_for_model.side_effect = KeyError("Model not found")

        # Set up fallback encoding
        mock_fallback = MagicMock()
        mock_fallback.encode.return_value = [1, 2, 3, 4, 5, 6]  # 6 tokens
        mock_get_encoding.return_value = mock_fallback

        # Test counting tokens
        count = count_tokens("This is a test text", model="unknown-model")

        # Check get_encoding was called with fallback encoding
        mock_get_encoding.assert_called_once_with("cl100k_base")

        # Check count is correct
        assert count == 6

    def test_calculate_file_hash(self):
        """Test SHA-256 hash calculation for a file."""
        # Create a temporary file with known content
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False) as temp_file:
            temp_file.write("Test content for hashing")
            temp_path = temp_file.name

        try:
            # Calculate the expected hash
            expected_hash = hashlib.sha256(b"Test content for hashing").hexdigest()

            # Test the hash calculation
            actual_hash = calculate_file_hash(temp_path)

            # Check the hash matches
            assert actual_hash == expected_hash
        finally:
            # Clean up
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_extract_display_text(self):
        """Test extracting display text from messages."""
        # Create mock nodes
        system_node = MagicMock()
        system_node.role = "system"
        system_node.content = "You are a helpful assistant"

        user_node = MagicMock()
        user_node.role = "user"
        user_node.content = "Hello, this is a test message that is longer than the max length"

        assistant_node = MagicMock()
        assistant_node.role = "assistant"
        assistant_node.content = "User: Hi\nAssistant: Hello! How can I help you today?"

        empty_node = MagicMock()
        empty_node.role = "user"
        empty_node.content = ""

        # Test extraction
        assert extract_display_text(system_node) == "System instructions"
        assert extract_display_text(user_node, max_length=20) == "Hello, this is a..."
        assert extract_display_text(assistant_node) == "Hello! How can I help you today?"
        assert extract_display_text(empty_node) == ""

    def test_format_size(self):
        """Test formatting file sizes."""
        # Test with different sizes
        assert format_size(512) == "512.0 B"
        assert format_size(1024) == "1.0 KB"
        assert format_size(1024 * 1024) == "1.0 MB"
        assert format_size(1024 * 1024 * 1024) == "1.0 GB"
        assert format_size(1024 * 1024 * 1024 * 1024) == "1.0 TB"

        # Test with non-round numbers
        assert format_size(1536) == "1.5 KB"
        assert format_size(1024 * 1024 * 2.5) == "2.5 MB"


class TestAdvancedFileUtils:
    """Tests for advanced file utilities including large file handling and async operations."""

    def test_process_large_text_file(self):
        """Test processing large text files in chunks."""
        # Create a temporary file with multiple chunks of text
        chunk_size = 1024  # Using a smaller size for testing
        test_content = "A" * (chunk_size * 2 + 500)  # 2.5 chunks

        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False) as temp_file:
            temp_file.write(test_content)
            temp_path = temp_file.name

        try:
            # Create a progress tracking callback
            progress_values = []
            def progress_callback(progress):
                progress_values.append(progress)

            # Process the file with our custom chunk size
            with patch('src.utils.file_utils.chunk_size', chunk_size):
                content, token_count = process_large_text_file(
                    temp_path,
                    "gpt-4o",
                    progress_callback
                )

            # Verify content matches
            assert content == test_content

            # Verify progress was tracked (should have at least 3 updates)
            assert len(progress_values) >= 3
            assert progress_values[-1] == 100  # Final progress should be 100%

        finally:
            # Clean up
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @patch('src.utils.file_utils.get_file_mime_type')
    @patch('src.utils.file_utils.read_text_file')
    @patch('src.utils.file_utils.count_tokens')
    def test_get_file_info(self, mock_count_tokens, mock_read_text_file, mock_get_file_mime_type):
        """Test getting file information."""
        # Set up mocks
        mock_get_file_mime_type.return_value = "text/plain"
        mock_read_text_file.return_value = "File content"
        mock_count_tokens.return_value = 10

        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False) as temp_file:
            temp_file.write("Test file")
            temp_path = temp_file.name

        try:
            # Test getting file info
            file_info = get_file_info(temp_path, model="gpt-4o")

            # Check calls were made correctly
            mock_get_file_mime_type.assert_called_once_with(temp_path)
            mock_read_text_file.assert_called_once_with(temp_path)
            mock_count_tokens.assert_called_once_with("File content", "gpt-4o")

            # Check returned info
            assert file_info["file_name"] == os.path.basename(temp_path)
            assert file_info["mime_type"] == "text/plain"
            assert file_info["content"] == "File content"
            assert file_info["token_count"] == 10
            assert file_info["path"] == temp_path
            assert "size" in file_info
        finally:
            # Clean up
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @patch('src.utils.file_utils.get_file_mime_type')
    def test_get_file_info_unsupported_type(self, mock_get_file_mime_type):
        """Test handling of unsupported file types."""
        # Set up mock to return a binary MIME type
        mock_get_file_mime_type.return_value = "application/octet-stream"

        # Test with a filename that doesn't have a text extension
        with pytest.raises(ValueError, match="Unsupported file type"):
            get_file_info("test.bin")

    @patch('src.utils.file_utils.get_file_mime_type')
    @patch('src.utils.file_utils.process_large_text_file')
    def test_get_file_info_large_file(self, mock_process_large, mock_get_file_mime_type):
        """Test getting file information for a large file."""
        # Set up mocks
        mock_get_file_mime_type.return_value = "text/plain"
        mock_process_large.return_value = ("Large file content", 100)

        # Create a temporary large file (just the size metadata matters)
        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as temp_file:
            # Write just over 1MB to trigger large file processing
            temp_file.write(b"X" * (1024 * 1024 + 1))
            temp_path = temp_file.name

        try:
            # Test getting file info
            file_info = get_file_info(temp_path, model="gpt-4o")

            # Verify large file processing was used
            mock_process_large.assert_called_once()

            # Check returned info
            assert file_info["content"] == "Large file content"
            assert file_info["token_count"] == 100
        finally:
            # Clean up
            if os.path.exists(temp_path):
                os.remove(temp_path)


class TestFileProcessingWorker:
    """Tests for the FileProcessingWorker class."""

    def test_file_processing_worker_init(self):
        """Test FileProcessingWorker initialization."""
        worker = FileProcessingWorker("test.txt", "gpt-4o", 10, "relative/path.txt")

        assert worker.file_path == "test.txt"
        assert worker.model == "gpt-4o"
        assert worker.max_size_mb == 10
        assert worker.relative_path == "relative/path.txt"
        assert worker.canceled is False

    @patch('src.utils.file_utils.calculate_file_hash')
    @patch('src.utils.file_utils.get_file_mime_type')
    @patch('src.utils.file_utils.process_large_text_file')
    def test_file_processing_worker_process(self, mock_process_large, mock_get_mime, mock_calc_hash):
        """Test FileProcessingWorker.process method."""
        # Set up mocks
        mock_calc_hash.return_value = "fakehash123"
        mock_get_mime.return_value = "text/plain"
        mock_process_large.return_value = ("Large content", 50)

        # Create a test file
        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as temp_file:
            # Create a file just over 1MB to trigger large file processing
            temp_file.write(b"X" * (1024 * 1024 + 100))
            temp_path = temp_file.name

        try:
            # Set up signals
            worker = FileProcessingWorker(temp_path, "gpt-4o")

            # Mock signals
            worker.progress = Mock()
            worker.file_processed = Mock()
            worker.error = Mock()
            worker.finished = Mock()

            # Process the file
            worker.process()

            # Verify signals were emitted
            worker.progress.emit.assert_called()
            worker.file_processed.emit.assert_called_once()
            worker.finished.emit.assert_called_once()
            worker.error.emit.assert_not_called()

            # Verify the file_processed signal contains the expected data
            file_info = worker.file_processed.emit.call_args[0][0]
            assert file_info["file_name"] == os.path.basename(temp_path)
            assert file_info["mime_type"] == "text/plain"
            assert file_info["content"] == "Large content"
            assert file_info["token_count"] == 50
            assert file_info["file_hash"] == "fakehash123"
        finally:
            # Clean up
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_file_processing_worker_cancel(self):
        """Test FileProcessingWorker.cancel method."""
        worker = FileProcessingWorker("test.txt")
        worker.cancel()
        assert worker.canceled is True


class TestGetFileInfoAsync:
    """Tests for the get_file_info_async function."""

    @patch('src.utils.file_utils.QThread')
    @patch('src.utils.file_utils.FileProcessingWorker')
    def test_get_file_info_async(self, MockWorker, MockThread):
        """Test asynchronous file info retrieval."""
        # Set up mocks
        mock_thread = MockThread.return_value
        mock_worker = MockWorker.return_value

        # Set up callbacks
        on_complete = Mock()
        on_error = Mock()
        on_progress = Mock()

        # Call the function
        thread, worker = get_file_info_async(
            "test.txt",
            "gpt-4o",
            on_complete,
            on_error,
            on_progress,
            10,
            "relative/path.txt"
        )

        # Verify worker was created correctly
        MockWorker.assert_called_once_with(
            "test.txt", "gpt-4o", 10, "relative/path.txt"
        )

        # Verify signals were connected
        mock_thread.started.connect.assert_called_once_with(mock_worker.process)
        mock_worker.finished.connect.assert_any_call(mock_thread.quit)
        mock_worker.file_processed.connect.assert_called_once_with(on_complete)
        mock_worker.error.connect.assert_called_once_with(on_error)
        mock_worker.progress.connect.assert_called_once_with(on_progress)

        # Verify thread was started
        mock_thread.start.assert_called_once()

        # Verify return values
        assert thread == mock_thread
        assert worker == mock_worker


class TestFileCacheManager:
    """Tests for the FileCacheManager class."""

    def setup_method(self):
        """Set up test environment before each test."""
        # Create a temporary directory for cache
        self.cache_dir = tempfile.mkdtemp()
        self.cache_manager = FileCacheManager(self.cache_dir)

    def teardown_method(self):
        """Clean up after each test."""
        # Clean up temp directory
        import shutil
        shutil.rmtree(self.cache_dir)

    def test_cache_file(self):
        """Test caching a file."""
        # Cache a file
        content = "Test file content"
        file_hash = "test_hash_123"

        cache_path = self.cache_manager.cache_file(content, file_hash)

        # Verify the file was created
        assert os.path.exists(cache_path)

        # Verify the content was written
        with open(cache_path, 'r', encoding='utf-8') as f:
            assert f.read() == content

    def test_get_cached_content(self):
        """Test retrieving cached content."""
        # Cache a file
        content = "Cached content"
        file_hash = "another_hash_456"

        self.cache_manager.cache_file(content, file_hash)

        # Retrieve the content
        retrieved = self.cache_manager.get_cached_content(file_hash)

        # Verify it matches
        assert retrieved == content

        # Test retrieving non-existent cache
        assert self.cache_manager.get_cached_content("nonexistent") is None

    def test_has_cached_file(self):
        """Test checking if a file is cached."""
        # Cache a file
        file_hash = "hash_789"
        self.cache_manager.cache_file("Content", file_hash)

        # Check if it exists
        assert self.cache_manager.has_cached_file(file_hash) is True
        assert self.cache_manager.has_cached_file("nonexistent") is False

    def test_clear_cache(self):
        """Test clearing the cache."""
        # Cache some files
        self.cache_manager.cache_file("Content 1", "hash1")
        self.cache_manager.cache_file("Content 2", "hash2")

        # Verify files exist
        assert os.path.exists(os.path.join(self.cache_dir, "hash1"))
        assert os.path.exists(os.path.join(self.cache_dir, "hash2"))

        # Clear the cache
        self.cache_manager.clear_cache()

        # Verify files are gone
        assert not os.path.exists(os.path.join(self.cache_dir, "hash1"))
        assert not os.path.exists(os.path.join(self.cache_dir, "hash2"))

    @patch('time.time')
    @patch('os.path.getmtime')
    def test_clear_cache_older_than(self, mock_getmtime, mock_time):
        """Test clearing cache files older than a certain age."""
        # Set up mock time (current time)
        mock_time.return_value = 1000000

        # Set up mock file modification times
        # hash1: 5 days old, hash2: 1 day old
        def mock_getmtime_side_effect(path):
            if path.endswith("hash1"):
                return 1000000 - (5 * 86400)
            elif path.endswith("hash2"):
                return 1000000 - (1 * 86400)
            return 1000000

        mock_getmtime.side_effect = mock_getmtime_side_effect

        # Cache some files
        self.cache_manager.cache_file("Content 1", "hash1")
        self.cache_manager.cache_file("Content 2", "hash2")

        # Clear files older than 3 days
        self.cache_manager.clear_cache(older_than_days=3)

        # Verify only the older file was removed
        assert not os.path.exists(os.path.join(self.cache_dir, "hash1"))
        assert os.path.exists(os.path.join(self.cache_dir, "hash2"))