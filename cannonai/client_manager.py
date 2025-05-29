"""
Gemini Chat CLI - Client Manager Module

This module provides a factory for creating client instances (sync or async)
and reduces redundancy between implementations.
"""

from pathlib import Path
from typing import Optional, Union, Dict, Any, Tuple

from base_client import BaseGeminiClient, Colors
from sync_client import SyncGeminiClient
from async_client import AsyncGeminiClient


class ClientManager:
    """Factory for creating and managing Gemini Chat clients."""
    
    @staticmethod
    def create_client(
        async_mode: bool = False,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        conversations_dir: Optional[Path] = None,
        params: Optional[Dict[str, Any]] = None,
        use_streaming: bool = False
    ) -> Union[SyncGeminiClient, AsyncGeminiClient]:
        """Create a client instance based on the specified mode.
        
        Args:
            async_mode: Whether to create an async client
            api_key: The API key to use
            model: The model to use
            conversations_dir: Directory for storing conversations
            params: Generation parameters
            use_streaming: Whether to enable streaming mode
            
        Returns:
            A client instance (sync or async)
        """
        # Create the appropriate client type
        if async_mode:
            client = AsyncGeminiClient(
                api_key=api_key,
                model=model,
                conversations_dir=conversations_dir
            )
        else:
            client = SyncGeminiClient(
                api_key=api_key, 
                model=model, 
                conversations_dir=conversations_dir
            )
        
        # Apply additional settings if provided
        if params:
            client.params = params
        
        client.use_streaming = use_streaming
        
        return client


def initialize_client(client) -> bool:
    """Initialize a client (sync or async).
    
    Args:
        client: The client to initialize
        
    Returns:
        True if initialization was successful, False otherwise
    """
    is_async = hasattr(client, 'initialize_client') and callable(getattr(client, 'initialize_client')) and 'async' in getattr(client.initialize_client, '__code__').co_varnames
    
    if is_async:
        import asyncio
        success = asyncio.run(client.initialize_client())
    else:
        success = client.initialize_client()
    
    if not success:
        print(f"{Colors.FAIL}Failed to initialize client. Exiting.{Colors.ENDC}")
        return False
    
    return True
