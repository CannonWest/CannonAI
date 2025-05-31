"""
AI Provider interfaces and implementations for CannonAI.

This module provides a unified interface for different AI providers (Gemini, Claude, OpenAI, etc.)
allowing the application to work with multiple AI services through a common API.
"""

from .base_provider import BaseAIProvider, ProviderError, ProviderConfig
from .gemini_provider import GeminiProvider

# Future imports will be added as we implement them
# from .claude_provider import ClaudeProvider  
# from .openai_provider import OpenAIProvider

__all__ = [
    'BaseAIProvider',
    'ProviderError',
    'ProviderConfig',
    'GeminiProvider',
    # 'ClaudeProvider',
    # 'OpenAIProvider',
]

# Provider registry for easy lookup
PROVIDERS = {
    'gemini': GeminiProvider,
    # 'claude': ClaudeProvider,
    # 'openai': OpenAIProvider,
}

def get_provider_class(provider_name: str):
    """Get the provider class by name.
    
    Args:
        provider_name: Name of the provider (e.g., 'gemini', 'claude', 'openai')
        
    Returns:
        The provider class
        
    Raises:
        ValueError: If provider is not found
    """
    print(f"DEBUG: Looking up provider class for: {provider_name}")
    
    if provider_name not in PROVIDERS:
        available = ', '.join(PROVIDERS.keys())
        raise ValueError(f"Unknown provider: {provider_name}. Available providers: {available}")
    
    return PROVIDERS[provider_name]
