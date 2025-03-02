"""
Utility functions for handling files in the OpenAI Chat application.
"""

import os
import mimetypes
from typing import Dict, Optional
import tiktoken


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
        content = read_text_file(file_path)
        token_count = count_tokens(content, model)

        return {
            "file_name": file_name,
            "mime_type": mime_type,
            "content": content,
            "token_count": token_count,
            "path": file_path,
            "size": os.path.getsize(file_path)
        }
    else:
        raise ValueError(f"Unsupported file type: {mime_type}")


def format_size(size_bytes):
    """Format file size in a human-readable way."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"