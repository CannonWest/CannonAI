"""
Asynchronous utility functions for handling files in the OpenAI Chat application.
Optimized for asyncio integration and large file handling.
"""

# Standard library imports
import asyncio
import concurrent.futures
import hashlib
import mimetypes
import os
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

# Third-party imports
import tiktoken
from PyQt6.QtCore import QObject, pyqtSignal

# Local application imports
from src.utils.logging_utils import get_logger, log_exception

# Get a logger for this module
logger = get_logger(__name__)

# Define chunk_size constant for large file processing
chunk_size = 1024 * 1024  # 1MB default chunk size for large file processing

# Add custom MIME types
mimetypes.add_type('text/markdown', '.md')
mimetypes.add_type('text/x-python', '.py')
mimetypes.add_type('application/json', '.json')


class AsyncFileProcessor(QObject):
    """
    Async processor for file operations with progress reporting
    """
    progress = pyqtSignal(int)  # Progress percentage
    file_processed = pyqtSignal(dict)  # Processed file info
    error = pyqtSignal(str)  # Error message
    finished = pyqtSignal()  # Processing completed

    def __init__(self, parent=None):
        super().__init__(parent)
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self._canceled = False
        self.logger = get_logger(f"{__name__}.AsyncFileProcessor")

    def cancel(self):
        """Cancel ongoing processing"""
        self._canceled = True
        self.logger.debug("File processing canceled")

    async def process_file(self, file_path: str, model: str = "gpt-4o",
                           max_size_mb: int = 10, relative_path: str = None) -> Dict:
        """
        Process a file asynchronously
        
        Args:
            file_path: Path to the file
            model: Model name for token counting
            max_size_mb: Maximum allowed file size in MB
            relative_path: Optional relative path for display
            
        Returns:
            Dictionary with file information
        """
        self._canceled = False
        
        try:
            # Check file size first
            file_size = os.path.getsize(file_path)
            max_size_bytes = max_size_mb * 1024 * 1024

            # Make sure to emit initial progress
            self.progress.emit(0)

            if file_size > max_size_bytes:
                error_msg = f"File exceeds maximum size of {max_size_mb}MB"
                self.error.emit(error_msg)
                self.finished.emit()
                return None

            # Get file info
            mime_type = await self._run_in_executor(get_file_mime_type, file_path)
            file_name = os.path.basename(file_path) if not relative_path else relative_path

            # Calculate file hash for identification/caching
            file_hash = await self._run_in_executor(calculate_file_hash, file_path)
            
            # Check if canceled
            if self._canceled:
                self.logger.debug("File processing canceled during hash calculation")
                self.finished.emit()
                return None

            # For very large text files, use chunked processing
            if file_size > 1024 * 1024:  # 1MB threshold for chunked processing
                content, token_count = await self._process_large_text_file(file_path, model)
            else:
                # For smaller files, use standard processing
                content = await self._run_in_executor(read_text_file, file_path)
                token_count = await self._run_in_executor(count_tokens, content, model)
                
                # Make sure to emit progress
                self.progress.emit(50)  # Middle progress
                
                # Check if canceled
                if self._canceled:
                    self.logger.debug("File processing canceled after reading")
                    self.finished.emit()
                    return None
                    
                self.progress.emit(100)  # Completed

            # Create file info dict
            file_info = {
                "file_name": file_name,
                "original_file_name": os.path.basename(file_path),
                "mime_type": mime_type,
                "content": content,
                "token_count": token_count,
                "path": file_path,
                "size": file_size,
                "file_hash": file_hash
            }

            self.file_processed.emit(file_info)
            return file_info
            
        except Exception as e:
            error_msg = f"Error processing file: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.error.emit(error_msg)
            return None
            
        finally:
            self.finished.emit()

    async def _run_in_executor(self, func, *args):
        """Run a function in the thread pool executor"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, func, *args)

    async def _process_large_text_file(self, file_path: str, model: str) -> Tuple[str, int]:
        """
        Process a large text file by reading and counting tokens in chunks
        
        Args:
            file_path: Path to the text file
            model: Model name for token counting
            
        Returns:
            Tuple of (content, token_count)
        """
        # Get file size for progress calculation
        file_size = os.path.getsize(file_path)
        bytes_processed = 0
        content_chunks = []
        token_count = 0
        
        # Get encoding for token counting
        encoding = await self._run_in_executor(
            lambda: tiktoken.encoding_for_model(model) if model in tiktoken.model.MODEL_TO_ENCODING else 
                   tiktoken.get_encoding("cl100k_base")
        )
        
        # Open file and read in chunks
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            while True:
                if self._canceled:
                    self.logger.debug("Canceled during large file processing")
                    return "", 0
                    
                # Read a chunk from the file
                chunk = await self._run_in_executor(f.read, chunk_size)
                if not chunk:
                    break
                    
                # Add chunk to content
                content_chunks.append(chunk)
                
                # Count tokens
                chunk_tokens = await self._run_in_executor(
                    lambda: len(encoding.encode(chunk))
                )
                token_count += chunk_tokens
                
                # Update progress
                bytes_processed += len(chunk.encode('utf-8'))
                progress = min(int((bytes_processed / file_size) * 100), 100)
                self.progress.emit(progress)
        
        # Join chunks
        content = ''.join(content_chunks)
        return content, token_count
        
    def close(self):
        """Shut down the executor"""
        self._executor.shutdown(wait=False)
        self.logger.debug("AsyncFileProcessor executor shut down")


# Standalone utility functions

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


class AsyncFileCacheManager:
    """Manager for caching file attachments to disk with async support"""

    def __init__(self, cache_dir=None):
        if cache_dir is None:
            from src.utils import DATA_DIR
            self.cache_dir = os.path.join(DATA_DIR, "file_cache")
        else:
            self.cache_dir = cache_dir

        # Ensure cache directory exists
        os.makedirs(self.cache_dir, exist_ok=True)
        self.logger = get_logger(f"{__name__}.AsyncFileCacheManager")

    async def cache_file(self, content: str, file_hash: str) -> str:
        """
        Cache file content to disk asynchronously

        Args:
            content: File content
            file_hash: Hash of the file

        Returns:
            Path to cached file
        """
        cache_path = os.path.join(self.cache_dir, file_hash)
        
        # Run file writing in a thread pool
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,  # Use default executor
            self._write_file,
            cache_path,
            content
        )
        
        return cache_path
        
    def _write_file(self, path: str, content: str):
        """Synchronous helper to write file content"""
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)

    async def get_cached_content(self, file_hash: str) -> Optional[str]:
        """
        Get content from cache asynchronously

        Args:
            file_hash: Hash of the file

        Returns:
            File content if cached, None otherwise
        """
        cache_path = os.path.join(self.cache_dir, file_hash)

        if os.path.exists(cache_path):
            # Run file reading in a thread pool
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,  # Use default executor
                self._read_file,
                cache_path
            )

        return None
        
    def _read_file(self, path: str) -> str:
        """Synchronous helper to read file content"""
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()

    def has_cached_file(self, file_hash: str) -> bool:
        """Check if file is cached"""
        cache_path = os.path.join(self.cache_dir, file_hash)
        return os.path.exists(cache_path)

    async def clear_cache(self, older_than_days: Optional[int] = None):
        """
        Clear cache files asynchronously

        Args:
            older_than_days: Only clear files older than this many days
        """
        import time

        now = time.time()
        
        # Get list of files to remove
        loop = asyncio.get_event_loop()
        files_to_remove = await loop.run_in_executor(
            None,
            self._get_files_to_remove,
            older_than_days,
            now
        )
        
        # Remove files in parallel
        if files_to_remove:
            self.logger.info(f"Clearing {len(files_to_remove)} cached files")
            await asyncio.gather(*[
                loop.run_in_executor(None, os.remove, file_path)
                for file_path in files_to_remove
            ])
            
    def _get_files_to_remove(self, older_than_days: Optional[int], now: float) -> List[str]:
        """Get list of files to remove"""
        files_to_remove = []
        
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

            files_to_remove.append(file_path)
            
        return files_to_remove


# Helper function for getting file info asynchronously
async def get_file_info_async(file_path: str, 
                              model: str = "gpt-4o", 
                              max_size_mb: int = 10, 
                              relative_path: str = None,
                              progress_callback: Callable[[int], None] = None,
                              error_callback: Callable[[str], None] = None) -> Dict:
    """
    Get file information asynchronously

    Args:
        file_path: Path to the file
        model: Model name for token counting
        max_size_mb: Maximum allowed file size in MB
        relative_path: Optional relative path for display
        progress_callback: Callback for progress updates
        error_callback: Callback for error notifications

    Returns:
        Dictionary with file information
    """
    processor = AsyncFileProcessor()
    
    # Connect signals if callbacks provided
    if progress_callback:
        processor.progress.connect(progress_callback)
    if error_callback:
        processor.error.connect(error_callback)
        
    try:
        return await processor.process_file(
            file_path=file_path,
            model=model,
            max_size_mb=max_size_mb,
            relative_path=relative_path
        )
    finally:
        # Clean up
        processor.deleteLater()
