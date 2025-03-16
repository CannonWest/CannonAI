"""
Utility functions for handling files in the OpenAI Chat application.
With optimizations for large file handling.
"""

import os
import mimetypes
import threading
import hashlib
from typing import Dict, Optional, Callable, Tuple, List
import tiktoken
from PyQt6.QtCore import QObject, pyqtSignal, QThread

# Define chunk_size constant for large file processing
chunk_size = 1024 * 1024  # 1MB default chunk size for large file processing

# Add custom MIME types
mimetypes.add_type('text/markdown', '.md')
mimetypes.add_type('text/x-python', '.py')
mimetypes.add_type('application/json', '.json')


class FileProcessingWorker(QObject):
    """Worker for processing files in a background thread"""
    progress = pyqtSignal(int)  # Progress percentage
    file_processed = pyqtSignal(dict)  # Processed file info
    error = pyqtSignal(str)  # Error message
    finished = pyqtSignal()  # Worker completed

    def __init__(self, file_path: str, model: str = "gpt-4o",
                 max_size_mb: int = 10,
                 relative_path: str = None):
        super().__init__()
        self.file_path = file_path
        self.model = model
        self.max_size_mb = max_size_mb
        self.relative_path = relative_path
        self.canceled = False

    def process(self):
        """Process the file in background thread"""
        try:
            # Check file size first
            file_size = os.path.getsize(self.file_path)
            max_size_bytes = self.max_size_mb * 1024 * 1024

            # Make sure to emit initial progress
            self.progress.emit(0)

            if file_size > max_size_bytes:
                self.error.emit(f"File exceeds maximum size of {self.max_size_mb}MB")
                self.finished.emit()
                return

            # Get file info
            mime_type = get_file_mime_type(self.file_path)
            file_name = os.path.basename(self.file_path) if not self.relative_path else self.relative_path

            # Calculate file hash for identification/caching
            file_hash = calculate_file_hash(self.file_path)

            # For very large text files, use chunked processing
            if file_size > 1024 * 1024:  # 1MB threshold for chunked processing
                content, token_count = process_large_text_file(
                    self.file_path,
                    self.model,
                    lambda p: self.progress.emit(p)
                )
            else:
                # For smaller files, use standard processing
                content = read_text_file(self.file_path)
                token_count = count_tokens(content, self.model)
                # Make sure to emit progress
                self.progress.emit(50)  # Middle progress
                self.progress.emit(100)  # Completed

            # Create file info dict
            file_info = {
                "file_name": file_name,
                "original_file_name": os.path.basename(self.file_path),
                "mime_type": mime_type,
                "content": content,
                "token_count": token_count,
                "path": self.file_path,
                "size": file_size,
                "file_hash": file_hash
            }

            self.file_processed.emit(file_info)
        except Exception as e:
            self.error.emit(f"Error processing file: {str(e)}")
        finally:
            self.finished.emit()

    def cancel(self):
        """Cancel the processing"""
        self.canceled = True


def get_file_mime_type(file_path: str) -> str:
    """Determine MIME type of a file."""
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type is None:
        # Default to text/plain for unknown types
        mime_type = "text/plain"
    return mime_type


def read_text_file(file_path: str) -> str:
    """Read a text file and return its content."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        # Try with different encoding if UTF-8 fails
        try:
            with open(file_path, 'r', encoding='latin-1') as f:
                return f.read()
        except Exception:
            # Last resort, try binary mode and decode as much as possible
            with open(file_path, 'rb') as f:
                return f.read().decode('utf-8', errors='replace')


def calculate_file_hash(file_path: str) -> str:
    """Calculate SHA-256 hash of file for identification/caching"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read in chunks for memory efficiency
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def process_large_text_file(file_path: str, model: str, progress_callback: Callable[[int], None] = None) -> Tuple[str, int]:
    """
    Process a large text file by reading and counting tokens in chunks
    to avoid memory issues.

    Args:
        file_path: Path to the text file
        model: Model name for token counting
        progress_callback: Callback for progress updates

    Returns:
        Tuple of (content, token_count)
    """
    # Initialize variables
    file_size = os.path.getsize(file_path)
    bytes_processed = 0
    content_chunks = []
    token_count = 0

    # Get encoding for token counting
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")

    # Process file in chunks
    # Use the global chunk_size variable defined at the top of the module
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break

            # Add chunk to content
            content_chunks.append(chunk)

            # Count tokens
            tokens = encoding.encode(chunk)
            token_count += len(tokens)

            # Update progress
            bytes_processed += len(chunk.encode('utf-8'))
            progress = min(int((bytes_processed / file_size) * 100), 100)
            if progress_callback:
                progress_callback(progress)

    # Join chunks
    content = ''.join(content_chunks)

    return content, token_count


