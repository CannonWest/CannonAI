# src/utils/file_utils.py
"""
Synchronous utility functions for handling files in the OpenAI Chat application.
"""

# Standard library imports
import hashlib
import mimetypes
import os
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

# Third-party imports
import tiktoken

# Local application imports
from src.utils.logging_utils import get_logger, log_exception
from src.utils import constants # For DATA_DIR if needed by cache manager

# Get a logger for this module
logger = get_logger(__name__)

# Define chunk_size constant for large file processing
chunk_size = 1024 * 1024  # 1MB default chunk size for large file processing

# Add custom MIME types if not already loaded globally somewhere else
mimetypes.add_type('text/markdown', '.md')
mimetypes.add_type('text/x-python', '.py')
mimetypes.add_type('application/json', '.json')


# --- Standalone Synchronous Utility Functions ---

def get_file_mime_type(file_path: str) -> str:
    """Determine MIME type of a file."""
    if not os.path.exists(file_path):
        logger.warning(f"File not found for MIME type check: {file_path}")
        return "application/octet-stream" # Default for non-existent file
    try:
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type is None:
            # Default to text/plain for unknown types
            mime_type = "text/plain"
        return mime_type
    except Exception as e:
        logger.error(f"Error guessing MIME type for {file_path}: {e}")
        return "application/octet-stream" # Fallback on error


def read_text_file(file_path: str) -> Optional[str]:
    """
    Read a text file and return its content. Returns None if file not found or error occurs.
    Handles common encodings.
    """
    if not os.path.exists(file_path):
        logger.error(f"Cannot read file, not found: {file_path}")
        return None
    try:
        # Try UTF-8 first
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        logger.warning(f"UTF-8 decoding failed for {file_path}, trying latin-1.")
        try:
            # Try Latin-1 as a common fallback
            with open(file_path, 'r', encoding='latin-1') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading file {file_path} with fallback encoding: {e}")
            # Last resort: try binary read and replace errors
            try:
                 with open(file_path, 'rb') as f:
                      return f.read().decode('utf-8', errors='replace')
            except Exception as bin_e:
                 logger.error(f"Could not read file {file_path} even in binary mode: {bin_e}")
                 return None
    except IOError as e:
        logger.error(f"IOError reading file {file_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error reading file {file_path}: {e}")
        return None


def calculate_file_hash(file_path: str) -> Optional[str]:
    """Calculate SHA-256 hash of file for identification/caching. Returns None on error."""
    if not os.path.exists(file_path):
        logger.error(f"Cannot hash file, not found: {file_path}")
        return None
    try:
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            # Read in chunks for memory efficiency
            while True:
                byte_block = f.read(4096)
                if not byte_block:
                    break
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except IOError as e:
         logger.error(f"IOError hashing file {file_path}: {e}")
         return None
    except Exception as e:
         logger.error(f"Unexpected error hashing file {file_path}: {e}")
         return None


def count_tokens(text: str, model: str = "gpt-4o") -> int:
    """
    Count tokens in a text string using tiktoken.

    Args:
        text: The text to count tokens for
        model: The model to use for token counting (determines encoding)

    Returns:
        Number of tokens, or 0 if text is empty/None.
    """
    if not text:
        return 0
    try:
        # Use a default encoding if the specific model is unknown to tiktoken
        try:
             encoding = tiktoken.encoding_for_model(model)
        except KeyError:
             logger.warning(f"Tiktoken encoding not found for model '{model}'. Using 'cl100k_base' as fallback.")
             encoding = tiktoken.get_encoding("cl100k_base")

        return len(encoding.encode(text))
    except Exception as e:
        logger.error(f"Error counting tokens for model {model}: {e}")
        # Fallback or default? Returning 0 might be misleading.
        # Maybe estimate based on characters? For now, return 0 on error.
        return 0


# --- File Info Helper ---

def get_file_info(file_path: str, model: str = "gpt-4o", max_size_mb: int = 10) -> Optional[Dict]:
    """
    Synchronously get basic file information (size, MIME, name, hash).
    Optionally reads content and counts tokens for text files under the size limit.

    Args:
        file_path: Path to the file.
        model: Model name for token counting (if applicable).
        max_size_mb: Maximum size in MB for reading content.

    Returns:
        Dictionary with file information, or None if file not found/error.
    """
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return None

    try:
        file_size = os.path.getsize(file_path)
        max_size_bytes = max_size_mb * 1024 * 1024

        mime_type = get_file_mime_type(file_path)
        file_name = os.path.basename(file_path)
        file_hash = calculate_file_hash(file_path)

        info = {
            "file_name": file_name,
            "path": file_path,
            "size": file_size,
            "mime_type": mime_type,
            "file_hash": file_hash,
            "content": None, # Default to None
            "token_count": 0 # Default to 0
        }

        # Read content and count tokens only for potentially textual files below size limit
        is_textual = mime_type.startswith('text/') or mime_type in ('application/json', 'application/xml', 'application/javascript') # Add other relevant types
        if is_textual and file_size <= max_size_bytes:
            logger.debug(f"Reading content for textual file: {file_name}")
            content = read_text_file(file_path)
            if content is not None:
                info["content"] = content
                info["token_count"] = count_tokens(content, model)
            else:
                 logger.warning(f"Could not read content for file: {file_name}")
        elif file_size > max_size_bytes:
            logger.warning(f"File '{file_name}' exceeds {max_size_mb}MB size limit for content reading.")
        else:
             logger.debug(f"Skipping content read for non-textual file type: {mime_type}")


        return info

    except Exception as e:
        logger.error(f"Error getting file info for {file_path}: {e}", exc_info=True)
        return None