"""
Base AI Provider Interface for CannonAI.

This module defines the abstract base class that all AI providers must implement.
It provides a consistent interface for interacting with different AI services.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Union, AsyncGenerator, Tuple, Callable
from pathlib import Path
import asyncio


@dataclass
class ProviderConfig:
    """Configuration for an AI provider."""
    api_key: str
    model: str
    api_base_url: Optional[str] = None  # For custom endpoints (e.g., Azure OpenAI)
    timeout: int = 60  # Request timeout in seconds
    max_retries: int = 3
    retry_delay: float = 1.0
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        print(f"DEBUG: Initializing ProviderConfig for model: {self.model}")
        if not self.api_key:
            raise ValueError("API key is required")
        if not self.model:
            raise ValueError("Model name is required")


class ProviderError(Exception):
    """Base exception for provider-related errors."""
    pass


class BaseAIProvider(ABC):
    """Abstract base class for AI providers.
    
    All AI providers (Gemini, Claude, OpenAI, etc.) must implement this interface
    to ensure compatibility with the CannonAI system.
    """
    
    def __init__(self, config: ProviderConfig):
        """Initialize the provider with configuration.
        
        Args:
            config: Provider configuration including API key, model, etc.
        """
        print(f"DEBUG: Initializing {self.__class__.__name__} with model: {config.model}")
        self.config = config
        self._client = None  # Will be initialized by concrete implementations
        self._is_initialized = False
    
    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the provider client.
        
        This method should set up the connection to the AI service and
        verify that the API key is valid.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def list_models(self) -> List[Dict[str, Any]]:
        """Get list of available models from the provider.
        
        Returns:
            List of model information dictionaries with at least:
            - name: str (model identifier)
            - display_name: str (human-readable name)
            - description: Optional[str]
            - input_token_limit: Optional[int]
            - output_token_limit: Optional[int]
        """
        pass
    
    @abstractmethod
    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        params: Optional[Dict[str, Any]] = None,
        stream: bool = False
    ) -> Union[Tuple[str, Dict[str, Any]], AsyncGenerator[Dict[str, Any], None]]:
        """Generate a response from the AI model.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            params: Optional generation parameters (temperature, max_tokens, etc.)
            stream: Whether to stream the response
            
        Returns:
            If stream=False: Tuple of (response_text, metadata)
            If stream=True: AsyncGenerator yielding response chunks
            
        The metadata should include token usage information when available.
        """
        pass
    
    @abstractmethod
    def validate_model(self, model_name: str) -> bool:
        """Check if a model name is valid for this provider.
        
        Args:
            model_name: The model identifier to validate
            
        Returns:
            True if the model is valid, False otherwise
        """
        pass
    
    @abstractmethod
    def get_default_params(self) -> Dict[str, Any]:
        """Get default generation parameters for this provider.
        
        Returns:
            Dictionary of default parameters
        """
        pass
    
    def normalize_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Normalize message format for the provider.
        
        This method can be overridden by providers that need special message formatting.
        
        Args:
            messages: List of messages with 'role' and 'content'
            
        Returns:
            Normalized messages for the provider's API
        """
        print(f"DEBUG: Normalizing {len(messages)} messages for {self.__class__.__name__}")
        
        # Default implementation - most providers use 'user' and 'assistant'
        normalized = []
        for msg in messages:
            role = msg.get('role', 'user')
            
            # Handle common role mappings
            if role in ['human', 'user']:
                role = 'user'
            elif role in ['ai', 'assistant', 'model']:
                role = 'assistant'
            elif role == 'system':
                # Some providers don't support system messages
                # Override this method in provider implementations if needed
                role = 'system'
            
            normalized.append({
                'role': role,
                'content': msg.get('content', '')
            })
        
        return normalized
    
    def extract_token_usage(self, response: Any) -> Dict[str, Any]:
        """Extract token usage information from a response.
        
        This method should be overridden by providers that support token counting.
        
        Args:
            response: The raw response from the provider's API
            
        Returns:
            Dictionary with token usage information (empty if not supported)
        """
        return {}
    
    @property
    def is_initialized(self) -> bool:
        """Check if the provider has been initialized."""
        return self._is_initialized
    
    @property
    def provider_name(self) -> str:
        """Get the name of this provider."""
        return self.__class__.__name__.replace('Provider', '').lower()
    
    def __repr__(self) -> str:
        """String representation of the provider."""
        return f"{self.__class__.__name__}(model={self.config.model}, initialized={self._is_initialized})"