def count_tokens(text: str, model: str = "gpt-4o") -> int:
    """
    Count tokens in a text string using tiktoken.

    Args:
        text: The text to count tokens for
        model: The model to use for token counting

    Returns:
        Number of tokens
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        # Fall back to cl100k_base (used by GPT-4, GPT-3.5)
        encoding = tiktoken.get_encoding("cl100k_base")

    return len(encoding.encode(text))


def get_file_info(file_path: str, model: str = "gpt-4o") -> Dict:
    """
    Get file information including content and token count.
    Warning: This blocks the UI thread. For large files,
    use get_file_info_async instead.

    Args:
        file_path: Path to the file
        model: Model to use for token counting

    Returns:
        Dictionary with file information
    """
    mime_type = get_file_mime_type(file_path)
    file_name = os.path.basename(file_path)

    # List of extensions we consider text files
    text_extensions = (
        '.txt', '.py', '.js', '.c', '.cpp', '.h', '.hpp', '.cs', '.java', '.json',
        '.md', '.csv', '.html', '.css', '.xml', '.yaml', '.yml', '.ini', '.cfg',
        '.sh', '.bat', '.ps1', '.sql', '.rb', '.php', '.go', '.rs', '.ts', '.jsx'
    )

    # Check if it's a text file
    if mime_type.startswith('text/') or file_name.lower().endswith(text_extensions):
        # For very large files, use chunked processing
        file_size = os.path.getsize(file_path)
        if file_size > 1024 * 1024:  # 1MB
            content, token_count = process_large_text_file(file_path, model)
        else:
            content = read_text_file(file_path)
            token_count = count_tokens(content, model)

        return {
            "file_name": file_name,
            "mime_type": mime_type,
            "content": content,
            "token_count": token_count,
            "path": file_path,
            "size": file_size
        }
    else:
        raise ValueError(f"Unsupported file type: {mime_type}")


def get_file_info_async(file_path: str, model: str = "gpt-4o",
                         on_complete: Callable[[Dict], None] = None,
                         on_error: Callable[[str], None] = None,
                         on_progress: Callable[[int], None] = None,
                         max_size_mb: int = 10,
                         relative_path: str = None) -> Tuple[QThread, FileProcessingWorker]:
    """
    Asynchronously get file information to avoid blocking the UI thread.

    Args:
        file_path: Path to the file
        model: Model to use for token counting
        on_complete: Callback when processing is complete
        on_error: Callback when an error occurs
        on_progress: Callback for progress updates
        max_size_mb: Maximum file size in MB
        relative_path: Optional relative path for display

    Returns:
        Tuple of (thread, worker) for management
    """
    # Create thread and worker
    thread = QThread()
    worker = FileProcessingWorker(file_path, model, max_size_mb, relative_path)

    # Move worker to thread
    worker.moveToThread(thread)

    # Connect signals
    thread.started.connect(worker.process)
    worker.finished.connect(thread.quit)
    worker.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)

    if on_complete:
        worker.file_processed.connect(on_complete)
    if on_error:
        worker.error.connect(on_error)
    if on_progress:
        worker.progress.connect(on_progress)

    # Start thread
    thread.start()

    return thread, worker

def extract_display_text(node, max_length=40):
    """
    Extract the most relevant part of a message for display in navigation elements.

    Args:
        node: The message node to extract text from
        max_length: Maximum length for the extracted text

    Returns:
        A short, relevant excerpt from the message
    """
    if not node or not hasattr(node, 'content') or not node.content:
        return ""

    content = node.content.strip()

    # For system messages, return a standard placeholder
    if node.role == "system":
        return "System instructions"

    # For assistant messages, try to extract the actual assistant's response
    if node.role == "assistant":
        # Look for the "Assistant:" prefix in the content
        if "Assistant:" in content:
            parts = content.split("Assistant:", 1)
            if len(parts) > 1:
                content = parts[1].strip()

    # For all messages, try to find the most relevant part by removing any repeated context
    lines = content.split('\n')
    non_empty_lines = [line for line in lines if line.strip()]

    # If we have multiple lines, use the first non-empty one that's not a role identifier
    if len(non_empty_lines) > 1:
        # Skip lines that just indicate roles
        for line in non_empty_lines:
            line = line.strip()
            if not (line.startswith('User:') or line.startswith('Assistant:') or line.startswith('System:')):
                content = line
                break

    # Truncate if needed
    if len(content) > max_length:
        content = content[:max_length - 3].rstrip() + "..."

    return content

def format_size(size_bytes):
    """Format file size in a human-readable way."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


class FileCacheManager:
    """Manager for caching file attachments to disk instead of memory"""

    def __init__(self, cache_dir=None):
        if cache_dir is None:
            from src.utils import DATA_DIR
            self.cache_dir = os.path.join(DATA_DIR, "file_cache")
        else:
            self.cache_dir = cache_dir

        # Ensure cache directory exists
        os.makedirs(self.cache_dir, exist_ok=True)

    def cache_file(self, content: str, file_hash: str) -> str:
        """
        Cache file content to disk

        Args:
            content: File content
            file_hash: Hash of the file

        Returns:
            Path to cached file
        """
        cache_path = os.path.join(self.cache_dir, file_hash)

        with open(cache_path, 'w', encoding='utf-8') as f:
            f.write(content)

        return cache_path

    def get_cached_content(self, file_hash: str) -> Optional[str]:
        """
        Get content from cache

        Args:
            file_hash: Hash of the file

        Returns:
            File content if cached, None otherwise
        """
        cache_path = os.path.join(self.cache_dir, file_hash)

        if os.path.exists(cache_path):
            with open(cache_path, 'r', encoding='utf-8') as f:
                return f.read()

        return None

    def has_cached_file(self, file_hash: str) -> bool:
        """Check if file is cached"""
        cache_path = os.path.join(self.cache_dir, file_hash)
        return os.path.exists(cache_path)

    def clear_cache(self, older_than_days: int = None):
        """
        Clear cache files

        Args:
            older_than_days: Only clear files older than this many days
        """
        import time

        now = time.time()

        for filename in os.listdir(self.cache_dir):
            file_path = os.path.join(self.cache_dir, filename)

            # Skip if not a file
            if not os.path.isfile(file_path):
                continue

            # Skip if not old enough
            if older_than_days is not None:
                file_age = now - os.path.getmtime(file_path)
                if file_age < older_than_days * 86400:  # days to seconds
                    continue

            # Remove file
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"Error removing cached file {file_path}: {e}")