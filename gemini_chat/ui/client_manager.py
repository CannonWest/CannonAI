"""
Client management for Gemini Chat UI message handlers.

This module provides a single point of reference for the chat client 
between the server and message handler modules.
"""

import logging
from typing import Any, Optional

# Configure logger
logger = logging.getLogger("gemini_chat.ui.client_manager")

# Global client reference that will be shared across modules
_client = None

def get_client() -> Optional[Any]:
    """Get the current chat client instance.
    
    Returns:
        The chat client instance or None if not initialized
    """
    global _client
    if _client is None:
        logger.debug("Client requested but not yet initialized")
    return _client

def set_client(client: Any) -> None:
    """Set the chat client instance to be shared across modules.
    
    Args:
        client: The chat client instance to share
    """
    global _client
    _client = client
    logger.debug(f"Client reference set: {client.__class__.__name__}")
